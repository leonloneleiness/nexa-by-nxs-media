"""Mẫu câu tiếng Việt cho sinh code, chạy cục bộ trong IntentRouter (không cần Gemini để hiểu lệnh).

- Viết code: "viết/tạo/sinh/lập trình/code … (hàm|script|chương trình|class|API|SQL|regex|python…)". Phải có động từ ở
  đầu câu VÀ một từ chỉ code, nên "tạo thư mục", "viết email", "tạo mô hình 3D" không bị bắt nhầm.
- Mở bảng, hủy, tiến độ, chạy thử, chỉnh sửa bản hiện tại.
- Chạy thử tệp có sẵn (mọi ngôn ngữ): "chạy thử file main.py", "chạy file đang mở trong VS Code" → run_file.
Trả về (kind, calls, reply, resume) như route_3d. Xét TRƯỚC route_3d (route_3d cũng khớp động từ "tạo/sinh").
"""
from __future__ import annotations

import re

Out = tuple[str, list[tuple[str, dict]], str, str | None]

LEAD = r"^(?:(?:hay|em|nexa|oi|giup (?:anh|toi|minh|em)|anh (?:can|muon)|toi (?:can|muon)|minh (?:can|muon)|" \
       r"cho (?:anh|toi|minh)|lam on)\s+)*"
GEN_VERB = LEAD + r"(?:viet|tao|sinh|lap trinh|code|gen|generate|write|xay dung|implement|lam)\b"
LANG_WORDS = (r"python|javascript|typescript|java|golang|rust|php|kotlin|swift|powershell|bash|nodejs|node\.?js|"
              r"react|vue|c sharp|c#|c\+\+|cpp|dart|flutter|django|flask|fastapi|express|spring|pandas|numpy")
CODE_OBJ = re.compile(
    # "code" trong tên "VS Code"/"Visual Studio Code" không phải yêu cầu viết code ("tạo file main.py trong vs code")
    r"\b(?:(?<!vs )(?<!studio )code|doan code|ma nguon|source|script|ham|function|method|phuong thuc|chuong trinh|app console|class|"
    r"lop (?:doi tuong|trong)|api|endpoint|rest|thuat toan|giai thuat|sql|query|cau truy van|truy van|regex|regexp|"
    r"bieu thuc chinh quy|unit test|test case|kiem thu|module|cli|crud|backend|frontend|component|dockerfile|"
    r"makefile|interface|struct|enum|decorator|middleware|parser|crawler|scraper|bot|tool dong lenh)\b|"
    r"\b(?:" + LANG_WORDS + r")(?![\w])")
BLOCK = re.compile(r"\b(?:thu muc|folder|email|e-mail|tin nhan|van ban|tai lieu word|bang tinh|slide|thuyet trinh|"
                   r"ghi chu|nhac nho|lich hen|bai hat|playlist|mo hinh|3d|ban ve|bai tho|bai van|cau chuyen|loi chuc)\b")

LANG_DETECT = [
    (r"\btypescript\b|\bts\b(?= |$)", "typescript"), (r"\bjavascript\b|\bnode\.?js\b|\bjs\b|\breact\b|\bexpress\b",
                                                     "javascript"),
    (r"\bpython\b|\bdjango\b|\bflask\b|\bfastapi\b|\bpandas\b|\bnumpy\b", "python"),
    (r"c#|\bc sharp\b|\.net\b|\bdotnet\b|\basp\.net\b", "csharp"), (r"c\+\+|\bcpp\b", "cpp"),
    (r"\bjava\b(?! ?script)|\bspring\b", "java"), (r"\bgolang\b|\bgo lang\b|\bbang go\b|\bngon ngu go\b", "go"),
    (r"\brust\b", "rust"), (r"\bphp\b", "php"), (r"\bkotlin\b", "kotlin"), (r"\bpowershell\b", "powershell"),
    (r"\bbash\b|\bshell script\b", "bash"), (r"\bsql\b|\btruy van\b|\bquery\b", "sql"), (r"\bdart\b|\bflutter\b", "dart"),
]

OPEN = re.compile(r"^(?:mo|hien|xem)( lai)? (?:bang|khung|trinh|man hinh) (?:sinh|tao|viet) code\b|"
                  r"^(?:mo|xem)( lai)? (?:code|doan code|ban code) (?:vua|moi) (?:tao|viet|sinh)")
# "Đóng code", "tắt bảng sinh code đi", "thoát khỏi chế độ code cho tôi". "đóng VS Code" không khớp (từ "vs" chặn).
CLOSE = re.compile(LEAD + r"(?:dong|tat|thoat|an|close)(?: khoi| lai)?(?: cai)?"
                   r"(?: (?:bang|khung|cua so|trinh|man hinh|che do|giao dien|phan))?(?: (?:sinh|tao|viet|xem))?"
                   r" (?:code|ma code|ma nguon|lap trinh)"
                   r"(?: (?:cho|giup|ho) (?:toi|anh|minh|em))?(?: (?:di|nhe|lai|luon|nay|do|ngay))*$")
CANCEL = re.compile(r"^(?:huy|dung|ngung|thoi)( viec)? (?:viet|tao|sinh|lap trinh) code\b")
STATUS = re.compile(r"^(?:tien do|trang thai) (?:viet|tao|sinh) code|^code (?:viet |tao )?(?:xong|den dau|toi dau)( chua)?$|"
                    r"^(?:da )?(?:viet|tao|sinh) (?:xong )?code (?:chua|xong chua)")
RUN = re.compile(r"^(?:chay thu|test thu|kiem thu|chay test|chay kiem thu)( lai)? (?:code|doan code|ban code|chuong trinh|"
                 r"bai test|test)( (?:vua|moi) (?:tao|viet|sinh))?( di| giup (?:anh|toi|minh))?$")
# Chạy thử một TỆP có sẵn: "chạy thử file main.py (trong VS Code)", "chạy main chấm py", "chạy file đang mở/này".
_RUN_VERB = LEAD + r"(?:chay thu|chay|run|thuc thi|test thu|kiem thu)(?: lai)?(?: (?:giup|cho|ho) (?:toi|anh|minh|em))?"
_RUN_TAIL = (r"(?: (?:trong|bang|tren|o|voi) (?:vs code|visual studio code|vscode|vs cot|vi es code))?"
             r"(?: (?:di|nhe|luon|ngay|giup (?:toi|anh|minh)|cho (?:toi|anh|minh)))*$")
_FILE_WORD = r"(?:cai )?(?:file|tep|tuep|tap tin)"
_ACTIVE = r"(?:nay|do|dang mo|hien tai|dang xem|dang sua|dang lam|vua mo|tren man hinh)"
RUN_ACTIVE = re.compile(_RUN_VERB + r" (?:" + _FILE_WORD + r"|code|doan code|chuong trinh)(?: code)? " + _ACTIVE
                        + _RUN_TAIL + r"|" + _RUN_VERB + r" (?:" + _FILE_WORD + r"|code|chuong trinh)(?: " + _ACTIVE
                        + r")? (?:trong|tren|o) (?:vs code|visual studio code|vscode|vs cot|vi es code)"
                        + r"(?: (?:di|nhe|luon|ngay|giup (?:toi|anh|minh)|cho (?:toi|anh|minh)))*$")
RUN_NAMED = re.compile(_RUN_VERB + r" " + _FILE_WORD + r"(?: ten| co ten)? (?P<n>.+?)" + _RUN_TAIL + r"|"
                       + _RUN_VERB + r" (?P<n2>\S+(?:\.| cham )\S+)" + _RUN_TAIL)
REFINE = re.compile(r"^(?:sua|chinh|chinh sua|toi uu|refactor|cai tien|bo sung|nang cap|doi)( lai)? (?:code|doan code|"
                    r"ban code|chuong trinh) (?:vua|moi|nay|do|tren|hien tai)?\s*(?:tao|viet|sinh)?\b")


def detect_language(orig: str, fold_text: str) -> str:
    low = (orig or "").lower()
    for pat, lang in LANG_DETECT:
        if re.search(pat, fold_text) or re.search(pat, low):
            return lang
    return ""


def route_code(orig: str, fold_text: str) -> Out | None:
    u = (fold_text or "").strip()
    if not u:
        return None
    if CANCEL.search(u):
        return "basic", [("cancel_code_job", {})], "", None
    if STATUS.search(u):
        return "basic", [("get_code_status", {})], "", None
    if CLOSE.match(u):
        return "basic", [("close_code_panel", {})], "", None
    if OPEN.search(u):
        return "basic", [("open_code_panel", {})], "", None
    if RUN.match(u):
        return "basic", [("run_code_tests", {})], "", None
    if RUN_ACTIVE.match(u):
        return "basic", [("run_file", {})], "", None
    m = RUN_NAMED.match(u)
    if m:
        g = "n" if m.group("n") is not None else "n2"
        off = len(fold_text) - len(fold_text.lstrip())
        name = m.group(g)
        if len(orig or "") == len(fold_text):               # lấy từ câu gốc (giữ dấu/hoa thường của tên tệp)
            name = orig[off + m.start(g):off + m.end(g)].strip(" ,;:!?\"'“”")
        if name and not re.fullmatch(r"(?:moi|vua tao|nao|gi|khac)", m.group(g)):
            return "basic", [("run_file", {"name": name})], "", None
    m = REFINE.match(u)
    if m and len(u) > m.end() + 3:
        return "basic", [("refine_code", {"instruction": orig.strip()})], "", None
    obj = CODE_OBJ.search(u) if re.match(GEN_VERB, u) else None
    blk = BLOCK.search(u) if obj else None
    # từ chặn chỉ có hiệu lực khi đứng TRƯỚC từ chỉ code: "tạo thư mục code" ≠ "tạo script dọn thư mục Temp"
    if obj and (blk is None or obj.start() < blk.start()):
        # "tạo file python" không kèm mô tả việc cần làm → để công cụ tạo tệp xử lý
        if re.fullmatch(LEAD + r"(?:tao|lam) (?:mot )?(?:file|tep)( \w+)?( moi)?", u):
            return None
        args = {"prompt": orig.strip()}
        lang = detect_language(orig, u)
        if lang:
            args["language"] = lang
        return "basic", [("generate_code", args)], "", None
    return None
