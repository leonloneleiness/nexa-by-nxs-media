"""Câu lệnh mẫu để tạo bộ dữ liệu TỔNG HỢP (giọng TTS) cho thí nghiệm nhận dạng lệnh nói lẫn Việt–Anh.

Mỗi câu có hai kiểu đọc:
- "orth": đưa đúng chính tả tiếng Anh cho giọng đọc ("mở VS Code") — giọng TTS tiếng Việt tự đọc theo kiểu Việt;
- "viet": đưa phiên âm kiểu Việt ("mở vi ét cốt") — mô phỏng cách người Việt thường nói từ tiếng Anh.
Câu chuẩn (reference) luôn viết đúng chính tả: "mở VS Code".

Ngữ cảnh (các tên đang mở trên máy) được gán THỰC TẾ theo loại lệnh: lệnh "mở X" thường là X CHƯA mở nên ngữ cảnh
không chứa X; lệnh "đóng/tắt X", "đóng tab X", "tìm trong X" thì X đang mở. Nhờ vậy thí nghiệm không thổi phồng
tác dụng của gợi ý ngữ cảnh.

Bộ tổng hợp chỉ để phát triển và kiểm tra nhanh; kết luận nghiên cứu phải dựa trên giọng người thật
(scripts/asr_corpus.py). Xem docs/research_asr.md.
"""
from __future__ import annotations

import random
from typing import Any

# thực thể: (chính tả, [cách đọc kiểu Việt])
ENTITIES: dict[str, tuple[str, list[str]]] = {
    "vscode": ("VS Code", ["vi ét cốt", "vê ét cốt"]),
    "youtube": ("YouTube", ["iu túp", "diu túp"]),
    "chatgpt": ("ChatGPT", ["chát gi pi ti", "chát ghi pi ti"]),
    "claude": ("Claude", ["cờ lốt", "clốt"]),
    "zalo": ("Zalo", ["da lô", "za lô"]),
    "word": ("Word", ["guốt"]),
    "excel": ("Excel", ["ếch xeo", "ếch xen"]),
    "powerpoint": ("PowerPoint", ["pao pơ poi"]),
    "chrome": ("Chrome", ["cờ rôm", "crôm"]),
    "discord": ("Discord", ["đít cọt", "đít co"]),
    "spotify": ("Spotify", ["sờ pô ti phai"]),
    "canva": ("Canva", ["can va"]),
    "gmail": ("Gmail", ["gi meo"]),
    "facebook": ("Facebook", ["phây búc"]),
    "tiktok": ("TikTok", ["tíc tóc"]),
    "gdrive": ("Google Drive", ["gu gồ đrai"]),
    "github": ("GitHub", ["ghít hấp"]),
    "docker": ("Docker", ["đốc cơ"]),
    "steam": ("Steam", ["xờ tim"]),
    "file": ("file", ["phai"]),
    "folder": ("folder", ["phôn đơ", "phôn đờ"]),
    "wifi": ("Wi-Fi", ["oai phai"]),
    "bluetooth": ("Bluetooth", ["blu tút"]),
    "pdf": ("PDF", ["pi đi ép"]),
    # tên "hiếm": KHÔNG có trong danh sách gợi ý tĩnh — chỉ gợi ý ngữ cảnh (ứng dụng đang mở) mới đưa được vào
    "photoshop": ("Photoshop", ["phốt tô sốp"]),
    "capcut": ("CapCut", ["cáp cắt"]),
    "obs": ("OBS", ["ô bê ét"]),
    "telegram": ("Telegram", ["tê lê gam", "te le gờ ram"]),
    "notion": ("Notion", ["nâu sần"]),
    "figma": ("Figma", ["phích ma"]),
    "outlook": ("Outlook", ["ao lúc"]),
    "obsidian": ("Obsidian", ["ốp si đi ần"]),
}

OPENABLE = ["vscode", "youtube", "chatgpt", "claude", "zalo", "word", "excel", "powerpoint", "chrome", "discord",
            "spotify", "canva", "gmail", "facebook", "tiktok", "gdrive", "github", "docker", "steam"]
CLOSABLE = ["youtube", "chatgpt", "claude", "zalo", "word", "excel", "chrome", "discord", "spotify", "facebook"]
LONG_TAIL = ["photoshop", "capcut", "obs", "telegram", "notion", "figma", "outlook", "obsidian"]
TABS = ["youtube", "chatgpt", "gmail", "facebook", "tiktok", "claude"]
SEARCHABLE = [("youtube", ["nhạc Sơn Tùng", "cách nấu phở", "tin tức hôm nay"]),
              ("chatgpt", ["thời tiết hôm nay", "cách viết email xin nghỉ phép"]),
              ("claude", ["tóm tắt báo cáo tháng này"])]
FILE_NAMES = ["báo cáo", "hợp đồng", "kế hoạch tháng mười"]
FOLDER_NAMES = ["dự án", "hình ảnh", "tài liệu mới"]

# Câu không có thực thể (đối chứng): gợi ý không được làm hỏng câu tiếng Việt thuần.
PLAIN = ["chụp màn hình", "phóng to cửa sổ", "bỏ qua quảng cáo", "tạm dừng", "mấy giờ rồi", "nghỉ đi"]


def _say(slot: str, style: str, rng: random.Random) -> tuple[str, str]:
    orth, viet = ENTITIES[slot]
    return orth, (orth if style == "orth" else rng.choice(viet))


def _context(target: str | None, rng: random.Random, include_target: bool) -> list[str]:
    pool = [k for k in OPENABLE if k != target]
    ctx = [ENTITIES[k][0] for k in rng.sample(pool, 2)]
    if include_target and target:
        ctx.insert(rng.randrange(len(ctx) + 1), ENTITIES[target][0])
    return ctx


def build_items(seed: int = 7, styles: tuple[str, ...] = ("orth", "viet")) -> list[dict[str, Any]]:
    """Danh sách câu: id, group, style, spoken (đưa cho TTS), reference, context, target."""
    rng = random.Random(seed)
    items: list[dict[str, Any]] = []

    def add(group: str, style: str, spoken: str, ref: str, target: str | None, ctx: list[str]) -> None:
        items.append({"id": f"{group}-{len(items):04d}-{style}", "group": group, "style": style,
                      "spoken": spoken, "reference": ref, "context": ctx,
                      "target": ENTITIES[target][0] if target else ""})

    for style in styles:
        for k in OPENABLE:
            o, s = _say(k, style, rng)
            add("open", style, f"mở {s}", f"mở {o}", k, _context(k, rng, include_target=False))
        for k in CLOSABLE:
            o, s = _say(k, style, rng)
            verb = rng.choice(["đóng", "tắt"])
            add("close", style, f"{verb} {s}", f"{verb} {o}", k, _context(k, rng, include_target=True))
        for k in LONG_TAIL:
            o, s = _say(k, style, rng)
            verb = rng.choice(["đóng", "tắt"])
            add("longtail", style, f"{verb} {s}", f"{verb} {o}", k, _context(k, rng, include_target=True))
        for k in TABS:
            o, s = _say(k, style, rng)
            add("tab", style, f"đóng tab {s}", f"đóng tab {o}", k, _context(k, rng, include_target=True))
        for k, queries in SEARCHABLE:
            for q in queries:
                o, s = _say(k, style, rng)
                prep = "trên" if k == "youtube" else "trong"
                add("search", style, f"tìm {prep} {s} {q}", f"tìm {prep} {o} {q}", k,
                    _context(k, rng, include_target=True))
        for name in FILE_NAMES:
            o, s = _say("file", style, rng)
            add("file", style, f"mở {s} {name}", f"mở {o} {name}", "file", _context(None, rng, False))
        for name in FOLDER_NAMES:
            o, s = _say("folder", style, rng)
            add("folder", style, f"tạo {s} {name}", f"tạo {o} {name}", "folder", _context(None, rng, False))
        for k in ("wifi", "bluetooth"):
            o, s = _say(k, style, rng)
            verb = rng.choice(["bật", "tắt"])
            add("system", style, f"{verb} {s}", f"{verb} {o}", k, _context(None, rng, False))
        o, s = _say("zalo", style, rng)
        add("zalo", style, f"kiểm tra tin nhắn {s}", f"kiểm tra tin nhắn {o}", "zalo",
            _context("zalo", rng, include_target=True))
        o, s = _say("word", style, rng)
        add("office", style, f"tạo file {s} mới", f"tạo file {o} mới", "word", _context(None, rng, False))
    for text in PLAIN:
        add("plain", "orth", text, text, None, _context(None, rng, False))
    return items
