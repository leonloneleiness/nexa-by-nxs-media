"""Provider cho các gateway tương thích OpenAI Chat Completions.

Gateway tùy chỉnh chỉ cần hỗ trợ /v1/chat/completions, tool calling và JSON output
ở mức thông thường. API key luôn lấy từ OPENAI_API_KEY, không ghi vào mã nguồn.
"""
from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from nexa.ai.gemini_provider import AIError, TurnResult
from nexa.ai.prompts import SYSTEM_INSTRUCTION, VISION_INSTRUCTION, COMPANION_INSTRUCTION
from nexa.core.safety import Cancelled, CancelToken
from nexa.utils.logging import get_logger, register_secret

log = get_logger("openai")


def _classify(exc: Exception, model: str) -> AIError:
    text = str(exc).lower()
    if any(x in text for x in ("401", "unauthorized", "invalid api key", "authentication")):
        return AIError("auth", "Gateway từ chối OPENAI_API_KEY hoặc key đã hết hạn.")
    if "403" in text or "permission" in text:
        return AIError("permission", f"Key không có quyền dùng model '{model}'.")
    if "404" in text or "not found" in text:
        return AIError("not_found", f"Gateway không tìm thấy model '{model}'.")
    if "429" in text or "rate limit" in text or "quota" in text:
        return AIError("rate_limit", "Gateway đang giới hạn tốc độ hoặc đã hết quota.", retryable=True)
    if "timeout" in text or "timed out" in text:
        return AIError("timeout", "Gateway phản hồi quá thời gian chờ.", retryable=True)
    if isinstance(exc, (ConnectionError, OSError)) or "connect" in text:
        return AIError("network", "Không kết nối được gateway API.", retryable=True)
    return AIError("api", f"Lỗi gateway API: {str(exc)[:160]}")


class OpenAICompatibleProvider:
    name = "openai"

    def __init__(self, config: Any, state_path: Any = None, client_factory: Callable[..., Any] | None = None) -> None:
        self.config = config
        self._client_factory = client_factory or self._default_client
        self._client = None
        self._client_key = ""
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="nexa-openai")
        self._history: list[dict[str, Any]] = []
        self._notes: list[str] = []
        self.calls = 0
        self.usage = {"prompt": 0, "output": 0, "thoughts": 0, "total": 0}
        self.last_error: AIError | None = None
        self.last_latency_ms = 0.0

    @staticmethod
    def _default_client(api_key: str, base_url: str, timeout_s: float) -> Any:
        from openai import OpenAI
        return OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_s, max_retries=0)

    @property
    def model(self) -> str:
        return self.config.openai_model

    @property
    def history_turns(self) -> int:
        return sum(1 for m in self._history if m.get("role") == "user")

    def _base_url(self) -> str:
        url = self.config.openai_base_url
        if url.endswith("/v1") or url.endswith("/v1beta"):
            return url
        return url + "/v1"

    def status(self) -> tuple[bool, str]:
        if self.config.ai_provider not in ("openai", "openai_compatible", "compatible"):
            return False, f"NEXA_AI_PROVIDER='{self.config.ai_provider}' chưa bật OpenAI-compatible."
        if self.config.openai_key_status() == "missing":
            return False, "Chưa có OPENAI_API_KEY."
        if self.config.openai_key_status() == "placeholder":
            return False, "OPENAI_API_KEY vẫn là giá trị mẫu."
        if self.calls >= int(self.config.get("ai.max_calls_per_session") or 300):
            return False, "Đã chạm giới hạn số lần gọi AI trong phiên."
        return True, f"OpenAI-compatible ({self.model})"

    def _get_client(self) -> Any:
        key = self.config.openai_api_key()
        if not key:
            raise AIError("auth", "Chưa có OPENAI_API_KEY hợp lệ.")
        register_secret(key)
        with self._lock:
            identity = key + "\0" + self._base_url()
            if self._client is None or self._client_key != identity:
                self._client = self._client_factory(key, self._base_url(), self.config.openai_timeout_s)
                self._client_key = identity
            return self._client

    def _request(self, messages: list[dict[str, Any]], token: CancelToken,
                 tools: list[dict[str, Any]] | None = None, *, model: str | None = None,
                 json_mode: bool = False, max_tokens: int | None = None,
                 temperature: float | None = None) -> Any:
        ok, reason = self.status()
        if not ok:
            raise AIError("unavailable", reason)
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "messages": list(messages),
            "max_tokens": int(max_tokens or self.config.get("ai.max_output_tokens") or 1024),
            "temperature": float(self.config.get("ai.temperature") if temperature is None else temperature),
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        self.calls += 1
        started = time.monotonic()
        future = self._pool.submit(client.chat.completions.create, **kwargs)
        deadline = started + self.config.openai_timeout_s + 5
        while not future.done():
            if token.cancelled:
                future.cancel()
                raise Cancelled("Người dùng hủy trong lúc chờ gateway API")
            if time.monotonic() > deadline:
                future.cancel()
                raise AIError("timeout", "Gateway phản hồi quá thời gian chờ.", retryable=True)
            time.sleep(0.05)
        try:
            response = future.result()
        except Exception as exc:
            err = _classify(exc, kwargs["model"])
            self.last_error = err
            raise err from exc
        self.last_error = None
        self.last_latency_ms = (time.monotonic() - started) * 1000
        usage = getattr(response, "usage", None)
        if usage is not None:
            prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
            output = int(getattr(usage, "completion_tokens", 0) or 0)
            self.usage.update({"prompt": self.usage["prompt"] + prompt,
                               "output": self.usage["output"] + output,
                               "total": self.usage["total"] + int(getattr(usage, "total_tokens", prompt + output) or 0)})
        return response

    @staticmethod
    def _tools(declarations: list[dict]) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {"name": d["name"], "description": d.get("description", ""),
                "parameters": d.get("parameters_json_schema") or {"type": "object", "properties": {}}}}
                for d in declarations]

    def add_note(self, note: str) -> None:
        with self._lock:
            self._notes.append(note[:300])
            del self._notes[:-5]

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()
            self._notes.clear()

    def converse(self, text: str, declarations: list[dict], execute_tool: Callable[[Any], dict],
                 token: CancelToken, context: str = "", *, companion: bool = False) -> TurnResult:
        system = COMPANION_INSTRUCTION if companion else SYSTEM_INSTRUCTION
        notes = ("[Ghi chú: " + " ".join(self._notes[-5:]) + "]\n") if self._notes else ""
        self._notes.clear()
        with self._lock:
            self._history.append({"role": "user", "content": context + notes + text})
        messages = [{"role": "system", "content": system}, *self._history]
        steps: list[dict[str, Any]] = []
        tools = None if companion else self._tools(declarations)
        try:
            for step in range(self.config.max_tool_steps + 1):
                resp = self._request(messages, token, tools)
                msg = resp.choices[0].message
                calls = list(getattr(msg, "tool_calls", None) or [])
                content = (getattr(msg, "content", None) or "").strip()
                assistant: dict[str, Any] = {"role": "assistant", "content": content or None}
                if calls:
                    assistant["tool_calls"] = [{"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}} for c in calls]
                messages.append(assistant)
                if companion and calls:
                    return TurnResult("Anh nói 'thoát chế độ tâm sự' nếu muốn em thao tác máy tính nhé.", [], "chat_only")
                if not calls:
                    with self._lock:
                        self._history.append({"role": "assistant", "content": content})
                    return TurnResult(content or "Dạ.", steps)
                if step >= self.config.max_tool_steps:
                    return TurnResult(f"Em dừng lại vì yêu cầu cần hơn {self.config.max_tool_steps} bước.", steps, "step_limit")
                for call in calls:
                    token.raise_if_cancelled()
                    try:
                        args = json.loads(call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    fc = SimpleNamespace(id=call.id, name=call.function.name, args=args)
                    payload = execute_tool(fc)
                    ok = bool(payload.get("ok"))
                    steps.append({"name": fc.name, "args": args, "ok": ok, "message": payload.get("message", "")})
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(payload, ensure_ascii=False)})
            return TurnResult("Em chưa hoàn thành được yêu cầu.", steps, "unknown")
        except (Cancelled, AIError):
            raise

    def test_connection(self) -> tuple[bool, str]:
        try:
            token = CancelToken(None, 0)
            self._request([{"role": "system", "content": "Trả lời đúng một từ: OK"}, {"role": "user", "content": "Kiểm tra kết nối"}], token, max_tokens=8, temperature=0)
            return True, f"Kết nối gateway thành công (model {self.model})."
        except AIError as exc:
            return False, exc.message

    def describe_image(self, data: bytes, mime: str, question: str, token: CancelToken) -> str:
        import base64
        content = [{"type": "text", "text": question},
                   {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(data).decode()}"}}]
        resp = self._request([{"role": "system", "content": VISION_INSTRUCTION}, {"role": "user", "content": content}], token, max_tokens=512, temperature=0.3)
        return (getattr(resp.choices[0].message, "content", None) or "").strip() or "Em không đọc được nội dung ảnh."

    def generate_json(self, prompt: str, schema: dict | None, token: CancelToken, system: str = "", images: list[tuple[bytes, str]] | None = None,
                      max_tokens: int = 2048, temperature: float = 0.2, **_: Any) -> Any:
        resp = self._request([{"role": "system", "content": system or SYSTEM_INSTRUCTION}, {"role": "user", "content": prompt}], token,
                             json_mode=True, max_tokens=max_tokens, temperature=temperature)
        text = (getattr(resp.choices[0].message, "content", None) or "").strip().strip("`")
        return json.loads(text)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
