"""Sinh landmarks bàn tay tổng hợp cho kiểm thử (không phải dữ liệu camera thật).

Ở góc 0° các ngón hướng lên trên. Xoay +90° (chiều kim đồng hồ trên ảnh) thì ngón trỏ chỉ sang phải và
ngón cái ở tư thế "thumb" (duỗi ngang sang trái) chuyển thành chỉ lên; -90° thì ngược lại.
"""
from __future__ import annotations

import math

import numpy as np

MCP = {"index": (-0.35, -1.0), "middle": (-0.1, -1.05), "ring": (0.15, -1.0), "pinky": (0.38, -0.9)}
ORDER = ["index", "middle", "ring", "pinky"]

EXTENDED = {"open": {"index", "middle", "ring", "pinky"}, "fist": set(), "two": {"index", "middle"},
            "thumb": set(), "point": {"index"}, "snap_ready": {"index"}, "snap_released": {"index"}}
THUMBS = {
    "out": [(-0.35, -0.25), (-0.6, -0.45), (-0.8, -0.62), (-0.95, -0.8)],      # xòe (bàn tay mở)
    "tucked": [(-0.3, -0.25), (-0.45, -0.45), (-0.3, -0.75), (-0.05, -0.95)],  # vắt ngang các ngón co
    "side": [(-0.3, -0.3), (-0.6, -0.4), (-0.9, -0.45), (-1.2, -0.5)],         # duỗi vuông góc với ngón
    "pinch_mid": [(-0.35, -0.25), (-0.5, -0.6), (-0.45, -1.0), (-0.32, -1.42)],  # đầu ngón cái ép đầu ngón giữa
}
# ngón giữa gập nửa chừng, đầu ngón chạm đầu ngón cái (chuẩn bị búng tay)
MIDDLE_HALF = [(-0.1, -1.05), (-0.1, -1.4), (-0.2, -1.55), (-0.3, -1.45)]
DEFAULT_THUMB = {"open": "out", "fist": "tucked", "two": "tucked", "thumb": "side", "point": "tucked",
                 "snap_ready": "pinch_mid", "snap_released": "side"}


def _finger(mcp, extended: bool):
    mx, my = mcp
    if extended:
        return [(mx, my), (mx, my - 0.45), (mx, my - 0.75), (mx, my - 1.0)]
    return [(mx, my), (mx, my - 0.3), (mx * 0.9, my - 0.1), (mx * 0.8, my + 0.2)]


def make_hand(pose: str, cx: float = 0.5, cy: float = 0.5, size: float = 0.12, angle_deg: float = 0.0,
              aspect: float = 4 / 3, jitter: float = 0.0, rng=None, thumb: str | None = None) -> np.ndarray:
    ext = EXTENDED[pose]
    pts = [(0.0, 0.0)] + THUMBS[thumb or DEFAULT_THUMB[pose]]
    for name in ORDER:
        pts += MIDDLE_HALF if (pose == "snap_ready" and name == "middle") else _finger(MCP[name], name in ext)
    arr = np.array(pts, dtype=np.float64)
    # Tâm lòng bàn tay ~ (0, -0.6): dời về gốc để xoay quanh tâm.
    arr[:, 1] += 0.6
    a = math.radians(angle_deg)
    rot = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    arr = arr @ rot.T * size
    if jitter and rng is not None:
        arr += rng.normal(0, jitter, arr.shape)
    out = np.zeros((21, 3))
    out[:, 0] = cx + arr[:, 0] / aspect
    out[:, 1] = cy + arr[:, 1]
    return out
