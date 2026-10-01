"""Chuẩn hóa văn bản tiếng Việt."""
from __future__ import annotations

import re
import unicodedata


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


def strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt để so khớp lệnh (giữ nguyên độ dài theo ký tự NFC)."""
    text = nfc(text).replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    out = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", out)


def fold(text: str) -> str:
    """Chữ thường, bỏ dấu, gộp khoảng trắng."""
    return re.sub(r"\s+", " ", strip_accents(text).lower()).strip()


def truncate(text: str, n: int) -> str:
    text = text or ""
    return text if len(text) <= n else text[: max(0, n - 1)] + "…"
