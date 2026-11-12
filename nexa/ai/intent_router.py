"""Bộ phân tích lệnh tiếng Việt xác định (không cần Gemini).

Phân loại mỗi câu thành: stop | cancel | confirm | deny | sleep | internal | basic | clarify | chat | ai.
- "basic": danh sách tool call đã xác định (chạy được cả khi mất mạng / thiếu key).
- "clarify": thiếu thông tin — hỏi lại đúng phần thiếu; câu trả lời tiếp theo được ghép vào `resume`.
- "ai": cần Gemini (hội thoại, soạn nội dung, lệnh linh hoạt). Khi Gemini không khả dụng, NEXA báo
  "Chế độ lệnh cơ bản" thay vì đoán.
Lệnh nhiều bước được tách theo "," / "rồi" / "sau đó" / "và"… và chỉ được chấp nhận khi MỌI
bước đều hiểu chắc chắn; lệnh gõ nội dung nuốt toàn bộ phần còn lại của câu.
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Callable

from nexa.ai.english_terms import normalize_english
from nexa.ai.site_search import SITE_RE, find_site
from nexa.desktop.app_aliases import known_app_for
from nexa.utils.text import nfc, strip_accents

CallList = list[tuple[str, dict]]


@dataclass
class Route:
    kind: str
    calls: CallList = field(default_factory=list)
    reply: str = ""
    resume: str | None = None
    action: str = ""
    text: str = ""


NUM_WORDS = {"khong": 0, "mot": 1, "mốt": 1, "hai": 2, "ba": 3, "bon": 4, "tu": 4, "nam": 5, "lam": 5, "sau": 6,
             "bay": 7, "tam": 8, "chin": 9, "muoi": 10}

KNOWN_SITES = {"youtube": "https://www.youtube.com", "facebook": "https://www.facebook.com",
               "gmail": "https://mail.google.com", "google": "https://www.google.com", "tiktok": "https://www.tiktok.com",
               "google drive": "https://drive.google.com", "chatgpt": "https://chatgpt.com"}

KEY_WORDS = {
    "enter": "enter", "en to": "enter", "entơ": "enter", "xuong dong": "enter", "control": "ctrl", "ctrl": "ctrl",
    "con tron": "ctrl", "shift": "shift", "sip": "shift", "alt": "alt", "tab": "tab", "esc": "esc", "escape": "esc",
    "space": "space", "cach": "space", "dau cach": "space", "phim cach": "space", "backspace": "backspace",
    "xoa lui": "backspace", "delete": "delete", "del": "delete", "len": "up", "xuong": "down", "trai": "left",
    "phai": "right", "home": "home", "end": "end", "page up": "pageup", "page down": "pagedown", "windows": "win",
    "win": "win",
}
SIMPLE_SHORTCUTS = [
    (r"^(sao chep|copy)( (noi dung|doan nay|cai nay))?$", ["ctrl", "c"]),
    (r"^(dan|paste|dan vao|dan noi dung)$", ["ctrl", "v"]),
    (r"^(chon tat ca|select all|boi den tat ca)$", ["ctrl", "a"]),
    (r"^(hoan tac|undo|quay lai buoc truoc)$", ["ctrl", "z"]),
    (r"^(lam lai|redo)$", ["ctrl", "y"]),
    (r"^(luu|luu lai|luu file|luu tep|save)$", ["ctrl", "s"]),
    (r"^(cat|cut)$", ["ctrl", "x"]),
    (r"^(mo tab moi|tab moi)$", ["ctrl", "t"]),
    (r"^(tai lai trang|lam moi trang|refresh)$", ["f5"]),
    (r"^(dong tab( nay)?)$", ["ctrl", "w"]),
]
SPLIT_RE = re.compile(r"\s*(?:,|;|\.\s|\band then\b|\bthen\b|\band\b|\bxong roi\b|\bsau do\b|\btiep theo\b|\broi\b|\bxong\b|\bva\b)\s*")


def parse_vi_number(folded: str) -> int | None:
    m = re.search(r"(\d{1,3})", folded)
    if m:
        return int(m.group(1))
    tokens = folded.split()
    for i, tok in enumerate(tokens):
        if tok not in NUM_WORDS and tok != "tram":
            continue
        # "mot tram"
        if i + 1 < len(tokens) and tokens[i + 1] == "tram" and tok in NUM_WORDS:
            return min(100, NUM_WORDS[tok] * 100)
        if tok == "muoi":
            val = 10
            if i + 1 < len(tokens) and tokens[i + 1] in NUM_WORDS and tokens[i + 1] not in ("muoi", "khong"):
                val += NUM_WORDS[tokens[i + 1]]
            return val
        if tok in NUM_WORDS:
            val = NUM_WORDS[tok]
            if i + 1 < len(tokens) and tokens[i + 1] in ("muoi", "muoi"):
                val *= 10
                if i + 2 < len(tokens) and tokens[i + 2] in NUM_WORDS and tokens[i + 2] not in ("muoi", "khong"):
                    val += NUM_WORDS[tokens[i + 2]]
                return val
            if tok in ("tu", "nam", "lam", "sau", "bay", "tam", "khong"):
                # các từ này dễ trùng nghĩa khác khi đứng một mình -> chỉ nhận nếu cuối câu/trước "phan tram"
                nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
                if nxt not in ("", "phan", "%"):
                    continue
            return val
    return None


class _Text:
    """Giữ song song văn bản gốc (NFC) và bản bỏ dấu chữ thường cùng độ dài để cắt đúng vị trí."""

    def __init__(self, text: str) -> None:
        self.orig = nfc(text).strip()
        self.fold = strip_accents(self.orig.lower())
        if len(self.fold) != len(self.orig):  # phòng ký tự đặc biệt làm lệch độ dài
            self.fold = "".join(strip_accents(ch.lower())[:1] or " " for ch in self.orig)

    def sub(self, start: int, end: int | None = None) -> str:
        return self.orig[start:end].strip(" ,.;:!?\"'“”")


WAKE_PREFIX = re.compile(r"^(?:(?:nay|e|oi|hey|ok)\s+)?(?:nexa|nexa|nech xa|nec xa|ne xa|next a|nek xa|nexar|nexxa)"
                         r"(?:\s+oi)?[\s,.:!]*")
# Lời chào đầu câu ("Xin chào, cho tôi hỏi…", "Chào em, mở…"): bỏ đi để nhận ra lệnh phía sau.
GREETING_PREFIX = re.compile(r"^(?:xin chao|chao|alo|a lo|hello|hi)(?:\s+(?:em|anh|ban|nexa|ca nha))?[\s,.:!]+")
POLITE_PREFIX = re.compile(r"^(?:(?:em|hay|lam on|giup anh|giup toi|giup minh|cho anh|cho toi|anh muon|toi muon|"
                           r"minh muon|em hay|em oi|oi|please|can you|could you|would you|i want you to)\s+)+")
POLITE_SUFFIX = re.compile(r"(?:\s+(?:giup anh|giup toi|giup minh|giup|nhe|nha|nhe em|di em|a|voi|gium|ho anh|ho|cai|"
                           r"luon|ngay))+\s*[.!?]*$")


# Lỗi nghe nhầm hay gặp của Whisper với các lệnh cơ bản (đã quan sát khi thử bằng giọng tổng hợp).
STT_FIXES = [
    (re.compile(r"^đắc âm lượng\b", re.I), "đặt âm lượng"),
    (re.compile(r"\b(chúc|chục|trúc) màn hình\b", re.I), "chụp màn hình"),
    (re.compile(r"\b(đã|đạt|đắt) (tâm|đâm) lượng\b", re.I), "đặt âm lượng"),
    (re.compile(r"\b(tâm|đâm) lượng\b", re.I), "âm lượng"),
    (re.compile(r"^(thìm|tiềm|tìn)\b", re.I), "tìm"),
    (re.compile(r"\bnốt pát\b|\bnốt bát\b|\bnote pad\b", re.I), "Notepad"),
    (re.compile(r"\b(nếch xa|néc xa|nếc xa|nếch sa|néc sa)\b", re.I), "Nexa"),
    (re.compile(r"\bchương trình (nghị|duyệt|duyện)\b", re.I), "trình duyệt"),
    (re.compile(r"\b(tik tok|tíc tốc|tích tốc|tích tắc)\b", re.I), "Tíc Tắc"),
    (re.compile(r"\bchên (youtube|web|mạng|google|màn hình)\b", re.I), r"trên \1"),
    # Log 2026-09-24: "Bỏ quán cáo", "Bỏ quán cao" = "Bỏ quảng cáo" (trước đây rơi sang Gemini, chờ ~8 s).
    (re.compile(r"\b(bỏ qua|bỏ|skip|tắt|chặn|tua) (quán|quản|quãng|quáng|quan|quăng|quạng|quảng) "
                r"(cáo|cao|cảo|cạo|kháo|khảo)\b", re.I), r"\1 quảng cáo"),
]


def collapse_repeat(text: str) -> str:
    """Whisper đôi khi chép một câu lặp 2–3 lần ("Bỏ qua quảng cáo Bỏ qua quảng cáo") → giữ một lần."""
    words = text.split()
    for k in (3, 2):
        if len(words) % k or len(words) // k < 2:
            continue
        size = len(words) // k
        chunks = [strip_accents(" ".join(words[i * size:(i + 1) * size]).lower()).strip(" .,!?")
                  for i in range(k)]
        if all(c == chunks[0] for c in chunks):
            return " ".join(words[:size]).rstrip(" ,.")
    return text

# Từ đệm đầu câu hay bị Whisper nghe ra trước lệnh ("Nhất mở…", "À mở…").
FILLERS = {"nhat", "a", "u", "uh", "um", "thi", "o", "ok", "oke", "roi", "nao", "vay", "ha", "e", "the", "va"}
COMMAND_VERBS = re.compile(r"^(mo|tim|bat|tat|go|nhap|nhan|bam|click|chon|dat|tang|giam|chup|thu nho|phong to|chuyen|"
                           r"cuon|phat|xem|nghe|dung|huy|tao|dong|sao chep|dan)\b")
ORDINALS = [(r"dau tien|thu nhat|so mot|so 1|thu 1", 1), (r"thu hai|thu 2|so hai|so 2", 2), (r"thu ba|thu 3|so ba|so 3", 3),
            (r"thu tu|thu 4|so bon|so 4", 4), (r"thu nam|thu 5|so nam|so 5", 5)]


# "trong máy tôi / trên máy tính" = tìm khắp các thư mục được phép, không phải một thư mục tên "máy tôi".
ANYWHERE = re.compile(r"^(may|may tinh|may nay|laptop)( cua)?( toi| anh| minh| em| nay)?$")
# "tắt tiếng / tắt máy / tắt wifi / tắt nhạc…" không phải đóng ứng dụng.
CLOSE_NOT_APP = re.compile(r"^(tieng|am thanh|am luong|loa|may|may tinh|man hinh|wi-?fi|wifi|bluetooth|den|camera|"
                           r"cu chi|dieu khien|mic|micro|thong bao|nhac|video|bai hat|che do|nguon|dien)\b")
# "tạo file word mới", "mở powerpoint mới"…
DOC_KINDS = {"word": "word", "van ban": "word", "tai lieu word": "word", "doc": "word", "docx": "word",
             "excel": "excel", "bang tinh": "excel", "xlsx": "excel", "xls": "excel", "trang tinh": "excel",
             "powerpoint": "powerpoint", "power point": "powerpoint", "pptx": "powerpoint", "ppt": "powerpoint",
             "slide": "powerpoint", "bai thuyet trinh": "powerpoint", "trinh chieu": "powerpoint"}
DOC_RE = "(?:" + "|".join(sorted((re.escape(k) for k in DOC_KINDS), key=len, reverse=True)) + ")"
# Công cụ quản trị nói bằng tiếng Việt/tiếng Anh (khớp với admin.ADMIN_TOOLS).
ADMIN_TOOL_RE = (r"(?:task manager|trinh quan ly tac vu|quan ly tac vu|device manager|trinh quan ly thiet bi|"
                 r"quan ly thiet bi|services|dich vu windows|dich vu|event viewer|nhat ky su kien|disk management|"
                 r"quan ly o dia|control panel|bang dieu khien|disk cleanup|don dep o dia|system information|"
                 r"thong tin he thong|registry editor|trinh sua registry|registry|computer management|"
                 r"quan ly may tinh|firewall|tuong lua|ung dung khoi dong|startup|windows update|cap nhat windows)")
OPEN_VERB = re.compile(r"^(mo|khoi dong|chay|bat)( ung dung| phan mem| app| chuong trinh)? (.+)$")


# Mở tệp bằng VS Code: "(mở|xem|đọc) (giúp tôi) (file|tệp) X trong/bằng VS Code (cho tôi)".
FILE_VERB = r"(?:mo|mo ra|mo lai|xem|doc|hien thi)(?: (?:giup|cho|ho))?(?: (?:toi|anh|minh|em))?"
FILE_WORD = r"(?:tep|tuep|file|tai lieu|tap tin)"
VSCODE_NAME = r"(?:vs code|visual studio code|vscode|vs cot|vi es code)"
IN_VSCODE = (rf"(?:trong|bang|tren|voi|vao) {VSCODE_NAME}"
             r"(?: (?:cho|giup|ho) (?:toi|anh|minh|em))?")

# Sau động từ quen thuộc, "file"/"folder" nghĩa là tệp/thư mục → dùng chung mẫu lệnh tiếng Việt.
EN_OBJECT = re.compile(r"\b(mở|tìm|tìm kiếm|tạo|xóa|xoá|đổi tên|sao chép|di chuyển|lưu)( lại| cái| một)? "
                       r"(file|tập tin|folder)\b", re.IGNORECASE)
# Whisper hay nghe "Mở" thành "Mà/Má/Mơ…" ở đầu câu ("Mà yêu đôi" = "Mở YouTube").
MISHEARD_OPEN = re.compile(r"^(mà|má|mạ|mả|mã|mơ|mờ|mớ|mỡ|mổ|mỏ|bở|mớ)\s+(.+)$", re.IGNORECASE)


def apply_stt_fixes(text: str) -> str:
    text = collapse_repeat(normalize_english(text))
    for pattern, repl in STT_FIXES:
        text = pattern.sub(repl, text)
    text = EN_OBJECT.sub(lambda m: f"{m.group(1)}{m.group(2) or ''} "
                                   f"{'thư mục' if m.group(3).lower() == 'folder' else 'tệp'}", text)
    m = MISHEARD_OPEN.match(text.strip())
    if m and (known_app_for(m.group(2).strip(" .!?"), fuzzy=False) is not None
              or strip_accents(m.group(2).strip(" .!?").lower()) in KNOWN_SITES):
        text = "Mở " + m.group(2)
    return text


def fix_app_name(t: "_Text") -> "_Text":
    """"Mở VS Của" / "mở video scop" / "mở chát dù bị tùy" → "mở Visual Studio Code" / "mở ChatGPT".

    Chỉ đổi khi phần sau động từ mở khớp ĐÚNG một cách nghe nhầm đã biết (không khớp mờ ở đây), để "mở video
    Sơn Tùng" vẫn là mở video.
    """
    m = OPEN_VERB.match(t.fold)
    if not m:
        return t
    known = known_app_for(POLITE_SUFFIX.sub("", m.group(3)), fuzzy=False)
    if known is None:
        return t
    return _Text(t.orig[:m.start(3)] + known.name)


class IntentRouter:
    def __init__(self, app_exists: Callable[[str], bool] | None = None,
                 viewer_active: Callable[[], bool] | None = None,
                 part_known: Callable[[str], bool] | None = None,
                 routine_for: Callable[[str], str | None] | None = None, registry=None) -> None:
        self.registry = registry
        self.app_exists = app_exists
        # Kịch bản làm việc (nexa/desktop/routines.py): câu đã bỏ dấu -> khóa kịch bản, hoặc None.
        self.routine_for = routine_for
        # Mô hình 3D (nexa/three_d/intents.py): lệnh viewer chỉ khớp khi viewer đang mở và tên bộ phận có thật.
        self.viewer_active = viewer_active
        self.part_known = part_known

    # ----- API -----
    def route(self, text: str, pending_confirmation: bool = False, resume: str | None = None,
              companion: bool = False) -> Route:
        t = self._clean(text)
        u = t.fold
        if not u:
            return Route("clarify", reply="Dạ, anh cần em giúp gì ạ?")
        if re.fullmatch(r"(dung lai|dung|stop|dung khan cap|dung ngay|dung het|dung lai di|thoi dung lai)", u):
            return Route("stop", reply="Em đã dừng.")
        if not pending_confirmation:
            if re.fullmatch(r"(?:(?:bat|vao|chuyen sang) (?:che do )?)?(?:tam su|tro chuyen lien tuc)(?: voi (?:em|nexa))?", u):
                return Route("internal", action="companion_on")
            if re.fullmatch(r"(?:tat|thoat|ket thuc) (?:che do )?(?:tam su|tro chuyen lien tuc)|quay lai (?:che do )?dieu khien", u):
                return Route("internal", action="companion_off")
        if companion and not pending_confirmation:
            if u in ("nghi di", "ngu di", "tam nghi", "ve che do cho"):
                return Route("sleep", reply="Ừ, mình nghỉ một chút nhé. Khi muốn nói tiếp, anh gọi em.")
            if re.fullmatch(r"(?:xoa|quen|lam moi)(?: cuoc| lich su)? (?:hoi thoai|tro chuyen)", u):
                return Route("internal", action="clear_history", reply="Em đã xóa hội thoại trong phiên này.")
            if u in ("huy", "huy bo", "huy lenh"):
                return Route("cancel", reply="Em đã hủy yêu cầu.")
            return Route("ai", text=text)
        if pending_confirmation:
            words = len(u.split())
            if words <= 5 and re.match(r"^(dong y|xac nhan|co|ok|oke|okay|duoc|lam di|dung roi|chac chan|yes|dong y lam)\b", u):
                return Route("confirm")
            if words <= 5 and re.match(r"^(khong|thoi|huy|dung lam|khong can|no|tu choi)\b", u):
                return Route("deny")
        if re.fullmatch(r"(huy|huy bo|thoi|bo qua|khong can nua|thoi khong can|thoi bo di|huy lenh)", u):
            return Route("cancel", reply="Dạ, em hủy rồi ạ.")
        from nexa.ai.bilingual import catalog_route, ui_route
        extra = catalog_route(t.orig, self.registry) or ui_route(t.orig)
        if extra is not None:
            return extra
        # Literal payloads must never trigger standby/history/code commands within the text.
        if re.match(r"^(go|nhap|viet noi dung)\b", u):
            literal_route = self._parse_one(t, 0, whole=True)
            if literal_route is not None:
                return literal_route
        if resume and not self._looks_like_command(u):
            filled = resume.replace("{}", t.orig)
            return self.route(filled, pending_confirmation=False, resume=None)
        # "Cho máy ngủ": khi bật ngủ canh gác chỉ tắt màn hình (tool system_power tự chọn). Xét trước "ngủ đi".
        if re.fullmatch(r"(nexa )?(cho |dua )?(may|may tinh|laptop) (di |vao )?(ngu|che do ngu|ngu canh gac)( di| nhe)?"
                        r"|(nexa )?(ngu canh gac|tat man hinh( di)?)", u):
            return Route("basic", [("system_power", {"action": "sleep"})])
        if re.fullmatch(r"(nghi di|di nghi|nghi ngoi di|ngu di|tam nghi|ve che do cho|che do cho|nghi thoi)", u) or \
                u in ("nghi", "nghi ngoi"):
            return Route("sleep", reply="Vâng, em nghỉ đây. Anh vỗ tay khi cần em nhé.")
        if re.fullmatch(r"(xoa|quen|lam moi)( cuoc| lich su)? (hoi thoai|tro chuyen)", u):
            return Route("internal", action="clear_history", reply="Em đã xóa hội thoại trong phiên này.")
        if self.routine_for is not None:
            key = self.routine_for(u)
            if key:
                return Route("basic", [("run_routine", {"name": key})])
        if re.fullmatch(r"chay thu (?:co|cot|cotd)", u):
            return Route("clarify", reply="Em chưa nghe rõ tên chương trình. Anh nói 'chạy thử code' hoặc 'run code tests' nhé.")
        # Sinh code: xét trước 3D (cùng động từ "tạo/sinh") và trước tách câu ("viết hàm X, rồi thêm test" là MỘT yêu cầu).
        from nexa.code.intents import route_code
        rc = route_code(t.orig, t.fold)
        if rc is not None:
            kind, calls, reply, resume_tpl = rc
            return Route(kind, calls=calls, reply=reply, resume=resume_tpl)
        # Mô hình 3D: xét trước khi tách câu nhiều bước ("tạo UAV bốn cánh, camera phía trước" là MỘT yêu cầu).
        from nexa.three_d.intents import route_3d
        active = bool(self.viewer_active and self.viewer_active())
        r3 = route_3d(t.orig, t.fold, active, self.part_known if active else None)
        if r3 is not None:
            kind, calls, reply, resume_tpl = r3
            return Route(kind, calls=calls, reply=reply, resume=resume_tpl)

        # "Tìm trong ChatGPT về X", "mở ChatGPT rồi tìm X": xét TRƯỚC khi tách câu nhiều bước, nếu không
        # "rồi tìm X" sẽ thành một bước tìm Google riêng.
        site = self._site_search(t)
        if site is not None:
            return site
        multi = self._parse_sequence(t)
        if multi is not None:
            return multi
        single = self._parse_one(t, 0, whole=True)
        if single is not None:
            return single
        from nexa.ai.bilingual import public_alias_route
        public = public_alias_route(t.orig, self.registry)
        if public is not None:
            return public
        chat = self._chat(u)
        if chat is not None:
            return chat
        return Route("ai", text=t.orig)

    # ----- tiền xử lý -----
    def _clean(self, text: str) -> _Text:
        # Keep literal payloads (dictation, explicit tool JSON) intact.
        t = _Text(nfc(text))
        words = t.fold.split(" ", 1)
        if len(words) == 2 and words[0] in FILLERS and COMMAND_VERBS.match(words[1]):
            t = _Text(t.orig[len(words[0]):])
        for _ in range(3):
            before = t.fold
            m = WAKE_PREFIX.match(t.fold)
            if m:
                t = _Text(t.orig[m.end():])
            m = GREETING_PREFIX.match(t.fold)
            if m and len(t.fold[m.end():].split()) >= 2:     # "Chào em" đứng một mình vẫn là lời chào
                t = _Text(t.orig[m.end():])
            m = POLITE_PREFIX.match(t.fold)
            if m and m.end() < len(t.fold):
                t = _Text(t.orig[m.end():])
            if t.fold == before:
                break
        from nexa.ai.bilingual import english_command, ui_route
        if not re.match(r"^(command|lenh)\b", t.fold) and ui_route(t.orig) is None:
            t = _Text(english_command(t.orig))
        literal = (re.match(r"^(?:command|lenh|go|nhap|viet noi dung)\b", t.fold) or "{" in t.orig
                   or re.search(r"(?:[,;]|\b(?:then|and|roi|va|sau do))\s+(?:type|dictate|go|nhap)\b", t.fold))
        if not literal:
            t = _Text(apply_stt_fixes(t.orig))
        # Giữ "đi" trong "nghỉ đi"; bỏ hậu tố lịch sự khác.
        if not re.search(r"\b(nghi|ngu) di$", t.fold):
            m = POLITE_SUFFIX.search(t.fold)
            if m and m.start() > 0 and not literal and not re.search(r"^(go|nhap|viet)\b", t.fold):
                t = _Text(t.orig[:m.start()])
        return fix_app_name(t if literal else _Text(t.orig.strip(" .!?")))

    @staticmethod
    def _site_search(t: _Text) -> Route | None:
        u = t.fold
        verb = r"(?:tim kiem|tim|tra cuu|tra|search|kiem)"
        prep = r"(?:tren|trong|o|bang|qua|voi|tai)"
        about = r"(?: (?:ve|cho|thong tin ve|xem|la|noi dung))?"
        web = r"(?:google|web|mang|internet|trinh duyet)"
        patterns = [
            (rf"^{verb}(?: thong tin)? {prep} (?P<site>{SITE_RE}){about}[\s,:]+(?P<q>.+)$", False),
            (rf"^(?:hoi|hoi thu|nho) (?P<site>{SITE_RE})(?: (?:ve|xem|la|giup|giup anh|rang))?[\s,:]+(?P<q>.+)$", True),
            (rf"^{verb} (?P<q>.+?) {prep} (?P<site>{SITE_RE}|{web})$", False),
            (rf"^(?:mo|vao) (?P<site>{SITE_RE})(?: (?:va|roi|sau do|xong|de))?[\s,]+(?:{verb}|hoi){about}[\s,:]+"
             rf"(?P<q>.+)$", False),
        ]
        for pattern, needs_ask in patterns:
            m = re.match(pattern, u)
            if not m:
                continue
            query = t.sub(m.start("q"), m.end("q"))
            if not query:
                continue
            if re.fullmatch(web, m.group("site")):
                return Route("basic", [("web_search", {"query": query})])
            site = find_site(m.group("site"))
            if site is None or (needs_ask and not site.ask):
                continue
            return Route("basic", [("site_search", {"site": site.key, "query": query})])
        return None

    @staticmethod
    def _looks_like_command(u: str) -> bool:
        return bool(re.match(r"^(mo|dong|tat|bat|go|nhap|tim|dat|tang|giam|chup|thu nho|phong to|chuyen|cuon|"
                             r"nhap|bam|nhan|tao|xoa|doi ten|dung|huy)\b", u))

    # ----- nhiều bước -----
    def _parse_sequence(self, t: _Text) -> Route | None:
        spans = []
        pos = 0
        for m in SPLIT_RE.finditer(t.fold):
            if m.start() > pos:
                spans.append((pos, m.start()))
            pos = m.end()
        if pos < len(t.fold):
            spans.append((pos, len(t.fold)))
        if len(spans) < 2:
            return None
        calls: CallList = []
        for i, (s, e) in enumerate(spans):
            seg_fold = t.fold[s:e].strip()
            if re.match(r"^(go|nhap|type|dictate)\b|^viet noi dung\b", seg_fold):
                # Lệnh gõ nuốt phần còn lại của câu (nội dung có thể chứa dấu phẩy).
                sub = self._clean(t.orig[s:])
                r = self._parse_one(sub, 0, whole=False)
                if r is None or r.kind != "basic":
                    return None
                calls.extend(r.calls)
                return Route("basic", calls=calls)
            sub = _Text(t.orig[s:e])
            from nexa.ai.bilingual import english_command, ui_route
            r = ui_route(sub.orig)
            if r is None:
                sub = _Text(english_command(sub.orig))
                r = self._parse_one(sub, 0, whole=False)
            if r is None or r.kind != "basic":
                return None
            calls.extend(r.calls)
        return Route("basic", calls=calls)

    # ----- một lệnh -----
    def _parse_one(self, t: _Text, _offset: int, whole: bool) -> Route | None:
        u = t.fold
        if not u:
            return None

        # 1) Chuột bằng tay — xét trước "bật điều khiển bằng tay" (chế độ cử chỉ). "dung" (bỏ dấu) có thể là
        #    "dùng" hoặc "dừng": xếp vào phía TẮT cho an toàn; muốn bật thì "bật/sử dụng chuột bằng tay".
        mouse = r"(chuot|con tro) (bang tay|ao|khong khi|cu chi|bang camera)|air mouse"
        if re.match(r"^(bat|mo|kich hoat|chay|su dung)( che do)? (" + mouse + r")\b", u):
            return Route("basic", [("set_air_mouse", {"enabled": True})])
        if re.match(r"^(tat|ngung|thoi|dung|bo)( che do)? (" + mouse + r")\b", u):
            return Route("basic", [("set_air_mouse", {"enabled": False})])

        # 1a) Chú ý qua webcam: tự khóa máy khi anh rời đi; chọn màn hình theo hướng quay đầu
        away = (r"(che do )?(tu dong khoa may|tu khoa may|khoa may khi (anh |toi |em )?(roi (may|di)|di vang|vang mat|di)"
                r"|nhan biet (co mat|ngoi may|anh ngoi may)|canh may|chong nhin trom)")
        if re.match(r"^(bat|mo|kich hoat|chay)( lai)? " + away + r"\b", u):
            return Route("basic", [("set_presence_lock", {"enabled": True})])
        if re.match(r"^(tat|ngung|thoi|dung|bo)( che do)? " + away + r"\b", u):
            return Route("basic", [("set_presence_lock", {"enabled": False})])
        if re.search(r"\b(hieu chinh|hieu chuan|can chinh|chinh lai) (huong nhin|huong quay dau|huong dau|huong mat|mat nhin)\b", u):
            return Route("basic", [("calibrate_head", {})])
        head = (r"(chon|chuyen|doi|focus|lam viec tren|dieu khien)( cua so| sang)? ?(man hinh )?theo "
                r"(huong )?(nhin|quay dau|dau|mat|anh nhin)")
        if re.match(r"^(tat|ngung|thoi|dung|bo) " + head + r"\b", u):
            return Route("basic", [("set_head_target", {"mode": "off"})])
        if re.match(r"^(bat|mo|kich hoat|chay)( che do)?( tu dong)? " + head + r"\b", u):
            mode = "auto" if re.search(r"\btu dong\b", u) else "commands"
            return Route("basic", [("set_head_target", {"mode": mode})])

        # 1b) Chế độ cử chỉ (neo đầu câu)
        if re.match(r"^(bat|mo|kich hoat|chay)( che do)? (dieu khien bang tay|cu chi|dieu khien cu chi|camera)\b", u):
            return Route("basic", [("set_gesture_mode", {"enabled": True})])
        if re.match(r"^(tat|dung|ngung)( che do)? (dieu khien bang tay|cu chi|dieu khien cu chi|camera)\b", u):
            return Route("basic", [("set_gesture_mode", {"enabled": False})])

        # 2) Lệnh có nội dung tự do: gõ, tìm tệp, tìm web, mở web — xét trước để không bắt nhầm từ khóa.
        m = re.match(r"^(go|nhap|viet)\b( noi dung| chu| van ban| dong chu| cau| doan)?( sau| nhu sau)?\s*[:\-]?\s*(.*)$", u)
        # "nhấp" (click) và "nhập" (gõ) cùng thành "nhap" khi bỏ dấu: xét chữ gốc và từ đi sau.
        is_click = m is not None and m.group(1) == "nhap" and (
            t.orig.lower().startswith("nhấp") or
            (not t.orig.lower().startswith("nhập") and re.match(r"^nhap (chuot|vao|dup|doi|tai|len|day)\b", u)))
        if m and not is_click and (m.group(1) != "viet" or m.group(2) == " noi dung" or ":" in t.orig[:m.start(4) + 1]):
            content = t.orig[m.start(4):].strip() if m.group(4) else ""
            if not content:
                return Route("clarify", reply="Anh muốn em gõ nội dung gì ạ?", resume="gõ nội dung: {}")
            return Route("basic", [("type_text", {"text": content})])
        m = re.match(r"^(tim|kiem|tim kiem) (tep|tuep|file|tai lieu|thu muc)( ten| co ten)? (.+?)(?: (trong|o) (.+))?$", u)
        if m:
            args = {"name": t.sub(m.start(4), m.end(4))}
            if m.group(6) and not ANYWHERE.match(m.group(6)):
                args["folder"] = t.sub(m.start(6))
            return Route("basic", [("find_files", args)])
        # YouTube: "tìm trên YouTube X" mở trang kết quả; "mở/phát video|nhạc … (đầu tiên)" mở thẳng video.
        m = re.match(r"^(tim|tim kiem|tra cuu)( tren| o)? youtube (.+)$", u)
        if m:
            q = t.sub(m.start(3))
            return Route("basic", [("open_url", {"url": "https://www.youtube.com/results?search_query=" +
                                                        urllib.parse.quote_plus(q)})])
        # "Đổi video", "bài khác", "bài tiếp theo": video kế tiếp của lần tìm gần nhất (log: trước rơi sang Gemini).
        if re.fullmatch(r"(?:doi|chuyen|sang|qua|mo|phat|bat|cho|nghe|xem)?\s*(?:sang |qua |toi )?"
                        r"(?:video|bai|bai hat|clip|mv|nhac)(?: khac| tiep| tiep theo| sau| ke tiep| moi)"
                        r"(?: di| nhe| giup anh| cho anh)*"
                        r"|(?:doi|chuyen|bo qua) (?:video|bai|bai hat|clip|nhac)(?: nay)?(?: di| nhe| giup anh| cho anh)*"
                        r"|next(?: video| bai)?", u):
            return Route("basic", [("play_youtube", {"next": True})])
        yt = self._youtube_play(t)
        if yt is not None:
            return yt
        m = re.match(r"^(tim kiem|tim|tra cuu|search|google)(?:\s+(?:tren|o|bang)\s+(?:web|mang|internet|google|trinh duyet))?"
                     r"(?:\s+(?:ve|thong tin ve))?\s+(.+)$", u)
        if m:
            q = t.sub(m.start(2))
            if q:
                return Route("basic", [("web_search", {"query": q})])
        m = re.match(r"^mo thu muc (tai lieu|tai ve|downloads|documents|desktop|man hinh nen|anh|hinh anh|pictures)$", u)
        if m:
            return Route("basic", [("open_path", {"path": m.group(1)})])
        # "Mở file main.py trong VS Code", "file main.by trong VS Code cho tôi", "đọc giúp tôi tệp main.3 trong
        # VS Code" (log 24–27/09): "trong VS Code" là mở BẰNG VS Code, không phải thư mục tên "VS Code".
        # Tên nghe sai ("main.by", "men chấm bay") để nguyên — FileService tự hiểu (desktop/spoken_names.py).
        m = (re.match(rf"^(?:{FILE_VERB} )?(?:cai )?(?P<w>{FILE_WORD}|thu muc|folder)(?: ten| co ten)? (?P<n>.+?) "
                      rf"{IN_VSCODE}$", u)
             or re.match(rf"^{FILE_VERB} (?P<n>\S+(?:\.| cham )\S+) {IN_VSCODE}$", u))
        if m and not re.match(r"moi\b", m.group("n")):
            kind = "folder" if m.groupdict().get("w") in ("thu muc", "folder") else "file"
            return Route("basic", [("open_named", {"name": t.sub(m.start("n"), m.end("n")), "kind": kind,
                                                   "app": "vscode"})])
        # "Mở file/tệp báo cáo", "mở folder/thư mục dự án (trong Downloads)": tìm theo tên rồi mở luôn.
        m = re.match(r"^(mo|xem) (tep|tuep|tai lieu|thu muc)( ten| co ten)? (.+?)(?: (trong|o) (.+))?$", u)
        if m and not re.fullmatch(VSCODE_NAME, m.group(6) or ""):     # "mở file mới trong VS Code": tạo file mới
            args = {"name": t.sub(m.start(4), m.end(4)), "kind": "folder" if m.group(2) == "thu muc" else "file"}
            if m.group(6) and not ANYWHERE.match(m.group(6)):
                args["folder"] = t.sub(m.start(6))
            return Route("basic", [("open_named", args)])
        m = re.match(r"^(mo|vao|truy cap)( trang| trang web| website| web)? ((?:https?://)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/\S*)?)$", u)
        if m:
            return Route("basic", [("open_url", {"url": t.orig[m.start(3):m.end(3)]})])
        m = re.match(r"^(mo|vao)( trang| trang web| web)? (youtube|facebook|gmail|google drive|google|tiktok|chatgpt)$", u)
        if m:
            return Route("basic", [("open_url", {"url": KNOWN_SITES[m.group(3)]})])
        m = re.match(r"^tao thu muc( moi)?( ten| co ten)? (.+?)(?: (trong|tren|o|tai) (.+))?$", u)
        if m:
            args = {"name": t.sub(m.start(3), m.end(3))}
            if m.group(5):
                args["parent"] = t.sub(m.start(5))
            return Route("basic", [("create_folder", args)])

        # 3) Đọc màn hình (Gemini Vision, luôn có xem trước + xác nhận) và chụp màn hình
        if re.match(r"^(doc|xem|mo ta|tom tat|phan tich) (noi dung )?(man hinh|cua so)\b|^tren man hinh (dang )?co gi", u):
            scope = "monitor" if "man hinh" in u and "cua so" not in u else "active_window"
            return Route("basic", [("describe_screen", {"question": t.orig, "scope": scope})])
        if re.match(r"^chup (anh )?man hinh\b", u):
            return Route("basic", [("take_screenshot", {"scope": "all"})])

        # 3b) Tài liệu mới / VS Code / quảng cáo / Zalo / quản trị
        r = self._productivity(t)
        if r is not None:
            return r

        # 4) Thời gian / hệ thống
        # "bao nhiêu" hay bị nghe thành "vô/bô/mô/vào nhiêu" (log 22:48: "Hôm nay là ngày vô nhiêu").
        how_many = r"(?:bao|vo|bo|mo|vao|bau) nhieu"
        if re.search(rf"\b(may gio|gio la may|bay gio la (may|bao)|hom nay (la )?(ngay|thu) (may|{how_many}|gi)|"
                     rf"ngay {how_many}|hom nay ngay may|xem gio)\b", u) and len(u.split()) <= 8:
            asks_time = bool(re.search(r"\b(may gio|gio la may|bay gio la|xem gio)\b", u))
            asks_date = bool(re.search(r"\b(ngay|thu)\b", u))
            part = "both" if asks_time == asks_date else ("time" if asks_time else "date")
            return Route("basic", [("get_time", {"part": part})])
        if re.match(r"^(xem |kiem tra |cho biet )?(cpu|ram|bo nho|thong tin (he thong|may)|may (dang )?chay (the nao|nang khong)|"
                    r"pin con bao nhieu)\b", u):
            return Route("basic", [("get_system_info", {})])

        # 5) Âm lượng
        r = self._volume(u)
        if r is not None:
            return r

        # 6) YouTube
        if re.fullmatch(r"(tam dung|dung|pause|ngung) (video|youtube|clip|phim|nhac)( lai)?( youtube)?", u):
            return Route("basic", [("youtube_pause", {})])
        if re.fullmatch(r"(phat tiep|tiep tuc phat|tiep tuc xem|play|chay tiep)( video| youtube| clip| phim| nhac)?( youtube)?", u):
            return Route("basic", [("youtube_resume", {})])

        # 7) Cửa sổ
        if re.fullmatch(r"(khoi phuc|mo lai|hien lai)( cua so| ung dung)?( vua)?( thu nho)?( lai)?", u):
            return Route("basic", [("restore_last_minimized", {})])
        m = re.match(r"^thu nho( cua so| ung dung)?(?: (.+))?$", u)
        if m:
            args = {"window": t.sub(m.start(2))} if m.group(2) and m.group(2) not in ("nay", "lai", "xuong") else {}
            return Route("basic", [("minimize_window", args)])
        m = re.match(r"^phong to( cua so| ung dung)?(?: (.+))?$", u)
        if m:
            args = {"window": t.sub(m.start(2))} if m.group(2) and m.group(2) not in ("nay", "len", "ra") else {}
            return Route("basic", [("maximize_window", args)])
        if re.match(r"^(chuyen|dua|di chuyen|keo)( cua so| ung dung)?( nay)? (sang|qua|toi|den|len) man hinh "
                    r"(2|hai|thu hai|phu|ben kia|con lai)\b", u):
            return Route("basic", [("move_window_to_monitor_2", {})])
        m = re.match(r"^dong cua so(?: (.+))?$", u)
        if m:
            args = {"window": t.sub(m.start(1))} if m.group(1) and m.group(1) != "nay" else {}
            return Route("basic", [("close_window", args)])
        # "Đóng mô hình UAV", "đóng code" trong câu nhiều bước ("đóng mô hình rồi mở Notepad"): mô hình 3D / bảng
        # Sinh code của NEXA, không phải một ứng dụng tên "mô hình".
        from nexa.code.intents import CLOSE as CLOSE_CODE
        from nexa.three_d.intents import CLOSE_MODEL
        if CLOSE_MODEL.match(u):
            return Route("basic", [("close_3d_viewer", {})])
        if CLOSE_CODE.match(u):
            return Route("basic", [("close_code_panel", {})])
        # "Đóng ChatGPT", "tắt YouTube", "thoát VS Code", "đóng tab YouTube", "tắt ứng dụng Zalo"
        if re.fullmatch(r"(dong|tat) (tab|trang)( nay| hien tai| dang mo)?", u):
            return Route("basic", [("press_keys", {"keys": ["ctrl", "w"]})])
        m = re.match(r"^(dong|tat|thoat|thoat khoi|tat bo)( ung dung| app| phan mem| tab| trang web| trang)? (.+)$", u)
        if m and not CLOSE_NOT_APP.match(m.group(3)):
            name = t.sub(m.start(3))
            kind = {" tab": "tab", " trang": "tab", " trang web": "tab"}.get(m.group(2) or "",
                                                                          "app" if m.group(2) else "any")
            if m.group(3) in ("nay", "do", "hien tai"):
                return Route("basic", [("press_keys", {"keys": ["ctrl", "w"]})] if kind == "tab"
                             else [("close_window", {})])
            return Route("basic", [("close_named", {"name": name, "kind": kind})])
        m = re.match(r"^(chuyen|qua|den) (sang |toi |den )?cua so (.+)$", u)
        if m:
            return Route("basic", [("focus_window", {"window": t.sub(m.start(3))})])

        # 8) Cuộn
        m = re.match(r"^cuon (len|xuong)(?: (.+?))?( nac| lan)?$", u)
        if m:
            n = parse_vi_number(m.group(2) or "") or 3
            return Route("basic", [("scroll", {"direction": "up" if m.group(1) == "len" else "down",
                                               "notches": max(1, min(30, n))})])

        # 9) Phím
        for pattern, keys in SIMPLE_SHORTCUTS:
            if re.fullmatch(pattern, u):
                return Route("basic", [("press_keys", {"keys": keys})])
        m = re.match(r"^(bam|nhan|an) (phim|to hop phim|to hop) (.+)$", u)
        if m:
            keys = self._parse_keys(m.group(3))
            if keys:
                return Route("basic", [("press_keys", {"keys": keys})])
            return Route("clarify", reply="Em chưa rõ phím nào. Anh nói lại tên phím, ví dụ 'bấm phím control C'.")

        # 10) Chuột
        if re.fullmatch(r"(nhap|click|bam|kich)( chuot)?( trai)? (dup|doi|hai lan|2 lan)", u):
            return Route("basic", [("mouse_click", {"double": True})])
        if re.fullmatch(r"(nhap|click|bam|kich) chuot phai|chuot phai", u):
            return Route("basic", [("mouse_click", {"button": "right"})])
        if re.fullmatch(r"(nhap|click|bam|kich) chuot( trai)?|click|nhap chuot mot lan", u):
            return Route("basic", [("mouse_click", {})])
        m = re.match(r"^(di chuyen|dua|di) chuot (sang |qua )?(len|xuong|trai|phai)(?: (\d+))?", u)
        if m:
            d = {"len": "up", "xuong": "down", "trai": "left", "phai": "right"}[m.group(3)]
            return Route("basic", [("mouse_move", {"direction": d, "distance": int(m.group(4) or 150)})])

        # 10b) Nhấp theo tọa độ: "nhấp chuột tại 500 300", "click vào tọa độ 120, 80"
        m = re.match(r"^(nhap|click|bam|kich|nhan)( dup| doi)?( chuot)?( trai| phai)?( dup| doi)? (tai|vao|o|len) (toa do |vi tri )?"
                     r"(-?\d{1,5})\s*(?:,|x|va|\s)\s*(-?\d{1,5})$", u)
        if m:
            args: dict = {"x": int(m.group(8)), "y": int(m.group(9))}
            if m.group(4) == " phai":
                args["button"] = "right"
            if m.group(2) or m.group(5):
                args["double"] = True
            return Route("basic", [("mouse_click", args)])
        # 10c) Nhấp vào chỗ con trỏ: "nhấp vào đây"
        if re.fullmatch(r"(nhap|click|bam|kich|nhan)( chuot)? (vao )?(day|cho nay|o day|cho do)", u):
            return Route("basic", [("mouse_click", {})])
        # 10d) Nhấp theo tên nút/mục bằng UI Automation: "bấm vào nút Lưu", "click Tải về", "chọn tab Cài đặt"
        m = re.match(r"^(nhap|click|bam|nhan|an|chon|kich)( chuot)?( vao| len| chon)?"
                     r"( nut| muc| tab| the| lien ket| link| o| bieu tuong| chu| menu| dong)? (.+)$", u)
        if m:
            target = t.sub(m.start(5))
            keys = self._parse_keys(m.group(5))
            if keys and not m.group(3) and not m.group(4):
                return Route("basic", [("press_keys", {"keys": keys})])   # "nhấn enter", "bấm esc"
            if target:
                return Route("basic", [("click_ui_control", {"name": target})])

        # 11) Mở ứng dụng (xét sau cùng)
        m = re.match(r"^(mo|khoi dong|chay|bat)( ung dung| phan mem| app| chuong trinh)?(?: (.+))?$", u)
        if m:
            name = t.sub(m.start(3)) if m.group(3) else ""
            if not name:
                return Route("clarify", reply="Anh muốn em mở ứng dụng nào ạ?", resume="mở {}")
            if m.group(1) == "bat" and not m.group(2):
                return None  # "bật ..." quá mơ hồ (bật đèn? bật tiếng?) — để AI/hỏi lại
            if self.app_exists is None or self.app_exists(name):
                return Route("basic", [("open_app", {"name": name})])
            return None
        if u in ("go", "nhap", "go chu"):
            return Route("clarify", reply="Anh muốn em gõ nội dung gì ạ?", resume="gõ nội dung: {}")
        return None

    @staticmethod
    def _youtube_play(t: _Text) -> Route | None:
        u = t.fold
        m = re.match(r"^(mo|phat|bat|xem|nghe|cho nghe|mo cho anh|bat cho anh)( lai)? (video|clip|bai hat|bai|nhac|mv|ket qua)\b(.*)$", u)
        if not m:
            return None
        rest_start = m.start(4)
        keep = [True] * (len(u) - rest_start)
        index = 1
        rest = u[rest_start:]
        for pattern, n in ORDINALS:
            for mm in re.finditer(r"\b(" + pattern + r")\b", rest):
                index = n
                for i in range(mm.start(), mm.end()):
                    keep[i] = False
        for mm in re.finditer(r"\b(tren|o|trong|tai) (youtube|trinh duyet|web|google|man hinh)\b|\b(tim duoc|vua tim)\b|^\s*(nay|do|kia)\b", rest):
            for i in range(mm.start(), mm.end()):
                keep[i] = False
        orig_rest = t.orig[rest_start:]
        query = "".join(ch for ch, k in zip(orig_rest, keep) if k)
        query = re.sub(r"\s+", " ", query).strip(" ,.:")
        kind = m.group(3)
        if query and kind in ("nhac", "bai hat", "mv"):
            query = {"nhac": "nhạc", "bai hat": "bài hát", "mv": "MV"}[kind] + " " + query
        if kind == "ket qua" and not re.search(r"\b(video|youtube)\b", u):
            return None   # "mở kết quả đầu tiên" của Google: để Gemini/UI Automation xử lý
        return Route("basic", [("play_youtube", {"query": query, "index": index})])

    @staticmethod
    def _productivity(t: _Text) -> Route | None:
        u = t.fold
        # --- tài liệu Office mới ---
        m = re.match(rf"^(?:tao|mo|soan|lam)(?P<what> (?:file|tep|tai lieu|ban|mot))? (?P<kind>{DOC_RE})"
                     rf"(?P<new>(?: (?:moi|trang|trong))*)(?: (?:ten|co ten|voi ten))?(?: (?P<name>.+))?$", u)
        # "mở Word" (không có "mới"/"file") = mở ỨNG DỤNG, để mục 11 xử lý.
        if m and u.startswith("mo ") and not m.group("what") and "moi" not in m.group("new"):
            m = None
        if m and (m.group("name") is None or not re.match(r"^(nay|do|kia|len|ra)$", m.group("name"))):
            args = {"kind": DOC_KINDS[m.group("kind")]}
            if m.group("name"):
                args["name"] = t.sub(m.start("name"))
            return Route("basic", [("new_document", args)])

        # --- file mới trong VS Code ---
        m = re.match(r"^(?:tao|mo|them)(?: (?:file|tep|mot file|mot tep))?( moi)?"
                     r"(?: (?:ten|co ten))? ?(.*?)(?: (?:trong|tren|o|bang|voi)) (?:vs code|visual studio code|vscode)$", u)
        if m:
            name = t.sub(m.start(2), m.end(2)) if m.group(2) else ""
            return Route("basic", [("vscode_new_file", {"name": name} if name else {})])
        m = re.match(r"^(?:trong |tren |o )?(?:vs code|visual studio code|vscode)[, ]+"
                     r"(?:tao|mo|them)(?: (?:file|tep))?( moi)?(?: (?:ten|co ten))? ?(.*)$", u)
        if m:
            name = t.sub(m.start(2)) if m.group(2) else ""
            return Route("basic", [("vscode_new_file", {"name": name} if name else {})])
        if re.fullmatch(r"(?:tao|mo|them) (?:file|tep) moi", u):
            return Route("basic", [("vscode_new_file", {})])
        # --- quảng cáo YouTube ---
        if re.match(r"^(?:tu dong |auto )?(?:bat|bat che do) (?:tu dong )?(?:bo qua|skip|tat|chan) quang cao", u):
            return Route("basic", [("auto_skip_ads", {"enabled": True})])
        if re.match(r"^(?:tat|dung|ngung|huy)(?: che do)? (?:tu dong )?(?:bo qua|skip|chan) quang cao", u):
            return Route("basic", [("auto_skip_ads", {"enabled": False})])
        if re.match(r"^(?:bo qua|skip|tat|tua|bo|chan|cho qua|nhay qua)(?: cai| doan| mau)? quang cao"
                    r"(?: (?:nay|di|giup anh|youtube|cua video|cua video nay|video nay|tren youtube))*$", u):
            return Route("basic", [("skip_youtube_ad", {})])
        # --- Zalo ---
        if re.match(r"^(?:kiem tra|check|xem|coi|doc)(?: (?:tin nhan|tin|hop thu|zalo))*(?: tren| trong| o)?"
                    r"(?: zalo)?(?: (?:xem |cho anh |giup anh |chua|chua doc|moi))*$", u) and "zalo" in u:
            return Route("basic", [("check_zalo", {})])
        if re.search(r"\bzalo\b", u) and len(u.split()) <= 10 and \
                re.search(r"\b(?:tin nhan|tin moi|gi moi|chua doc|ai nhan|co gi)\b", u):
            return Route("basic", [("check_zalo", {})])
        if re.match(r"^(?:co )?(?:ai|nguoi nao)(?: nao)? (?:nhan tin|nhan|gui tin nhan|nhan cho|noi gi)"
                    r"(?: (?:cho|toi|voi|den))?(?: (?:toi|anh|minh|em))?(?: (?:tren|trong|qua|o))? ?(?:zalo)?"
                    r"(?: khong| ko| chua)?$", u):
            return Route("basic", [("check_zalo", {})])
        # --- quản trị ---
        if re.match(r"^(?:chay|khoi dong|mo|bat)(?: lai)?(?: nexa| em)?(?: voi| bang| duoi)? (?:quyen |che do )?"
                    r"(?:quan tri|admin|administrator|toan quyen)(?: vien)?$", u) or \
                re.fullmatch(r"(?:xin|cap|cho em|cho|lay)(?: quyen)? (?:quan tri|admin|administrator|toan quyen)"
                             r"(?: vien)?( di| nhe| giup anh)?", u):
            return Route("basic", [("request_admin", {})])
        if re.match(r"^(?:nexa |em )?(?:dang |co )?(?:chay )?(?:voi |o )?(?:quyen )?(?:quan tri|admin)"
                    r"(?: khong| chua| ko)$", u):
            return Route("basic", [("admin_status", {})])
        m = re.match(r"^mo (?:cua so )?(powershell|cmd|command prompt|terminal|windows terminal)"
                     r"(?: voi| bang| duoi)? (?:quyen )?(?:quan tri|admin|administrator)$", u)
        if m:
            kind = {"cmd": "cmd", "command prompt": "cmd", "terminal": "terminal",
                    "windows terminal": "terminal"}.get(m.group(1), "powershell")
            return Route("basic", [("admin_shell", {"kind": kind})])
        m = re.match(rf"^(?:mo|bat)(?: (?:cua so|ung dung|cong cu|trinh))? ({ADMIN_TOOL_RE})$", u)
        if m:
            return Route("basic", [("open_admin_tool", {"name": m.group(1)})])
        if re.match(r"^(?:ung dung|app|tien trinh|cai gi|gi)(?: nao)? (?:dang )?(?:ngon|chiem|an|ton|nang)"
                    r"(?: nhieu)? ?(?:cpu|ram|bo nho|may|tai nguyen)?", u) or \
                re.match(r"^(?:xem|kiem tra|liet ke)(?: cac)? (?:ung dung|tien trinh) (?:ngon|nang|chiem nhieu)", u):
            by = "ram" if re.search(r"\b(ram|bo nho)\b", u) else ("cpu" if "cpu" in u else "both")
            return Route("basic", [("top_processes", {"by": by})])
        m = re.match(r"^(?:buoc |ep |force )?(?:tat|dong|ket thuc|kill|dung)"
                     r"(?: (?:han|ngay|cung))?(?: (?:tien trinh|ung dung|app|chuong trinh))? (.+?)"
                     r"(?: (?:dang )?(?:bi )?(?:treo|do|khong phan hoi|dung hinh))?$", u)
        if m and re.match(r"^(?:buoc |ep |force )", u) and not CLOSE_NOT_APP.match(m.group(1)):
            return Route("basic", [("end_process", {"name": t.sub(m.start(1), m.end(1)), "force": True})])
        m = re.match(r"^(?:tat|dong|ket thuc|kill)(?: (?:tien trinh|ung dung|app|chuong trinh))? (.+?) "
                     r"(?:dang )?(?:bi )?(?:treo|do|khong phan hoi|dung hinh)$", u)
        if m and not CLOSE_NOT_APP.match(m.group(1)):
            return Route("basic", [("end_process", {"name": t.sub(m.start(1), m.end(1))})])
        if re.match(r"^(?:xem|kiem tra|con)?\s*(?:dung luong|bo nho|o dia|o cung|dia)"
                    r"(?:\s+(?:o dia|o cung|con|trong|bao nhieu|the nao|con lai|nhu the nao))*\??$", u):
            return Route("basic", [("disk_usage", {})])
        if re.match(r"^(?:xem|kiem tra)?\s*(?:thong tin )?(?:mang|wi-?fi|internet|ket noi)"
                    r"(?: (?:the nao|sao|con|co khong|khong|ra sao))*\??$", u) or \
                re.fullmatch(r"(?:may )?(?:co )?(?:vao duoc )?(?:mang|internet|wi-?fi) (?:khong|ko|chua)\??", u):
            return Route("basic", [("network_info", {})])
        return None

    def _volume(self, u: str) -> Route | None:
        if re.fullmatch(r"(tat tieng|tat am thanh|tat loa|im lang)( may tinh| may| loa)?", u):
            return Route("basic", [("mute", {"on": True})])
        if re.fullmatch(r"(bat tieng|mo tieng|bat am thanh|bat loa|mo loa)( may tinh| may| lai)?", u):
            return Route("basic", [("mute", {"on": False})])
        if not re.match(r"^((dat|chinh|de|cho|tang|giam|bot|ha|van|chuyen|dieu chinh)( lai)? )?(am luong|volume)\b", u):
            return None
        n = parse_vi_number(u)
        if n is not None:
            n = max(0, min(100, n))
            if re.search(r"\b(len|xuong|con|muc|o muc|thanh|bang|ve)\s+\S*\s*" + str(n) + r"|\b(dat|chinh|de|cho|chuyen)\b", u) \
                    or re.search(r"\b(len|xuong|con|muc|thanh|bang|ve)\b", u):
                return Route("basic", [("set_volume", {"percent": n})])
            if re.search(r"\b(tang|them|to)\b", u):
                return Route("basic", [("change_volume", {"delta": n})])
            if re.search(r"\b(giam|bot|ha|nho)\b", u):
                return Route("basic", [("change_volume", {"delta": -n})])
            return Route("basic", [("set_volume", {"percent": n})])
        if re.search(r"\b(tang|to len|lon len|them)\b", u):
            return Route("basic", [("change_volume", {"delta": 10})])
        if re.search(r"\b(giam|nho lai|nho xuong|bot|ha)\b", u):
            return Route("basic", [("change_volume", {"delta": -10})])
        return Route("clarify", reply="Anh muốn đặt âm lượng bao nhiêu phần trăm ạ?", resume="đặt âm lượng {} phần trăm")

    @staticmethod
    def _parse_keys(spec: str) -> list[str]:
        spec = spec.replace("+", " ").replace("-", " ")
        tokens = spec.split()
        keys: list[str] = []
        i = 0
        while i < len(tokens):
            two = " ".join(tokens[i:i + 2])
            if two in KEY_WORDS:
                keys.append(KEY_WORDS[two])
                i += 2
                continue
            tok = tokens[i]
            if tok in KEY_WORDS:
                keys.append(KEY_WORDS[tok])
            elif re.fullmatch(r"f(1[0-2]|[1-9])", tok) or re.fullmatch(r"[a-z0-9]", tok):
                keys.append(tok)
            elif tok in ("phim", "va", "cong", "voi"):
                pass
            else:
                return []
            i += 1
        return keys[:4]

    @staticmethod
    def _chat(u: str) -> Route | None:
        if re.fullmatch(r"(xin chao|chao|chao em|chao nexa|hello|hi|alo)( em| nexa| ban)?", u):
            return Route("chat", reply="Dạ, em chào anh Sơn. Anh cần em giúp gì ạ?")
        if re.search(r"\b(cam on|thank)", u) and len(u.split()) <= 5:
            return Route("chat", reply="Dạ, không có gì ạ.")
        if re.search(r"\b(em|ban) la ai\b|gioi thieu (ve )?(ban than|em)", u):
            return Route("chat", reply="Em là Nexa, trợ lý máy tính của anh Sơn, do NXS MEDIA phát triển.")
        if re.search(r"\bem (co the )?(lam|giup) (duoc )?(nhung )?(gi|viec gi)\b", u):
            return Route("chat", reply="Em có thể mở ứng dụng, tìm trên web, chỉnh âm lượng, chụp màn hình, quản lý "
                                       "cửa sổ, gõ chữ và điều khiển bằng cử chỉ tay. Khi có Gemini, em còn trò chuyện "
                                       "và soạn nội dung giúp anh.")
        return None
