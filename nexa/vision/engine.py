"""Nối camera → landmarks → đặc trưng/quỹ đạo → máy trạng thái cử chỉ → router.

Camera chỉ bật khi người dùng bật chế độ cử chỉ. Tắt camera, đổi tay điều khiển, mất tay hoặc dừng
khẩn cấp đều xóa ứng viên chuyển động trong máy trạng thái.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

from nexa.vision.air_mouse import MouseParams, mouse_frame
from nexa.vision.gesture_features import POSE_LABELS_VI, Pose, classify
from nexa.vision.gesture_state_machine import GestureParams, GestureStateMachine, Observation
from nexa.utils.logging import get_logger

log = get_logger("gesture")

HAND_CONNECTIONS = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11),
                    (11, 12), (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17)]


class GestureEngine:
    def __init__(self, config: Any, models_dir: Path, window_manager: Any, router: Any,
                 on_status: Callable[[dict], None] | None = None, air_mouse: Any = None,
                 on_failsafe: Callable[[], None] | None = None) -> None:
        self.config = config
        self.air_mouse = air_mouse          # chuột bằng tay (nexa/vision/air_mouse.py); None = không có
        self.on_failsafe = on_failsafe
        self.models_dir = models_dir
        self.wm = window_manager
        self.router = router
        self.on_status = on_status
        self.camera = None
        self.tracker = None
        self.sm = GestureStateMachine(GestureParams.from_config(config.gestures),
                                      on_candidate_start=self._snapshot)
        self._thread: threading.Thread | None = None
        self._running = False
        self._paused = False
        self._lock = threading.Lock()
        self._preview: np.ndarray | None = None
        self._preview_seq = 0
        self.preview_enabled = False   # chỉ vẽ preview khi bảng Cử chỉ đang mở (tiết kiệm CPU)
        self.fps = 0.0
        self.error = ""
        self._hand_label: str | None = None
        self._last_center: tuple[float, float] | None = None
        self._calibration: dict | None = None
        self.last_status: dict[str, Any] = {}
        # Chế độ VIEWER_3D (nexa/three_d/gesture_controller.py): độc quyền — không chuột bằng tay, không sáu cử chỉ
        # hệ thống, mỗi khung camera (~30 Hz) đưa thẳng cho máy trạng thái của viewer.
        # Bảng Sinh code dùng cùng đường này (exclusive_mode = "code", nexa/code/gesture_controller.py).
        self.viewer_mode = False
        self.exclusive_mode = ""                 # "" | "3d" | "code"
        self._viewer_feed: Callable[[Observation, float], Any] | None = None
        # Nhận diện mặt trên cùng luồng camera (nexa/core/attention.py): có mặt ở máy + hướng quay đầu.
        # face_consumer có wants_faces() -> bool và on_faces(faces, t). Lỗi phần mặt không bao giờ làm hỏng cử chỉ tay.
        self.face_consumer: Any = None
        self.before_snapshot: Callable[[], Any] | None = None   # chọn cửa sổ ở màn hình đang nhìn trước khi chụp
        self.face_tracker = None
        self.face_error = ""
        self._face_frame = 0

    # ----- vòng đời -----
    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> tuple[bool, str]:
        if self._running:
            return True, "Chế độ cử chỉ đang bật."
        from nexa.vision.camera import Camera
        from nexa.vision.hand_tracker import HandTracker
        try:
            self.tracker = HandTracker(self.models_dir / "hand_landmarker.task",
                                       num_hands=max(1, min(2, int(self.config.get("gestures.num_hands") or 1))))
        except FileNotFoundError as exc:
            self.error = str(exc)
            return False, self.error
        except Exception as exc:
            self.error = f"Không khởi tạo được MediaPipe: {exc}"
            log.exception(self.error)
            return False, self.error
        g = self.config.get("gestures")
        self.camera = Camera(int(g.get("camera_index", 0)), int(g.get("camera_width", 640)),
                             int(g.get("camera_height", 480)), int(g.get("camera_fps", 30)))
        if not self.camera.open():
            self.error = self.camera.error
            self.tracker.close()
            self.tracker = None
            return False, self.error
        self.reload_params()
        self.sm.reset("bật camera")
        self._running = True
        self._paused = False
        self.error = ""
        self._thread = threading.Thread(target=self._loop, name="nexa-gesture", daemon=True)
        self._thread.start()
        log.info("Đã bật chế độ cử chỉ (camera %s)", g.get("camera_index", 0))
        return True, "Đã bật điều khiển bằng tay. Camera đang hoạt động."

    def stop(self, reason: str = "tắt") -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        if self.camera:
            self.camera.close()
            self.camera = None
        if self.tracker:
            self.tracker.close()
            self.tracker = None
        if self.face_tracker:
            self.face_tracker.close()
            self.face_tracker = None
        self.face_error = ""
        self.sm.reset(reason)
        self.router.clear()
        if self.air_mouse is not None:
            self.air_mouse.set_enabled(False, reason)
        with self._lock:
            self._preview = None
        log.info("Đã tắt chế độ cử chỉ (%s)", reason)

    def pause_events(self, paused: bool) -> None:
        """Tạm ngừng phát sự kiện (dừng khẩn cấp) nhưng vẫn hiển thị preview."""
        self._paused = paused
        self.sm.reset("tạm dừng" if paused else "tiếp tục")
        self.router.clear()
        if paused and self.air_mouse is not None:
            self.air_mouse.release("tạm dừng")

    def reload_params(self) -> None:
        self.sm.update_params(GestureParams.from_config(self.config.gestures))
        if self.air_mouse is not None:
            self.air_mouse.update_params(MouseParams.from_config(self.config.gestures))

    # ----- chuột bằng tay -----
    @property
    def mouse_mode(self) -> bool:
        return self.air_mouse is not None and self.air_mouse.enabled

    def set_mouse_mode(self, on: bool) -> None:
        """Bật/tắt chuột bằng tay. Trong lúc bật, sáu cử chỉ lệnh tạm ngưng (không lẫn với động tác chuột)."""
        if self.air_mouse is None or (on and self.viewer_mode):
            return                                  # đang xem 3D: cử chỉ chỉ điều khiển viewer
        self.air_mouse.set_enabled(on, "" if on else "tắt chuột bằng tay")
        self.sm.reset("chuột bằng tay" if on else "tắt chuột bằng tay")
        self.router.clear()
        log.info("Chuột bằng tay: %s", "BẬT" if on else "tắt")

    def set_viewer_mode(self, on: bool, feed: Callable[[Observation, float], Any] | None = None,
                        name: str = "3d") -> None:
        """Bật/tắt chế độ cử chỉ độc quyền (VIEWER_3D hoặc bảng Sinh code). Bật: nhả chuột bằng tay, xóa ứng viên sáu
        cử chỉ. Tắt: về trạng thái sạch."""
        on = bool(on) and feed is not None
        mode = name if on else ""
        if on == self.viewer_mode and mode == self.exclusive_mode and feed is self._viewer_feed:
            return
        self.viewer_mode = on
        self.exclusive_mode = mode
        self._viewer_feed = feed if on else None
        what = {"3d": "xem 3D", "code": "bảng code"}.get(name, name)
        if self.air_mouse is not None:
            self.air_mouse.release(what if on else "đóng " + what)
        self.sm.reset(what if on else "đóng " + what)
        self.router.clear()
        log.info("Chế độ cử chỉ độc quyền: %s", mode.upper() if on else "tắt")

    def _drive_mouse(self, hand, feats, aspect: float, t: float) -> None:
        am = self.air_mouse
        try:
            if hand is None:
                am.lost(t)
                return
            for act in am.update(mouse_frame(hand.landmarks, aspect, feats.pose if feats else None), t):
                if not act.startswith("scroll"):
                    log.debug("Chuột bằng tay: %s", act)
        except Exception as exc:
            if type(exc).__name__ == "FailSafeException":
                # Anh đưa chuột thật vào góc màn hình chính: dừng khẩn cấp như mọi thao tác khác của NEXA.
                am.set_enabled(False, "fail-safe góc màn hình")
                log.warning("Fail-safe góc màn hình khi đang dùng chuột bằng tay")
                if self.on_failsafe:
                    self.on_failsafe()
            else:
                log.exception("Lỗi chuột bằng tay")
                am.release("lỗi")

    # ----- hiệu chuẩn hướng -----
    def calibrate(self, step: str, on_done: Callable[[str], None]) -> None:
        """step: 'right' (anh giữ ngón trỏ chỉ sang phải) hoặc 'up' (anh giữ ngón cái chỉ lên)."""
        def cb(dx: float, dy: float) -> bool:
            if (step == "right" and dx == 0) or (step != "right" and dy == 0):
                return False              # tư thế không thuộc bước này
            if step == "right":
                inv = dx < 0
                self.config.set_gesture("calibration.invert_x", inv)
                msg = "Hướng ngang: " + ("đã đảo" if inv else "giữ nguyên") + f" (đo được dx={dx:+.1f})."
            else:
                inv = dy > 0
                self.config.set_gesture("calibration.invert_y", inv)
                msg = "Hướng dọc: " + ("đã đảo" if inv else "giữ nguyên") + f" (đo được dy={dy:+.1f})."
            self.config.save_gestures()
            self.reload_params()
            on_done(msg)
            return True
        self.sm.calibration_callback = cb

    # ----- preview -----
    def preview(self) -> tuple[int, np.ndarray | None]:
        with self._lock:
            return self._preview_seq, self._preview

    # ----- nội bộ -----
    def _snapshot(self):
        if self.before_snapshot is not None and not self._paused:
            try:
                self.before_snapshot()
            except Exception:
                log.exception("Lỗi chọn màn hình theo hướng nhìn")
        try:
            return self.wm.snapshot_foreground()
        except Exception:
            log.exception("Không chụp được trạng thái cửa sổ")
            return None

    def _choose(self, hands):
        want = (self.config.get("gestures.control_hand") or "any").lower()
        cands = [h for h in hands if want == "any" or h.handedness.lower() == want]
        if not cands:
            return None
        if self._last_center is not None:
            def dist(h):
                c = h.landmarks[[0, 5, 9, 13, 17], :2].mean(axis=0)
                return float(np.hypot(c[0] - self._last_center[0], c[1] - self._last_center[1]))
            return min(cands, key=dist)
        return max(cands, key=lambda h: float(np.ptp(h.landmarks[:, 1])))

    def _loop(self) -> None:
        import cv2
        last_seq = -1
        frames, t_fps = 0, time.monotonic()
        last_status = 0.0
        while self._running:
            cam = self.camera
            if cam is None or not cam.running:
                self.error = cam.error if cam else "Camera đã tắt"
                self._running = False
                self.sm.reset("camera lỗi")
                break
            seq, t_frame, frame = cam.latest(last_seq)
            if frame is None:
                time.sleep(0.004)
                continue
            last_seq = seq
            h, w = frame.shape[:2]
            aspect = w / float(h)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            try:
                hands = self.tracker.detect(rgb, int(t_frame * 1000))
            except Exception:
                log.exception("Lỗi MediaPipe")
                continue
            self._faces(rgb, t_frame)
            hand = self._choose(hands)
            feats = None
            if hand is None:
                obs = Observation(t=t_frame, present=False)
                self._last_center = None
            else:
                if self._hand_label is not None and hand.handedness != self._hand_label and \
                        (self.config.get("gestures.control_hand") or "any") == "any":
                    self.sm.reset("đổi tay điều khiển")
                self._hand_label = hand.handedness
                c = hand.landmarks[[0, 5, 9, 13, 17], :2].mean(axis=0)
                self._last_center = (float(c[0]), float(c[1]))
                feats = classify(hand.landmarks, aspect=aspect, handedness_score=max(0.6, hand.score))
                # Tọa độ đẳng hướng: x theo tỷ lệ khung hình, đơn vị = chiều cao khung.
                obs = Observation(t=t_frame, present=True, pose=feats.pose, confidence=feats.confidence,
                                  center=feats.center, scale=feats.scale,
                                  snap_ready=feats.snap_ready, snap_released=feats.snap_released)
                obs.pointer = (float(hand.landmarks[8, 0]), float(hand.landmarks[8, 1]))
            if self.viewer_mode and self._viewer_feed is not None:
                if not self._paused:                        # dừng khẩn cấp: không đưa khung nào cho viewer
                    try:
                        self._viewer_feed(obs, t_frame)
                    except Exception:
                        log.exception("Lỗi cử chỉ chế độ %s", self.exclusive_mode)
                signals = []
            elif self.mouse_mode and not self._paused and self.sm.calibration_callback is None:
                self._drive_mouse(hand, feats, aspect, t_frame)
                signals = []
            else:
                signals = self.sm.update(obs)
            if not self._paused:
                for sig in signals:
                    log.info("Cử chỉ: %s (%s)", sig.event.value, sig.amount or "")
                    self.router.submit(sig)
            frames += 1
            now = time.monotonic()
            if now - t_fps >= 1.0:
                self.fps = frames / (now - t_fps)
                frames, t_fps = 0, now
            if self.preview_enabled:
                self._draw(frame, hand, feats)
            if now - last_status > 0.1 and self.on_status:
                last_status = now
                st = self.sm.status(now)
                st.update({
                    "present": hand is not None,
                    "pose": feats.pose.value if feats else "NONE",
                    "pose_label": POSE_LABELS_VI.get(feats.pose, "") if feats else "Không thấy tay",
                    "confidence": round(feats.confidence, 2) if feats else 0.0,
                    "hand": hand.handedness if hand else "",
                    "fps": round(self.fps, 1), "camera_fps": round(cam.measured_fps, 1),
                    "paused": self._paused, "calibrating": self.sm.calibration_callback is not None,
                    "viewer_mode": self.viewer_mode, "exclusive_mode": self.exclusive_mode,
                    "face_error": self.face_error,
                })
                if self.air_mouse is not None:
                    st.update(self.air_mouse.status())
                self.last_status = st
                self.on_status(st)

    def _faces(self, rgb: np.ndarray, t_frame: float) -> None:
        fc = self.face_consumer
        try:
            if fc is None or not fc.wants_faces():
                return
        except Exception:
            return
        self._face_frame += 1
        n = max(1, int(self.config.get("attention.face_every_n_frames") or 3))
        if self._face_frame % n:
            return
        if self.face_tracker is None:
            if self.face_error:
                return                              # đã lỗi một lần: không thử lại cho tới lần bật camera sau
            try:
                from nexa.vision.face_tracker import FaceTracker
                self.face_tracker = FaceTracker(self.models_dir / "face_landmarker.task", num_faces=3)
            except Exception as exc:
                self.face_error = str(exc) if isinstance(exc, FileNotFoundError) else f"Lỗi nhận diện mặt: {exc}"
                log.warning("Không bật được nhận diện mặt: %s", self.face_error)
                return
        try:
            faces = self.face_tracker.detect(rgb, int(t_frame * 1000))
            fc.on_faces(faces, t_frame)
        except Exception:
            log.exception("Lỗi nhận diện mặt")

    def _draw(self, frame: np.ndarray, hand, feats) -> None:
        import cv2
        img = cv2.resize(frame, (320, int(320 * frame.shape[0] / frame.shape[1])))
        if hand is not None and self.config.get("gestures.show_landmarks"):
            hh, ww = img.shape[:2]
            pts = [(int(x * ww), int(y * hh)) for x, y, _ in hand.landmarks]
            color = {Pose.OPEN_PALM: (238, 211, 34), Pose.FIST: (247, 85, 168), Pose.TWO_FINGERS: (129, 140, 248),
                     Pose.THUMB_UP: (94, 197, 34), Pose.THUMB_DOWN: (60, 76, 231), Pose.POINT_RIGHT: (11, 158, 245)}.get(
                feats.pose if feats else Pose.UNKNOWN, (160, 160, 160))
            for a, b in HAND_CONNECTIONS:
                cv2.line(img, pts[a], pts[b], color, 2, cv2.LINE_AA)
            for pt in pts:
                cv2.circle(img, pt, 3, (255, 255, 255), -1, cv2.LINE_AA)
        with self._lock:
            self._preview = img
            self._preview_seq += 1
