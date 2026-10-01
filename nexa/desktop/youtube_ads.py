"""Bỏ qua quảng cáo YouTube: bấm nút "Bỏ qua" / "Skip" của trình phát qua UI Automation — đúng như anh tự bấm.

Không chặn quảng cáo, không chèn script: chỉ bấm nút bỏ qua khi YouTube cho phép. Quảng cáo chưa cho bỏ qua thì chờ
(tối đa `timeout`) rồi bấm ngay khi nút hiện ra. Chỉ đọc được nội dung của TAB ĐANG XEM trong mỗi cửa sổ trình duyệt,
nên nếu YouTube nằm ở tab khác thì chọn tab đó trước.
AutoSkipper (tùy chọn, mặc định tắt): cứ vài giây kiểm tra các cửa sổ đang xem YouTube và tự bấm "Bỏ qua".

Nhanh: chỉ đọc cây giao diện của TRÌNH PHÁT (#movie_player, ~25–60 phần tử) thay vì cả trang YouTube (hàng nghìn
phần tử: bình luận, video đề xuất), lấy tên/lớp HTML theo lô bằng CacheRequest. Chromium đưa `id` HTML thành
AutomationId và `class` thành ClassName nên nhận quảng cáo chính xác: YouTube gắn lớp `ad-showing` vào trình phát
khi đang chiếu quảng cáo, nút bỏ qua có lớp `ytp-skip-ad-button` (bản cũ: `ytp-ad-skip-button…`).
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

from nexa.core.events import ToolResult
from nexa.utils.logging import get_logger
from nexa.utils.text import fold

log = get_logger("youtube_ads")

SKIP_RE = re.compile(r"^(bo qua|skip)( quang cao| ads?| video)?\W*$")
AD_RE = re.compile(r"\b(quang cao|duoc tai tro|sponsored)\b|^ad\b")
SKIP_CLASSES = ("ytp-skip-ad-button", "ytp-ad-skip-button")
AD_CLASSES = ("ytp-ad-", "ytp-skip-ad", "video-ads")
PLAYER_ID = "movie_player"


@dataclass
class PlayerState:
    ad: bool                 # đang chiếu quảng cáo
    skip: Any = None         # IUIAutomationElement của nút "Bỏ qua" đang hiện (None nếu chưa có)


def _is_skip(ctype_button: bool, name: str, cls: str) -> bool:
    return ctype_button and (any(c in cls for c in SKIP_CLASSES) or bool(SKIP_RE.match(fold(name))))


def classify(player_class: str, items: list[tuple[bool, str, str, bool]]) -> tuple[bool, int | None]:
    """Phần thuần logic (kiểm thử được): items = (là Button, tên, lớp HTML, ngoài màn hình).

    Trả về (đang có quảng cáo, chỉ số nút bỏ qua trong items hoặc None)."""
    ad = "ad-showing" in player_class.split()
    skip_idx = None
    for i, (is_button, name, cls, offscreen) in enumerate(items):
        if offscreen:
            continue
        if skip_idx is None and _is_skip(is_button, name, cls):
            skip_idx = i
        # Tên chỉ xét ở phần tử có lớp HTML riêng (nhãn "Được tài trợ", nút "Thông tin quảng cáo"…);
        # chữ phụ đề không có lớp nên lời bài hát có chữ "quảng cáo" không bị nhận nhầm.
        if not ad and (any(c in cls for c in AD_CLASSES) or ((cls or is_button) and AD_RE.search(fold(name)))):
            ad = True
    if skip_idx is not None:
        ad = True
    return ad, skip_idx


class _Player:
    """Tìm và nhớ trình phát YouTube theo cửa sổ; trang đổi (điều hướng, đổi tab) thì tìm lại."""

    def __init__(self) -> None:
        self._cache: dict[int, Any] = {}

    def get(self, hwnd: int):
        from nexa.desktop import uia
        iuia, UIA = uia.uia_core()
        el = self._cache.get(hwnd)
        if el is not None:
            try:
                r = el.CurrentBoundingRectangle
                if el.CurrentAutomationId == PLAYER_ID and r.right - r.left > 0:   # tab ẩn: khung rỗng
                    return el
            except Exception:
                pass
            self._cache.pop(hwnd, None)
        doc = uia.page_document(hwnd)
        if doc is None:
            return None
        cond = iuia.CreatePropertyCondition(UIA.UIA_AutomationIdPropertyId, PLAYER_ID)
        try:
            el = doc.FindFirst(UIA.TreeScope_Descendants, cond)
        except Exception:
            return None
        if not el:
            return None
        self._cache[hwnd] = el
        return el

    def forget(self, hwnd: int) -> None:
        self._cache.pop(hwnd, None)


_PLAYERS = _Player()


def player_state(hwnd: int) -> PlayerState | None:
    """Trạng thái quảng cáo của trình phát trong tab đang xem; None nếu tab đó không có trình phát YouTube."""
    from nexa.desktop import uia
    iuia, UIA = uia.uia_core()
    player = _PLAYERS.get(hwnd)
    if player is None:
        return None
    cr = iuia.CreateCacheRequest()
    for pid in (UIA.UIA_NamePropertyId, UIA.UIA_ControlTypePropertyId, UIA.UIA_ClassNamePropertyId,
                UIA.UIA_IsOffscreenPropertyId):
        cr.AddProperty(pid)
    try:
        player_class = player.CurrentClassName or ""
        arr = player.FindAllBuildCache(UIA.TreeScope_Descendants, iuia.CreateTrueCondition(), cr)
    except Exception:
        _PLAYERS.forget(hwnd)       # phần tử cũ không còn (trang vừa đổi)
        return None
    elems, items = [], []
    for k in range(arr.Length):
        e = arr.GetElement(k)
        try:
            items.append((e.CachedControlType == UIA.UIA_ButtonControlTypeId, (e.CachedName or "").strip(),
                          e.CachedClassName or "", bool(e.CachedIsOffscreen)))
            elems.append(e)
        except Exception:
            continue
    ad, idx = classify(player_class, items)
    return PlayerState(ad=ad, skip=elems[idx] if idx is not None else None)


def press(elem, click: bool = False) -> bool:
    """Bấm bằng Invoke (không đụng chuột); `click=True` = nhấp chuột thật khi Invoke không có tác dụng."""
    from nexa.desktop import uia
    w = uia.wrap(elem)
    try:
        if click:
            w.click_input()
        else:
            w.invoke()
        return True
    except Exception:
        try:
            w.click_input()
            return True
        except Exception:
            log.exception("Không bấm được nút bỏ qua quảng cáo")
            return False


# Giữ tên cũ cho code/kiểm thử khác.
def find_skip_button(hwnd: int):
    st = player_state(hwnd)
    return st.skip if st else None


def ad_showing(hwnd: int) -> bool:
    st = player_state(hwnd)
    return bool(st and st.ad)


def youtube_windows(wm: Any) -> list[int]:
    """Cửa sổ trình duyệt đang XEM tab YouTube (tiêu đề cửa sổ = tiêu đề tab đang xem)."""
    from nexa.desktop.uia import BROWSER_PROCESSES
    return [w["hwnd"] for w in wm.list_windows(limit=80)
            if w["process"].lower() in BROWSER_PROCESSES and "youtube" in fold(w["title"])]


def _bring_youtube_tab(wm: Any) -> list[int]:
    """Không có cửa sổ nào đang xem YouTube: chọn tab YouTube đầu tiên (không dùng chuột)."""
    from nexa.desktop import uia
    for w in wm.list_windows(limit=80):
        if w["process"].lower() not in uia.BROWSER_PROCESSES:
            continue
        for tab in uia.browser_tabs(w["hwnd"]):
            if "youtube" in fold(uia.tab_title(tab)):
                try:
                    tab.select()
                except Exception:
                    continue
                # Đợi trang của tab vừa chọn hiện trình phát (thường < 0,5 s) thay vì chờ cố định.
                for _ in range(15):
                    time.sleep(0.1)
                    if player_state(w["hwnd"]) is not None:
                        break
                return [w["hwnd"]]
    return []


def skip_ad(wm: Any, timeout: float = 12.0, cancelled: Callable[[], bool] = lambda: False,
            sleep: Callable[[float], None] = time.sleep, state: Callable[[int], PlayerState | None] | None = None,
            press_fn: Callable[..., bool] | None = None) -> ToolResult:
    state = state or player_state
    press_fn = press_fn or press
    windows = youtube_windows(wm) or _bring_youtube_tab(wm)
    if not windows:
        return ToolResult.failure("Em không thấy tab YouTube nào đang mở.", "no_youtube")
    started = time.monotonic()
    deadline = started + timeout
    saw_player = pressed = False
    presses = 0
    while not cancelled():
        any_ad = False
        for hwnd in windows:
            try:
                st = state(hwnd)
            except Exception:
                log.debug("Đọc trình phát lỗi", exc_info=True)
                st = None
            if st is None:
                continue
            saw_player = True
            if st.skip is not None:
                any_ad = True
                # Nút vẫn còn sau 2 lần Invoke (trang chưa nhận): nhấp chuột thật như anh tự bấm.
                if press_fn(st.skip, click=presses >= 2):
                    pressed = True
                    presses += 1
                continue                 # vòng sau kiểm tra quảng cáo đã hết chưa (có thể còn quảng cáo thứ 2)
            if st.ad:
                any_ad = True
        if pressed and not any_ad and saw_player:
            log.info("Đã bỏ qua quảng cáo sau %.1f s", time.monotonic() - started)
            return ToolResult.success("Đã bỏ qua quảng cáo.", verified=True)
        if not any_ad and not pressed:
            if saw_player:
                return ToolResult.success("Video YouTube hiện không có quảng cáo.", verified=True, no_op=True)
            if time.monotonic() - started > 2.0:
                return ToolResult.failure("Tab YouTube đang xem không có video nào đang mở.", "no_player")
        if time.monotonic() >= deadline:
            break
        sleep(0.25)
    if cancelled():
        return ToolResult.failure("Đã hủy bỏ qua quảng cáo.", "cancelled")
    if pressed:
        return ToolResult.success("Đã bỏ qua quảng cáo, nhưng vẫn còn quảng cáo tiếp theo chưa cho bỏ qua.",
                                  verified=False)
    return ToolResult.failure(f"Quảng cáo này chưa cho bỏ qua (em đã chờ {timeout:.0f} giây).", "not_skippable")


class AutoSkipper:
    """Tự bấm "Bỏ qua" khi đang xem YouTube. Chạy luồng nền rất nhẹ: chỉ quét trình phát của tab đang xem."""

    def __init__(self, wm: Any, interval_s: float = 1.0) -> None:
        self.wm = wm
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.skipped = 0

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="nexa-adskip", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass
        while not self._stop.wait(self.interval_s):
            for hwnd in youtube_windows(self.wm):
                try:
                    st = player_state(hwnd)
                    if st is not None and st.skip is not None and press(st.skip):
                        self.skipped += 1
                        log.info("Tự bỏ qua quảng cáo YouTube (lần %d)", self.skipped)
                except Exception:
                    log.debug("AutoSkipper lỗi một lượt", exc_info=True)
