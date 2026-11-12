"""Tool registry: schema, kiểm tra tham số và các công cụ NEXA được phép dùng.

Giọng nói, bàn phím, cử chỉ và Gemini đều gọi CÙNG các công cụ ở đây qua Executor.
- Tham số được kiểm tra bằng validate_schema (kiểu, enum, min/max, độ dài, trường lạ).
- Mức rủi ro (Risk) do mã tính từ tham số + ngữ cảnh thật (tiến trình đích, phần mở rộng tệp, tổ hợp
  phím…), không tin bất kỳ trường nào do model tự khai.
- Trường nội bộ (ví dụ use_gesture_snapshot) không xuất hiện trong schema gửi cho Gemini và bị từ
  chối nếu AI cố gửi.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from nexa.core.events import Risk, Source, ToolResult
from nexa.core.safety import Assessment
from nexa.utils.logging import get_logger
from nexa.utils.text import fold, truncate

log = get_logger("tools")

MESSAGING_OR_BROWSER = {
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe", "coccoc.exe", "vivaldi.exe",
    "zalo.exe", "telegram.exe", "discord.exe", "slack.exe", "teams.exe", "ms-teams.exe", "outlook.exe", "olk.exe",
    "thunderbird.exe", "whatsapp.exe", "messenger.exe", "skype.exe", "signal.exe", "viber.exe", "line.exe",
}
TERMINALS = {"cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe", "wt.exe", "openconsole.exe",
             "conhost.exe", "wsl.exe", "bash.exe", "mintty.exe", "python.exe", "pythonw.exe", "putty.exe"}
DANGEROUS_CONTROL_WORDS = ["gui", "send", "dang", "post", "publish", "xoa", "delete", "remove", "submit", "mua", "buy",
                           "thanh toan", "pay", "checkout", "dat hang", "order", "chuyen tien", "transfer",
                           "xac nhan", "confirm", "cai dat", "install", "uninstall", "go cai", "format", "reset",
                           "dang xuat", "sign out", "log out", "tat may", "shut down", "restart", "khoi dong lai",
                           "chia se", "share", "reply all", "tra loi tat ca"]


# ------------------------------------------------------------------ schema
def validate_schema(schema: dict, value: Any, path: str = "args") -> tuple[bool, str, Any]:
    t = schema.get("type")
    if t == "object":
        if not isinstance(value, dict):
            return False, f"{path} phải là object", None
        props = schema.get("properties", {})
        out = {}
        for key in value:
            if key not in props and not schema.get("additionalProperties", False):
                return False, f"{path}.{key} không được phép", None
        for req in schema.get("required", []):
            if req not in value or value[req] is None:
                return False, f"thiếu {path}.{req}", None
        for key, sub in props.items():
            if key in value and value[key] is not None:
                ok, err, v = validate_schema(sub, value[key], f"{path}.{key}")
                if not ok:
                    return False, err, None
                out[key] = v
            elif "default" in sub:
                out[key] = sub["default"]
        return True, "", out
    if t == "string":
        if not isinstance(value, str):
            return False, f"{path} phải là chuỗi", None
        v = value.strip()
        if "enum" in schema and v not in schema["enum"]:
            return False, f"{path} phải thuộc {schema['enum']}", None
        if len(v) < schema.get("minLength", 0):
            return False, f"{path} quá ngắn", None
        if len(v) > schema.get("maxLength", 10_000):
            return False, f"{path} quá dài (tối đa {schema.get('maxLength')})", None
        return True, "", v
    if t == "integer":
        if isinstance(value, bool):
            return False, f"{path} phải là số nguyên", None
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            value = int(value.strip())
        if not isinstance(value, int):
            return False, f"{path} phải là số nguyên", None
        if "minimum" in schema and value < schema["minimum"]:
            return False, f"{path} nhỏ hơn {schema['minimum']}", None
        if "maximum" in schema and value > schema["maximum"]:
            return False, f"{path} lớn hơn {schema['maximum']}", None
        return True, "", value
    if t == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False, f"{path} phải là số", None
        if not math.isfinite(value):
            return False, f"{path} phải là số hữu hạn", None
        if "minimum" in schema and value < schema["minimum"]:
            return False, f"{path} nhỏ hơn {schema['minimum']}", None
        if "maximum" in schema and value > schema["maximum"]:
            return False, f"{path} lớn hơn {schema['maximum']}", None
        return True, "", float(value)
    if t == "boolean":
        if not isinstance(value, bool):
            return False, f"{path} phải là true/false", None
        return True, "", value
    if t == "array":
        if not isinstance(value, list):
            return False, f"{path} phải là mảng", None
        if len(value) > schema.get("maxItems", 100) or len(value) < schema.get("minItems", 0):
            return False, f"{path} có số phần tử không hợp lệ", None
        out = []
        for i, item in enumerate(value):
            ok, err, v = validate_schema(schema.get("items", {}), item, f"{path}[{i}]")
            if not ok:
                return False, err, None
            out.append(v)
        return True, "", out
    return False, f"{path}: kiểu schema không hỗ trợ", None


def obj(props: dict[str, dict], required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


S_STR = lambda desc, maxlen=300, **kw: {"type": "string", "description": desc, "maxLength": maxlen, **kw}  # noqa: E731
S_INT = lambda desc, lo, hi, **kw: {"type": "integer", "description": desc, "minimum": lo, "maximum": hi, **kw}  # noqa: E731
S_BOOL = lambda desc, **kw: {"type": "boolean", "description": desc, **kw}  # noqa: E731


# ------------------------------------------------------------------ ToolSpec
@dataclass
class ToolSpec:
    name: str
    title: str
    description: str
    parameters: dict
    handler: Callable[[dict, Any], ToolResult]
    risk: Callable[[dict, Any], Assessment] | Risk = Risk.LOW
    internal_params: set[str] = field(default_factory=set)
    fingerprint_fn: Callable[[dict, Any], str] | None = None
    describe_fn: Callable[[dict, Any, Assessment], str] | None = None
    preview: Callable[[dict, Any], dict] | None = None
    precheck: Callable[[dict, Any], "ToolResult | None"] | None = None
    always_confirm: bool = False      # vẫn hỏi xác nhận kể cả ở chế độ toàn quyền
    expose_to_ai: bool = True
    ai_enabled: Callable[[], bool] | None = None
    needs_control: bool = True
    allowed_when_paused: bool = False

    def assess(self, args: dict, ctx: Any) -> Assessment:
        if callable(self.risk):
            return self.risk(args, ctx)
        return Assessment(self.risk, "")

    def fingerprint(self, args: dict, ctx: Any) -> str:
        base = json.dumps({"tool": self.name, "args": args}, sort_keys=True, ensure_ascii=False, default=str)
        extra = self.fingerprint_fn(args, ctx) if self.fingerprint_fn else ""
        return hashlib.sha256((base + "|" + extra).encode("utf-8")).hexdigest()

    def describe(self, args: dict, ctx: Any, assessment: Assessment) -> str:
        if self.describe_fn:
            return self.describe_fn(args, ctx, assessment)
        shown = ", ".join(f"{k}={truncate(str(v), 60)}" for k, v in args.items() if k not in self.internal_params)
        text = f"{self.title}" + (f" ({shown})" if shown else "")
        return text + (f". {assessment.reason}" if assessment.reason else "")

    def ai_schema(self) -> dict:
        schema = json.loads(json.dumps(self.parameters))
        for k in self.internal_params:
            schema.get("properties", {}).pop(k, None)
            if k in schema.get("required", []):
                schema["required"].remove(k)
        return schema


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Trùng tên công cụ {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def validate(self, name: str, args: Any, source: Source = Source.SYSTEM) -> tuple[bool, str, dict]:
        spec = self._tools.get(name)
        if spec is None:
            return False, f"công cụ {name} không tồn tại", {}
        if source == Source.AI:
            if not spec.expose_to_ai or (spec.ai_enabled and not spec.ai_enabled()):
                return False, f"công cụ {name} không được phép cho AI", {}
            schema = spec.ai_schema()
        else:
            schema = spec.parameters
        ok, err, cleaned = validate_schema(schema, args if args is not None else {})
        return ok, err, cleaned or {}

    def gemini_declarations(self) -> list[dict[str, Any]]:
        out = []
        for spec in self._tools.values():
            if not spec.expose_to_ai or (spec.ai_enabled and not spec.ai_enabled()):
                continue
            out.append({"name": spec.name, "description": spec.description, "parameters_json_schema": spec.ai_schema()})
        return out


# ------------------------------------------------------------------ Services
@dataclass
class Services:
    config: Any
    wm: Any = None
    monitors: Any = None
    input: Any = None
    apps: Any = None
    files: Any = None
    shots: Any = None
    volume: Any = None
    media: Any = None
    vision: Any = None
    three_d: Any = None                                    # nexa.three_d.service.ThreeDService
    code: Any = None                                       # nexa.code.service.CodeService
    side_by_side: Any = None                               # nexa.desktop.side_by_side.SideBySide
    hooks: dict[str, Callable[..., Any]] = field(default_factory=dict)
    notify: Callable[[str, dict], None] | None = None
    memory: dict[str, Any] = field(default_factory=dict)   # ngữ cảnh ngắn hạn: từ khóa vừa tìm, control vừa đọc

    def emit(self, kind: str, **data: Any) -> None:
        if self.notify:
            try:
                self.notify(kind, data)
            except Exception:
                log.exception("notify lỗi")


# ------------------------------------------------------------------ trợ giúp đích cửa sổ
def _target_window(args: dict, ctx: Any) -> tuple[int | None, str]:
    wm = ctx.services.wm
    if args.get("use_gesture_snapshot"):
        ok, reason = wm.verify_snapshot(ctx.snapshot)
        return (ctx.snapshot.identity.hwnd if ok else None), reason
    query = (args.get("window") or "").strip()
    if query:
        matches = wm.find_windows(query)
        if not matches:
            return None, f"Không thấy cửa sổ nào khớp '{query}'."
        if len(matches) > 1:
            exact = [m for m in matches if fold(m["title"]) == fold(query)]
            if len(exact) == 1:
                return exact[0]["hwnd"], ""
            names = "; ".join(truncate(m["title"], 40) for m in matches[:4])
            return None, f"Có {len(matches)} cửa sổ khớp '{query}': {names}. Anh nói rõ hơn giúp em."
        return matches[0]["hwnd"], ""
    return wm.resolve_work_window()


def _target_process(args: dict, ctx: Any) -> str:
    try:
        hwnd, _ = _target_window(args, ctx)
        if hwnd:
            ident = ctx.services.wm.identity(hwnd)
            return (ident.process_name if ident else "").lower()
    except Exception:
        pass
    return ""


def _window_fp(args: dict, ctx: Any) -> str:
    try:
        hwnd, _ = _target_window(args, ctx)
        if hwnd:
            ident = ctx.services.wm.identity(hwnd)
            return f"{hwnd}|{ident.pid if ident else 0}|{ctx.services.wm.api.get_title(hwnd)}"
    except Exception:
        pass
    return "none"


def _focus_target(args: dict, ctx: Any) -> tuple[int | None, ToolResult | None]:
    hwnd, reason = _target_window(args, ctx)
    if not hwnd:
        return None, ToolResult.failure(reason or "Không xác định được cửa sổ đích.", "no_target")
    wm = ctx.services.wm
    if wm.api.get_foreground() != hwnd:
        r = wm.focus(hwnd)
        if not r.ok:
            return None, r
    if wm.api.get_foreground() != hwnd:
        return None, ToolResult.failure("Cửa sổ đích không ở trên cùng nên em không nhập liệu.", "target_not_foreground")
    return hwnd, None


def _emit_window(ctx: Any, hwnd: int | None, text: str) -> None:
    if hwnd:
        try:
            ctx.services.emit("highlight", rect=list(ctx.services.wm.api.get_rect(hwnd)), text=text)
        except Exception:
            pass


# ------------------------------------------------------------------ đánh giá rủi ro
def risk_press_keys(args: dict, ctx: Any) -> Assessment:
    keys = [k.lower().strip() for k in args.get("keys", [])]
    combo = set(keys)
    proc = _target_process(args, ctx)
    if {"alt", "f4"} <= combo or ({"ctrl", "w"} <= combo) or ({"ctrl", "q"} <= combo) or ({"ctrl", "f4"} <= combo):
        return Assessment(Risk.HIGH, "Tổ hợp này đóng cửa sổ/tab và có thể làm mất nội dung chưa lưu.")
    if {"win", "r"} <= combo or {"win", "x"} <= combo:
        return Assessment(Risk.HIGH, "Tổ hợp này mở hộp thoại chạy lệnh/menu quản trị.")
    if "shift" in combo and "delete" in combo:
        return Assessment(Risk.HIGH, "Shift+Delete có thể xóa vĩnh viễn.")
    if "delete" in combo and proc == "explorer.exe":
        return Assessment(Risk.HIGH, "Phím Delete trong File Explorer sẽ xóa tệp đang chọn.")
    if combo & {"enter", "return"}:
        if proc in TERMINALS:
            return Assessment(Risk.HIGH, f"Enter trong {proc} sẽ chạy lệnh.")
        if proc in MESSAGING_OR_BROWSER:
            return Assessment(Risk.HIGH, f"Enter trong {proc} có thể gửi tin nhắn/biểu mẫu.")
    return Assessment(Risk.LOW, "")


def risk_type_text(args: dict, ctx: Any) -> Assessment:
    proc = _target_process(args, ctx)
    text = args.get("text", "")
    if proc in TERMINALS:
        return Assessment(Risk.HIGH, f"Gõ vào {proc} có thể chạy lệnh.")
    if "\n" in text and proc in MESSAGING_OR_BROWSER:
        return Assessment(Risk.HIGH, f"Nội dung có xuống dòng; Enter trong {proc} có thể gửi đi.")
    return Assessment(Risk.LOW, "")


def risk_click_control(args: dict, ctx: Any) -> Assessment:
    name = fold(args.get("name", ""))
    if any(w in name for w in DANGEROUS_CONTROL_WORDS):
        return Assessment(Risk.HIGH, f"Nút '{args.get('name')}' có thể gửi/xóa/thanh toán/thay đổi hệ thống.")
    return Assessment(Risk.LOW, "")


def risk_mouse(args: dict, ctx: Any) -> Assessment:
    if "x" in args and "y" in args:
        return Assessment(Risk.MEDIUM, f"Nhấp theo tọa độ ({args.get('x')}, {args.get('y')}) — không kiểm chứng được control.")
    return Assessment(Risk.LOW, "")


def risk_open_path(args: dict, ctx: Any) -> Assessment:
    try:
        p = ctx.services.files.check(args["path"])
    except Exception:
        return Assessment(Risk.LOW, "")
    if ctx.services.files.is_executable(p):
        return Assessment(Risk.HIGH, f"'{p.name}' là tệp thực thi/lối tắt — mở nó sẽ chạy chương trình.")
    return Assessment(Risk.LOW, "")


def risk_transfer(move: bool) -> Callable[[dict, Any], Assessment]:
    def fn(args: dict, ctx: Any) -> Assessment:
        if args.get("overwrite"):
            return Assessment(Risk.HIGH, "Ghi đè tệp đã có ở thư mục đích (bản cũ vào Thùng rác).")
        return Assessment(Risk.MEDIUM if move else Risk.LOW, "Di chuyển tệp." if move else "")
    return fn


def risk_power(args: dict, ctx: Any) -> Assessment:
    action = args.get("action")
    if action in ("shutdown", "restart"):
        return Assessment(Risk.HIGH, "Các ứng dụng đang mở sẽ bị đóng.")
    if action == "sleep":
        cfg = getattr(getattr(ctx, "services", None), "config", None)
        if cfg is not None and cfg.get("power.clap_wake_guard"):
            return Assessment(Risk.LOW, "Chỉ tắt màn hình; vỗ tay để bật lại.")
        return Assessment(Risk.MEDIUM, "Máy sẽ ngủ.")
    return Assessment(Risk.LOW, "")


def _path_fp(args: dict, ctx: Any) -> str:
    parts = []
    for key in ("path", "dest_folder"):
        if key in args:
            try:
                parts.append(ctx.services.files.fingerprint(ctx.services.files.check(args[key])))
            except Exception:
                parts.append(f"{args[key]}|invalid")
    return "|".join(parts)


# ------------------------------------------------------------------ handlers
def h_open_app(args: dict, ctx: Any) -> ToolResult:
    apps = ctx.services.apps
    app, candidates = apps.resolve(args["name"])
    if app is None:
        if candidates:
            return ToolResult.failure("Em thấy nhiều ứng dụng khớp: " + ", ".join(c.name for c in candidates) +
                                      ". Anh muốn mở cái nào?", "ambiguous", candidates=[c.name for c in candidates])
        return ToolResult.failure(f"Em chưa tìm thấy ứng dụng '{args['name']}'. Anh thêm nó trong Cài đặt > Ứng dụng.",
                                  "not_found")
    result = apps.launch(app)
    if result.ok and result.data.get("hwnd"):
        _emit_window(ctx, result.data["hwnd"], f"Đã mở {app.name}")
    return result


def h_open_url(args: dict, ctx: Any) -> ToolResult:
    return ctx.services.apps.open_url(args["url"])


def h_web_search(args: dict, ctx: Any) -> ToolResult:
    ctx.services.memory["last_query"] = args["query"]
    return ctx.services.apps.web_search(args["query"])


def h_site_search(args: dict, ctx: Any) -> ToolResult:
    from nexa.ai.site_search import find_site, search_url
    site = find_site(args.get("site") or "")
    query = (args.get("query") or "").strip()
    if site is None:
        return ToolResult.failure(f"Em chưa biết cách tìm trong '{args.get('site')}'.", "unknown_site")
    if not query:
        return ToolResult.failure(f"Anh muốn tìm gì trên {site.name} ạ?", "empty")
    r = ctx.services.apps.open_url(search_url(site, query))
    if not r.ok:
        return r
    if not site.ask:
        return ToolResult(ok=True, verified=r.verified, message=f"Đã tìm trên {site.name}: {truncate(query, 80)}.",
                          data=dict(r.data, site=site.key, query=query))
    how = _ensure_question_sent(ctx, site, query)
    data = dict(r.data, site=site.key, query=query, sent=how)
    if how in ("auto", "typed", "enter"):
        return ToolResult.success(f"Đã hỏi {site.name}: {truncate(query, 80)}.", verified=True, **data)
    return ToolResult(ok=True, verified=False, data=data,
                      message=f"Em đã mở {site.name} với câu hỏi “{truncate(query, 60)}” nhưng chưa thấy trang gửi đi. "
                              f"Anh bấm gửi giúp em nhé.")


def _ensure_question_sent(ctx: Any, site: Any, query: str, timeout: float = 10.0) -> str:
    """Chờ trang trợ lý AI tự gửi câu hỏi từ ?q=; nếu không, gửi hộ bằng bàn phím — CHỈ khi con trỏ đang ở ô soạn
    thảo trong đúng trang đó. Trả về "auto" | "enter" | "typed" | "unknown"."""
    import time as _time
    from nexa.desktop import uia
    wm = ctx.services.wm
    deadline = _time.monotonic() + timeout
    fallback_after = _time.monotonic() + 3.5
    tried = False
    hwnd = None
    while _time.monotonic() < deadline and not ctx.token.cancelled:
        if hwnd is None:
            for w in wm.list_windows(limit=60):
                if w["process"].lower() in uia.BROWSER_PROCESSES and fold(site.name) in fold(w["title"]):
                    hwnd = w["hwnd"]
                    break
        if hwnd is not None:
            title = uia.page_title(hwnd)
            address = uia.address_bar(hwnd)
            # Đã gửi: địa chỉ chuyển sang cuộc trò chuyện (/c/<id>), hoặc tiêu đề trang chứa chính câu hỏi
            # (ChatGPT chưa đăng nhập: "Thủ đô của Pháp là gì | ChatGPT"). Không suy từ tiêu đề lúc đang tải.
            if "/c/" in address or "/chat/" in address or (title and fold(query)[:20] in fold(title)):
                return "typed" if tried else "auto"
            if not tried and _time.monotonic() >= fallback_after:
                editor = uia.focused_page_editor(hwnd, site.name)
                if editor is not None:
                    tried = True
                    _info, current = editor
                    if fold(query) in fold(current):
                        ctx.services.input.hotkey(["enter"], hwnd)
                        log.info("%s đã điền sẵn câu hỏi nhưng chưa gửi — em nhấn Enter", site.name)
                        return "enter"
                    log.info("%s chưa nhận câu hỏi từ địa chỉ — em gõ vào ô chat rồi gửi", site.name)
                    typed = ctx.services.input.type_text(query, hwnd, cancelled=lambda: ctx.token.cancelled)
                    if typed.ok:
                        ctx.services.input.hotkey(["enter"], hwnd)
                        return "typed"
        _time.sleep(0.3)
    return "unknown"


def h_play_youtube(args: dict, ctx: Any) -> ToolResult:
    memory = ctx.services.memory
    query = (args.get("query") or "").strip() or memory.get("last_query", "")
    if not query:
        return ToolResult.failure("Anh muốn mở video gì ạ? (ví dụ: mở video nhạc Tíc Tắc)", "no_query")
    # "Đổi video / bài khác": video kế tiếp trong kết quả tìm gần nhất (kết quả đã nhớ nên không tải lại).
    index = int(memory.get("last_index", 1)) + 1 if args.get("next") else int(args.get("index", 1))
    if index > 20:
        index = 1
    memory["last_query"] = query
    memory["last_index"] = index
    r = ctx.services.apps.play_youtube(query, index)
    media = getattr(ctx.services, "media", None)
    if r.ok and media is not None:
        media.expect(r.data.get("video_id", ""), r.data.get("title", ""))   # "tạm dừng" sau đó nhắm đúng video này
    return r


def h_list_windows(args: dict, ctx: Any) -> ToolResult:
    items = ctx.services.wm.list_windows()
    return ToolResult.success(f"Có {len(items)} cửa sổ ứng dụng.", verified=True, windows=items)


def h_active_window(args: dict, ctx: Any) -> ToolResult:
    hwnd, reason = ctx.services.wm.resolve_work_window()
    if not hwnd:
        return ToolResult.failure(reason, "no_target")
    return ToolResult.success("Cửa sổ đang làm việc.", verified=True, **ctx.services.wm.info(hwnd))


def h_focus_window(args: dict, ctx: Any) -> ToolResult:
    hwnd, reason = _target_window({"window": args["window"]}, ctx)
    if not hwnd:
        return ToolResult.failure(reason, "no_target")
    r = ctx.services.wm.focus(hwnd)
    _emit_window(ctx, hwnd if r.ok else None, "Cửa sổ đích")
    return r


def h_minimize(args: dict, ctx: Any) -> ToolResult:
    hwnd, reason = _target_window(args, ctx)
    if not hwnd:
        return ToolResult.failure(reason, "no_target")
    rect = ctx.services.wm.api.get_rect(hwnd)
    r = ctx.services.wm.minimize(hwnd)
    if r.ok and not r.data.get("no_op"):
        ctx.services.emit("minimize", rect=list(rect), text=r.message)
    return r


def h_restore_last(args: dict, ctx: Any) -> ToolResult:
    r = ctx.services.wm.restore_last()
    if r.ok:
        ctx.services.emit("restore", rect=r.data.get("rect"), text=r.message)
    return r


def h_maximize(args: dict, ctx: Any) -> ToolResult:
    hwnd, reason = _target_window(args, ctx)
    if not hwnd:
        return ToolResult.failure(reason, "no_target")
    return ctx.services.wm.maximize(hwnd)


def h_move_to_monitor_2(args: dict, ctx: Any) -> ToolResult:
    hwnd, reason = _target_window(args, ctx)
    if not hwnd:
        return ToolResult.failure(reason, "no_target")
    r = ctx.services.wm.move_to_target_monitor(hwnd)
    if r.ok and not r.data.get("no_op"):
        ctx.services.emit("move_monitor", source=r.data.get("source_rect"), target=r.data.get("target_rect"),
                          rect=r.data.get("rect"), text=r.message)
    return r


def h_close_window(args: dict, ctx: Any) -> ToolResult:
    hwnd, reason = _target_window(args, ctx)
    if not hwnd:
        return ToolResult.failure(reason, "no_target")
    return ctx.services.wm.close(hwnd)


def _close_queries(name: str) -> list[str]:
    """Tên anh nói + tên chuẩn của ứng dụng quen thuộc ("VS Của" → "visual studio code")."""
    from nexa.desktop.app_aliases import known_app_for
    raw = fold(name).strip()
    out = [raw] if raw else []
    known = known_app_for(name)
    if known is not None and fold(known.name) not in out:
        out.append(fold(known.name))
    return out


def h_close_named(args: dict, ctx: Any) -> ToolResult:
    """Đóng theo tên: tab trình duyệt trước (ChatGPT, YouTube…), không có thì cửa sổ ứng dụng (VS Code, Zalo…)."""
    from nexa.desktop import uia
    name = (args.get("name") or "").strip()
    kind = args.get("kind") or "any"
    queries = _close_queries(name)
    if not queries:
        return ToolResult.failure("Anh muốn em đóng gì ạ?", "empty")
    wm = ctx.services.wm
    windows = wm.list_windows(limit=100)

    def hit(text: str) -> bool:
        t = fold(text)
        return any(q in t for q in queries)

    if kind in ("any", "tab"):
        closed: list[str] = []
        for w in windows:
            if w["process"].lower() not in uia.BROWSER_PROCESSES:
                continue
            for tab in [t for t in uia.browser_tabs(w["hwnd"]) if hit(uia.tab_title(t))]:
                if ctx.token.cancelled:
                    break
                title = uia.tab_title(tab)
                if uia.close_tab(w["hwnd"], tab, hotkey=ctx.services.input.hotkey):
                    closed.append(title)
        if closed:
            label = closed[0] if len(closed) == 1 else f"{len(closed)} tab"
            return ToolResult.success(f"Đã đóng tab {truncate(label, 50)}.", verified=True, closed=closed)
        if kind == "tab":
            return ToolResult.failure(f"Em không thấy tab nào tên '{name}' đang mở.", "not_found")

    targets = []
    for w in windows:
        process = w["process"].rsplit(".", 1)[0]
        if w["process"].lower() in uia.BROWSER_PROCESSES and not any(q == fold(process) for q in queries):
            continue    # cửa sổ trình duyệt chỉ khớp vì tab đang xem: bước tab ở trên đã xử lý
        if hit(w["title"]) or any(q == fold(process) for q in queries):
            targets.append(w)
    if not targets:
        return ToolResult.failure(f"Em không thấy ứng dụng hay tab nào tên '{name}' đang mở.", "not_found")
    results = [wm.close(w["hwnd"]) for w in targets]
    done = [r for r in results if r.ok and r.verified]
    if len(done) == len(results):
        what = truncate(targets[0]["title"], 50) if len(targets) == 1 else f"{len(targets)} cửa sổ {name}"
        return ToolResult.success(f"Đã đóng {what}.", verified=True)
    pending = [r for r in results if not r.verified]
    return ToolResult(ok=True, verified=False, message=pending[0].message if pending else "Em đã gửi lệnh đóng.",
                      data={"closed": len(done), "total": len(results)})


def h_new_document(args: dict, ctx: Any) -> ToolResult:
    from nexa.desktop.office import new_office_document
    folder = None
    if args.get("folder"):
        try:
            folder = ctx.services.files.resolve_folder(args["folder"])
        except PermissionError as exc:
            return ToolResult.failure(str(exc), "out_of_scope")
    return new_office_document(args["kind"], (args.get("name") or "").strip() or None, folder)


def h_vscode_new_file(args: dict, ctx: Any) -> ToolResult:
    """Tạo file mới rồi mở trong VS Code (có tên = file thật trên đĩa; không tên = Ctrl+N trong VS Code)."""
    from nexa.desktop.office import find_vscode, open_in_vscode, unique_path
    name = (args.get("name") or "").strip()
    if not name:
        app, _ = ctx.services.apps.resolve("visual studio code")
        if app is None:
            return ToolResult.failure("Em không tìm thấy VS Code trên máy.", "not_found")
        for w in ctx.services.wm.list_windows(limit=80):
            if fold("visual studio code") in fold(w["title"]):
                hwnd, err = _focus_target({"window": w["title"]}, ctx)
                if err:
                    return err
                r = ctx.services.input.hotkey(["ctrl", "n"], hwnd)
                return ToolResult.success("Đã mở file mới trong VS Code.", verified=True) if r.ok else r
        if not find_vscode():
            return ToolResult.failure("Em không tìm thấy VS Code trên máy.", "not_found")
        ctx.services.apps.launch(app)
        return ToolResult(ok=True, verified=False, message="Đã mở VS Code. Anh nói lại 'file mới' để tạo file nhé.")
    try:
        folder = ctx.services.files.resolve_folder(args.get("folder") or "")
    except PermissionError as exc:
        return ToolResult.failure(str(exc), "out_of_scope")
    from pathlib import Path
    stem, ext = Path(name).stem, (Path(name).suffix or ".txt")
    if not ctx.services.files.validate_name(stem + ext):
        return ToolResult.failure(f"Tên tệp '{stem + ext}' không hợp lệ.", "bad_name")
    path = unique_path(folder, stem, ext)
    try:
        path.write_text("", encoding="utf-8")
    except OSError as exc:
        return ToolResult.failure(f"Không tạo được tệp: {exc}", "write_failed")
    r = open_in_vscode(str(path))
    return ToolResult(ok=r.ok, verified=r.verified, message=f"Đã tạo {path.name} và mở trong VS Code."
                      if r.ok else r.message, data={"path": str(path)})


def h_skip_youtube_ad(args: dict, ctx: Any) -> ToolResult:
    from nexa.desktop.youtube_ads import skip_ad
    return skip_ad(ctx.services.wm, timeout=float(args.get("wait_s") or 12.0),
                   cancelled=lambda: ctx.token.cancelled)


def h_auto_skip_ads(args: dict, ctx: Any) -> ToolResult:
    skipper = ctx.services.hooks.get("ad_skipper")
    if skipper is None:
        return ToolResult.failure("Chức năng tự bỏ qua quảng cáo không khả dụng.", "unavailable")
    on = bool(args["enabled"])
    skipper.start() if on else skipper.stop()
    return ToolResult.success("Đã bật tự bỏ qua quảng cáo YouTube." if on else "Đã tắt tự bỏ qua quảng cáo.",
                              verified=True)


def h_check_zalo(args: dict, ctx: Any) -> ToolResult:
    from nexa.desktop.zalo import check_unread
    return check_unread()


def h_admin_status(args: dict, ctx: Any) -> ToolResult:
    from nexa.desktop.admin import is_admin
    if is_admin():
        return ToolResult.success("NEXA đang chạy với quyền quản trị.", verified=True, admin=True)
    return ToolResult.success("NEXA đang chạy với quyền thường. Anh nói 'chạy với quyền quản trị' nếu cần.",
                              verified=True, admin=False)


def h_request_admin(args: dict, ctx: Any) -> ToolResult:
    from nexa.desktop.admin import relaunch_as_admin
    r = relaunch_as_admin()
    if r.ok and r.data.get("relaunched"):
        quit_fn = ctx.services.hooks.get("quit")
        if quit_fn is not None:
            import threading
            threading.Timer(1.5, quit_fn).start()
    return r


def h_admin_shell(args: dict, ctx: Any) -> ToolResult:
    from nexa.desktop.admin import open_admin_shell
    return open_admin_shell(args.get("kind") or "powershell")


def h_admin_tool(args: dict, ctx: Any) -> ToolResult:
    from nexa.desktop.admin import open_admin_tool
    return open_admin_tool(args["name"])


def h_top_processes(args: dict, ctx: Any) -> ToolResult:
    from nexa.desktop.admin import top_processes
    return top_processes(int(args.get("count") or 5), by=args.get("by") or "both")


def h_end_process(args: dict, ctx: Any) -> ToolResult:
    from nexa.desktop.admin import end_process
    return end_process(args["name"], bool(args.get("force")), wm=ctx.services.wm)


def h_disk_usage(args: dict, ctx: Any) -> ToolResult:
    from nexa.desktop.admin import disk_usage
    return disk_usage()


def h_network_info(args: dict, ctx: Any) -> ToolResult:
    from nexa.desktop.admin import network_info
    return network_info()


def h_type_text(args: dict, ctx: Any) -> ToolResult:
    hwnd, err = _focus_target(args, ctx)
    if err:
        return err
    _emit_window(ctx, hwnd, "Đang gõ…")
    text = args["text"]
    if len(text) > 600 and "\n" not in text:
        return ctx.services.input.paste_text(text, hwnd)
    return ctx.services.input.type_text(text, hwnd, cancelled=lambda: ctx.token.cancelled)


def h_press_keys(args: dict, ctx: Any) -> ToolResult:
    hwnd, err = _focus_target(args, ctx)
    if err:
        return err
    return ctx.services.input.hotkey(args["keys"], hwnd)


UI_RECT_TTL_S = 90.0


def _point_in_recent_controls(ctx: Any, x: int, y: int) -> bool:
    import time as _time
    now = _time.monotonic()
    for rect, ts in ctx.services.memory.get("ui_rects", []):
        if now - ts <= UI_RECT_TTL_S and rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]:
            return True
    return False


def h_mouse_click(args: dict, ctx: Any) -> ToolResult:
    x, y = args.get("x"), args.get("y")
    if ctx.source == Source.AI and x is not None and y is not None and not _point_in_recent_controls(ctx, x, y):
        # Gemini không nhìn thấy màn hình: không cho nhấp vào tọa độ tự đoán.
        return ToolResult.failure(
            "Không nhấp: tọa độ này không thuộc control nào NEXA vừa đọc được, nên em không biết ở đó có gì. "
            "Hãy dùng list_ui_controls rồi click_ui_control theo tên, hoặc play_youtube để mở video.",
            "unverified_coordinates")
    r = ctx.services.input.click(args.get("button", "left"), x, y, double=bool(args.get("double")))
    if r.ok:
        ctx.services.emit("click", x=r.data.get("x"), y=r.data.get("y"))
    return r


def h_mouse_move(args: dict, ctx: Any) -> ToolResult:
    if "x" in args and "y" in args:
        return ctx.services.input.move(args["x"], args["y"])
    cx, cy = ctx.services.input.cursor()
    dist = int(args.get("distance", 100))
    dx, dy = {"left": (-dist, 0), "right": (dist, 0), "up": (0, -dist), "down": (0, dist)}.get(args.get("direction", ""), (0, 0))
    return ctx.services.input.move(cx + dx, cy + dy)


def h_mouse_drag(args: dict, ctx: Any) -> ToolResult:
    return ctx.services.input.drag(args["x1"], args["y1"], args["x2"], args["y2"], cancelled=lambda: ctx.token.cancelled)


def h_scroll(args: dict, ctx: Any) -> ToolResult:
    if args.get("use_gesture_snapshot"):
        ok, reason = ctx.services.wm.verify_snapshot(ctx.snapshot)
        if not ok:
            return ToolResult.failure(reason, "target_changed")
    notches = int(args.get("notches", 3))
    return ctx.services.input.scroll(notches if args.get("direction", "up") == "up" else -notches)


def h_set_volume(args: dict, ctx: Any) -> ToolResult:
    return ctx.services.volume.set(args["percent"])


def h_change_volume(args: dict, ctx: Any) -> ToolResult:
    return ctx.services.volume.change(args["delta"])


def h_mute(args: dict, ctx: Any) -> ToolResult:
    return ctx.services.volume.mute(bool(args["on"]))


def h_screenshot(args: dict, ctx: Any) -> ToolResult:
    rect = None
    if args.get("scope") == "active_monitor":
        hwnd, _ = ctx.services.wm.resolve_work_window()
        monitors = ctx.services.monitors.refresh()
        mon = ctx.services.monitors.monitor_of_window(hwnd, monitors) if hwnd else ctx.services.monitors.primary(monitors)
        rect = mon.rect if mon else None
    r = ctx.services.shots.capture(rect)
    if r.ok:
        ctx.services.emit("toast", text="Đã chụp màn hình")
    return r


def h_time(args: dict, ctx: Any) -> ToolResult:
    from nexa.desktop.system import now_text
    return ToolResult.success(now_text(args.get("part") or "both"), verified=True)


def h_sysinfo(args: dict, ctx: Any) -> ToolResult:
    from nexa.desktop.system import system_info
    return system_info()


def h_find_files(args: dict, ctx: Any) -> ToolResult:
    return ctx.services.files.find(args["name"], args.get("folder"), cancelled=lambda: ctx.token.cancelled)


def h_open_path(args: dict, ctx: Any) -> ToolResult:
    return ctx.services.files.open(args["path"])


def h_open_named(args: dict, ctx: Any) -> ToolResult:
    return ctx.services.files.open_by_name(args["name"], args.get("kind") or "any", args.get("folder"),
                                           cancelled=lambda: ctx.token.cancelled, app=args.get("app") or "default")


def h_create_folder(args: dict, ctx: Any) -> ToolResult:
    return ctx.services.files.create_folder(args.get("parent"), args["name"])


def h_rename(args: dict, ctx: Any) -> ToolResult:
    return ctx.services.files.rename(args["path"], args["new_name"])


def h_copy(args: dict, ctx: Any) -> ToolResult:
    return ctx.services.files.copy(args["path"], args["dest_folder"], bool(args.get("overwrite")))


def h_move(args: dict, ctx: Any) -> ToolResult:
    return ctx.services.files.move(args["path"], args["dest_folder"], bool(args.get("overwrite")))


def h_delete(args: dict, ctx: Any) -> ToolResult:
    return ctx.services.files.delete_to_recycle_bin(args["path"])


def h_youtube_pause(args: dict, ctx: Any) -> ToolResult:
    r = ctx.services.media.pause()
    ctx.services.emit("media", state="paused" if r.ok and r.data.get("state") == "paused" else "error", text=r.message)
    return r


def h_youtube_resume(args: dict, ctx: Any) -> ToolResult:
    r = ctx.services.media.resume()
    ctx.services.emit("media", state="playing" if r.ok and r.data.get("state") == "playing" else "error", text=r.message)
    return r


def h_gesture_mode(args: dict, ctx: Any) -> ToolResult:
    fn = ctx.services.hooks.get("set_gesture_mode")
    if fn is None:
        return ToolResult.failure("Chế độ cử chỉ không khả dụng.", "unavailable")
    return fn(bool(args["enabled"]))


def h_air_mouse(args: dict, ctx: Any) -> ToolResult:
    fn = ctx.services.hooks.get("set_air_mouse")
    if fn is None:
        return ToolResult.failure("Chuột bằng tay không khả dụng.", "unavailable")
    return fn(bool(args["enabled"]))


def h_presence_lock(args: dict, ctx: Any) -> ToolResult:
    fn = ctx.services.hooks.get("set_presence")
    if fn is None:
        return ToolResult.failure("Nhận biết có mặt không khả dụng.", "unavailable")
    return fn(bool(args["enabled"]))


def h_head_target(args: dict, ctx: Any) -> ToolResult:
    fn = ctx.services.hooks.get("set_head_target")
    if fn is None:
        return ToolResult.failure("Chọn màn hình theo hướng nhìn không khả dụng.", "unavailable")
    return fn(str(args.get("mode") or "commands"))


def h_calibrate_head(args: dict, ctx: Any) -> ToolResult:
    fn = ctx.services.hooks.get("calibrate_head")
    if fn is None:
        return ToolResult.failure("Hiệu chuẩn hướng nhìn không khả dụng.", "unavailable")
    return fn()


def h_list_controls(args: dict, ctx: Any) -> ToolResult:
    from nexa.desktop import uia
    hwnd, reason = _target_window(args, ctx)
    if not hwnd:
        return ToolResult.failure(reason, "no_target")
    r = uia.list_controls(hwnd, control_type=args.get("control_type"), contains=args.get("contains"))
    if r.ok:
        import time as _time
        now = _time.monotonic()
        ctx.services.memory["ui_rects"] = [(tuple(c["rect"]), now) for c in r.data.get("controls", []) if c.get("rect")]
    return r


def h_click_control(args: dict, ctx: Any) -> ToolResult:
    from nexa.desktop import uia
    hwnd, err = _focus_target(args, ctx)
    if err:
        return err
    r = uia.invoke_control(hwnd, args["name"], args.get("control_type"), args.get("automation_id"),
                           window_rect=ctx.services.wm.api.get_rect(hwnd), index=args.get("index"))
    if r.ok and r.data.get("x") is not None:
        ctx.services.emit("click", x=r.data["x"], y=r.data["y"])
    return r


def h_power(args: dict, ctx: Any) -> ToolResult:
    from nexa.desktop.system import power_action
    if args["action"] == "sleep":
        # Ngủ canh gác: chỉ tắt màn hình để NEXA còn nghe tiếng vỗ tay (ngủ thật thì NEXA bị đóng băng).
        guard = ctx.services.hooks.get("guard_sleep")
        result = guard() if guard else None
        if result is not None:
            return result
    return power_action(args["action"])


def h_wait(args: dict, ctx: Any) -> ToolResult:
    secs = float(args.get("seconds", 1))
    if ctx.token.wait(secs):
        return ToolResult.failure("Đã hủy trong lúc chờ.", "cancelled")
    return ToolResult.success(f"Đã chờ {secs:g} giây.", verified=True)


def precheck_screen(args: dict, ctx: Any) -> ToolResult | None:
    """Chạy trước mọi bước chụp: tính năng tắt thì không chụp, không xem trước, không gửi."""
    if not ctx.services.config.cloud_screen_vision:
        return ToolResult.failure("Tính năng đọc màn hình bằng Gemini đang tắt. Anh bật trong Cài đặt > AI "
                                  "(NEXA_CLOUD_SCREEN_VISION) nếu muốn dùng.", "vision_disabled")
    if ctx.services.vision is None or not ctx.services.vision.available():
        return ToolResult.failure("Gemini chưa sẵn sàng nên chưa đọc màn hình được.", "ai_unavailable")
    return None


def preview_screen(args: dict, ctx: Any) -> dict:
    """Chụp vùng cần gửi TRƯỚC khi hỏi xác nhận để người dùng xem trước/cắt vùng."""
    services = ctx.services
    scope = args.get("scope", "active_window")
    rect = None
    if scope == "active_window":
        hwnd, _ = services.wm.resolve_work_window()
        if hwnd:
            rect = services.wm.api.get_rect(hwnd)
    if rect is None:
        monitors = services.monitors.refresh()
        hwnd, _ = services.wm.resolve_work_window()
        mon = services.monitors.monitor_of_window(hwnd, monitors) if hwnd else services.monitors.primary(monitors)
        rect = mon.rect if mon else (0, 0, 1280, 720)
    img = services.shots.grab_image(rect)
    fd, path = tempfile.mkstemp(prefix="nexa_screen_", suffix=".png")
    os.close(fd)
    img.save(path, "PNG")
    return {"image_path": path, "width": img.width, "height": img.height, "rect": list(rect)}


def h_describe_screen(args: dict, ctx: Any) -> ToolResult:
    services = ctx.services
    if not services.config.cloud_screen_vision:
        return ToolResult.failure("Tính năng đọc màn hình bằng Gemini đang tắt (NEXA_CLOUD_SCREEN_VISION=false).",
                                  "vision_disabled")
    path = ctx.extra.get("image_path")
    if not path or not Path(path).exists():
        return ToolResult.failure("Không có ảnh đã được anh duyệt để gửi.", "no_image")
    try:
        return services.vision.describe(path, args.get("question") or "Mô tả ngắn gọn nội dung màn hình này.",
                                        crop=ctx.extra.get("crop"), token=ctx.token)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _describe_screen_text(args: dict, ctx: Any, a: Assessment) -> str:
    return ("Gửi ảnh chụp " + ("cửa sổ đang làm việc" if args.get("scope", "active_window") == "active_window"
                                 else "màn hình") +
            " lên Gemini (dịch vụ đám mây của Google) để trả lời: “" + truncate(args.get("question", ""), 120) +
            "”. Anh xem trước, kéo chọn vùng cần gửi (tránh vùng có mật khẩu/key) rồi bấm Đồng ý.")


# ------------------------------------------------------------------ đăng ký
def build_registry(config: Any) -> ToolRegistry:
    reg = ToolRegistry()
    W = S_STR("Một phần tiêu đề hoặc tên ứng dụng của cửa sổ đích; bỏ trống = cửa sổ đang làm việc", 120)
    G = S_BOOL("Nội bộ: dùng cửa sổ chụp lúc bắt đầu cử chỉ")
    add = reg.register

    add(ToolSpec("open_app", "Mở ứng dụng", "Mở một ứng dụng đã cài (trình duyệt, Notepad, File Explorer, Calculator, "
                 "Paint, ứng dụng người dùng thêm, hoặc lối tắt Start Menu) theo tên.",
                 obj({"name": S_STR("Tên ứng dụng, ví dụ 'Notepad', 'trình duyệt', 'File Explorer'", 80, minLength=1)},
                     ["name"]), h_open_app))
    add(ToolSpec("open_url", "Mở trang web", "Mở một URL http/https trong trình duyệt mặc định.",
                 obj({"url": S_STR("URL http(s)", 2000, minLength=3)}, ["url"]), h_open_url))
    add(ToolSpec("web_search", "Tìm trên web", "Tìm kiếm web bằng trình duyệt.",
                 obj({"query": S_STR("Từ khóa tìm kiếm", 300, minLength=1)}, ["query"]), h_web_search))
    from nexa.ai.site_search import SITES
    add(ToolSpec("site_search", "Tìm trong trang",
                 "Tìm kiếm hoặc hỏi NGAY TRONG một trang/dịch vụ cụ thể (ChatGPT, YouTube, Facebook, Shopee…) bằng địa chỉ "
                 "tìm kiếm chính thức của trang đó. Dùng khi anh nói 'tìm trong/trên <trang>' hoặc 'hỏi ChatGPT…'; "
                 "không dùng Google thay thế.",
                 obj({"site": {"type": "string", "enum": [x.key for x in SITES]},
                      "query": S_STR("Nội dung cần tìm/hỏi", 500, minLength=1)}, ["site", "query"]),
                 h_site_search, needs_control=False))
    add(ToolSpec("play_youtube", "Mở video YouTube", "Tìm trên YouTube và mở thẳng video thứ `index` (mặc định video đầu "
                 "tiên). Dùng cho mọi yêu cầu mở/phát/xem video, bài hát, nhạc. Bỏ trống query = dùng từ khóa anh vừa tìm.",
                 obj({"query": S_STR("Từ khóa video/bài hát", 200), "index": S_INT("Thứ tự video, 1 = đầu tiên", 1, 10, default=1),
                      "next": S_BOOL("true = video kế tiếp của lần tìm gần nhất (đổi video, bài khác)")}),
                 h_play_youtube, needs_control=False))
    add(ToolSpec("list_windows", "Liệt kê cửa sổ", "Liệt kê các cửa sổ ứng dụng đang mở (tiêu đề, tiến trình).",
                 obj({}), h_list_windows, needs_control=False))
    add(ToolSpec("get_active_window", "Cửa sổ hiện tại", "Cho biết cửa sổ ứng dụng đang làm việc.",
                 obj({}), h_active_window, needs_control=False))
    add(ToolSpec("focus_window", "Chuyển cửa sổ", "Đưa một cửa sổ đang mở lên trước.",
                 obj({"window": S_STR("Một phần tiêu đề hoặc tên ứng dụng", 120, minLength=1)}, ["window"]), h_focus_window))
    add(ToolSpec("minimize_window", "Thu nhỏ cửa sổ", "Thu nhỏ cửa sổ xuống thanh tác vụ (như nút −).",
                 obj({"window": W, "use_gesture_snapshot": G}), h_minimize, internal_params={"use_gesture_snapshot"},
                 fingerprint_fn=_window_fp))
    add(ToolSpec("restore_last_minimized", "Khôi phục cửa sổ", "Khôi phục đúng cửa sổ NEXA vừa thu nhỏ gần nhất.",
                 obj({}), h_restore_last))
    add(ToolSpec("maximize_window", "Phóng to cửa sổ", "Phóng to cửa sổ.", obj({"window": W}), h_maximize,
                 fingerprint_fn=_window_fp))
    add(ToolSpec("move_window_to_monitor_2", "Chuyển sang màn hình 2",
                 "Chuyển cửa sổ đang làm việc từ màn hình nguồn sang màn hình đích (màn hình 2).",
                 obj({"window": W, "use_gesture_snapshot": G}), h_move_to_monitor_2,
                 internal_params={"use_gesture_snapshot"}, fingerprint_fn=_window_fp))
    add(ToolSpec("close_window", "Đóng cửa sổ", "Đóng cửa sổ theo cách thông thường (ứng dụng có thể hỏi lưu).",
                 obj({"window": W}), h_close_window,
                 risk=lambda a, c: Assessment(Risk.HIGH, "Nội dung chưa lưu có thể bị mất nếu ứng dụng không hỏi lưu."),
                 fingerprint_fn=_window_fp))
    add(ToolSpec("close_named", "Đóng ứng dụng/tab", "Đóng theo TÊN: tab trình duyệt (ChatGPT, YouTube…) hoặc cửa sổ "
                 "ứng dụng (VS Code, Zalo…). Đóng thông thường — ứng dụng vẫn có thể hỏi lưu.",
                 obj({"name": S_STR("Tên ứng dụng hoặc tiêu đề tab", 120, minLength=1),
                      "kind": {"type": "string", "enum": ["any", "tab", "app"], "default": "any"}}, ["name"]),
                 h_close_named,
                 risk=lambda a, c: Assessment(Risk.HIGH, "Nội dung chưa lưu có thể bị mất nếu ứng dụng không hỏi lưu.")))
    add(ToolSpec("new_document", "Tạo tài liệu mới",
                 "Tạo tài liệu Word/Excel/PowerPoint MỚI (qua Office COM). Có 'name' thì lưu luôn vào thư mục Tài liệu.",
                 obj({"kind": {"type": "string", "enum": ["word", "excel", "powerpoint"]},
                      "name": S_STR("Tên tệp, bỏ trống = tài liệu chưa lưu", 120),
                      "folder": S_STR("Thư mục lưu (tùy chọn)", 200)}, ["kind"]), h_new_document,
                 needs_control=False))
    add(ToolSpec("vscode_new_file", "File mới trong VS Code",
                 "Tạo file mới trong VS Code. Có 'name' thì tạo tệp thật rồi mở; không tên thì Ctrl+N trong VS Code.",
                 obj({"name": S_STR("Tên tệp, ví dụ main.py", 120), "folder": S_STR("Thư mục (tùy chọn)", 200)}),
                 h_vscode_new_file))
    add(ToolSpec("skip_youtube_ad", "Bỏ qua quảng cáo YouTube",
                 "Bấm nút 'Bỏ qua' của quảng cáo trên video YouTube đang xem; chờ tới khi nút hiện ra.",
                 obj({"wait_s": S_INT("Số giây chờ tối đa", 1, 60, default=12)}), h_skip_youtube_ad,
                 needs_control=False))
    add(ToolSpec("auto_skip_ads", "Tự bỏ qua quảng cáo",
                 "Bật/tắt chế độ tự động bấm 'Bỏ qua' mỗi khi YouTube hiện quảng cáo.",
                 obj({"enabled": S_BOOL("true = bật")}, ["enabled"]), h_auto_skip_ads, needs_control=False))
    add(ToolSpec("check_zalo", "Kiểm tra Zalo",
                 "Xem có ai nhắn tin Zalo chưa đọc không. CHỈ trả về TÊN người/nhóm và số tin — không đọc nội dung.",
                 obj({}), h_check_zalo, needs_control=False, allowed_when_paused=True))
    add(ToolSpec("admin_status", "Quyền quản trị", "NEXA có đang chạy quyền Administrator không.", obj({}),
                 h_admin_status, needs_control=False, allowed_when_paused=True))
    add(ToolSpec("request_admin", "Xin quyền quản trị",
                 "Khởi động lại NEXA với quyền Administrator (Windows sẽ hỏi anh xác nhận qua hộp thoại UAC).",
                 obj({}), h_request_admin, needs_control=False, always_confirm=True,
                 risk=lambda a, c: Assessment(Risk.HIGH, "NEXA sẽ tắt và mở lại với toàn quyền trên máy.")))
    add(ToolSpec("admin_shell", "Mở PowerShell quyền quản trị",
                 "Mở cửa sổ PowerShell/CMD với quyền Administrator (Windows hỏi xác nhận). NEXA không tự gõ lệnh vào đó.",
                 obj({"kind": {"type": "string", "enum": ["powershell", "cmd", "terminal"], "default": "powershell"}}),
                 h_admin_shell, needs_control=False, always_confirm=True,
                 risk=lambda a, c: Assessment(Risk.HIGH, "Cửa sổ dòng lệnh toàn quyền trên máy.")))
    add(ToolSpec("open_admin_tool", "Mở công cụ quản trị",
                 "Mở công cụ quản trị Windows: Task Manager, Device Manager, Services, Event Viewer, Disk Management, "
                 "Registry Editor, Control Panel, Firewall, Windows Update…",
                 obj({"name": S_STR("Tên công cụ", 60, minLength=1)}, ["name"]), h_admin_tool, needs_control=False))
    add(ToolSpec("top_processes", "Ứng dụng ngốn máy", "Ứng dụng đang dùng nhiều CPU và RAM nhất.",
                 obj({"count": S_INT("Số ứng dụng", 1, 10, default=5),
                      "by": {"type": "string", "enum": ["cpu", "ram", "both"], "default": "both"}}),
                 h_top_processes, needs_control=False, allowed_when_paused=True))
    add(ToolSpec("end_process", "Tắt ứng dụng treo",
                 "Đóng tiến trình theo tên. Mặc định đóng lịch sự; force=true thì buộc dừng (mất dữ liệu chưa lưu). "
                 "Tiến trình hệ thống thiết yếu luôn bị từ chối.",
                 obj({"name": S_STR("Tên ứng dụng/tiến trình", 60, minLength=2),
                      "force": S_BOOL("true = buộc dừng")}, ["name"]), h_end_process, needs_control=False,
                 risk=lambda a, c: Assessment(Risk.HIGH if a.get("force") else Risk.MEDIUM,
                                              "Buộc dừng sẽ mất dữ liệu chưa lưu." if a.get("force")
                                              else "Ứng dụng sẽ đóng lại.")))
    add(ToolSpec("disk_usage", "Dung lượng ổ đĩa", "Dung lượng trống/tổng của các ổ đĩa.", obj({}), h_disk_usage,
                 needs_control=False, allowed_when_paused=True))
    add(ToolSpec("network_info", "Thông tin mạng", "Wi-Fi đang kết nối, địa chỉ IP và có vào được Internet không.",
                 obj({}), h_network_info, needs_control=False, allowed_when_paused=True))
    add(ToolSpec("type_text", "Gõ nội dung", "Gõ văn bản Unicode (tiếng Việt có dấu) vào cửa sổ đích. Chỉ soạn bản "
                 "nháp; không tự gửi/đăng.",
                 obj({"text": S_STR("Nội dung cần gõ", 8000, minLength=1), "window": W}, ["text"]), h_type_text,
                 risk=risk_type_text, fingerprint_fn=_window_fp))
    add(ToolSpec("press_keys", "Bấm phím", "Bấm một phím hoặc tổ hợp phím, ví dụ ['ctrl','c'], ['ctrl','a'], ['enter'].",
                 obj({"keys": {"type": "array", "items": S_STR("Tên phím", 20, minLength=1), "minItems": 1, "maxItems": 4},
                      "window": W}, ["keys"]), h_press_keys, risk=risk_press_keys, fingerprint_fn=_window_fp))
    add(ToolSpec("mouse_click", "Nhấp chuột", "Nhấp chuột tại vị trí hiện tại hoặc tọa độ màn hình (pixel vật lý). "
                 "Ưu tiên click_ui_control; chỉ dùng tọa độ khi không có control.",
                 obj({"x": S_INT("Tọa độ x", -20000, 20000), "y": S_INT("Tọa độ y", -20000, 20000),
                      "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                      "double": S_BOOL("Nhấp đúp", default=False)}), h_mouse_click, risk=risk_mouse))
    add(ToolSpec("mouse_move", "Di chuyển chuột", "Di chuột tới tọa độ hoặc theo hướng.",
                 obj({"x": S_INT("x", -20000, 20000), "y": S_INT("y", -20000, 20000),
                      "direction": {"type": "string", "enum": ["left", "right", "up", "down"]},
                      "distance": S_INT("Khoảng cách pixel", 1, 2000, default=100)}), h_mouse_move))
    add(ToolSpec("mouse_drag", "Kéo thả", "Kéo thả chuột trái từ (x1,y1) tới (x2,y2).",
                 obj({k: S_INT(k, -20000, 20000) for k in ("x1", "y1", "x2", "y2")}, ["x1", "y1", "x2", "y2"]),
                 h_mouse_drag, risk=lambda a, c: Assessment(Risk.MEDIUM, "Kéo thả theo tọa độ.")))
    add(ToolSpec("scroll", "Cuộn trang", "Cuộn cửa sổ dưới con trỏ chuột lên hoặc xuống.",
                 obj({"direction": {"type": "string", "enum": ["up", "down"], "default": "up"},
                      "notches": S_INT("Số nấc cuộn", 1, 30, default=3), "use_gesture_snapshot": G}),
                 h_scroll, internal_params={"use_gesture_snapshot"}))
    add(ToolSpec("set_volume", "Đặt âm lượng", "Đặt âm lượng loa mặc định theo phần trăm.",
                 obj({"percent": S_INT("0–100", 0, 100)}, ["percent"]), h_set_volume, needs_control=False))
    add(ToolSpec("change_volume", "Tăng/giảm âm lượng", "Tăng (dương) hoặc giảm (âm) âm lượng theo điểm phần trăm.",
                 obj({"delta": S_INT("-100..100", -100, 100)}, ["delta"]), h_change_volume, needs_control=False))
    add(ToolSpec("mute", "Tắt/bật tiếng", "Tắt tiếng (on=true) hoặc bật tiếng loa.",
                 obj({"on": S_BOOL("true = tắt tiếng")}, ["on"]), h_mute, needs_control=False))
    add(ToolSpec("take_screenshot", "Chụp màn hình", "Chụp màn hình và lưu vào thư mục ảnh đã cấu hình (không gửi đi đâu).",
                 obj({"scope": {"type": "string", "enum": ["all", "active_monitor"], "default": "all"}}), h_screenshot,
                 needs_control=False))
    add(ToolSpec("get_time", "Xem giờ", "Thời gian và ngày hiện tại.",
                 obj({"part": {"type": "string", "enum": ["time", "date", "both"], "default": "both"}}), h_time,
                 needs_control=False,
                 allowed_when_paused=True))
    add(ToolSpec("get_system_info", "Thông tin máy", "CPU, RAM, pin thực tế.", obj({}), h_sysinfo,
                 needs_control=False, allowed_when_paused=True))
    add(ToolSpec("find_files", "Tìm tệp", "Tìm tệp/thư mục theo tên trong các thư mục được phép (hiểu cả tên bị "
                 "nghe sai như 'main.by' = main.py; kết quả xếp theo độ khớp). Muốn MỞ tệp thì dùng open_named.",
                 obj({"name": S_STR("Một phần tên tệp", 120, minLength=1),
                      "folder": S_STR("Thư mục tìm (desktop, tài liệu, tải về, ảnh hoặc đường dẫn)", 400)}, ["name"]),
                 h_find_files, needs_control=False))
    add(ToolSpec("open_path", "Mở tệp/thư mục", "Mở tệp hoặc thư mục trong phạm vi được phép.",
                 obj({"path": S_STR("Đường dẫn", 500, minLength=1)}, ["path"]), h_open_path, risk=risk_open_path,
                 fingerprint_fn=_path_fp))
    add(ToolSpec("open_named", "Mở tệp/thư mục theo tên",
                 "Tìm tệp hoặc thư mục theo TÊN (không cần đường dẫn) trong các thư mục được phép rồi mở; "
                 "nếu nhiều kết quả thì trả về danh sách để hỏi lại. Tên có thể đưa nguyên như anh nói (kể cả bị nghe "
                 "sai kiểu 'main.by', 'men chấm bay', 'read.md') — công cụ tự hiểu và so khớp gần đúng. "
                 "'mở file X trong VS Code' → app='vscode' (KHÔNG đặt folder='VS Code').",
                 obj({"name": S_STR("Tên (một phần) của tệp/thư mục"),
                      "kind": {"type": "string", "enum": ["file", "folder", "any"], "default": "any"},
                      "folder": S_STR("Chỉ tìm trong thư mục này (tùy chọn)"),
                      "app": {"type": "string", "enum": ["default", "vscode"], "default": "default",
                              "description": "Mở bằng ứng dụng mặc định hay VS Code"}}, ["name"]),
                 h_open_named, needs_control=False))
    add(ToolSpec("create_folder", "Tạo thư mục", "Tạo thư mục mới (không ghi đè).",
                 obj({"name": S_STR("Tên thư mục", 200, minLength=1), "parent": S_STR("Thư mục cha", 400)}, ["name"]),
                 h_create_folder, needs_control=False))
    add(ToolSpec("rename_path", "Đổi tên", "Đổi tên tệp/thư mục (không ghi đè).",
                 obj({"path": S_STR("Đường dẫn", 500, minLength=1), "new_name": S_STR("Tên mới", 200, minLength=1)},
                     ["path", "new_name"]), h_rename, risk=Risk.MEDIUM, fingerprint_fn=_path_fp, needs_control=False))
    add(ToolSpec("copy_path", "Sao chép tệp", "Sao chép tệp/thư mục vào thư mục đích.",
                 obj({"path": S_STR("Nguồn", 500, minLength=1), "dest_folder": S_STR("Thư mục đích", 500, minLength=1),
                      "overwrite": S_BOOL("Ghi đè nếu trùng", default=False)}, ["path", "dest_folder"]), h_copy,
                 risk=risk_transfer(False), fingerprint_fn=_path_fp, needs_control=False))
    add(ToolSpec("move_path", "Di chuyển tệp", "Di chuyển tệp/thư mục vào thư mục đích.",
                 obj({"path": S_STR("Nguồn", 500, minLength=1), "dest_folder": S_STR("Thư mục đích", 500, minLength=1),
                      "overwrite": S_BOOL("Ghi đè nếu trùng", default=False)}, ["path", "dest_folder"]), h_move,
                 risk=risk_transfer(True), fingerprint_fn=_path_fp, needs_control=False))
    add(ToolSpec("delete_to_recycle_bin", "Xóa vào Thùng rác", "Chuyển tệp/thư mục vào Recycle Bin (không xóa vĩnh viễn).",
                 obj({"path": S_STR("Đường dẫn", 500, minLength=1)}, ["path"]), h_delete,
                 risk=lambda a, c: Assessment(Risk.HIGH, "Tệp sẽ được chuyển vào Thùng rác."),
                 fingerprint_fn=_path_fp, needs_control=False))
    add(ToolSpec("youtube_pause", "Tạm dừng YouTube", "Tạm dừng video YouTube đã gắn (không đảo trạng thái).",
                 obj({}), h_youtube_pause, needs_control=False))
    add(ToolSpec("youtube_resume", "Phát tiếp YouTube", "Phát tiếp video YouTube mà NEXA vừa tạm dừng.",
                 obj({}), h_youtube_resume, needs_control=False))
    add(ToolSpec("set_gesture_mode", "Điều khiển bằng tay", "Bật/tắt chế độ cử chỉ tay (camera).",
                 obj({"enabled": S_BOOL("true = bật")}, ["enabled"]), h_gesture_mode, needs_control=False))
    add(ToolSpec("set_air_mouse", "Chuột bằng tay", "Bật/tắt chuột bằng tay qua camera (di con trỏ theo tay, chụm ngón "
                 "để click/kéo thả). Chỉ gọi khi anh Sơn yêu cầu rõ ràng.",
                 obj({"enabled": S_BOOL("true = bật")}, ["enabled"]), h_air_mouse, needs_control=False))
    add(ToolSpec("set_presence_lock", "Tự khóa khi rời máy", "Bật/tắt nhận biết anh Sơn có ngồi ở máy qua webcam (chạy "
                 "cục bộ): rời máy thì dừng video và khóa Windows, có người nhìn từ phía sau thì thu nhỏ cửa sổ nhạy cảm.",
                 obj({"enabled": S_BOOL("true = bật")}, ["enabled"]), h_presence_lock, needs_control=False))
    add(ToolSpec("set_head_target", "Chọn màn hình theo hướng nhìn", "Chọn màn hình theo hướng quay đầu (webcam): "
                 "off = tắt, commands = lệnh giọng nói/cử chỉ tác động lên màn hình đang nhìn, auto = focus tự theo "
                 "hướng nhìn.", obj({"mode": {"type": "string", "enum": ["off", "commands", "auto"]}}, ["mode"]),
                 h_head_target, needs_control=False))
    add(ToolSpec("calibrate_head", "Hiệu chuẩn hướng nhìn", "Hiệu chuẩn hướng quay đầu cho từng màn hình (anh nhìn "
                 "vào giữa từng màn hình khi khung sáng lên).", obj({}), h_calibrate_head, needs_control=False))
    add(ToolSpec("list_ui_controls", "Đọc giao diện", "Liệt kê nút/liên kết/ô nhập có tên đang hiển thị trong cửa sổ đích "
                 "(UI Automation), theo thứ tự đọc từ trên xuống, kèm tọa độ thật. Gọi trước khi bấm nếu chưa biết tên control.",
                 obj({"window": W, "control_type": {"type": "string", "enum": ["Button", "Hyperlink", "MenuItem", "TabItem",
                                                                                 "ListItem", "Edit", "CheckBox", "ComboBox"]},
                      "contains": S_STR("Chỉ lấy control có tên chứa chuỗi này", 80)}), h_list_controls, needs_control=False))
    add(ToolSpec("click_ui_control", "Bấm control", "Kích hoạt một nút/mục theo tên bằng UI Automation "
                 "(ưu tiên hơn nhấp tọa độ).",
                 obj({"name": S_STR("Tên control như hiển thị", 120, minLength=1),
                      "control_type": {"type": "string", "enum": ["Button", "MenuItem", "Hyperlink", "CheckBox",
                                                                  "RadioButton", "TabItem", "ListItem", "TreeItem",
                                                                  "ComboBox", "Edit", "SplitButton"]},
                      "automation_id": S_STR("AutomationId nếu biết", 120),
                      "index": S_INT("Nếu nhiều control khớp: chọn cái thứ mấy theo thứ tự đọc (1 = đầu tiên)", 1, 50),
                      "window": W}, ["name"]),
                 h_click_control, risk=risk_click_control, fingerprint_fn=_window_fp))
    add(ToolSpec("system_power", "Nguồn máy", "Khóa máy, ngủ (khi bật ngủ canh gác: chỉ tắt màn hình, vỗ tay để bật lại), "
                 "tắt máy/khởi động lại (hẹn 60 giây), hủy lịch tắt.",
                 obj({"action": {"type": "string", "enum": ["lock", "sleep", "shutdown", "restart", "cancel_shutdown"]}},
                     ["action"]), h_power, risk=risk_power, needs_control=False))
    add(ToolSpec("wait", "Chờ", "Chờ vài giây (ví dụ đợi trang web tải).",
                 obj({"seconds": {"type": "number", "minimum": 0.2, "maximum": 10}}, ["seconds"]), h_wait,
                 needs_control=False))
    add(ToolSpec("describe_screen", "Đọc màn hình", "Chụp cửa sổ/màn hình được chọn, cho người dùng xem trước và cắt "
                 "vùng, rồi nhờ Gemini mô tả/tóm tắt. Chỉ dùng khi người dùng yêu cầu xem màn hình.",
                 obj({"question": S_STR("Câu hỏi về nội dung màn hình", 400, minLength=1),
                      "scope": {"type": "string", "enum": ["active_window", "monitor"], "default": "active_window"}},
                     ["question"]), h_describe_screen,
                 risk=lambda a, c: Assessment(Risk.HIGH, "Ảnh sẽ được gửi lên dịch vụ đám mây."),
                 describe_fn=_describe_screen_text, preview=preview_screen, precheck=precheck_screen,
                 needs_control=False, always_confirm=True,
                 ai_enabled=lambda: bool(config.cloud_screen_vision)))
    from nexa.three_d.tools import register_3d_tools
    register_3d_tools(reg, config)
    from nexa.code.tools import register_code_tools
    register_code_tools(reg, config)
    from nexa.desktop.routines import register_routine_tools
    register_routine_tools(reg, config)
    from nexa.ai.ui_commands import register_ui_tools
    register_ui_tools(reg, config)
    return reg
