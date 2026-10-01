"""Điều khiển YouTube theo mục tiêu đã gắn, với Pause/Resume riêng và đọc lại trạng thái.

Backend:
- "bridge" (khuyến nghị): extension NEXA Bridge gọi video.pause()/video.play() trên đúng tab
  YouTube đã gắn, kiểm tra videoId trước khi thao tác, đọc lại video.paused. Hoạt động cả khi trình
  duyệt không có focus hoặc nằm ở màn hình còn lại. Không giành focus, không gửi phím Space/K.
- "gsmtc": Windows Global System Media Transport Controls (TryPauseAsync/TryPlayAsync riêng biệt).
  Chỉ xác định được ứng dụng (vd. MSEdge) + tiêu đề media, KHÔNG xác định được tab; NEXA kiểm tra
  tiêu đề không đổi trước mỗi lệnh.

Tự chọn mục tiêu (không cần bấm "Gắn tab"): "tạm dừng" lấy video ĐANG PHÁT, "phát tiếp" lấy video ĐANG
DỪNG; ưu tiên video NEXA vừa mở, rồi mục tiêu đã gắn, rồi bridge, rồi mới nhất. Với GSMTC chỉ nhận phiên của
trình duyệt — Spotify hay ứng dụng khác không bao giờ bị động tới.
"""
from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from nexa.core.events import ToolResult
from nexa.utils.logging import get_logger
from nexa.utils.text import fold, truncate

log = get_logger("media")

BROWSER_APPS = ("msedge", "chrome", "firefox", "brave", "opera", "coccoc", "browser", "vivaldi")


def is_browser_app(app: str) -> bool:
    a = (app or "").lower()
    return any(b in a for b in BROWSER_APPS)


class Playback(str, Enum):
    PLAYING = "playing"
    PAUSED = "paused"
    UNKNOWN = "unknown"
    GONE = "gone"          # tab/phiên đã đóng hoặc video đã đổi


@dataclass(frozen=True)
class MediaTarget:
    backend: str           # bridge | gsmtc
    key: str               # bridge: "<browser>:<tabId>", gsmtc: SourceAppUserModelId
    video_id: str          # bridge: YouTube videoId; gsmtc: ""
    title: str
    app: str = ""
    # Trạng thái lúc liệt kê (chỉ để chọn mục tiêu tự động, không thuộc danh tính).
    playing: bool | None = field(default=None, compare=False)
    updated: float = field(default=0.0, compare=False)

    @property
    def identity(self) -> tuple[str, str, str, str]:
        # Với GSMTC, tiêu đề là phần duy nhất giúp phân biệt nội dung.
        return (self.backend, self.key, self.video_id, self.title if self.backend == "gsmtc" else "")

    def to_dict(self) -> dict[str, Any]:
        return {"backend": self.backend, "key": self.key, "video_id": self.video_id, "title": self.title,
                "app": self.app, "id": f"{self.backend}|{self.key}|{self.video_id}|{self.title}"}


class MediaBackend(Protocol):
    name: str

    def list_targets(self) -> list[MediaTarget]: ...
    def state(self, target: MediaTarget) -> tuple[Playback, str]: ...
    def pause(self, target: MediaTarget) -> tuple[Playback, str]: ...
    def play(self, target: MediaTarget) -> tuple[Playback, str]: ...


class BridgeBackend:
    name = "bridge"

    def __init__(self, server: Any) -> None:
        self.server = server

    def list_targets(self) -> list[MediaTarget]:
        return [MediaTarget("bridge", t.key, t.video_id, t.title, t.browser,
                            playing=None if t.paused is None else not t.paused, updated=t.updated)
                for t in self.server.tabs() if t.video_id]

    def _run(self, target: MediaTarget, action: str) -> tuple[Playback, str]:
        res = self.server.command(target.key, target.video_id, action)
        err = res.get("error") or ""
        if err in ("tab_gone", "video_changed", "no_video"):
            return Playback.GONE, err
        if not res.get("ok"):
            state = res.get("state") or {}
            if "paused" in state:
                return (Playback.PAUSED if state["paused"] else Playback.PLAYING), err or "failed"
            return Playback.UNKNOWN, err or "failed"
        state = res.get("state") or {}
        if state.get("videoId") and state.get("videoId") != target.video_id:
            return Playback.GONE, "video_changed"
        paused = state.get("paused")
        if paused is None:
            return Playback.UNKNOWN, "no_state"
        return (Playback.PAUSED if paused else Playback.PLAYING), ""

    def state(self, target: MediaTarget) -> tuple[Playback, str]:
        return self._run(target, "state")

    def pause(self, target: MediaTarget) -> tuple[Playback, str]:
        return self._run(target, "pause")

    def play(self, target: MediaTarget) -> tuple[Playback, str]:
        return self._run(target, "play")


class GsmtcBackend:
    """Windows GSMTC qua gói winrt-Windows.Media.Control. Chạy vòng asyncio riêng trong một luồng."""
    name = "gsmtc"
    PLAYING, PAUSED = 4, 5

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, name="nexa-gsmtc", daemon=True)
        self._thread.start()
        self.available = True
        try:
            import importlib
            getattr(importlib.import_module("winrt.windows.media.control"), "GlobalSystemMediaTransportControlsSessionManager")
        except Exception:
            self.available = False

    def _call(self, awaitable, timeout: float = 4.0):
        # Thao tác WinRT (IAsyncOperation) không phải coroutine: bọc lại để chạy trên vòng asyncio riêng.
        loop = getattr(self, "_loop", None)
        if loop is None:
            if asyncio.iscoroutine(awaitable):
                awaitable.close()
            raise RuntimeError("Vòng asyncio GSMTC chưa chạy")

        async def run():
            return await awaitable
        return asyncio.run_coroutine_threadsafe(run(), loop).result(timeout)

    async def _sessions(self):
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as M
        mgr = await M.request_async()
        out = []
        for s in mgr.get_sessions():
            try:
                props = await s.try_get_media_properties_async()
                out.append((s, s.source_app_user_model_id, props.title or ""))
            except Exception:
                continue
        return out

    def list_targets(self) -> list[MediaTarget]:
        if not self.available:
            return []
        try:
            sessions = self._call(self._sessions())
        except Exception:
            log.exception("Không đọc được phiên media Windows")
            return []
        out = []
        for s, app, title in sessions:
            try:
                st = self._status(s)
            except Exception:
                st = Playback.UNKNOWN
            out.append(MediaTarget("gsmtc", app, "", title, app,
                                   playing=None if st == Playback.UNKNOWN else st == Playback.PLAYING))
        return out

    def _find(self, target: MediaTarget):
        for s, app, title in self._call(self._sessions()):
            if app == target.key and title == target.title:
                return s
        return None

    def _status(self, session) -> Playback:
        st = int(session.get_playback_info().playback_status)
        return Playback.PLAYING if st == self.PLAYING else Playback.PAUSED if st == self.PAUSED else Playback.UNKNOWN

    def state(self, target: MediaTarget) -> tuple[Playback, str]:
        s = self._find(target)
        return (self._status(s), "") if s is not None else (Playback.GONE, "session_gone")

    def _act(self, target: MediaTarget, pause: bool) -> tuple[Playback, str]:
        s = self._find(target)
        if s is None:
            return Playback.GONE, "session_gone"
        ok = self._call(s.try_pause_async() if pause else s.try_play_async())
        want = Playback.PAUSED if pause else Playback.PLAYING
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            cur = self._status(s)
            if cur == want:
                return cur, ""
            time.sleep(0.1)
        return self._status(s), "" if ok else "refused"

    def pause(self, target: MediaTarget) -> tuple[Playback, str]:
        return self._act(target, True)

    def play(self, target: MediaTarget) -> tuple[Playback, str]:
        return self._act(target, False)


class MediaController:
    def __init__(self, backends: dict[str, MediaBackend], preferred: str = "auto") -> None:
        self.backends = backends
        self.preferred = preferred
        self._lock = threading.RLock()
        self.bound: MediaTarget | None = None
        self.paused_by_nexa: MediaTarget | None = None
        self.last_state: Playback = Playback.UNKNOWN
        self.listeners: list = []
        self._hint: tuple[str, str, float] | None = None   # (video_id, tiêu đề fold, lúc mở) video NEXA vừa mở

    # ----- tự chọn mục tiêu -----
    def expect(self, video_id: str = "", title: str = "") -> None:
        """Ghi nhận video NEXA vừa mở để lần tạm dừng/phát tiếp sau ưu tiên đúng video đó."""
        with self._lock:
            self._hint = (video_id or "", fold(title or "")[:40], time.monotonic())

    def _matches_hint(self, t: MediaTarget) -> bool:
        h = self._hint
        if h is None or time.monotonic() - h[2] > 6 * 3600:
            return False
        vid, title, _ = h
        return bool((vid and t.video_id == vid) or (title[:24] and title[:24] in fold(t.title)))

    def _auto_target(self, want_playing: bool) -> MediaTarget | None:
        cands = [t for t in self.list_targets()
                 if t.playing is want_playing and (t.backend != "gsmtc" or is_browser_app(t.app))]
        if not cands:
            return None
        bound = self.bound

        def rank(t: MediaTarget):
            return (self._matches_hint(t), bound is not None and t.identity == bound.identity,
                    t.backend == "bridge", t.updated)
        return max(cands, key=rank)

    def _adopt(self, t: MediaTarget, why: str) -> None:
        with self._lock:
            changed = self.bound is None or self.bound.identity != t.identity
            self.bound = t
            if changed:
                self.paused_by_nexa = None
        if changed:
            log.info("Tự chọn video (%s): %s [%s]", why, truncate(t.title, 60), t.backend)
            self._notify()

    # ----- mục tiêu -----
    def list_targets(self) -> list[MediaTarget]:
        out: list[MediaTarget] = []
        order = ["bridge", "gsmtc"] if self.preferred in ("auto", "bridge") else ["gsmtc", "bridge"]
        for name in order:
            b = self.backends.get(name)
            if b is None or (self.preferred not in ("auto", name)):
                continue
            try:
                out.extend(b.list_targets())
            except Exception:
                log.exception("Backend %s lỗi khi liệt kê", name)
        return out

    def bind(self, target: MediaTarget) -> ToolResult:
        with self._lock:
            self.bound = target
            self.paused_by_nexa = None
        self._notify()
        return ToolResult.success(f"Đã gắn video: {truncate(target.title, 60)}.", verified=True, target=target.to_dict())

    def bind_by_id(self, target_id: str) -> ToolResult:
        for t in self.list_targets():
            if t.to_dict()["id"] == target_id:
                return self.bind(t)
        return ToolResult.failure("Không còn thấy mục tiêu đã chọn. Anh làm mới danh sách.", "not_found")

    def unbind(self, reason: str = "") -> None:
        with self._lock:
            self.bound = None
            self.paused_by_nexa = None
        if reason:
            log.info("Bỏ gắn media: %s", reason)
        self._notify()

    def can_resume(self) -> bool:
        with self._lock:
            return self.paused_by_nexa is not None and self.bound is not None and \
                self.paused_by_nexa.identity == self.bound.identity

    def on_bridge_event(self, ev: dict) -> None:
        with self._lock:
            b = self.bound
            if b is None or b.backend != "bridge":
                return
            if ev.get("type") in ("tab_closed",) and ev.get("key") == b.key:
                self.bound = None
                self.paused_by_nexa = None
                reason = "tab đã đóng"
            elif ev.get("type") == "tab_update" and ev.get("key") == b.key and ev.get("video_id") != b.video_id:
                self.bound = None
                self.paused_by_nexa = None
                reason = "tab đã chuyển sang video khác"
            elif ev.get("type") == "disconnected" and b.key in (ev.get("keys") or []):
                self.bound = None
                self.paused_by_nexa = None
                reason = "trình duyệt ngắt kết nối"
            else:
                return
        log.info("Hủy mục tiêu YouTube: %s", reason)
        self._notify()

    # ----- điều khiển -----
    def _backend(self, t: MediaTarget) -> MediaBackend | None:
        return self.backends.get(t.backend)

    def pause(self) -> ToolResult:
        with self._lock:
            t = self.bound
        backend = self._backend(t) if t is not None else None
        state, err = backend.state(t) if backend is not None else (Playback.GONE, "no_target")
        if state != Playback.PLAYING:
            # Mục tiêu cũ đã mất / đang dừng: nếu có video KHÁC đang phát thì chuyển sang nó.
            auto = self._auto_target(want_playing=True)
            if auto is not None:
                self._adopt(auto, "đang phát")
                t, backend = auto, self._backend(auto)
                state, err = backend.state(t)
            elif state == Playback.GONE:
                if t is not None:
                    self.unbind(err)
                return ToolResult.failure("Em không thấy video nào đang phát trong trình duyệt.", "no_target")
        if state == Playback.PAUSED:
            self.last_state = state
            self._notify()
            return ToolResult.success("Video đang dừng sẵn, em giữ nguyên.", verified=True, no_op=True,
                                      state=state.value, title=t.title)
        if state == Playback.UNKNOWN:
            return ToolResult.failure("Em không đọc được trạng thái video nên không thao tác.", "unknown_state")
        new_state, err = backend.pause(t)
        self.last_state = new_state
        if new_state == Playback.PAUSED:
            with self._lock:
                if self.bound is not None and self.bound.identity == t.identity:
                    self.paused_by_nexa = t
            self._notify()
            return ToolResult.success(f"Đã tạm dừng: {truncate(t.title, 60)}.", verified=True, state="paused",
                                      title=t.title)
        if new_state == Playback.GONE:
            self.unbind(err)
        self._notify()
        return ToolResult.failure("Trình duyệt chưa tạm dừng video.", "not_verified", state=new_state.value)

    def resume(self) -> ToolResult:
        with self._lock:
            t = self.bound
        backend = self._backend(t) if t is not None else None
        state, err = backend.state(t) if backend is not None else (Playback.GONE, "no_target")
        if state == Playback.GONE:
            if t is not None:
                self.unbind(err)
            auto = self._auto_target(want_playing=False)
            if auto is None:
                return ToolResult.failure("Em không thấy video nào đang dừng để phát tiếp.", "no_paused_target")
            self._adopt(auto, "đang dừng")
            t, backend = auto, self._backend(auto)
            state, err = backend.state(t)
            if state == Playback.GONE:
                self.unbind(err)
                return ToolResult.failure("Video vừa chọn không còn (tab đóng hoặc đổi video).", "target_gone")
        if state == Playback.PLAYING:
            with self._lock:
                self.paused_by_nexa = None
            self.last_state = state
            self._notify()
            return ToolResult.success("Video đang phát sẵn, em giữ nguyên.", verified=True, no_op=True, state="playing")
        new_state, err = backend.play(t)
        self.last_state = new_state
        if new_state == Playback.PLAYING:
            with self._lock:
                self.paused_by_nexa = None
            self._notify()
            return ToolResult.success(f"Đã phát tiếp: {truncate(t.title, 60)}.", verified=True, state="playing",
                                      title=t.title)
        self._notify()
        if err == "NotAllowedError":
            return ToolResult.failure("Trình duyệt từ chối tự phát (chính sách autoplay). Anh bấm vào video một lần.",
                                      "play_refused")
        return ToolResult.failure("Trình duyệt chưa phát tiếp video.", "not_verified", state=new_state.value)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"bound": self.bound.to_dict() if self.bound else None,
                    "can_resume": self.paused_by_nexa is not None,
                    "last_state": self.last_state.value}

    def _notify(self) -> None:
        for fn in list(self.listeners):
            try:
                fn(self.status())
            except Exception:
                log.exception("Listener media lỗi")
