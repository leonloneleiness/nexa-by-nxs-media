"""Hiệu ứng giọng nói cho NEXA (xử lý số, chạy cục bộ).

"jarvis" (mặc định): giọng AI trong trẻo, lớp kép và vang phòng ngắn — xem jarvis().
"robot": ring modulation (sóng mang ~ 50 Hz, kiểu giọng Dalek) trộn với giọng gốc để vẫn nghe rõ,
cộng bộ lọc lược (comb) tạo tiếng vang kim loại ngắn và cắt dải thấp/cao nhẹ. `strength` 0..1.
"""
from __future__ import annotations

import numpy as np


def robot(x: np.ndarray, sr: int, strength: float = 0.6, carrier_hz: float = 50.0) -> np.ndarray:
    if x.size == 0:
        return x
    s = float(min(1.0, max(0.0, strength)))
    if s <= 0:
        return x.astype(np.float32, copy=False)
    t = np.arange(x.size, dtype=np.float32) / sr
    ring = x * np.sin(2 * np.pi * carrier_hz * t, dtype=np.float32)
    y = (1.0 - 0.7 * s) * x + (0.7 * s) * ring * 1.6
    # Vang kim loại: comb feedforward 2 nhánh (7 ms và 13 ms).
    for delay_ms, gain in ((7.0, 0.45 * s), (13.0, 0.25 * s)):
        d = int(sr * delay_ms / 1000)
        if 0 < d < y.size:
            y[d:] = y[d:] + gain * y[:-d]
    # Lọc thông dải nhẹ 150 Hz – 6 kHz cho chất "loa bộ đàm".
    try:
        from scipy.signal import butter, sosfilt
        sos = butter(2, [150, min(6000, sr / 2 - 100)], btype="bandpass", fs=sr, output="sos")
        y = sosfilt(sos, y)
    except Exception:
        pass
    peak = float(np.max(np.abs(y))) or 1.0
    ref = float(np.max(np.abs(x))) or 1.0
    return (y * (ref / peak)).astype(np.float32)


def jarvis(x: np.ndarray, sr: int, strength: float = 0.5) -> np.ndarray:
    """Giọng AI "lịch lãm": giữ giọng gốc rõ và tự nhiên, chỉ phủ một lớp xử lý nhẹ.

    - Cắt dải thấp < 90 Hz (bớt ù), nâng dải "hiện diện" 2,5–5 kHz cho giọng sáng, gần tai.
    - Lớp kép (doubling) 9 ms + một chút ring modulation 60 Hz rất nhẹ: ánh kim "kỹ thuật số" nhưng không méo.
    - Phản xạ sớm ngắn (23–71 ms, đã lọc thấp) như giọng vang trong phòng điều khiển nhỏ.
    - Nén mềm (tanh) rồi trả về đúng mức đỉnh của giọng gốc.
    """
    if x.size == 0:
        return x
    s = float(min(1.0, max(0.0, strength)))
    x = x.astype(np.float32, copy=False)
    if s <= 0:
        return x
    try:
        from scipy.signal import butter, sosfilt
        y = sosfilt(butter(2, 90, btype="highpass", fs=sr, output="sos"), x)
        hi = min(5000, sr / 2 - 200)
        presence = sosfilt(butter(2, [2500, hi], btype="bandpass", fs=sr, output="sos"), y)
        y = y + 0.9 * s * presence
        lp = butter(2, min(4500, sr / 2 - 200), btype="lowpass", fs=sr, output="sos")
    except Exception:
        y, lp = x.copy(), None
    t = np.arange(y.size, dtype=np.float32) / sr
    y = y + 0.10 * s * y * np.sin(2 * np.pi * 60.0 * t, dtype=np.float32)
    d = int(sr * 0.009)
    if 0 < d < y.size:
        y[d:] = y[d:] + 0.22 * s * y[:-d]
    room = np.zeros_like(y)
    for delay_ms, gain in ((23.0, 0.30), (37.0, 0.22), (53.0, 0.16), (71.0, 0.10)):
        d = int(sr * delay_ms / 1000)
        if 0 < d < y.size:
            room[d:] += gain * y[:-d]
    if lp is not None:
        room = sosfilt(lp, room)
    y = y + 0.55 * s * room
    peak = float(np.max(np.abs(y))) or 1.0
    y = np.tanh(1.3 * y / peak)
    ref = float(np.max(np.abs(x))) or 1.0
    return (y * (ref / (float(np.max(np.abs(y))) or 1.0))).astype(np.float32)


EFFECTS = ("jarvis", "robot", "none")


def apply(effect: str, x: np.ndarray, sr: int, strength: float) -> np.ndarray:
    if effect == "robot":
        return robot(x, sr, strength)
    if effect == "jarvis":
        return jarvis(x, sr, strength)
    return x
