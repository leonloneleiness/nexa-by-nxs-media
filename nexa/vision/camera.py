"""Đọc webcam bằng OpenCV trong một luồng riêng, chỉ giữ khung hình MỚI NHẤT (không tích lũy frame cũ).

Khung hình được lật gương đúng MỘT lần tại đây để preview và tọa độ cử chỉ khớp với những gì
người dùng nhìn thấy.
"""
from __future__ import annotations

import threading
import time

import numpy as np

from nexa.utils.logging import get_logger

log = get_logger("camera")


def list_cameras(max_index: int = 5) -> list[dict]:
    import cv2
    out = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        ok = cap.isOpened()
        if ok:
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            out.append({"index": i, "name": f"Camera {i} ({w}×{h})"})
        cap.release()
    return out


class Camera:
    def __init__(self, index: int = 0, width: int = 640, height: int = 480, fps: int = 30) -> None:
        self.index, self.width, self.height, self.fps = index, width, height, fps
        self._cap = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._frame_t = 0.0
        self._seq = 0
        self.error = ""
        self.measured_fps = 0.0

    def open(self) -> bool:
        import cv2
        cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            cap = cv2.VideoCapture(self.index, cv2.CAP_MSMF)
        if not cap.isOpened():
            self.error = f"Không mở được camera {self.index} (đang bị ứng dụng khác dùng hoặc bị chặn quyền)."
            log.error(self.error)
            return False
        # MJPG giúp nhiều webcam USB giữ đủ 30 FPS ở 640×480 (YUY2 thường bị giới hạn băng thông).
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._cap = cap
        self._running = True
        self.error = ""
        self._thread = threading.Thread(target=self._loop, name="nexa-camera", daemon=True)
        self._thread.start()
        return True

    def _loop(self) -> None:
        import cv2
        fails = 0
        count, t_fps = 0, time.monotonic()
        while self._running:
            ok, frame = self._cap.read()
            if not ok or frame is None:
                fails += 1
                if fails > 30:
                    self.error = "Camera ngừng trả hình."
                    log.error(self.error)
                    self._running = False
                    break
                time.sleep(0.03)
                continue
            fails = 0
            frame = cv2.flip(frame, 1)          # lật gương duy nhất một lần
            with self._lock:
                self._frame = frame
                self._frame_t = time.monotonic()
                self._seq += 1
            count += 1
            now = time.monotonic()
            if now - t_fps >= 1.0:
                self.measured_fps = count / (now - t_fps)
                count, t_fps = 0, now

    def latest(self, after_seq: int = -1) -> tuple[int, float, np.ndarray | None]:
        with self._lock:
            if self._seq == after_seq:
                return self._seq, self._frame_t, None
            return self._seq, self._frame_t, self._frame

    @property
    def running(self) -> bool:
        return self._running

    def close(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        with self._lock:
            self._frame = None
