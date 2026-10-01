"""Tên ứng dụng hay dùng + các cách Whisper hay nghe nhầm khi nói tiếng Việt, và khớp mờ tên ứng dụng.

Tên phần mềm là tiếng Anh nên model tiếng Việt thường phiên âm sai: "VS Code" → "VS Của", "video scop", "viết của";
"ChatGPT" → "chát dù bị tùy"; "Claude" → "clout". Bảng KNOWN_APPS gom các biến thể đã gặp (dạng fold: không dấu,
chữ thường) về đúng một ứng dụng. Nếu ứng dụng đó có trong Start Menu thì mở bản cài đặt, nếu là dịch vụ web thì mở URL.

Khớp mờ (fuzzy_pick) chỉ nhận khi ứng viên tốt nhất đủ giống VÀ bỏ xa ứng viên thứ hai, để không mở nhầm ứng dụng.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Iterable, Sequence

from nexa.utils.text import fold


@dataclass(frozen=True)
class KnownApp:
    name: str                               # tên hiển thị chuẩn
    installed: tuple[str, ...]              # tên lối tắt Start Menu (fold) để tìm bản cài
    spoken: tuple[str, ...]                 # cách nói / cách Whisper hay ghi ra (fold)
    url: str = ""                           # dự phòng khi chưa cài (dịch vụ web)
    hint: tuple[str, ...] = field(default=())  # từ gợi ý cho Whisper


KNOWN_APPS: tuple[KnownApp, ...] = (
    KnownApp("Visual Studio Code", ("visual studio code", "code"),
             ("vs code", "vscode", "vsiko", "vs ko", "vi si ko", "vs cot", "vs cod", "vs cua", "vs co", "vs kot", "vi et code", "vi es code",
              "vi ech code", "vi ep code", "vi et cot", "vi es cot", "visual code", "visual cot", "visual corp",
              "visual studio code", "visual studio", "video scop", "video scope", "video cop", "video code",
              "viet code", "viet cot", "viet cua", "vit code", "vit cot", "vit cua", "vi xi code", "code editor"),
             hint=("VS Code", "Visual Studio Code")),
    KnownApp("ChatGPT", ("chatgpt",),
             ("chatgpt", "chat gpt", "chat gi pi ti", "chat gi bi ti", "chat du bi tuy", "chat du bi ti",
              "chat di pi ti", "chat ji pi ti", "chat gi pi", "chat bot gpt", "chat gpt ai"),
             url="https://chatgpt.com", hint=("ChatGPT",)),
    KnownApp("Claude", ("claude",),
             ("claude", "clau", "claud", "clout", "cloud ai", "claude ai", "co lot", "clo", "clot", "clao", "co lao", "co rau", "co lau"),
             url="https://claude.ai", hint=("Claude",)),
    KnownApp("Gemini", ("gemini",), ("gemini", "gem mi nai", "je mi nai", "dem mi nai", "gemini ai"),
             url="https://gemini.google.com", hint=("Gemini",)),
    KnownApp("Zalo", ("zalo",), ("zalo", "da lo", "za lo", "gia lo", "ra lo"), url="https://chat.zalo.me",
             hint=("Zalo",)),
    KnownApp("Discord", ("discord",), ("discord", "di con", "dis cot", "dit cot", "dit cord", "dis cord", "dis co"),
             hint=("Discord",)),
    KnownApp("Canva", ("canva",), ("canva", "can va", "ca va", "kan va"), url="https://www.canva.com", hint=("Canva",)),
    KnownApp("Google Chrome", ("google chrome",), ("chrome", "google chrome", "crom", "co rom", "co ron", "co son", "chom", "gu gou chrome"),
             hint=("Chrome",)),
    KnownApp("Cốc Cốc", ("coc coc",), ("coc coc", "coc coc browser", "cot cot"), hint=("Cốc Cốc",)),
    KnownApp("Microsoft Edge", ("microsoft edge",), ("edge", "microsoft edge", "e dit", "et dit"), hint=("Edge",)),
    KnownApp("Word", ("word", "wps docs"), ("word", "microsoft word", "uot", "guot", "wot", "quot", "uoc"),
             hint=("Word",)),
    KnownApp("Excel", ("excel", "wps sheets"), ("excel", "microsoft excel", "ec xen", "ech xen", "ec sen", "ex cel"),
             hint=("Excel",)),
    KnownApp("PowerPoint", ("powerpoint", "wps slides"),
             ("powerpoint", "power point", "pao po", "pao point", "power phone", "powerporn", "power pon", "pau pone", "pao poi", "pao bo"), hint=("PowerPoint",)),
    KnownApp("Docker Desktop", ("docker desktop",), ("docker", "docker desktop", "doc co", "dot co", "doc ker"),
             hint=("Docker",)),
    KnownApp("Steam", ("steam",), ("steam", "stim", "sa tim", "x tim"), hint=("Steam",)),
    KnownApp("Antigravity", ("antigravity", "antigravity ide"), ("antigravity", "anti gravity", "an ti gra vi ti"),
             hint=("Antigravity",)),
    KnownApp("Arduino IDE", ("arduino ide",), ("arduino", "arduino ide", "a du i no", "ac du i no", "a rui no"),
             hint=("Arduino",)),
    KnownApp("Windows PowerShell", ("windows powershell",), ("powershell", "power shell", "pao seo", "pao sheo"),
             hint=("PowerShell",)),
    KnownApp("Command Prompt", ("command prompt",), ("cmd", "command prompt", "xi em di", "com man"), hint=("CMD",)),
    KnownApp("Task Manager", ("task manager",), ("task manager", "tat ma na ger", "quan ly tac vu"),
             hint=("Task Manager",)),
    KnownApp("Control Panel", ("control panel",), ("control panel", "con tron pa nen", "bang dieu khien"),
             hint=("Control Panel",)),
    KnownApp("Spotify", ("spotify",), ("spotify", "spo ti phai", "sa po ti phai", "spot ti fy"),
             url="https://open.spotify.com", hint=("Spotify",)),
    KnownApp("Facebook", ("facebook",), ("facebook", "phay buc", "phet buc", "fb", "phay bu"),
             url="https://www.facebook.com", hint=("Facebook",)),
    KnownApp("Messenger", ("messenger",), ("messenger", "me sen go", "mes sen ger", "mess"),
             url="https://www.messenger.com", hint=("Messenger",)),
    KnownApp("Gmail", ("gmail",), ("gmail", "gi meo", "gi mail", "dmail"), url="https://mail.google.com",
             hint=("Gmail",)),
    KnownApp("Google Drive", ("google drive",), ("google drive", "drive", "gu gou drai"),
             url="https://drive.google.com", hint=("Google Drive",)),
    KnownApp("Google Maps", ("google maps",), ("google map", "google maps", "ban do"), url="https://maps.google.com",
             hint=("Google Maps",)),
    KnownApp("GitHub", ("github desktop",), ("github", "git hub", "git hap", "ghit hup"), url="https://github.com",
             hint=("GitHub",)),
    KnownApp("Git Bash", ("git bash",), ("git bash", "git bat", "ghit bash"), hint=("Git Bash",)),
    KnownApp("YouTube", (), ("youtube", "you tube", "iu tup", "diu tup", "yeu tup", "du tup", "giu tup", "yu tup",
                              "yeu doi", "yeu tu", "iu tu", "diu tu", "yeu tub", "du tub"),
             url="https://www.youtube.com", hint=("YouTube",)),
    KnownApp("Google", (), ("google", "gu go", "gut go", "gu gho"), url="https://www.google.com", hint=("Google",)),
    KnownApp("TikTok", ("tiktok",), ("tiktok", "tik tok", "tic tac", "tich toc"), url="https://www.tiktok.com",
             hint=("TikTok",)),
)

_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")


def norm(text: str) -> str:
    """fold + bỏ ký tự lạ + gộp khoảng trắng."""
    return re.sub(r"\s+", " ", _NON_ALNUM.sub(" ", fold(text))).strip()


def _similar(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    r1 = SequenceMatcher(None, a, b).ratio()
    r2 = SequenceMatcher(None, a.replace(" ", ""), b.replace(" ", "")).ratio()
    return max(r1, r2)


def known_app_for(name: str, fuzzy: bool = True) -> KnownApp | None:
    """Tìm ứng dụng quen thuộc theo tên nói ra: khớp đúng biến thể trước, rồi (nếu fuzzy) khớp mờ với ngưỡng chặt."""
    q = norm(name)
    if not q:
        return None
    compact = q.replace(" ", "")
    for app in KNOWN_APPS:
        for s in app.spoken:
            if q == s or compact == s.replace(" ", ""):
                return app
    if not fuzzy or len(compact) < 4:
        return None                             # tên quá ngắn: khớp mờ dễ sai
    idx = fuzzy_pick(q, [(i, s) for i, app in enumerate(KNOWN_APPS) for s in app.spoken], min_score=0.82)
    return KNOWN_APPS[idx] if idx is not None else None


def fuzzy_pick(query: str, candidates: Iterable[tuple[object, str]], min_score: float = 0.8,
               min_gap: float = 0.08):
    """Trả về khóa của ứng viên giống nhất nếu đủ giống và rõ ràng hơn ứng viên (khác khóa) đứng thứ hai."""
    q = norm(query)
    best: dict[object, float] = {}
    for key, text in candidates:
        score = _similar(q, norm(text))
        if score > best.get(key, 0.0):
            best[key] = score
    if not best:
        return None
    ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
    top_key, top = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    if top >= min_score and top - second >= min_gap:
        return top_key
    return None


def whisper_vocabulary(extra: Sequence[str] = (), limit: int = 40) -> list[str]:
    """Danh sách tên riêng đưa vào gợi ý của Whisper (ứng dụng quen thuộc + ứng dụng anh tự thêm)."""
    words: list[str] = []
    for w in [*extra, *(h for app in KNOWN_APPS for h in app.hint)]:
        if w and w not in words:
            words.append(w)
    return words[:limit]
