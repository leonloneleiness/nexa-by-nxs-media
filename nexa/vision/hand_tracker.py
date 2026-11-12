"""MediaPipe Hand Landmarker (Tasks API, chế độ VIDEO) chạy cục bộ trên CPU.

Model hand_landmarker.task tải từ nguồn chính thức của Google bằng scripts/download_models.py và
lưu ở models/hand_landmarker.task.
Ảnh đưa vào đã được lật gương; MediaPipe giả định ảnh selfie đã lật khi gán nhãn tay trái/phải,
nên nhãn "Right" tương ứng tay phải thật của người dùng.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/"
             "float16/latest/hand_landmarker.task")


@dataclass
class HandObservation:
    landmarks: np.ndarray       # (21, 3) chuẩn hóa theo khung hình đã lật
    handedness: str             # "Left" | "Right"
    score: float


class HandTracker:
    def __init__(self, model_path: Path, num_hands: int = 2, min_detection: float = 0.6,
                 min_presence: float = 0.5, min_tracking: float = 0.5) -> None:
        if not model_path.exists():
            raise FileNotFoundError(
                f"Chưa có model {model_path.name}. Chạy: python scripts/download_models.py --hands")
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python import vision
        self._mp = mp
        options = vision.HandLandmarkerOptions(
            # MediaPipe's Windows native file opener cannot read some Unicode
            # paths (for example a Vietnamese Windows account name). Python
            # opens Unicode paths correctly; pass the model bytes to the SDK.
            base_options=BaseOptions(model_asset_buffer=model_path.read_bytes()),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=num_hands,
            min_hand_detection_confidence=min_detection,
            min_hand_presence_confidence=min_presence,
            min_tracking_confidence=min_tracking)
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        self._last_ts = -1

    def detect(self, rgb: np.ndarray, t_ms: int) -> list[HandObservation]:
        # Timestamp phải tăng nghiêm ngặt trong chế độ VIDEO.
        if t_ms <= self._last_ts:
            t_ms = self._last_ts + 1
        self._last_ts = t_ms
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        result = self._landmarker.detect_for_video(image, t_ms)
        hands = []
        for i, lms in enumerate(result.hand_landmarks or []):
            arr = np.array([[lm.x, lm.y, lm.z] for lm in lms], dtype=np.float32)
            label, score = "Unknown", 0.0
            if result.handedness and i < len(result.handedness) and result.handedness[i]:
                cat = result.handedness[i][0]
                label, score = cat.category_name, float(cat.score)
            hands.append(HandObservation(arr, label, score))
        return hands

    def close(self) -> None:
        try:
            self._landmarker.close()
        except Exception:
            pass
