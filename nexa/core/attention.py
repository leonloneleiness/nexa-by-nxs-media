"""Chú ý của anh qua webcam (chạy cục bộ, cùng luồng camera cử chỉ): có ngồi ở máy không + đang nhìn màn hình nào.

- Rời máy (không thấy mặt, không phím/chuột ~45 s): báo đếm ngược → tạm dừng video đang phát, khóa Windows.
  Quay lại (thấy mặt / mở khóa): phát tiếp video — chỉ khi chính NEXA đã dừng nó.
- Người thứ hai nhìn màn hình từ phía sau: thu nhỏ các cửa sổ nhạy cảm (ngân hàng, Zalo, .env…). Không tự mở lại.
- Hướng quay đầu → màn hình: lệnh giọng nói/cử chỉ tác động lên cửa sổ ở màn hình anh đang nhìn (head_target =
  "commands"), hoặc focus tự theo hướng nhìn khi anh không gõ phím/di chuột (head_target = "auto").

Không lưu ảnh: chỉ vài con số mỗi khung (góc quay đầu, kích thước mặt). Mở khóa máy vẫn do anh (PIN/Windows Hello).
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

from nexa.utils.logging import get_logger
from nexa.utils.text import fold
from nexa.vision.head_monitor import HeadMonitorSelector, HeadParams
from nexa.vision.presence import AWAY, PresenceMonitor, PresenceParams, split_faces

log = get_logger("attention")


def _lock_workstation() -> bool:
    import ctypes
    try:
        return bool(ctypes.windll.user32.LockWorkStation())
    except Exception:
        log.exception("LockWorkStation lỗi")
        return False


def _session_locked() -> bool | None:
    from nexa.desktop.sleep_guard import session_locked
    return session_locked()


def monitor_key(m: Any) -> str:
    return getattr(m, "device_id", "") or m.device_name


class AttentionService:
    def __init__(self, config: Any, wm: Any, monitors: Any, media: Any, notify: Callable[[str, dict], None],
                 input_idle_s: Callable[[], float | None], can_act: Callable[[], bool],
                 camera_running: Callable[[], bool] = lambda: True,
                 move_cursor: Callable[[int, int], Any] | None = None,
                 cursor_pos: Callable[[], tuple[int, int]] | None = None,
                 lock: Callable[[], bool] = _lock_workstation,
                 session_locked: Callable[[], bool | None] = _session_locked,
                 run_async: Callable[[Callable[[], None], str], None] | None = None) -> None:
        self.config = config
        self.wm = wm
        self.monitors = monitors
        self.media = media
        self.notify = notify
        self.input_idle_s = input_idle_s
        self.can_act = can_act
        self.camera_running = camera_running
        self.move_cursor = move_cursor
        self.cursor_pos = cursor_pos
        self.lock = lock
        self.session_locked = session_locked
        self.run_async = run_async or (lambda fn, name: threading.Thread(target=fn, name=name, daemon=True).start())
        self.presence = PresenceMonitor(PresenceParams.from_config(self._presence_cfg()))
        self.head = HeadMonitorSelector(HeadParams.from_config(config.get("attention.head") or {}),
                                        self._load_centers())
        self._lock = threading.RLock()
        self._last_face_t: float | None = None
        self._paused_media = False           # NEXA dừng video lúc anh rời máy → phát tiếp khi quay lại
        self._locked_by_nexa = False
        self._resume_waiter: threading.Thread | None = None
        self._status_t = 0.0
        self._auto_key: str | None = None    # màn hình auto-focus đã theo lần cuối
        self._auto_busy = False
        self._voice_key: tuple[str, float] | None = None
        self._calib_queue: list[Any] = []
        self._calib_done: Callable[[bool, str], None] | None = None
        self._calib_results: list[str] = []
        self.last_follow = ""
        self._mon_cache: tuple[float, list] = (-1e9, [])

    # ----- cấu hình -----
    def _presence_cfg(self) -> dict:
        a = self.config.get("attention") or {}
        return {"away_after_s": a.get("away_after_s", 45), "warning_s": a.get("warning_s", 10)}

    def _load_centers(self) -> dict[str, tuple[float, float]]:
        raw = self.config.get("attention.head_calibration") or {}
        out = {}
        for k, v in raw.items():
            try:
                out[str(k)] = (float(v[0]), float(v[1]))
            except Exception:
                continue
        return out

    def reload(self) -> None:
        self.presence.params = PresenceParams.from_config(self._presence_cfg())
        self.head.set_centers(self._load_centers())

    @property
    def presence_enabled(self) -> bool:
        return bool(self.config.get("attention.presence_enabled"))

    @property
    def head_mode(self) -> str:
        mode = str(self.config.get("attention.head_target") or "off").lower()
        return mode if mode in ("off", "commands", "auto") else "off"

    def wants_faces(self) -> bool:
        return self.presence_enabled or self.head_mode != "off" or bool(self._calib_queue)

    # ----- khung camera (luồng camera: không được chặn lâu) -----
    def on_faces(self, faces: list, t: float) -> None:
        idle = self.input_idle_s()
        owner_seen, onlookers = split_faces([f.size for f in faces], self.presence.params)
        owner = faces[0] if owner_seen else None
        with self._lock:
            self._last_face_t = t
            key = self.head.update(t, owner.yaw if owner else None, owner.pitch if owner else None)
            events = self.presence.update(t, owner_seen, onlookers, idle) if self.presence_enabled else []
        for ev in events:
            self._on_presence(ev.kind, ev.seconds)
        if self.head_mode == "auto" and key is not None and self.head.looking_at(t) == key:
            self._maybe_auto_follow(key, t, idle)
        if t - self._status_t >= 0.2:
            self._status_t = t
            self.notify("attention_status", self.status(t))

    def camera_stopped(self) -> None:
        with self._lock:
            self.presence.reset(time.monotonic())
            self.head.cancel_calibration()
        self._calib_queue = []
        self.notify("attention_status", self.status(time.monotonic()))

    # ----- có mặt / vắng -----
    def _on_presence(self, kind: str, seconds: float) -> None:
        a = self.config.get("attention") or {}
        log.info("Có mặt: %s (%.1f s)", kind, seconds)
        if kind == "warning":
            if a.get("lock_on_away", True) or a.get("pause_media_on_away", True):
                self._toast(f"Em không thấy anh — {'khóa máy' if a.get('lock_on_away', True) else 'dừng video'} "
                            f"sau {round(seconds)} giây. Anh cử động hoặc nhìn vào camera để hủy.")
        elif kind == "cancel":
            self._toast("Đã hủy — em thấy anh rồi.")
        elif kind == "away":
            self.run_async(self._do_away, "nexa-away")
        elif kind == "back":
            self.run_async(self._do_back, "nexa-back")
        elif kind == "onlooker":
            if a.get("privacy_guard", True):
                self.run_async(self._do_privacy, "nexa-privacy")
        self.notify("attention_event", {"kind": kind, "seconds": round(seconds, 1)})

    def _do_away(self) -> None:
        a = self.config.get("attention") or {}
        if not self.can_act():
            log.info("Rời máy nhưng điều khiển đang tạm khóa — không làm gì")
            return
        if a.get("pause_media_on_away", True):
            try:
                r = self.media.pause()
                self._paused_media = bool(r.ok and not r.data.get("no_op"))
                if self._paused_media:
                    log.info("Rời máy: đã tạm dừng video")
            except Exception:
                log.exception("Không dừng được video khi rời máy")
        if a.get("lock_on_away", True) and self.session_locked() is not True:
            self._locked_by_nexa = self.lock()
            log.info("Rời máy: khóa Windows %s", "OK" if self._locked_by_nexa else "LỖI")

    def _do_back(self) -> None:
        if not self._paused_media:
            self._locked_by_nexa = False
            return
        if self._resume_waiter is not None and self._resume_waiter.is_alive():
            return

        def wait_then_resume() -> None:
            deadline = time.monotonic() + 30 * 60
            while time.monotonic() < deadline and self._paused_media:
                if self.session_locked() is not True:
                    time.sleep(0.8)                  # để desktop hiện ra hẳn
                    self._paused_media = False
                    self._locked_by_nexa = False
                    if not (self.config.get("attention.resume_media_on_back", True) and self.can_act()):
                        return
                    try:
                        if self.media.can_resume():
                            r = self.media.resume()
                            if r.ok and not r.data.get("no_op"):
                                self._toast("Chào anh quay lại — em phát tiếp video.")
                    except Exception:
                        log.exception("Không phát tiếp được video")
                    return
                time.sleep(1.0)
        self._resume_waiter = threading.Thread(target=wait_then_resume, name="nexa-resume-wait", daemon=True)
        self._resume_waiter.start()

    # ----- người phía sau -----
    def sensitive_windows(self) -> list[int]:
        a = self.config.get("attention") or {}
        procs = {str(p).lower() for p in a.get("sensitive_processes") or []}
        words = [fold(str(w)) for w in a.get("sensitive_titles") or [] if str(w).strip()]
        out = []
        for info in self.wm.list_windows(limit=80):
            if info.get("minimized"):
                continue
            title = fold(info.get("title") or "")
            if (info.get("process") or "").lower() in procs or any(w and w in title for w in words):
                out.append(info["hwnd"])
        return out

    def _do_privacy(self) -> None:
        if not self.can_act():
            return
        hidden = []
        for hwnd in self.sensitive_windows():
            try:
                r = self.wm.minimize(hwnd)
                if r.ok and not r.data.get("no_op"):
                    hidden.append(r.data.get("title") or "")
            except Exception:
                log.exception("Không thu nhỏ được cửa sổ nhạy cảm")
        if hidden:
            log.info("Có người phía sau: đã thu nhỏ %d cửa sổ nhạy cảm", len(hidden))
            self._toast(f"Có người nhìn màn hình phía sau — em đã thu nhỏ {len(hidden)} cửa sổ nhạy cảm. "
                        "Nói 'khôi phục cửa sổ' để mở lại.")
        else:
            self._toast("Có người nhìn màn hình phía sau anh.")

    # ----- hướng nhìn → màn hình -----
    def _monitor_list(self) -> list:
        t, mons = self._mon_cache
        now = time.monotonic()
        if now - t > 2.0 or not mons:
            try:
                mons = self.monitors.refresh()
            except Exception:
                log.exception("Không đọc được danh sách màn hình")
            self._mon_cache = (now, mons)
        return mons

    def _monitor_for_key(self, key: str | None):
        if not key:
            return None
        for m in self._monitor_list():
            if monitor_key(m) == key or m.device_name == key:
                return m
        return None

    def looking_at(self):
        """MonitorInfo anh đang nhìn (None = chưa hiệu chuẩn / không thấy mặt / camera tắt)."""
        if not self.camera_running() or self.head_mode == "off":
            return None
        t = self._last_face_t
        if t is None:
            return None
        with self._lock:
            key = self.head.looking_at(t)
        if key is None or time.monotonic() - t > 1.0:
            return None
        return self._monitor_for_key(key)

    def capture_for_voice(self) -> None:
        """Lúc anh bắt đầu nói: nhớ màn hình đang nhìn (lệnh xử lý xong mới áp dụng)."""
        if self.head_mode == "off":
            return
        m = self.looking_at()
        self._voice_key = (monitor_key(m), time.monotonic()) if m is not None else None

    def apply_for_voice(self) -> None:
        """Trước khi chạy lệnh giọng nói: đưa cửa sổ ở màn hình anh nhìn lúc nói lên foreground."""
        vk, self._voice_key = self._voice_key, None
        if vk is None or time.monotonic() - vk[1] > 30 or self.head_mode == "off":
            return
        m = self._monitor_for_key(vk[0])
        if m is not None:
            self.follow(m, "lệnh giọng nói")

    def before_gesture(self) -> None:
        """Bắt đầu một cử chỉ lệnh (luồng camera): chọn cửa sổ ở màn hình anh đang nhìn trước khi chụp trạng thái."""
        if self.head_mode == "off":
            return
        m = self.looking_at()
        if m is not None:
            self.follow(m, "cử chỉ")

    def follow(self, m: Any, why: str) -> bool:
        if not self.can_act():
            return False
        try:
            r = self.wm.follow_attention(m.device_name)
        except Exception:
            log.exception("Không chuyển được sang màn hình đang nhìn")
            return False
        if not r.ok:
            log.info("Theo hướng nhìn (%s): %s", why, r.message)
            return False
        if r.data.get("no_op"):
            self._cursor_to(m, r.data.get("hwnd"))
            return True
        self.last_follow = f"{why}: {m.device_name}"
        log.info("Theo hướng nhìn (%s) → %s: %s", why, m.device_name, r.message)
        self._cursor_to(m, r.data.get("hwnd"))
        if r.data.get("rect"):
            self.notify("overlay", {"kind": "highlight", "rect": r.data["rect"], "text": "👀 " + r.message})
        return True

    def _cursor_to(self, m: Any, hwnd: int | None) -> None:
        """Cuộn chuột đi theo con trỏ: con trỏ đang ở màn hình khác thì đưa về giữa cửa sổ vừa chọn."""
        if not self.config.get("attention.head_move_cursor", True) or self.move_cursor is None \
                or self.cursor_pos is None:
            return
        try:
            x, y = self.cursor_pos()
            l, t, r, b = m.rect
            if l <= x < r and t <= y < b:
                return
            if hwnd:
                wl, wt, wr, wb = self.wm.api.get_rect(hwnd)
                cx, cy = (max(wl, l) + min(wr, r)) // 2, (max(wt, t) + min(wb, b)) // 2
            else:
                cx, cy = (l + r) // 2, (t + b) // 2
            self.move_cursor(int(cx), int(cy))
        except Exception:
            log.exception("Không đưa được con trỏ sang màn hình đang nhìn")

    def _maybe_auto_follow(self, key: str, t: float, idle: float | None) -> None:
        dwell = float(self.config.get("attention.head_auto_dwell_s") or 0.8)
        if key == self._auto_key or self._auto_busy or t - self.head.since < dwell:
            return
        if idle is not None and idle < 1.0:
            return                                   # anh đang gõ/di chuột: không giành focus
        m = self._monitor_for_key(key)
        if m is None:
            return
        self._auto_key = key
        self._auto_busy = True

        def run() -> None:
            try:
                self.follow(m, "tự động")
            finally:
                self._auto_busy = False
        self.run_async(run, "nexa-head-follow")

    # ----- hiệu chuẩn hướng nhìn -----
    def calibrate(self, on_done: Callable[[bool, str], None]) -> tuple[bool, str]:
        if not self.camera_running():
            return False, "Cần bật camera trước (nút Bật camera hoặc nói 'bật điều khiển bằng tay')."
        mons = self.monitors.refresh()
        if len(mons) < 2:
            return False, "Chỉ có một màn hình nên không cần hiệu chuẩn hướng nhìn."
        mons = sorted(mons, key=lambda m: (m.rect[0], m.rect[1]))
        self._calib_queue = list(mons)
        self._calib_done = on_done
        self._calib_results = []
        with self._lock:
            self.head.set_centers({})
        self._calib_next()
        return True, f"Hiệu chuẩn {len(mons)} màn hình: nhìn vào giữa màn hình đang sáng khung, mỗi màn hình ~2 giây."

    def _calib_next(self) -> None:
        if not self._calib_queue:
            centers = {k: [round(v[0], 2), round(v[1], 2)] for k, v in self.head.centers.items()}
            self.config.set("attention.head_calibration", centers)
            self.config.save()
            msg = "Đã hiệu chuẩn hướng nhìn: " + "; ".join(self._calib_results) + "."
            if self.head_mode == "off":
                self.config.set("attention.head_target", "commands")
                self.config.save()
                msg += " Đã bật chọn màn hình theo hướng quay đầu."
            self._finish_calibration(True, msg)
            return
        m = self._calib_queue[0]
        label = m.device_name.replace("\\\\.\\", "").replace("\\", "").replace(".", "")
        self.notify("overlay", {"kind": "highlight", "rect": list(m.rect), "text": f"👀 Nhìn vào giữa {label}"})

        def start() -> None:
            time.sleep(1.0)                          # để anh kịp quay đầu sang màn hình này
            if not self._calib_queue or self._calib_queue[0] is not m:
                return
            with self._lock:
                self.head.start_calibration(monitor_key(m), self._last_face_t or time.monotonic(), self._calib_step)
        self.run_async(start, "nexa-head-calib")

    def _calib_step(self, key: str, center: tuple[float, float] | None, msg: str) -> None:
        # Gọi từ luồng camera (trong head.update) — việc tiếp theo chạy ở luồng khác.
        if not self._calib_queue:
            return
        m = self._calib_queue[0]
        if center is None:
            self._calib_queue = []
            self.run_async(lambda: self._finish_calibration(False, msg), "nexa-head-calib")
            return
        self._calib_queue.pop(0)
        label = m.device_name.replace("\\\\.\\", "").replace("\\", "").replace(".", "")
        self._calib_results.append(f"{label} {msg}")
        self.run_async(self._calib_next, "nexa-head-calib")

    def _finish_calibration(self, ok: bool, msg: str) -> None:
        if not ok:
            self.head.set_centers(self._load_centers())
        done, self._calib_done = self._calib_done, None
        log.info("Hiệu chuẩn hướng nhìn: %s", msg)
        if done:
            done(ok, msg)

    # ----- trạng thái -----
    def status(self, t: float | None = None) -> dict[str, Any]:
        t = time.monotonic() if t is None else t
        with self._lock:
            st = self.head.status(t)
            st.update(self.presence.status(t))
        key = st.get("head_monitor")
        m = self._monitor_for_key(key) if key else None
        st.update({"presence_enabled": self.presence_enabled, "head_target": self.head_mode,
                   "head_monitor_name": m.device_name.replace("\\\\.\\", "") if m is not None else "",
                   "head_calibrated": sorted(self.head.centers), "face_active": self._last_face_t is not None
                   and time.monotonic() - self._last_face_t < 1.5, "last_follow": self.last_follow,
                   "away": st.get("presence") == AWAY})
        return st

    def _toast(self, text: str) -> None:
        self.notify("overlay", {"kind": "toast", "text": text})
