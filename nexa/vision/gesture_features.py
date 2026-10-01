"""Đặc trưng bàn tay từ 21 landmarks MediaPipe: tư thế, tâm lòng bàn tay, kích thước tay.

Mỗi tư thế khác nhau ở TẬP NGÓN DUỖI (và hướng ngón cái / ngón trỏ), để không bao giờ lẫn nhau:
  mở tay = 5 ngón · nắm tay = 0 ngón, ngón cái áp vào · like/dislike = chỉ ngón cái, chỉ dọc ·
  chỉ tay = chỉ ngón trỏ (hướng ngang/lên) · hai ngón = trỏ + giữa.
Tư thế nằm giữa các ngưỡng hoặc hướng chéo → UNKNOWN (không phát lệnh).

Tọa độ đầu vào là tọa độ chuẩn hóa [0,1] của khung hình ĐÃ LẬT GƯƠNG (đúng như người dùng thấy
trong preview). Trục x được nhân với tỷ lệ khung hình để khoảng cách đẳng hướng. Mọi ngưỡng tính
theo "kích thước bàn tay" nên không phụ thuộc khoảng cách tới camera.

Chỉ số landmarks: 0 cổ tay; ngón cái 1–4; trỏ 5–8; giữa 9–12; áp út 13–16; út 17–20.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

FINGERS = {  # mcp, pip, dip, tip
    "index": (5, 6, 7, 8),
    "middle": (9, 10, 11, 12),
    "ring": (13, 14, 15, 16),
    "pinky": (17, 18, 19, 20),
}
PALM_POINTS = (0, 5, 9, 13, 17)


class Pose(str, Enum):
    OPEN_PALM = "OPEN_PALM"
    FIST = "FIST"
    TWO_FINGERS = "TWO_FINGERS"
    THUMB_UP = "THUMB_UP"
    THUMB_DOWN = "THUMB_DOWN"
    POINT_RIGHT = "POINT_RIGHT"
    POINT_LEFT = "POINT_LEFT"
    POINT_UP = "POINT_UP"
    UNKNOWN = "UNKNOWN"


POSE_LABELS_VI = {
    Pose.OPEN_PALM: "Bàn tay mở",
    Pose.FIST: "Nắm tay",
    Pose.TWO_FINGERS: "Hai ngón (trỏ + giữa)",
    Pose.THUMB_UP: "Ngón cái chỉ lên",
    Pose.THUMB_DOWN: "Ngón cái chỉ xuống",
    Pose.POINT_RIGHT: "Ngón trỏ chỉ sang phải",
    Pose.POINT_LEFT: "Ngón trỏ chỉ sang trái (không gán)",
    Pose.POINT_UP: "Ngón trỏ chỉ lên (không gán)",
    Pose.UNKNOWN: "Chưa rõ",
}

# Góc lệch tối đa so với hướng chuẩn: tan(35°) cho ngón trỏ chỉ ngang, tan(40°) cho ngón cái chỉ dọc.
POINT_TAN = 0.70
THUMB_TAN = 0.84


@dataclass
class HandFeatures:
    pose: Pose
    confidence: float
    center: tuple[float, float]      # tâm lòng bàn tay (đơn vị: chiều cao khung hình, x đã nhân tỷ lệ)
    scale: float                      # kích thước bàn tay cùng đơn vị
    finger_scores: dict[str, float]   # 0 = co, 1 = duỗi
    thumb_score: float
    snap_ready: bool = False          # đầu ngón cái chạm đầu ngón giữa, áp út + út co (chuẩn bị búng tay)
    snap_released: bool = False       # dáng ngay sau khi búng: ngón giữa đập xuống lòng bàn tay, ngón cái bật ra


def snap_shape(p: np.ndarray, center: np.ndarray, scale: float, scores: dict[str, float]) -> tuple[bool, bool]:
    """(chuẩn bị búng, vừa búng xong) — không phải tư thế riêng nên không ảnh hưởng sáu cử chỉ hệ thống."""
    gap_mid = float(np.linalg.norm(p[4] - p[12])) / scale
    gap_idx = float(np.linalg.norm(p[4] - p[8])) / scale
    ring_pinky = max(scores["ring"], scores["pinky"])
    # nắm tay cũng có ngón cái sát đầu ngón giữa, nhưng khi đó đầu ngón giữa nằm trong lòng bàn tay
    mid_out = float(np.linalg.norm(p[12] - center)) / scale
    ready = (gap_mid < 0.3 and gap_idx > gap_mid + 0.15 and ring_pinky <= 0.5 and scores["middle"] < 0.75
             and mid_out >= 0.5)
    released = gap_mid >= 0.7 and scores["middle"] <= 0.45 and ring_pinky <= 0.5 and thumb_extension(p, scale) >= 0.5
    return ready, released


def _pts(landmarks, aspect: float) -> np.ndarray:
    arr = np.asarray(landmarks, dtype=np.float64)[:, :2].copy()
    arr[:, 0] *= aspect
    return arr


def _clip01(v: float) -> float:
    return float(min(1.0, max(0.0, v)))


def _cos_angle(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-9 or nb < 1e-9:
        return 1.0
    return float(np.dot(a, b) / (na * nb))


def hand_scale(p: np.ndarray) -> float:
    palm_len = np.linalg.norm(p[9] - p[0])
    palm_w = np.linalg.norm(p[17] - p[5])
    return float(max(palm_len, palm_w * 1.3, 1e-6))


def finger_score(p: np.ndarray, idx: tuple[int, int, int, int], center: np.ndarray, scale: float) -> float:
    mcp, pip, dip, tip = (p[i] for i in idx)
    # 1) Độ thẳng: góc giữa đốt gốc và phần ngón còn lại.
    straight = _cos_angle(pip - mcp, tip - pip)                     # 1 thẳng, <0 gập
    s1 = _clip01((straight - 0.2) / 0.6)
    # 2) Tầm với: đầu ngón xa cổ tay hơn khớp giữa.
    reach = np.linalg.norm(tip - p[0]) / max(1e-6, np.linalg.norm(pip - p[0]))
    s2 = _clip01((reach - 0.95) / 0.35)
    # 3) Khoảng cách đầu ngón tới tâm lòng bàn tay.
    dist = np.linalg.norm(tip - center) / scale
    s3 = _clip01((dist - 0.75) / 0.6)
    return float(0.35 * s1 + 0.35 * s2 + 0.30 * s3)


def thumb_score(p: np.ndarray, scale: float) -> float:
    straight = _cos_angle(p[3] - p[2], p[4] - p[3])
    s1 = _clip01((straight - 0.3) / 0.6)
    spread = np.linalg.norm(p[4] - p[5]) / scale
    s2 = _clip01((spread - 0.35) / 0.4)
    return float(0.4 * s1 + 0.6 * s2)


def thumb_extension(p: np.ndarray, scale: float) -> float:
    """0 = ngón cái áp lên các ngón đang co (nắm tay), 1 = ngón cái duỗi hẳn ra ngoài (like/dislike).

    Chỉ có ý nghĩa khi bốn ngón kia đang co: đo khoảng cách đầu ngón cái tới đốt giữa/đốt xa của ngón trỏ và
    ngón giữa — khi nắm tay, ngón cái nằm vắt ngang ngay trên các đốt này.
    """
    near = min(np.linalg.norm(p[4] - p[j]) for j in (6, 7, 10, 11)) / scale
    return _clip01((near - 0.3) / 0.3)


def _direction(v: np.ndarray, tan_limit: float, horizontal: bool) -> int:
    """+1/-1 nếu vector nằm trong nón quanh trục đã chọn (x: +1 = phải; y: +1 = xuống), 0 nếu chéo."""
    a, b = (v[0], v[1]) if horizontal else (v[1], v[0])
    if abs(a) < 1e-9 or abs(b) > tan_limit * abs(a):
        return 0
    return 1 if a > 0 else -1


def classify(landmarks, aspect: float = 4 / 3, handedness_score: float = 1.0) -> HandFeatures:
    p = _pts(landmarks, aspect)
    scale = hand_scale(p)
    center = p[list(PALM_POINTS)].mean(axis=0)
    scores = {name: finger_score(p, idx, center, scale) for name, idx in FINGERS.items()}
    thumb = thumb_score(p, scale)
    ext, cur = 0.6, 0.35
    i, m, r, k = scores["index"], scores["middle"], scores["ring"], scores["pinky"]
    pose, margin = Pose.UNKNOWN, 0.0
    if min(i, m, r, k) >= ext and thumb >= 0.3:
        pose = Pose.OPEN_PALM
        margin = min(min(i, m, r, k) - ext, thumb - 0.3) / (1 - ext)
    elif max(i, m, r, k) <= cur:
        # Bốn ngón co: nắm tay nếu ngón cái áp vào, like/dislike nếu ngón cái duỗi theo chiều dọc.
        te = thumb_extension(p, scale)
        curl_margin = (cur - max(i, m, r, k)) / cur
        if te <= 0.35:
            pose = Pose.FIST
            margin = min(curl_margin, (0.5 - te) / 0.5)
        elif te >= 0.65:
            d = _direction(p[4] - p[2], THUMB_TAN, horizontal=False)
            if d:
                pose = Pose.THUMB_DOWN if d > 0 else Pose.THUMB_UP
                margin = min(curl_margin, (te - 0.5) / 0.5)
    elif i >= ext and max(m, r, k) <= cur:
        # Chỉ ngón trỏ (ngón cái tùy ý, kiểu "khẩu súng" vẫn được).
        v = p[8] - p[5]
        margin = min(i - ext, cur - max(m, r, k)) / cur
        if _direction(v, POINT_TAN, horizontal=True) > 0:
            pose = Pose.POINT_RIGHT
        elif _direction(v, POINT_TAN, horizontal=True) < 0:
            pose = Pose.POINT_LEFT
        elif _direction(v, POINT_TAN, horizontal=False) < 0:
            pose = Pose.POINT_UP
    elif min(i, m) >= ext and max(r, k) <= cur:
        pose = Pose.TWO_FINGERS
        margin = min(min(i, m) - ext, cur - max(r, k)) / cur
    confidence = _clip01(0.5 + 0.5 * margin) * _clip01(handedness_score) if pose != Pose.UNKNOWN else 0.0
    ready, released = snap_shape(p, center, scale, scores)
    return HandFeatures(pose=pose, confidence=confidence, center=(float(center[0]), float(center[1])),
                        scale=scale, finger_scores=scores, thumb_score=thumb, snap_ready=ready, snap_released=released)
