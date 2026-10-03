"""GeminiProvider — Google Gen AI SDK (gói google-genai), API models.generate_content.

Lựa chọn API surface: generate_content với function calling THỦ CÔNG
(automatic_function_calling.disable=True). Lịch sử hội thoại được giữ phía máy (stateless trên
dịch vụ, không dùng tính năng lưu hội thoại phía server). Nội dung model trả về được nối nguyên
vẹn vào lịch sử để bảo toàn function call id và thought signature theo tài liệu SDK.

Mọi function call chỉ được chuyển cho `execute_tool` do NEXA cung cấp; SDK không bao giờ tự gọi
hàm Python. Retry chỉ áp dụng cho REQUEST mạng (429/5xx/timeout) với backoff giới hạn; công cụ đã
chạy không bao giờ chạy lại khi retry vì kết quả của nó đã nằm trong lịch sử.
"""
from __future__ import annotations

import hashlib
import random
import re
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from nexa.ai.prompts import SYSTEM_INSTRUCTION, VISION_INSTRUCTION, COMPANION_INSTRUCTION
from nexa.ai.conversation_history import ConversationHistory, bounded
from nexa.core.safety import Cancelled, CancelToken
from nexa.utils.logging import get_logger, register_secret

log = get_logger("gemini")


class AIError(Exception):
    def __init__(self, kind: str, message: str, retryable: bool = False, code: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.retryable = retryable
        self.code = code


@dataclass
class TurnResult:
    text: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    stopped: str = ""          # "" | step_limit | blocked | empty


class AIProvider(Protocol):
    name: str

    def status(self) -> tuple[bool, str]: ...
    def test_connection(self) -> tuple[bool, str]: ...
    def converse(self, text: str, declarations: list[dict], execute_tool: Callable[[Any], dict],
                 token: CancelToken, context: str = "", *, companion: bool = False) -> TurnResult: ...
    def add_note(self, note: str) -> None:
        """Ghi chú ngữ cảnh (ví dụ lệnh cơ bản vừa chạy) gửi kèm lượt Gemini kế tiếp."""
        with self._lock:
            self._notes.append(note[:300])
            del self._notes[:-5]

    def clear_history(self) -> None: ...


def classify_error(exc: Exception, model: str) -> AIError:
    """Chuyển lỗi SDK/mạng thành AIError có thông báo tiếng Việt, không chứa bí mật."""
    try:
        from google.genai import errors
    except ImportError:  # pragma: no cover
        errors = None
    import httpx
    if errors is not None and isinstance(exc, errors.APIError):
        code = int(getattr(exc, "code", 0) or 0)
        status = str(getattr(exc, "status", "") or "")
        msg = str(getattr(exc, "message", "") or "")
        low = (msg + " " + status).lower()
        if code in (401,) or "api_key_invalid" in low or "api key not valid" in low or "api key expired" in low:
            return AIError("auth", "Gemini từ chối API key (không hợp lệ hoặc đã hết hạn). Anh kiểm tra GEMINI_API_KEY.",
                           code=code)
        if code == 403 or status == "PERMISSION_DENIED":
            return AIError("permission", "Key không có quyền dùng Gemini API/model này (403). Anh kiểm tra dự án và quyền của key.",
                           code=code)
        if code == 404 or status == "NOT_FOUND":
            return AIError("not_found", f"Model '{model}' không tồn tại hoặc key không truy cập được. Anh đổi GEMINI_MODEL trong Cài đặt.",
                           code=code)
        if code == 429 or status == "RESOURCE_EXHAUSTED":
            quota = "quota" in low or "exceeded your current quota" in low
            return AIError("quota" if quota else "rate_limit",
                           "Gemini báo vượt hạn mức (quota) của tài khoản." if quota else
                           "Gemini đang giới hạn tốc độ (429).", retryable=True, code=code)
        if code >= 500:
            return AIError("server", f"Dịch vụ Gemini đang lỗi ({code}).", retryable=True, code=code)
        if code == 400:
            return AIError("bad_request", f"Yêu cầu gửi Gemini không hợp lệ: {msg[:160]}", code=code)
        return AIError("api", f"Lỗi Gemini {code}: {msg[:160]}", code=code)
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return AIError("timeout", "Gemini phản hồi quá thời gian chờ.", retryable=True)
    if isinstance(exc, (httpx.NetworkError, httpx.ConnectError, httpx.RemoteProtocolError, ConnectionError, OSError)):
        return AIError("network", "Không kết nối được Gemini (mất mạng?).", retryable=True)
    return AIError("unknown", f"Lỗi không xác định khi gọi Gemini: {type(exc).__name__}")


def _retry_delay(exc: Exception) -> float | None:
    details = getattr(exc, "details", None)
    text = str(details) if details else ""
    m = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s", text)
    return float(m.group(1)) if m else None


class GeminiProvider:
    name = "gemini"

    def __init__(self, config: Any, client_factory: Callable[[str, float], Any] | None = None,
                 sleep: Callable[[float], None] = time.sleep, state_path: Any = None,
                 history_path: Any = None) -> None:
        self.config = config
        self._state_path = state_path
        self._client_factory = client_factory or self._default_client
        self._client = None
        self._client_key_hash = ""
        self._sleep = sleep
        self._lock = threading.RLock()
        # Yêu cầu bị bỏ vì quá hạn vẫn giữ luồng tới khi HTTP timeout: cần đủ luồng để câu hỏi mới không phải
        # xếp hàng sau các yêu cầu đang treo (trước đây 3 luồng → câu thứ hai cũng hết giờ khi Google quá tải).
        self._pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="nexa-gemini")
        self._history: list[Any] = []
        self._turn_starts: list[int] = []
        self._notes: list[str] = []
        self._disabled_key_hash = ""   # key đã bị từ chối (không retry vô hạn lỗi xác thực)
        self._disabled_reason = ""
        self.calls = 0
        self.usage = {"prompt": 0, "output": 0, "thoughts": 0, "total": 0}
        self.last_error: AIError | None = None
        self._thinking_supported = True
        self._no_thinking: set[str] = set()          # model không nhận thinking_level
        self._sick_until: dict[str, float] = {}       # model -> lúc hết "nghỉ"
        self.last_model = ""
        self.last_latency_ms = 0.0                    # thời gian phản hồi của lần gọi thành công gần nhất
        self._good_model = ""                         # model trả lời thành công gần nhất: dùng trước, chờ đủ lâu
        self._load_state()
        from nexa.utils.config import CONFIG_DIR, LOCAL_DATA_DIR
        history_dir = LOCAL_DATA_DIR
        if state_path is not None:
            history_dir = Path(state_path).parent
        elif (hasattr(config, "settings_path") and
              Path(config.settings_path).resolve() != (CONFIG_DIR / "settings.yaml").resolve()):
            # An explicitly isolated/custom config also isolates its history.
            history_dir = Path(config.settings_path).parent
        self._history_store = ConversationHistory(
            history_path if history_path is not None else history_dir / "conversation_history.json")
        self._saved_turns: list[tuple[str, str]] = []
        self._history_generation = 0
        self._clear_generation = 0
        self._persist_history = self.config.get("ai.persist_history") is True
        if self._persist_history:
            from google.genai import types
            self._saved_turns = self._history_store.load(self._history_limit())
            for user, model in self._saved_turns:
                self._turn_starts.append(len(self._history))
                self._history.extend([types.Content(role=role, parts=[types.Part(text=text)])
                                      for role, text in (("user", user), ("model", model))])
        if hasattr(self.config, "watch_history_settings"):
            self.config.watch_history_settings(self._history_settings_changed)

    # ----- cấu hình -----
    @staticmethod
    def _default_client(api_key: str, timeout_s: float):
        from google import genai
        from google.genai import types
        return genai.Client(api_key=api_key, http_options=types.HttpOptions(
            timeout=int(timeout_s * 1000), retry_options=types.HttpRetryOptions(attempts=1)))

    @property
    def model(self) -> str:
        return self.config.gemini_model

    @staticmethod
    def _hash(key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    def status(self) -> tuple[bool, str]:
        if self.config.ai_provider != "gemini":
            return False, f"NEXA_AI_PROVIDER='{self.config.ai_provider}' chưa được hỗ trợ (bản này dùng gemini)."
        key_status = self.config.gemini_key_status()
        if key_status == "missing":
            return False, "Chưa có GEMINI_API_KEY."
        if key_status == "placeholder":
            return False, "GEMINI_API_KEY vẫn là giá trị mẫu."
        key = self.config.gemini_api_key()
        if self._disabled_key_hash and self._disabled_key_hash == self._hash(key):
            return False, self._disabled_reason
        if self.calls >= int(self.config.get("ai.max_calls_per_session") or 300):
            return False, "Đã chạm giới hạn số lần gọi Gemini trong phiên (giới hạn nội bộ của NEXA)."
        return True, f"Gemini ({self.model})"

    def _get_client(self):
        key = self.config.gemini_api_key()
        if not key:
            raise AIError("auth", "Chưa có GEMINI_API_KEY hợp lệ.")
        register_secret(key)
        h = self._hash(key)
        with self._lock:
            if self._client is None or self._client_key_hash != h:
                self._client = self._client_factory(key, self.config.gemini_timeout_s)
                self._client_key_hash = h
            return self._client

    # ----- gọi API -----
    # ----- chọn model -----
    SICK_S = 300.0          # model vừa lỗi 503/504/quá hạn: cho "nghỉ" 5 phút, đi thẳng sang model dự phòng
    SICK_ERRORS = ("server", "timeout", "rate_limit", "quota")

    def _candidates(self) -> list[str]:
        """Model chính rồi các model dự phòng (ai.fallback_models), bỏ model đang "nghỉ" nếu còn model khác."""
        chain = [self.model]
        for m in self.config.get("ai.fallback_models") or []:
            m = str(m).strip()
            if m and m not in chain:
                chain.append(m)
        now = time.monotonic()
        healthy = [m for m in chain if self._sick_until.get(m, 0.0) <= now]
        out = healthy or chain
        if self._good_model in out:
            out = [self._good_model] + [m for m in out if m != self._good_model]
        return out

    def _mark_sick(self, model: str, err: "AIError") -> None:
        if err.kind in self.SICK_ERRORS:
            self._sick_until[model] = time.monotonic() + self.SICK_S
            log.info("Tạm bỏ qua model %s trong %.0f phút (%s)", model, self.SICK_S / 60, err.kind)
            self._save_state()

    # Nhớ model chạy được qua các lần mở NEXA: trước đây mỗi lần khởi động câu hỏi đầu lại chờ ~7 s model chính
    # đang quá tải (log 2026-09-24: gemini-3.5-flash-lite quá hạn ở cả 5 lần mở) rồi mới đổi sang dự phòng.
    def _load_state(self) -> None:
        if self._state_path is None:
            return
        try:
            import json
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except Exception:
            return
        chain = [self.model, *(str(m).strip() for m in self.config.get("ai.fallback_models") or [])]
        good = str(data.get("good_model") or "")
        if good in chain:
            self._good_model = good
        now_wall, now_mono = time.time(), time.monotonic()
        for model, until in (data.get("sick") or {}).items():
            left = float(until) - now_wall
            if model in chain and 0 < left <= self.SICK_S:
                self._sick_until[model] = now_mono + left

    def _save_state(self) -> None:
        if self._state_path is None:
            return
        try:
            import json
            now_wall, now_mono = time.time(), time.monotonic()
            sick = {m: now_wall + (t - now_mono) for m, t in self._sick_until.items() if t > now_mono}
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(json.dumps({"good_model": self._good_model, "sick": sick}), encoding="utf-8")
        except Exception:
            log.debug("Không lưu được trạng thái model Gemini", exc_info=True)

    @property
    def active_model(self) -> str:
        return self._candidates()[0]

    def _call(self, contents: list, cfg: Any, token: CancelToken, models: list[str] | None = None,
              timeout_s: float | None = None) -> Any:
        """models/timeout_s: tác vụ dài (dựng CAD DSL…) dùng chuỗi model và thời hạn riêng, không theo ngân sách hội
        thoại giọng nói (20 s) — và không làm thay đổi model "tốt" của hội thoại."""
        ok, reason = self.status()
        if not ok:
            raise AIError("unavailable", reason)
        configured = self.config.get("ai.max_retries")
        max_retries = max(0, min(5, int(2 if configured is None else configured)))
        long_task = timeout_s is not None
        # Hạn tổng cho lần hỏi này (kể cả thử lại / đổi model): quá hạn thì báo lỗi ngay thay vì để anh chờ cả phút.
        budget_s = float(timeout_s) * 2.2 if long_task else float(self.config.get("ai.request_budget_s") or 20.0)
        attempt_cap = float(timeout_s) if long_task else float(self.config.get("ai.attempt_timeout_s") or 9.0)
        give_up_at = time.monotonic() + budget_s
        sick: set[str] = set()
        attempt = 0
        while True:
            token.raise_if_cancelled()
            client = self._get_client()
            if models:
                chain = [m for m in models if m not in sick] or list(models)
            else:
                chain = self._candidates()
            model = chain[0]
            more = len(chain) > 1
            use_cfg = cfg if model not in self._no_thinking else cfg.model_copy(update={"thinking_config": None})
            self.calls += 1
            snapshot = list(contents)
            sent_at = time.monotonic()
            future = self._pool.submit(client.models.generate_content, model=model, contents=snapshot, config=use_cfg)
            per_try = float(timeout_s) + 5 if long_task else self.config.gemini_timeout_s + 5
            if more and model != self._good_model and not long_task:
                # Model chưa chắc chạy được mà còn dự phòng: đừng để nó treo ăn hết thời gian của câu hỏi.
                per_try = min(per_try, attempt_cap)
            deadline = min(time.monotonic() + per_try, give_up_at)
            err: AIError | None = None
            delay_hint: float | None = None
            while not future.done():
                if token.cancelled:
                    future.cancel()  # kết quả đến muộn (nếu có) bị bỏ, không bao giờ tới executor
                    raise Cancelled("Người dùng hủy trong lúc chờ Gemini")
                if time.monotonic() > deadline:
                    future.cancel()
                    err = AIError("timeout", "Gemini phản hồi quá thời gian chờ.", retryable=True)
                    break
                time.sleep(0.05)
            if err is None:
                try:
                    resp = future.result()
                except Exception as exc:
                    err = classify_error(exc, model)
                    delay_hint = _retry_delay(exc)
                else:
                    if token.cancelled:
                        raise Cancelled("Kết quả Gemini đến sau khi đã hủy")
                    self.last_error = None
                    self.last_model = model
                    self.last_latency_ms = (time.monotonic() - sent_at) * 1000.0
                    if models:
                        return resp
                    if model != self._good_model:
                        log.info("Gemini trả lời bằng model %s — dùng model này trước cho các câu sau", model)
                        self._good_model = model
                        self._save_state()
                    return resp
            if err.kind == "bad_request" and "thinking" in err.message.lower() and \
                    getattr(use_cfg, "thinking_config", None) is not None:
                # Model không hỗ trợ thinking_level: bỏ tham số này cho RIÊNG model đó rồi gửi lại (không tính thử lại).
                log.info("Model %s không nhận thinking_level, bỏ tham số này", model)
                self._no_thinking.add(model)
                continue
            self.last_error = err
            log.warning("Gemini lỗi (%s, %s, lần %d): %s", err.kind, model, attempt + 1, err.message)
            if err.kind in ("auth", "permission"):
                self._disabled_key_hash = self._client_key_hash
                self._disabled_reason = err.message
            if models:
                # chuỗi model riêng của tác vụ dài: model lỗi (không tồn tại, quá tải, hết quota…) → thử model kế tiếp
                if err.kind in ("auth", "permission") or (not err.retryable and err.kind not in ("not_found", "quota")):
                    raise err
                sick.add(model)
                left = [m for m in models if m not in sick]
                if left:
                    log.info("Tác vụ dài: model %s lỗi (%s), chuyển sang %s", model, err.kind, left[0])
                    continue
                if not err.retryable or attempt >= max_retries:
                    raise err
                attempt += 1
                sick.clear()
                delay = min(20.0, delay_hint if delay_hint is not None else 3.0 * attempt)
                if time.monotonic() + delay + 5.0 > give_up_at:
                    raise err
                if token.wait(delay):
                    raise Cancelled("Người dùng hủy trong lúc chờ thử lại")
                continue
            if not err.retryable or attempt >= max_retries:
                raise err
            attempt += 1
            self._mark_sick(model, err)
            if model == self._good_model:
                self._good_model = ""
                self._save_state()
            switched = more and self._candidates()[0] != model
            if switched:
                delay = 0.0                        # đổi sang model khác: gửi lại ngay, không cần chờ
            else:
                base = float(self.config.get("ai.retry_base_s") or 1.5)
                delay = min(10.0, delay_hint if delay_hint is not None else (base * 2 ** (attempt - 1)))
                delay += random.uniform(0, 0.25 * base)
            if time.monotonic() + delay + 2.0 > give_up_at:
                log.warning("Hết hạn %.0fs cho Gemini, không thử lại nữa", budget_s)
                raise err
            if switched:
                log.info("Chuyển sang model dự phòng %s", self._candidates()[0])
            if delay and token.wait(delay):
                raise Cancelled("Người dùng hủy trong lúc chờ thử lại")

    def _account(self, resp: Any) -> None:
        um = getattr(resp, "usage_metadata", None)
        if um is None:
            return
        self.usage["prompt"] += int(getattr(um, "prompt_token_count", 0) or 0)
        self.usage["output"] += int(getattr(um, "candidates_token_count", 0) or 0)
        self.usage["thoughts"] += int(getattr(um, "thoughts_token_count", 0) or 0)
        self.usage["total"] += int(getattr(um, "total_token_count", 0) or 0)

    def _config(self, declarations: list[dict], system: str = SYSTEM_INSTRUCTION, max_tokens: int | None = None):
        from google.genai import types
        tools = None
        tool_config = None
        if declarations:
            tools = [types.Tool(function_declarations=[types.FunctionDeclaration(**d) for d in declarations])]
            tool_config = types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="AUTO"))
        return types.GenerateContentConfig(
            system_instruction=system, tools=tools, tool_config=tool_config,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            max_output_tokens=int(max_tokens or self.config.get("ai.max_output_tokens") or 1024),
            temperature=float(self.config.get("ai.temperature") or 0.6),
            thinking_config=self._thinking_config())

    def _thinking_config(self):
        """Mức suy nghĩ thấp giúp phản hồi nhanh hơn (đo trên máy: ~2,6 s → ~1,4 s với minimal)."""
        from google.genai import types
        level = (self.config.get("ai.thinking_level") or "").strip().lower()
        if not level or not self._thinking_supported:
            return None
        return types.ThinkingConfig(thinking_level=level)

    # ----- hội thoại -----
    def _history_limit(self) -> int:
        limit = self.config.get("ai.max_history_turns")
        return limit if type(limit) is int and 1 <= limit <= 50 else 12

    def _history_settings_changed(self) -> None:
        with self._lock:
            enabled = self.config.get("ai.persist_history") is True
            if enabled != self._persist_history:
                self._history_generation += 1
                self._saved_turns.clear()
                self._persist_history = enabled
                # Enabling mid-session starts with future turns; never backfill private turns.
                self._history_store.delete()
            self._saved_turns = bounded(self._saved_turns, self._history_limit())
            if enabled and self._saved_turns:
                self._history_store.save(self._saved_turns, self._history_limit())

    def _save_exchange(self, user: str, model: str, generation: int) -> None:
        with self._lock:
            if (not self._persist_history or self.config.get("ai.persist_history") is not True
                    or generation != self._history_generation):
                return
            self._saved_turns = bounded(self._saved_turns + [(user, model)], self._history_limit())
            self._history_store.save(self._saved_turns, self._history_limit())

    def add_note(self, note: str) -> None:
        """Ghi chú ngữ cảnh (ví dụ lệnh cơ bản vừa chạy) gửi kèm lượt Gemini kế tiếp."""
        with self._lock:
            self._notes.append(note[:300])
            del self._notes[:-5]

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()
            self._turn_starts.clear()
            self._notes.clear()
            self._history_generation += 1
            self._clear_generation += 1
            self._saved_turns.clear()
            self._history_store.delete()

    @property
    def history_turns(self) -> int:
        return len(self._turn_starts)

    def _rollback(self, start: int, note: str = "") -> None:
        with self._lock:
            del self._history[start:]
            while self._turn_starts and self._turn_starts[-1] >= start:
                self._turn_starts.pop()
            if note:
                self._notes.append(note)

    def _trim(self, reserve: int = 0) -> None:
        """Giữ tối đa max_history_turns lượt (tính cả lượt sắp thêm nếu reserve=1); cắt đúng ranh giới lượt."""
        limit = self._history_limit() - reserve
        with self._lock:
            while len(self._turn_starts) > max(0, limit) and len(self._turn_starts) > 0:
                if len(self._turn_starts) == 1:
                    self._history.clear()
                    self._turn_starts.clear()
                    break
                cut = self._turn_starts[1]
                del self._history[:cut]
                self._turn_starts = [s - cut for s in self._turn_starts[1:]]

    def converse(self, text: str, declarations: list[dict], execute_tool: Callable[[Any], dict],
                 token: CancelToken, context: str = "", *, companion: bool = False) -> TurnResult:
        from google.genai import types
        cfg = self._config([] if companion else declarations,
                           system=COMPANION_INSTRUCTION if companion else SYSTEM_INSTRUCTION)
        max_steps = self.config.max_tool_steps
        self._trim(reserve=1)
        with self._lock:
            start = len(self._history)
            generation = self._history_generation
            clear_generation = self._clear_generation
            persist_turn = self._persist_history
            notes = ("[Ghi chú: " + " ".join(self._notes[-5:]) + "]\n") if self._notes else ""
            self._notes.clear()
            self._history.append(types.Content(role="user", parts=[types.Part(text=context + notes + text)]))
            self._turn_starts.append(start)
        steps: list[dict[str, Any]] = []
        try:
            for step in range(max_steps + 1):
                resp = self._call(self._history, cfg, token)
                token.raise_if_cancelled()
                with self._lock:
                    if clear_generation != self._clear_generation:
                        raise Cancelled("Lịch sử hội thoại đã bị xóa")
                self._account(resp)
                cand = resp.candidates[0] if getattr(resp, "candidates", None) else None
                content = getattr(cand, "content", None) if cand is not None else None
                if content is None or not getattr(content, "parts", None):
                    reason = str(getattr(cand, "finish_reason", "") or getattr(resp, "prompt_feedback", "") or "trống")
                    self._rollback(start)
                    return TurnResult(f"Gemini không trả lời được yêu cầu này (lý do: {reason}).", steps, "empty")
                with self._lock:
                    if clear_generation != self._clear_generation:
                        raise Cancelled("Lịch sử hội thoại đã bị xóa")
                    self._history.append(content)
                calls = [p.function_call for p in content.parts if getattr(p, "function_call", None)]
                if companion and calls:
                    self._rollback(start)
                    return TurnResult("Anh nói 'thoát chế độ tâm sự' nếu muốn em thao tác máy tính nhé.", [], "chat_only")
                if not calls:
                    text_out = "".join(p.text for p in content.parts
                                       if getattr(p, "text", None) and not getattr(p, "thought", False)).strip()
                    self._trim()
                    plain_text = (content.role == "model" and all(
                        set(p.model_dump(exclude_none=True)) <= {"text", "thought", "thought_signature"}
                        for p in content.parts))
                    if persist_turn and not steps and text_out and plain_text:
                        self._save_exchange(text, text_out, generation)
                    return TurnResult(text_out or "Dạ.", steps)
                if step >= max_steps:
                    done = ", ".join(f"{s['name']}({'ok' if s['ok'] else 'lỗi'})" for s in steps)
                    self._rollback(start, f"Lượt trước dừng do vượt {max_steps} bước; đã làm: {done}.")
                    return TurnResult(f"Em dừng lại vì yêu cầu cần hơn {max_steps} bước. Các bước đã làm: {done or 'chưa có'}.",
                                      steps, "step_limit")
                parts = []
                for fc in calls:
                    token.raise_if_cancelled()
                    payload = execute_tool(fc)
                    ok = bool(payload.get("ok"))
                    steps.append({"name": fc.name, "args": dict(fc.args or {}), "ok": ok,
                                  "message": payload.get("message", "")})
                    response = {"output": payload} if ok else {"error": payload}
                    parts.append(types.Part(function_response=types.FunctionResponse(
                        id=getattr(fc, "id", None), name=fc.name, response=response)))
                with self._lock:
                    if clear_generation != self._clear_generation:
                        raise Cancelled("Lịch sử hội thoại đã bị xóa")
                    self._history.append(types.Content(role="user", parts=parts))
        except Cancelled:
            done = ", ".join(f"{s['name']}({'ok' if s['ok'] else 'lỗi'})" for s in steps)
            with self._lock:
                if clear_generation == self._clear_generation:
                    self._rollback(start, f"Lượt trước bị người dùng hủy; đã làm: {done or 'chưa có'}." if steps else "")
            raise
        except AIError:
            done = ", ".join(f"{s['name']}({'ok' if s['ok'] else 'lỗi'})" for s in steps)
            with self._lock:
                if clear_generation == self._clear_generation:
                    self._rollback(start, f"Lượt trước lỗi kết nối; đã làm: {done}." if steps else "")
            raise
        return TurnResult("Em chưa hoàn thành được yêu cầu.", steps, "unknown")

    # ----- kiểm tra & ảnh -----
    def test_connection(self) -> tuple[bool, str]:
        from google.genai import types
        # Nút kiểm tra luôn cho phép thử lại key/model hiện tại (người dùng vừa sửa cấu hình).
        self._disabled_key_hash = ""
        ok, reason = self.status()
        if not ok:
            return False, reason
        token = CancelToken(None, 0)
        cfg = types.GenerateContentConfig(system_instruction="Trả lời đúng một từ: OK",
                                          automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                                          max_output_tokens=64, temperature=0)
        try:
            resp = self._call([types.Content(role="user", parts=[types.Part(text="Kiểm tra kết nối")])], cfg, token)
        except AIError as e:
            return False, e.message
        except Exception as exc:  # pragma: no cover
            return False, classify_error(exc, self.model).message
        self._account(resp)
        return True, f"Kết nối Gemini thành công (model {self.model})."

    def describe_image(self, data: bytes, mime: str, question: str, token: CancelToken) -> str:
        from google.genai import types
        cfg = types.GenerateContentConfig(system_instruction=VISION_INSTRUCTION,
                                          automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                                          max_output_tokens=512, temperature=0.3)
        contents = [types.Content(role="user", parts=[types.Part.from_bytes(data=data, mime_type=mime),
                                                      types.Part(text=question)])]
        resp = self._call(contents, cfg, token)
        self._account(resp)
        text = getattr(resp, "text", None) or ""
        return text.strip() or "Em không đọc được nội dung ảnh."

    def generate_json(self, prompt: str, schema: dict | None, token: CancelToken, system: str = "",
                      images: list[tuple[bytes, str]] | None = None, max_tokens: int = 2048,
                      temperature: float = 0.2, *, models: list[str] | None = None, timeout_s: float | None = None,
                      thinking: str | None = None) -> Any:
        """Một lượt hỏi KHÔNG công cụ, trả JSON (dùng cho planner/đánh giá/dựng CAD DSL của mô hình 3D).

        schema=None → chỉ ép MIME JSON (cây DSL đệ quy, tự do: schema object rỗng khiến Gemini trả {}). models/timeout_s:
        tác vụ dài với chuỗi model riêng; thinking: mức suy nghĩ riêng ("" = mặc định của model). Không đụng tới lịch sử
        hội thoại. JSON trả về chỉ là dữ liệu — nơi gọi phải kiểm tra lại bằng schema/whitelist của NEXA.
        """
        import json as _json
        from google.genai import types
        if thinking is None:
            think = self._thinking_config()
        else:
            think = types.ThinkingConfig(thinking_level=thinking) if thinking and self._thinking_supported else None
        extra = {}
        if timeout_s is not None:
            extra["http_options"] = types.HttpOptions(timeout=int((float(timeout_s) + 5) * 1000),
                                                      retry_options=types.HttpRetryOptions(attempts=1))
        cfg = types.GenerateContentConfig(
            system_instruction=system or None, response_mime_type="application/json",
            response_json_schema=schema if schema else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            max_output_tokens=int(max_tokens), temperature=float(temperature), thinking_config=think, **extra)
        parts = [types.Part.from_bytes(data=d, mime_type=m) for d, m in (images or [])] + [types.Part(text=prompt)]
        resp = self._call([types.Content(role="user", parts=parts)], cfg, token, models=models, timeout_s=timeout_s)
        self._account(resp)
        text = (getattr(resp, "text", None) or "").strip()
        if text.startswith("```"):
            text = text.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
        try:
            return _json.loads(text)
        except _json.JSONDecodeError as exc:
            finish = ""
            try:
                finish = str(resp.candidates[0].finish_reason)
            except Exception:
                pass
            if "MAX_TOKENS" in finish:
                raise AIError("bad_response", "Gemini trả JSON bị cắt giữa chừng (hết max_output_tokens).") from exc
            raise AIError("bad_response", f"Gemini trả JSON không hợp lệ: {exc}") from exc

    def generate_image(self, prompt: str, token: CancelToken, model: str,
                       references: list[tuple[bytes, str]] | None = None) -> tuple[bytes, str]:
        """Tạo ảnh bằng model ảnh Gemini (response_modalities IMAGE). Trả (bytes, mime).

        Model ảnh gọi thẳng (không qua chuỗi model dự phòng văn bản). Theo tài liệu: ảnh nằm ở part.inline_data.
        """
        from google.genai import types
        ok, reason = self.status()
        if not ok:
            raise AIError("unavailable", reason)
        token.raise_if_cancelled()
        client = self._get_client()
        wait_s = max(60.0, self.config.gemini_timeout_s * 3)
        cfg = types.GenerateContentConfig(response_modalities=["IMAGE"],
                                          automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                                          http_options=types.HttpOptions(timeout=int(wait_s * 1000),
                                                                         retry_options=types.HttpRetryOptions(attempts=1)))
        parts = [types.Part.from_bytes(data=d, mime_type=m) for d, m in (references or [])] + [types.Part(text=prompt)]
        self.calls += 1
        future = self._pool.submit(client.models.generate_content, model=model,
                                   contents=[types.Content(role="user", parts=parts)], config=cfg)
        deadline = time.monotonic() + wait_s
        while not future.done():
            if token.cancelled:
                future.cancel()
                raise Cancelled("Người dùng hủy trong lúc tạo ảnh")
            if time.monotonic() > deadline:
                future.cancel()
                raise AIError("timeout", "Tạo ảnh tham chiếu quá thời gian chờ.", retryable=True)
            time.sleep(0.05)
        try:
            resp = future.result()
        except Exception as exc:
            raise classify_error(exc, model) from exc
        if token.cancelled:
            raise Cancelled("Ảnh đến sau khi đã hủy")
        self._account(resp)
        for cand in getattr(resp, "candidates", None) or []:
            for part in getattr(getattr(cand, "content", None), "parts", None) or []:
                blob = getattr(part, "inline_data", None)
                if blob is not None and getattr(blob, "data", None) and not getattr(part, "thought", False):
                    return bytes(blob.data), str(getattr(blob, "mime_type", "image/png") or "image/png")
        raise AIError("bad_response", "Model ảnh không trả về ảnh nào.")

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
