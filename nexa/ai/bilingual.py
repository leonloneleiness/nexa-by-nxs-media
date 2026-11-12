"""Deterministic English commands; translate command structure, never user payloads.

The explicit command form exposes the registry's public schemas in both languages.
It still returns ordinary tool calls, so validation/confirmation/cancellation stay in
Executor. No eval, dynamic method lookup from user text, or AI dependency.
"""
from __future__ import annotations

import json
import re

from nexa.utils.text import strip_accents


def folded(text: str) -> str:
    return strip_accents(text.lower()).strip()


EXACT = {
    "pause": "tạm dừng video", "resume": "phát tiếp video",
    "reset view": "đặt lại góc nhìn",
    "zoom cai nay len": "phóng to cái này", "zoom in this": "phóng to cái này",
    "zoom this in": "phóng to cái này", "zoom in cai nay": "phóng to cái này",
    "rotate sang trai": "xoay mô hình trái", "rotate sang phai": "xoay mô hình phải",
    "rotate left": "xoay mô hình trái", "rotate right": "xoay mô hình phải",
    "emergency stop": "dừng khẩn cấp", "stop everything": "dừng khẩn cấp",
    "cancel": "hủy", "cancel task": "hủy", "cancel command": "hủy",
    "confirm": "xác nhận", "approve": "đồng ý", "deny": "từ chối",
    "do not proceed": "từ chối", "reject": "từ chối",
    "go to standby": "về chế độ chờ", "standby": "về chế độ chờ",
    "go to sleep": "nghỉ đi", "clear conversation": "xóa hội thoại",
    "clear chat history": "xóa hội thoại", "enable companion mode": "bật tâm sự",
    "disable companion mode": "tắt tâm sự", "exit companion mode": "tắt tâm sự",
    "take a screenshot": "chụp màn hình", "take screenshot": "chụp màn hình",
    "screenshot": "chụp màn hình", "what time is it": "mấy giờ rồi",
    "what is the date today": "hôm nay ngày bao nhiêu", "system information": "xem thông tin hệ thống",
    "show system information": "xem thông tin hệ thống", "mute": "tắt tiếng", "unmute": "bật tiếng",
    "pause video": "tạm dừng video", "resume video": "phát tiếp video",
    "pause youtube": "tạm dừng video", "resume youtube": "phát tiếp video",
    "next video": "video tiếp theo", "skip ad": "bỏ qua quảng cáo",
    "minimize window": "thu nhỏ cửa sổ", "minimize the window": "thu nhỏ cửa sổ",
    "maximize window": "phóng to cửa sổ", "restore window": "khôi phục cửa sổ",
    "close window": "đóng cửa sổ", "move window to monitor 2": "chuyển sang màn hình 2",
    "new tab": "mở tab mới", "close tab": "đóng tab", "refresh page": "tải lại trang",
    "lock computer": "khóa máy", "sleep computer": "cho máy ngủ",
    "shut down computer": "tắt máy", "restart computer": "khởi động lại máy",
    "cancel shutdown": "hủy tắt máy", "open code panel": "mở bảng sinh code",
    "close code panel": "đóng bảng sinh code", "code status": "tiến độ sinh code",
    "cancel code generation": "hủy sinh code", "run code tests": "chạy thử code",
    "open 3d model": "mở mô hình 3d", "close 3d viewer": "đóng trình xem 3d",
    "list 3d models": "danh sách mô hình", "3d job status": "tiến độ tạo mô hình",
    "cancel 3d generation": "hủy tạo mô hình", "explode assembly": "tách mô hình",
    "collapse assembly": "lắp lại mô hình", "show all parts": "hiện tất cả bộ phận",
    "reset 3d view": "đặt lại góc nhìn", "start model animation": "bật chuyển động",
    "stop model animation": "tắt chuyển động", "zoom in model": "phóng to mô hình",
    "zoom out model": "thu nhỏ mô hình", "wireframe mode": "khung dây", "xray mode": "x-quang",
    "normal render mode": "bình thường", "calibrate head tracking": "hiệu chuẩn hướng nhìn",
    "list windows": "liệt kê cửa sổ", "show active window": "cửa sổ hiện tại",
    "check zalo": "kiểm tra zalo", "show disk usage": "dung lượng ổ đĩa",
    "show network information": "thông tin mạng", "run current file": "chạy file đang mở",
}


def english_command(text: str) -> str:
    """Translate anchored, known command grammar only; keep arbitrary tails intact."""
    text = re.sub(r"^(?:(?:please|can you|could you|would you|i want you to)\s+)+", "", text, flags=re.I)
    u = folded(text)
    if u in EXACT:
        return EXACT[u]
    m = re.fullmatch(r"(enable|disable|turn on|turn off) (gestures|gesture control|air mouse|presence lock|auto skip ads)", u)
    if m:
        on = m[1] in ("enable", "turn on")
        target = {"gestures": "cử chỉ", "gesture control": "cử chỉ", "air mouse": "chuột bằng tay",
                  "presence lock": "tự khóa máy", "auto skip ads": "tự bỏ qua quảng cáo"}[m[2]]
        return ("bật " if on else "tắt ") + target
    patterns = [
        (r"^(?:type text|type|dictate)(?::|\s)+(.*)$", lambda m: "gõ nội dung: " + m[1]),
        (r"^set (?:the )?volume(?: to)? (.+?)(?: percent|%)?$", lambda m: "đặt âm lượng " + number(m[1]) + " phần trăm"),
        (r"^(increase|decrease) volume(?: by)? (.+?)(?: percent|%)?$", lambda m: ("tăng" if m[1].lower() == "increase" else "giảm") + " âm lượng " + number(m[2]) + " phần trăm"),
        (r"^search (?:the web|google)(?: for)? (.+)$", lambda m: "tìm trên web " + m[1]),
        (r"^search (youtube|chatgpt|facebook|tiktok) for (.+)$", lambda m: "tìm trên " + m[1] + " " + m[2]),
        (r"^find (?:file|files) (.+?)(?: in (.+))?$", lambda m: "tìm tệp " + m[1] + (" trong " + m[2] if m[2] else "")),
        (r"^open (file|folder) (.+?)(?: in (.+))?$", lambda m: "mở " + ("tệp" if m[1].lower() == "file" else "thư mục") + " " + m[2] + (" trong " + m[3] if m[3] else "")),
        (r"^create (?:a |new )?folder (.+?)(?: in (.+))?$", lambda m: "tạo thư mục " + m[1] + (" trong " + m[2] if m[2] else "")),
        (r"^run (?:file )?(.+\.[\w]+)$", lambda m: "chạy file " + m[1]),
        (r"^create ((?:code|python|javascript|typescript|java|c\+\+|rust|sql|script|function)\b.*)$", lambda m: "generate " + m[1]),
        (r"^(?:play|watch) (?:video|music) (.+)$", lambda m: "mở video " + m[1]),
        (r"^create (?:a |new )?(word|excel|powerpoint) document(?: named (.+))?$", lambda m: "tạo tài liệu " + m[1] + (" tên " + m[2] if m[2] else " mới")),
        (r"^refine code (.+)$", lambda m: "sửa code " + m[1]),
        (r"^scroll (up|down)(?: (\d+)(?: notches)?)?$", lambda m: "cuộn " + ("lên" if m[1].lower() == "up" else "xuống") + (" " + m[2] + " nấc" if m[2] else "")),
        (r"^press (?:keys? )?(.+)$", lambda m: "bấm phím " + m[1]),
        (r"^(?:read|describe|summarize) (?:the )?screen(.*)$", lambda m: "đọc màn hình" + m[1]),
        (r"^rotate (?:the )?model (left|right|up|down)(?: (\d+) degrees)?$", lambda m: "xoay mô hình " + {"left":"trái", "right":"phải", "up":"lên", "down":"xuống"}[m[1].lower()] + (" " + m[2] + " độ" if m[2] else "")),
        (r"^(hide|isolate|focus) part (.+)$", lambda m: {"hide":"ẩn", "isolate":"tách riêng", "focus":"xem chi tiết"}[m[1].lower()] + " " + m[2]),
        (r"^open (.+)$", lambda m: "mở " + m[1]),
        (r"^close (.+)$", lambda m: "đóng " + m[1]),
    ]
    for pattern, convert in patterns:
        m = re.fullmatch(pattern, text, re.I)
        if m:
            return convert(m)
    return text


def ui_route(text: str):
    from nexa.ai.intent_router import Route
    from nexa.ai.tool_registry import validate_schema
    from nexa.ai.ui_commands import COMMANDS

    def basic(name, args=None):
        return Route("basic", [(name, args or {})])

    u = folded(text)
    if u in ("danh sach lenh", "list commands", "command help", "huong dan lenh"):
        return basic("list_commands")
    m = re.fullmatch(r"(?:dat cau hinh nexa|set nexa setting) ([\w.]+) (?:bang|to) (.+)", u)
    if m:
        value = text[m.start(2):m.end(2)]
        value = {"bat":"true", "tat":"false", "on":"true", "off":"false"}.get(folded(value), value)
        return basic("set_nexa_setting", {"key":m[1], "value":value, "scope":"settings"})
    panels = {"cai dat":"settings", "settings":"settings", "bang cu chi":"gestures", "gesture panel":"gestures",
              "lich su":"history", "history":"history", "edu":"edu", "hoc tap":"edu", "education":"edu",
              "khong gian 3d":"3d", "3d workspace":"3d", "thu vien 3d":"3d", "3d library":"3d",
              "ho so lap rap":"build", "build dossier":"build", "anh video san pham":"media", "product media":"media"}
    m = re.fullmatch(r"(mo|open|dong|close) (.+)", u)
    if m and m[2] in panels:
        return basic("navigate_nexa" if m[1] in ("mo", "open") else "close_nexa_panel", {"panel":panels[m[2]]})
    lessons = {"cau chiu tai":"bridge_load", "bridge load":"bridge_load", "con lac don":"pendulum", "pendulum":"pendulum",
               "mach dien":"circuit", "mach dien mot chieu":"circuit", "circuit":"circuit", "thang ph":"ph_scale", "ph scale":"ph_scale",
               "tam pin mat troi":"solar", "solar panel":"solar", "he mat troi":"solar_system", "solar system":"solar_system"}
    m = re.fullmatch(r"(?:chon bai hoc|mo bai hoc|select lesson|open lesson) (.+)", u)
    if m and m[1] in lessons:
        return basic("edu_select_lesson", {"lesson_id":lessons[m[1]]})
    m = re.fullmatch(r"(?:dat tham so bai hoc|set lesson parameter) (.+?) (?:bang|to) (-?\d+(?:[.,]\d+)?)", u)
    if m:
        from nexa.education.simulations import LESSONS
        aliases = {folded(p["label"]):p["id"] for lesson in LESSONS for p in lesson.parameters}
        return basic("edu_set_parameter", {"key":aliases.get(m[1], m[1]), "value":float(m[2].replace(",", "."))})
    m = re.fullmatch(r"(?:xuat mo hinh(?: 3d)?|export (?:3d )?model)(?: (?:dang|as))? (glb|stl|obj|3mf)", u)
    if m:
        return basic("export_3d_model", {"format":m[1]})
    m = re.fullmatch(r"(?:chay kich ban|run routine) (.+)", text, re.I)
    if not m:
        m = re.fullmatch(r"chạy kịch bản (.+)", text, re.I)
    if m:
        return basic("run_routine", {"name":m[1]})
    for cmd in sorted(COMMANDS, key=lambda c: max(len(c.vi), len(c.en)), reverse=True):
        for alias in (folded(cmd.vi), cmd.en):
            if u != alias and not u.startswith(alias + " ") and not u.startswith(alias + ":"):
                continue
            tail = text[len(alias):].lstrip(" :")
            required = [k for k, v in cmd.params.items() if "default" not in v]
            try:
                if tail.startswith("{"):
                    args = json.loads(tail)
                elif tail and len(required) == 1:
                    key = required[0]
                    typ = cmd.params[key]["type"]
                    val = tail
                    if typ == "boolean":
                        values = {"on":True,"off":False,"bat":True,"tat":False,"true":True,"false":False}
                        val = values[folded(tail)]
                    elif typ != "string":
                        val = json.loads(tail)
                    args = {key:val}
                elif not tail:
                    args = {}
                else:
                    raise ValueError("Cần tham số JSON / JSON arguments required")
                ok, error, args = validate_schema({"type":"object","properties":cmd.params,"required":required}, args)
                if not ok:
                    raise ValueError(error)
            except (ValueError, KeyError, TypeError) as exc:
                return Route("clarify", reply=f"{cmd.vi} / {cmd.en}: {exc}")
            return basic(cmd.name, args)
    return None


def public_alias_route(text: str, registry):
    """Recognize exact public command names, after the richer natural grammar."""
    if registry is None:
        return None
    u = folded(text)
    for name in registry.names():
        spec = registry.get(name)
        for alias in (folded(spec.title), name.replace("_", " ")):
            if u == alias or u.startswith(alias + " ") or u.startswith(alias + ":"):
                return catalog_route("command " + text, registry)
    return None


def number(text: str) -> str:
    words = {"zero":0, "one":1, "two":2, "three":3, "four":4, "five":5, "six":6, "seven":7,
             "eight":8, "nine":9, "ten":10, "eleven":11, "twelve":12, "thirteen":13, "fourteen":14,
             "fifteen":15, "sixteen":16, "seventeen":17, "eighteen":18, "nineteen":19,
             "twenty":20, "thirty":30, "forty":40, "fifty":50, "sixty":60, "seventy":70, "eighty":80, "ninety":90}
    tokens = text.lower().replace("-", " ").split()
    if tokens == ["one", "hundred"]:
        return "100"
    if len(tokens) == 1 and tokens[0] in words:
        return str(words[tokens[0]])
    if len(tokens) == 2 and words.get(tokens[0], 0) >= 20 and 0 < words.get(tokens[1], 0) < 10:
        return str(words[tokens[0]] + words[tokens[1]])
    return text


def catalog_route(text: str, registry):
    """Explicit escape hatch: 'command <English name>' / 'lệnh <Vietnamese title>'.

Single required arguments accept a plain spoken tail; complex arguments use JSON.
Invalid/unknown explicit commands must not fall through to AI or OS app launching.
"""
    from nexa.ai.intent_router import Route
    m = re.match(r"^(?:command|lenh)\s+", folded(text))
    if not m:
        return None
    if registry is None:
        return Route("clarify", reply="Danh mục lệnh chưa sẵn sàng / Command catalog unavailable.")
    body = text[m.end():].strip()
    names = []
    for name in registry.names():
        spec = registry.get(name)
        for alias in (spec.title, name.replace("_", " "), name):
            names.append((folded(alias), spec))
    for alias, spec in sorted(names, key=lambda x: len(x[0]), reverse=True):
        u = folded(body)
        if u != alias and not u.startswith(alias + " ") and not u.startswith(alias + ":"):
            continue
        tail = body[len(alias):].lstrip(" :")
        schema = spec.ai_schema()  # Never expose internal gesture snapshots.
        required = schema.get("required", [])
        try:
            if tail.startswith("{"):
                args = json.loads(tail)
            elif tail and len(required) == 1:
                key = required[0]
                typ = schema["properties"][key]["type"]
                args = {key: tail if typ == "string" else json.loads(tail)}
            elif not tail:
                args = {}
            else:
                raise ValueError("Hãy dùng tham số JSON / Use JSON arguments.")
            from nexa.ai.tool_registry import validate_schema
            ok, error, args = validate_schema(schema, args)
            if not ok:
                raise ValueError(error)
        except (ValueError, TypeError) as exc:
            return Route("clarify", reply=f"{spec.title}: {exc}")
        return Route("basic", [(spec.name, args)])
    return Route("clarify", reply="Không có lệnh này. Nói 'danh sách lệnh' / Say 'list commands'.")
