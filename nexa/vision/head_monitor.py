"""Chọn màn hình theo hướng quay đầu — phần thuần (không camera, không Win32) để test được.

Hiệu chuẩn: anh nhìn vào giữa từng màn hình ~1,5 giây; NEXA lấy trung vị (yaw, pitch) làm "tâm" của màn hình đó.
Lưu trong config/settings.yaml → attention.head_calibration, khóa theo device_id (dự phòng device_name) của MonitorManager.

Phân loại: tâm gần nhất (yaw nặng hơn pitch), có trễ (chỉ đổi khi tâm mới gần hơn rõ rệt) và phải giữ hướng mới
dwell_s giây mới xác nhận — lướt mắt qua màn hình kia không làm đổi mục tiêu.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class HeadParams:
    dwell_s: float = 0.35           # giữ hướng mới bao lâu mới đổi màn hình
    hysteresis: float = 0.7         # đổi khi khoảng cách tới tâm mới < hysteresis × khoảng cách tới tâm hiện tại
    pitch_weight: float = 0.5       # pitch ít tin cậy hơn yaw
    smoothing: float = 0.5          # EMA góc (0 = không làm mượt)
    stale_s: float = 1.0            # mất mặt quá lâu → không biết anh nhìn đâu
    calib_s: float = 1.5            # thời gian lấy mẫu mỗi màn hình
    min_separation: float = 6.0     # hai tâm phải cách nhau ít nhất (độ) mới chấp nhận hiệu chuẩn

    @classmethod
    def from_config(cls, cfg: dict[str, Any] | None) -> "HeadParams":
        p = cls()
        for k, v in (cfg or {}).items():
            if hasattr(p, k) and isinstance(v, (int, float)) and not isinstance(v, bool):
                setattr(p, k, float(v))
        return p


class HeadMonitorSelector:
    def __init__(self, params: HeadParams | None = None, centers: dict[str, tuple[float, float]] | None = None) -> None:
        self.params = params or HeadParams()
        self.centers: dict[str, tuple[float, float]] = dict(centers or {})
        self.current: str | None = None
        self.since: float = 0.0            # lúc xác nhận màn hình hiện tại
        self._cand: str | None = None
        self._cand_since = 0.0
        self._yaw: float | None = None
        self._pitch: float | None = None
        self._t_seen: float | None = None
        # hiệu chuẩn
        self._cal_key: str | None = None
        self._cal_until = 0.0
        self._cal_samples: list[tuple[float, float]] = []
        self._cal_done: Callable[[str, tuple[float, float] | None, str], None] | None = None

    # ----- cấu hình -----
    @property
    def ready(self) -> bool:
        return len(self.centers) >= 2

    def set_centers(self, centers: dict[str, tuple[float, float]]) -> None:
        self.centers = {k: (float(v[0]), float(v[1])) for k, v in centers.items()}
        if self.current not in self.centers:
            self.current = None

    def _dist(self, yaw: float, pitch: float, c: tuple[float, float]) -> float:
        return math.hypot(yaw - c[0], (pitch - c[1]) * self.params.pitch_weight)

    # ----- hiệu chuẩn -----
    @property
    def calibrating(self) -> str | None:
        return self._cal_key

    def start_calibration(self, key: str, t: float,
                          on_done: Callable[[str, tuple[float, float] | None, str], None]) -> None:
        self._cal_key = key
        self._cal_until = t + self.params.calib_s
        self._cal_samples = []
        self._cal_done = on_done

    def cancel_calibration(self) -> None:
        self._cal_key = None
        self._cal_done = None

    def _feed_calibration(self, t: float, yaw: float | None, pitch: float | None) -> None:
        if yaw is not None and pitch is not None:
            self._cal_samples.append((yaw, pitch))
        if t < self._cal_until:
            return
        key, done, samples = self._cal_key, self._cal_done, self._cal_samples
        self._cal_key, self._cal_done = None, None
        if len(samples) < 5:
            if done:
                done(key or "", None, "Không thấy rõ mặt anh trong lúc hiệu chuẩn — ngồi đối diện camera rồi thử lại.")
            return
        c = (statistics.median(s[0] for s in samples), statistics.median(s[1] for s in samples))
        for other, oc in self.centers.items():
            if other != key and self._dist(c[0], c[1], oc) < self.params.min_separation:
                if done:
                    done(key or "", None, "Hướng nhìn này gần như trùng với màn hình kia — quay hẳn đầu về giữa "
                                          "màn hình cần hiệu chuẩn rồi thử lại.")
                return
        self.centers[key or ""] = c
        if done:
            done(key or "", c, f"yaw {c[0]:+.1f}°, pitch {c[1]:+.1f}°")

    # ----- cập nhật mỗi khung -----
    def update(self, t: float, yaw: float | None, pitch: float | None) -> str | None:
        """yaw/pitch của mặt chủ máy (None = không thấy). Trả về khóa màn hình đang nhìn (None = chưa biết)."""
        if self._cal_key is not None:
            self._feed_calibration(t, yaw, pitch)
        if yaw is None or pitch is None:
            if self._t_seen is not None and t - self._t_seen > self.params.stale_s:
                self._yaw = self._pitch = None
                self._cand = None
            return self.current
        a = self.params.smoothing
        if self._yaw is None or self._t_seen is None or t - self._t_seen > self.params.stale_s:
            self._yaw, self._pitch = yaw, pitch
        else:
            self._yaw = a * self._yaw + (1 - a) * yaw
            self._pitch = a * self._pitch + (1 - a) * pitch
        self._t_seen = t
        if not self.ready:
            return self.current
        best = min(self.centers, key=lambda k: self._dist(self._yaw, self._pitch, self.centers[k]))
        if best == self.current:
            self._cand = None
            return self.current
        if self.current is not None and self.current in self.centers:
            d_cur = self._dist(self._yaw, self._pitch, self.centers[self.current])
            d_new = self._dist(self._yaw, self._pitch, self.centers[best])
            if d_new >= self.params.hysteresis * d_cur:
                self._cand = None
                return self.current
        if self._cand != best:
            self._cand, self._cand_since = best, t
        if t - self._cand_since >= self.params.dwell_s or self.current is None:
            self.current, self.since = best, t
            self._cand = None
        return self.current

    def looking_at(self, t: float) -> str | None:
        """Màn hình đang nhìn, chỉ khi còn thấy mặt gần đây."""
        if self._t_seen is None or t - self._t_seen > self.params.stale_s:
            return None
        return self.current

    def status(self, t: float) -> dict[str, Any]:
        return {"head_yaw": None if self._yaw is None else round(self._yaw, 1),
                "head_pitch": None if self._pitch is None else round(self._pitch, 1),
                "head_monitor": self.looking_at(t), "head_ready": self.ready,
                "head_calibrating": self._cal_key}
