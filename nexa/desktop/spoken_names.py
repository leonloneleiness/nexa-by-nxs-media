"""Hiểu tên tệp đọc bằng giọng nói và so khớp gần đúng với tên tệp thật.

Whisper nghe tên tệp tiếng Anh theo kiểu phiên âm tiếng Việt (log thật 24–27/09):
  "main.py"   → "main.by", "main.3" ("pai" → "ba" → 3), "men chấm bay"
  "README.md" → "read.md"            "public.html" → "Public HTML"
parse_spoken_name() tách phần tên + đuôi (đổi "chấm" thành ".", đuôi đọc sai về đuôi thật); score_name() chấm điểm
một tên tệp thật so với câu nói: trùng hẳn > chứa chuỗi > gần đúng theo âm ("men" ~ "main", "rít mi" ~ "readme").
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from nexa.utils.text import fold

# Đuôi thật → các cách Whisper hay viết ra (đã bỏ dấu, bỏ khoảng trắng).
_EXT_SOUNDS: dict[str, tuple[str, ...]] = {
    "py": ("py", "pi", "pai", "pay", "bai", "bay", "by", "bi", "bye", "pie", "ba", "pa", "3", "python", "paithon"),
    "md": ("md", "emdi", "emde", "emd", "markdown", "macdao"),
    "html": ("html", "htm", "htmel", "hatemeo", "hotemeo", "hatemel"),
    "css": ("css", "xeetet", "xetet", "sietet"),
    "cs": ("cs", "csharp"),
    "js": ("js", "gs", "jes", "jet", "giet", "jayet", "jayes", "javascript"),
    "ts": ("ts", "teet", "ties", "tiet", "typescript"),
    "json": ("json", "jason", "jsn", "giayson", "giason", "jayson", "gison"),
    "txt": ("txt", "text", "tech", "teichte"),
    "cpp": ("cpp", "c++", "xepepe", "sipipi", "cplusplus"),
    "c": ("c", "xe", "si"),
    "h": ("h",),
    "java": ("java", "giava", "diava"),
    "ipynb": ("ipynb", "notebook"),
    "yaml": ("yaml", "yml", "diamo", "giamo"),
    "csv": ("csv", "xeetve", "sivi"),
    "xml": ("xml",), "sql": ("sql", "sequel"), "php": ("php",), "go": ("go",), "rs": ("rs",), "kt": ("kt",),
    "toml": ("toml",), "ini": ("ini",), "bat": ("bat",), "ps1": ("ps1",), "sh": ("sh",),
    "docx": ("docx", "doc", "dox", "docs", "word"),
    "xlsx": ("xlsx", "xls", "excel"),
    "pptx": ("pptx", "ppt", "powerpoint"),
    "pdf": ("pdf", "pdp", "bdf", "pedeep", "pideep"),
    "png": ("png",), "jpg": ("jpg", "jpeg", "jpe"), "gif": ("gif",), "svg": ("svg",),
    "mp3": ("mp3",), "mp4": ("mp4",), "zip": ("zip", "dip"), "rar": ("rar",), "stl": ("stl",), "glb": ("glb",),
}
EXT_ALIASES: dict[str, str] = {sound: ext for ext, sounds in _EXT_SOUNDS.items() for sound in sounds}
# Chữ đứng cuối KHÔNG có dấu chấm chỉ coi là đuôi khi là đuôi viết đúng ("báo cáo pdf", "main py"),
# không nhận "ba"/"bai"… vì đó cũng là chữ tiếng Việt thường ("bài ba").
_BARE_EXTS = {"py", "md", "html", "css", "js", "ts", "json", "txt", "cpp", "java", "ipynb", "yaml", "csv", "sql",
              "docx", "xlsx", "pptx", "pdf", "png", "jpg", "jpeg", "svg", "mp3", "mp4", "zip", "stl", "glb"}
# Đuôi tệp mã nguồn/văn bản kỹ thuật: gặp các đuôi này thì ưu tiên thư mục dự án đang mở trong VS Code.
CODE_EXTS = {"py", "md", "html", "css", "js", "ts", "json", "txt", "cpp", "c", "h", "java", "ipynb", "yaml", "csv",
             "xml", "sql", "php", "go", "rs", "kt", "toml", "ini", "bat", "ps1", "sh"}

_SPOKEN_DOT = re.compile(r"\s*(?:\b(?:cham|dot)\b|\.)\s*")


def key(text: str) -> str:
    """Khóa so khớp: bỏ dấu, chữ thường, '_', '-', '.' và khoảng trắng gộp thành một khoảng trắng."""
    return re.sub(r"[\s_\-.]+", " ", fold(text)).strip()


@dataclass(frozen=True)
class SpokenName:
    raw: str
    stem: str               # khóa phần tên ("main", "read", "bao cao")
    ext: str | None         # đuôi đã chuẩn hóa ("py") hoặc None nếu không nói/không đoán được

    @property
    def display(self) -> str:
        """Tên em hiểu được, để báo lại cho anh ("main.py")."""
        return f"{self.stem}.{self.ext}" if self.ext else self.stem


def parse_spoken_name(name: str) -> SpokenName:
    text = fold(name).strip(" ,;:!?\"'")
    text = _SPOKEN_DOT.sub(".", text).strip(".")
    ext: str | None = None
    stem = text
    if "." in text:
        head, _, tail = text.rpartition(".")
        tail_key = tail.replace(" ", "")
        if head and tail_key in EXT_ALIASES:
            stem, ext = head, EXT_ALIASES[tail_key]
        elif head and re.fullmatch(r"[a-z0-9]{2,5}", tail_key):
            stem, ext = head, tail_key            # đuôi lạ nhưng có vẻ là đuôi thật (".vue", ".docm"…)
        elif head and re.fullmatch(r"[a-z0-9]", tail_key):
            stem = head                           # "main.v": đuôi một chữ nghe không ra → chỉ so phần tên
    else:
        words = text.split()
        if len(words) >= 2 and words[-1] in _BARE_EXTS:
            stem, ext = " ".join(words[:-1]), EXT_ALIASES[words[-1]]
    return SpokenName(name, key(stem), ext)


# ---------------------------------------------------------------- so khớp theo âm
_CONSONANTS = [("ph", "f"), ("th", "t"), ("sh", "s"), ("ck", "k"), ("gi", "d"), ("qu", "k"), ("c", "k"), ("q", "k"),
               ("j", "d"), ("z", "d"), ("x", "s"), ("b", "p"), ("g", "k"), ("d", "t"), ("w", "u")]
_VOWELS = [(r"ai|ay|ei|ey|ae", "e"), (r"ee|ea|ie|iy|y", "i"), (r"oo|ou|uo|ew", "u"), (r"au|ao|aw|ow|oa", "o")]


def _sound_word(w: str) -> str:
    w = re.sub(r"ch$", "k", w)                 # "lích" (lick) — "ch" cuối tiếng Việt đọc như "k"
    for a, b in _CONSONANTS:
        w = w.replace(a, b)
    for pat, b in _VOWELS:
        w = re.sub(pat, b, w)
    return re.sub(r"(.)\1+", r"\1", w)


def sound(text: str) -> str:
    """Khóa âm thô: "main" → "men", "readme" → "ritme", "rít mi" → "ritmi", "pắp lích" → "paplik"."""
    return "".join(_sound_word(w) for w in re.findall(r"[a-z0-9]+", fold(text)))


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def _parts(name: str, is_dir: bool) -> tuple[str, str]:
    p = Path(name)
    return key(name if is_dir else p.stem), ("" if is_dir else p.suffix.lower().lstrip("."))


def _ext_ok(q: SpokenName, f_ext: str, is_dir: bool) -> bool:
    return q.ext is None or (not is_dir and EXT_ALIASES.get(f_ext, f_ext) == q.ext)


def _sim(q: SpokenName, f_stem: str) -> float:
    """Độ giống phần tên: lấy cao hơn giữa so chữ và so theo âm."""
    return max(_ratio(q.stem.replace(" ", ""), f_stem.replace(" ", "")), _ratio(sound(q.stem), sound(f_stem)))


def score_name(q: SpokenName, name: str, is_dir: bool) -> float:
    """0 = không khớp; 1.0 = trùng hẳn. Trùng phần tên 0.95–1.0; chứa chuỗi 0.7–0.87 (phủ càng nhiều tên càng cao,
    "read" trong "readme" > "men" trong "comment"); gần đúng theo âm 0.735–0.88 ("men" ~ "main").
    Đuôi nói ra mà khác đuôi tệp: trùng/chứa thì giảm mạnh (main.js khi anh nói main.py), gần đúng thì bỏ hẳn."""
    if not q.stem:
        return 0.0
    f_stem, f_ext = _parts(name, is_dir)
    ext_ok = _ext_ok(q, f_ext, is_dir)
    penalty = 1.0 if ext_ok else 0.7
    q_compact = q.stem.replace(" ", "")
    s_compact = f_stem.replace(" ", "")
    if q.stem == f_stem or q_compact == s_compact:
        return 1.0 if q.ext and ext_ok else 0.95 * penalty
    full_q = f"{q.stem} {q.ext}" if q.ext else q.stem
    if q.stem in f_stem or q_compact in s_compact or full_q in key(name):
        cover = min(1.0, len(q_compact) / max(1, len(s_compact)))
        return (0.7 + 0.12 * cover + (0.05 if s_compact.startswith(q_compact) else 0.0)) * penalty
    if len(q_compact) < 3 or not ext_ok:
        return 0.0
    qs, fs = sound(q.stem), sound(f_stem)
    if len(qs) < 3 and qs != fs:
        return 0.0
    sim = _sim(q, f_stem)
    return 0.3 + 0.58 * sim if sim >= 0.75 else 0.0


def near_score(q: SpokenName, name: str, is_dir: bool) -> float:
    """Gợi ý khi không có tệp nào khớp: cùng đuôi anh nói và tên hơi giống ("public.html" → popup.html)."""
    if not q.ext or is_dir or len(q.stem) < 3:
        return 0.0
    f_stem, f_ext = _parts(name, is_dir)
    if not _ext_ok(q, f_ext, is_dir):
        return 0.0
    sim = _sim(q, f_stem)
    return sim if sim >= 0.45 else 0.0
