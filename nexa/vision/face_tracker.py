"""MediaPipe Face Landmarker (Tasks API, chế độ VIDEO) chạy cục bộ trên CPU — cho nhận biết anh có ngồi ở máy
và hướng quay đầu (chọn màn hình).

Model face_landmarker.task tải từ nguồn chính thức của Google bằng scripts/download_models.py --faces và lưu ở
models/face_landmarker.task. Không lưu, không gửi ảnh khuôn mặt đi đâu: mỗi khung chỉ giữ vài con số (góc quay đầu,
kích thước mặt).

Ảnh đưa vào đã được lật gương (nexa/vision/camera.py). Dấu của góc quay không quan trọng: hướng nhìn từng màn hình
được hiệu chuẩn bằng chính số đo trên máy (nexa/vision/head_monitor.py).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/"
             "float16/latest/face_landmarker.task")

# Chỉ số landmark của face mesh (478 điểm)
EYE_OUTER_A, EYE_OUTER_B, NOSE_TIP = 33, 263, 1


@dataclass
class FaceObservation:
    yaw: float                  # độ, quay trái/phải (dấu tùy camera — chỉ dùng qua hiệu chuẩn)
    pitch: float                # độ, ngẩng/cúi
    size: float                 # khoảng cách hai khóe mắt ngoài / chiều rộng khung (mặt càng gần càng lớn)
    center: tuple[float, float]  # tâm hai mắt, tọa độ chuẩn hóa 0..1


def angles_from_matrix(m: np.ndarray) -> tuple[float, float]:
    """(yaw, pitch) theo độ từ ma trận biến đổi 4×4 của MediaPipe (phần xoay 3×3)."""
    r = np.asarray(m, dtype=np.float64)[:3, :3]
    yaw = math.degrees(math.atan2(-r[2, 0], math.hypot(r[0, 0], r[1, 0])))
    pitch = math.degrees(math.atan2(r[2, 1], r[2, 2]))
    return yaw, pitch


def angles_from_landmarks(lms: np.ndarray, aspect: float) -> tuple[float, float]:
    """Dự phòng khi không có ma trận: độ lệch mũi so với trung điểm hai mắt, quy ra độ gần đúng."""
    a, b, nose = lms[EYE_OUTER_A], lms[EYE_OUTER_B], lms[NOSE_TIP]
    mx, my = (a[0] + b[0]) / 2 * aspect, (a[1] + b[1]) / 2
    eye = max(1e-6, math.hypot((b[0] - a[0]) * aspect, b[1] - a[1]))
    return math.degrees(math.atan((nose[0] * aspect - mx) / eye * 2)), math.degrees(math.atan((nose[1] - my) / eye * 2))


def observation(lms: np.ndarray, aspect: float, matrix: np.ndarray | None = None) -> FaceObservation:
    a, b = lms[EYE_OUTER_A], lms[EYE_OUTER_B]
    yaw, pitch = angles_from_matrix(matrix) if matrix is not None else angles_from_landmarks(lms, aspect)
    size = float(math.hypot((b[0] - a[0]) * aspect, b[1] - a[1]) / max(aspect, 1e-6))
    return FaceObservation(yaw=float(yaw), pitch=float(pitch), size=size,
                           center=(float((a[0] + b[0]) / 2), float((a[1] + b[1]) / 2)))


class FaceTracker:
    def __init__(self, model_path: Path, num_faces: int = 2, min_detection: float = 0.5,
                 min_presence: float = 0.5, min_tracking: float = 0.5) -> None:
        if not model_path.exists():
            raise FileNotFoundError(
                f"Chưa có model {model_path.name}. Chạy: python scripts/download_models.py --faces")
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python import vision
        self._mp = mp
        options = vision.FaceLandmarkerOptions(
            # Use Python's Unicode-aware file I/O for non-ASCII install paths.
            base_options=BaseOptions(model_asset_buffer=model_path.read_bytes()),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=num_faces,
            min_face_detection_confidence=min_detection,
            min_face_presence_confidence=min_presence,
            min_tracking_confidence=min_tracking,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=True)
        self._landmarker = vision.FaceLandmarker.create_from_options(options)
        self._last_ts = -1

    def detect(self, rgb: np.ndarray, t_ms: int) -> list[FaceObservation]:
        """Các khuôn mặt trong khung, mặt lớn nhất (gần camera nhất) đứng đầu."""
        if t_ms <= self._last_ts:                 # timestamp phải tăng nghiêm ngặt trong chế độ VIDEO
            t_ms = self._last_ts + 1
        self._last_ts = t_ms
        h, w = rgb.shape[:2]
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        result = self._landmarker.detect_for_video(image, t_ms)
        mats = list(result.facial_transformation_matrixes or [])
        faces = []
        for i, lms in enumerate(result.face_landmarks or []):
            arr = np.array([[lm.x, lm.y, lm.z] for lm in lms], dtype=np.float32)
            faces.append(observation(arr, w / float(h), mats[i] if i < len(mats) else None))
        faces.sort(key=lambda f: f.size, reverse=True)
        return faces

    def close(self) -> None:
        try:
            self._landmarker.close()
        except Exception:
            pass
