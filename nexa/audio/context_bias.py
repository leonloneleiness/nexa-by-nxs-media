"""Gợi ý ngữ cảnh động cho Whisper: tên riêng lấy từ trạng thái máy lúc anh đang nói.

Gợi ý tĩnh (build_hotwords) luôn là cùng ~30 tên. Nhưng khi anh nói "đóng Zalo" thì gần như chắc chắn Zalo đang mở;
khi nói "chuyển sang tab ChatGPT" thì ChatGPT đang có trong tiêu đề cửa sổ trình duyệt. ContextBias gom các tên đó
(ứng dụng đang hiển thị, dịch vụ web xuất hiện trong tiêu đề cửa sổ) và đặt LÊN ĐẦU danh sách hotwords, trước danh
sách tĩnh — Whisper ưu tiên viết đúng chính tả các tên này.

Đây cũng là biến thí nghiệm của nghiên cứu nhận dạng lệnh nói lẫn Việt–Anh (docs/research_asr.md):
stt.bias_mode = none (không gợi ý) | static (gợi ý tĩnh) | context (tĩnh + ngữ cảnh, mặc định).

Chỉ ĐỌC tên tiến trình và tiêu đề cửa sổ; không chụp màn hình, không đọc nội dung ứng dụng. Chỉ giữ lại tên nằm
trong từ vựng đã biết (KNOWN_APPS + ứng dụng anh tự thêm) nên tiêu đề tài liệu/tin nhắn không bao giờ lọt vào gợi ý.
Làm mới ở luồng nền khi bắt đầu có tiếng nói (không chặn nhận dạng); quá TTL thì dùng lại kết quả cũ.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any, Callable, Iterable, Sequence

from nexa.utils.logging import get_logger

log = get_logger("stt.bias")

BIAS_MODES = ("none", "static", "context")

MODE_TERMS = {
    "3d": ("rotate", "zoom in", "zoom out", "reset view", "model", "bộ phận", "phóng to", "thu nhỏ"),
    "code": ("Python", "JavaScript", "TypeScript", "debug", "terminal", "run tests", "save code"),
    "system": ("Chrome", "pause", "resume", "scroll", "cửa sổ"),
}


def interaction_terms(mode: str, terms: Sequence[str] = ()) -> tuple[str, ...]:
    return tuple(merge_terms(MODE_TERMS.get(mode, ()), terms, 30))

# Tên tiến trình (chữ thường) → tên đưa vào gợi ý. Chỉ các ứng dụng hay được gọi tên khi ra lệnh.
PROCESS_TERMS: dict[str, tuple[str, ...]] = {
    "code.exe": ("VS Code",), "chrome.exe": ("Chrome",), "msedge.exe": ("Edge",), "firefox.exe": ("Firefox",),
    "browser.exe": ("Cốc Cốc",), "zalo.exe": ("Zalo",), "winword.exe": ("Word",), "excel.exe": ("Excel",),
    "powerpnt.exe": ("PowerPoint",), "wps.exe": ("Word",), "et.exe": ("Excel",), "wpp.exe": ("PowerPoint",),
    "discord.exe": ("Discord",), "spotify.exe": ("Spotify",), "steam.exe": ("Steam",),
    "docker desktop.exe": ("Docker",), "claude.exe": ("Claude",), "chatgpt.exe": ("ChatGPT",),
    "telegram.exe": ("Telegram",), "notepad.exe": ("Notepad",),
    "powershell.exe": ("PowerShell",), "windowsterminal.exe": ("Terminal",), "arduino ide.exe": ("Arduino",),
    "antigravity.exe": ("Antigravity",), "canva.exe": ("Canva",), "obs64.exe": ("OBS",),
    "capcut.exe": ("CapCut",), "photoshop.exe": ("Photoshop",), "premiere pro.exe": ("Premiere",),
    "notion.exe": ("Notion",), "figma.exe": ("Figma",), "outlook.exe": ("Outlook",), "olk.exe": ("Outlook",),
    "ms-teams.exe": ("Teams",), "obsidian.exe": ("Obsidian",),
}
# Tiến trình không bao giờ đưa vào gợi ý (explorer luôn chạy nên không mang thông tin).
_IGNORED_PROCESSES = {"explorer.exe", "python.exe", "pythonw.exe", "nexa.exe", "textinputhost.exe",
                      "applicationframehost.exe", "systemsettings.exe", "searchhost.exe", "startmenuexperiencehost.exe"}


def title_vocabulary(extra: Iterable[str] = ()) -> list[str]:
    """Các tên được phép lấy ra từ tiêu đề cửa sổ (dịch vụ web + ứng dụng quen thuộc + ứng dụng anh tự thêm)."""
    from nexa.desktop.app_aliases import KNOWN_APPS
    words: list[str] = []
    for w in [*extra, *(h for app in KNOWN_APPS for h in app.hint)]:
        w = str(w).strip()
        if len(w) >= 3 and w not in words:
            words.append(w)
    return words


def terms_from_windows(windows: Sequence[tuple[str, str]], vocabulary: Sequence[str]) -> list[str]:
    """[(tên tiến trình, tiêu đề)] theo thứ tự Z (trên cùng trước) → tên riêng theo thứ tự ưu tiên, không trùng."""
    patterns = [(w, re.compile(r"(?<![\w])" + re.escape(w) + r"(?![\w])", re.IGNORECASE))
                for w in sorted(vocabulary, key=len, reverse=True)]
    out: list[str] = []

    def add(term: str) -> None:
        if term and term not in out:
            out.append(term)

    for process, title in windows:
        proc = (process or "").lower()
        if proc not in _IGNORED_PROCESSES:
            for term in PROCESS_TERMS.get(proc, ()):
                add(term)
        # Tiêu đề chỉ dùng để nhận ra tên ĐÃ BIẾT ("ChatGPT - Microsoft Edge" → ChatGPT), không lấy chữ tự do.
        low = title or ""
        taken: list[tuple[int, int]] = []
        for word, pat in patterns:
            for m in pat.finditer(low):
                if any(a < m.end() and m.start() < b for a, b in taken):
                    continue                    # "Google Drive" đã khớp thì bỏ "Google" bên trong
                taken.append((m.start(), m.end()))
                add(word)
    return out


def merge_terms(first: Sequence[str], rest: Sequence[str], limit: int) -> list[str]:
    out: list[str] = []
    for w in [*first, *rest]:
        if w and w not in out:
            out.append(w)
    return out[:limit]


class ContextBias:
    """Giữ danh sách tên riêng theo ngữ cảnh máy, làm mới ở luồng nền."""

    def __init__(self, config: Any, windows_provider: Callable[[], list[tuple[str, str]]] | None = None,
                 ttl_s: float = 3.0, clock: Callable[[], float] = time.monotonic) -> None:
        self.config = config
        self.windows_provider = windows_provider
        self.ttl_s = ttl_s
        self.clock = clock
        self._terms: list[str] = []
        self._at = -1e9
        self._lock = threading.Lock()
        self._refreshing = False

    @property
    def mode(self) -> str:
        mode = str(self.config.get("stt.bias_mode") or "context").lower()
        return mode if mode in BIAS_MODES else "context"

    def context_terms(self) -> list[str]:
        with self._lock:
            return list(self._terms)

    def refresh(self) -> list[str]:
        """Đọc lại cửa sổ đang mở (đồng bộ). Lỗi thì giữ danh sách cũ."""
        if self.windows_provider is None:
            return []
        try:
            windows = self.windows_provider()
            custom = [str(i.get("name", "")).strip() for i in (self.config.get("apps.custom") or [])
                      if isinstance(i, dict)]
            vocab = title_vocabulary([*(self.config.get("stt.hotwords") or []), *custom])
            terms = terms_from_windows(windows, vocab)[:int(self.config.get("stt.context_max_terms") or 12)]
        except Exception as exc:
            log.debug("Không đọc được ngữ cảnh cửa sổ: %s", exc)
            return self.context_terms()
        with self._lock:
            self._terms, self._at = terms, self.clock()
        return terms

    def refresh_async(self) -> None:
        """Gọi khi bắt đầu có tiếng nói: nhận dạng chạy sau khi anh nói xong nên kết quả thường kịp dùng."""
        if self.mode != "context" or self.windows_provider is None:
            return
        with self._lock:
            if self._refreshing or self.clock() - self._at < self.ttl_s:
                return
            self._refreshing = True

        def run() -> None:
            try:
                self.refresh()
            finally:
                with self._lock:
                    self._refreshing = False

        threading.Thread(target=run, name="nexa-stt-bias", daemon=True).start()


def win32_windows_provider(api: Any) -> Callable[[], list[tuple[str, str]]]:
    """Cửa sổ ứng dụng đang hiển thị theo thứ tự Z: [(tên tiến trình, tiêu đề)]."""
    def provider() -> list[tuple[str, str]]:
        import psutil
        names: dict[int, str] = {}
        out: list[tuple[str, str]] = []
        own = api.own_pid()
        for hwnd in api.enum_windows():
            try:
                if not api.is_visible(hwnd) or api.is_cloaked(hwnd):
                    continue
                title = api.get_title(hwnd)
                if not title:
                    continue
                pid = api.get_pid(hwnd)
                if pid == own:
                    continue
                if pid not in names:
                    try:
                        names[pid] = psutil.Process(pid).name()
                    except Exception:
                        names[pid] = ""
                out.append((names[pid], title))
            except Exception:
                continue
            if len(out) >= 40:
                break
        return out
    return provider
