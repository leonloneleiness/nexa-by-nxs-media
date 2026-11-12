"""Từ tiếng Anh / viết tắt hay dùng khi nói tiếng Việt, và cách Whisper hay ghi chúng theo phiên âm.

Người Việt nói "mở phai", "tạo phôn đơ", "mở iu túp", "bật oai phai"… Model nhận dạng tiếng Việt ghi đúng
phiên âm đó chứ không ghi "file", "folder", "YouTube", "Wi-Fi". Bảng dưới đưa các phiên âm về đúng từ gốc TRƯỚC
khi phân tích lệnh. Chỉ dùng các cụm đủ đặc trưng (có dấu thanh cụ thể) để không đụng từ tiếng Việt thường:
"phai" (không dấu, hiếm gặp) → file, nhưng "phải" (có dấu hỏi) vẫn là "phải".

Thêm cách nghe nhầm mới: chép đúng chuỗi trong log ("Nghe được …") vào nhóm tương ứng.
"""
from __future__ import annotations

import re

# (từ chuẩn, [các cách viết/phiên âm]). So khớp không phân biệt hoa thường, theo ranh giới từ, GIỮ dấu thanh.
TERMS: list[tuple[str, list[str]]] = [
    ("YouTube", ["iu túp", "iu tút", "diu túp", "diu tút", "yêu túp", "du túp", "giu túp", "yu túp", "iu-túp",
                 "diu-túp", "you tube", "iu tu bê", "yiu túp"]),
    ("ChatGPT", ["chát gpt", "chát gi pê tê", "chát gi pi ti", "chát gi pê te", "chat gpt"]),
    ("Google", ["gu gồ", "gu gô", "gút gồ", "gu-gồ", "gu gơ", "gu gồ gồ"]),
    ("Facebook", ["phây búc", "phê búc", "phết búc", "phây bút", "phây-búc", "phay búc"]),
    ("Messenger", ["mét xen giơ", "mes sen giơ", "mét-xen-giơ"]),
    ("TikTok", ["tíc tóc", "tíc-tóc", "tik tok"]),
    ("Chrome", ["crôm", "cờ rôm", "cơ rôm"]),
    ("Wi-Fi", ["oai phai", "goai phai", "quai phai", "wai phai", "wi fi", "wifi", "oai-phai"]),
    ("Bluetooth", ["blu tút", "bờ lu tút", "blu-tút", "bu lu tút", "blue tooth"]),
    ("email", ["i meo", "y meo", "ê meo", "i-meo", "e mail"]),
    ("Gmail", ["gi meo", "gờ meo", "gi-meo"]),
    ("file", ["phai", "fai", "phai-l", "phai lờ"]),
    ("folder", ["phôn đơ", "phôn đờ", "pôn đơ", "phôn-đơ", "phoăn đơ", "phôn đơn", "phôn dơ", "fôn đơ", "fol đơ",
                "phô đơ", "phô đờ", "phôn đớ"]),
    ("download", ["đao lốt", "đao lát", "đau lốt", "đao-lốt"]),
    ("desktop", ["đét tốp", "đéc tốp", "đét-tốp"]),
    ("laptop", ["láp tốp", "láp-tốp", "lap tốp"]),
    ("copy", ["cóp pi", "cốp pi", "cóp-pi", "cop pi"]),
    ("paste", ["pết"]),
    ("tab", ["táp mới"]),
    ("screenshot", ["sờ crin sót", "sờ-crin-sót", "cờ rin sót", "sờ-cờ-rin-sót"]),
    ("Windows", ["uyn đâu", "uynh đâu", "win đâu", "quyn đâu", "uyn đô", "uyn-đâu"]),
    ("settings", ["sét tinh", "sét-ting", "sét tin"]),
    ("PDF", ["pi đi ép", "pê đê ép", "bê đê ép", "pi-đi-ép", "pê-đê-ép"]),
    ("USB", ["u ét bê", "iu ét bi", "u ét bi", "u-ét-bê"]),
    ("CPU", ["xi pi iu", "xê pê u", "xi-pi-iu"]),
    ("Zalo", ["da lô", "za lô", "gia lô"]),
    ("Word", ["guốt", "uốt"]),
    ("Excel", ["ếch xeo", "ét xeo", "ếch-xeo", "ét-xeo", "ếch xen"]),
    ("PowerPoint", ["pao pơ poi", "pao-pơ-poi", "pao poi"]),
    ("zoom", ["dum", "zum"]),
    ("online", ["on lai", "on-lai"]),
    ("update", ["ấp đết", "áp đết", "ấp-đết"]),
]

# "tab" chỉ đổi trong cụm "táp mới" → giữ nguyên chữ "mới".
_SPECIAL = {"táp mới": "tab mới"}


def _build() -> list[tuple[re.Pattern, str]]:
    out = []
    for canon, variants in TERMS:
        for v in sorted(variants, key=len, reverse=True):
            repl = _SPECIAL.get(v, canon)
            words = [re.escape(w) for w in re.split(r"[\s-]+", v)]
            pattern = r"(?<![\w])" + r"[\s-]+".join(words) + r"(?![\w])"
            if canon == "file":
                pattern += r"(?!\s+(?:màu|nhạt|tàn|phôi))"      # "phai màu" vẫn là tiếng Việt
            out.append((re.compile(pattern, re.IGNORECASE), repl))
    return out


_PATTERNS = _build()


def normalize_english(text: str) -> str:
    """Đổi phiên âm tiếng Việt của từ tiếng Anh về đúng từ gốc ("mở phôn đơ dự án" → "mở folder dự án")."""
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


def whisper_prompt_terms() -> list[str]:
    return [canon for canon, _ in TERMS]
