"""Phát hiện tiếng búng tay từ tín hiệu mic (16 kHz mono, xử lý theo bước 10 ms).

Tiếng búng tay khác tiếng vỗ tay:
1. Tần số cao hơn: đỉnh ở 2-6 kHz (vỗ tay rộng hơn, từ vài trăm Hz)
2. Thời lượng ngắn hơn: < 15 ms (vỗ tay 20-40 ms)
3. Năng lượng thấp hơn: điển hình -50 đến -35 dBFS (vỗ tay -45 đến -25 dBFS)
4. Phổ hẹp hơn: năng lượng tập trung ở dải cao
5. Tắt cực nhanh: decay < 10 ms

Thuật toán:
1. Phát hiện xung vượt ngưỡng thích nghi
2. Kiểm tra tỷ lệ năng lượng dải cao (> 2 kHz) / dải thấp (< 1 kHz) > 2.0
3. Kiểm tra độ rộng xung < 2 hop (< 20 ms)
4. Kiểm tra decay nhanh sau đỉnh
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np

SR = 16000
HOP = 160           # 10 ms
NFFT = 256


@dataclass
class SnapConfig:
    mode: str = "single"
    sensitivity: float = 0.6
    min_level_dbfs: float = -50.0
    double_min_gap_ms: int = 100
    double_max_gap_ms: int = 500
    debounce_ms: int = 100
    cooldown_ms: int = 1200
    calibration_seconds: float = 2.0
    hf_min_ratio: float = 0.55       # tỷ lệ năng lượng > 2 kHz (búng tay có nhiều hơn)
    hf_lf_ratio: float = 1.8         # tỷ lệ (> 2 kHz) / (< 1 kHz) - búng tay cao hơn
    decay_db: float = 15.0
    max_width_hops: int = 2          # < 20 ms

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "SnapConfig":
        d = d or {}
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)

    @property
    def margin_db(self) -> float:
        s = min(1.0, max(0.0, float(self.sensitivity)))
        return 20.0 - 12.0 * s        # 20 dB (kém nhạy) … 8 dB (rất nhạy)

    @property
    def rise_db(self) -> float:
        return max(8.0, self.margin_db * 0.75)


@dataclass
class SnapEvent:
    t: float
    peak_db: float
    kind: str           # "snap" (một tiếng lẻ) | "trigger" (đủ điều kiện kích hoạt)
    count: int
    hf_ratio: float
    hf_lf_ratio: float


class SnapDetector:
    def __init__(self, cfg: SnapConfig | None = None) -> None:
        self.cfg = cfg or SnapConfig()
        self._window = np.hanning(HOP).astype(np.float32)
        freqs = np.fft.rfftfreq(NFFT, 1.0 / SR)
        self._hf_mask = freqs >= 2000.0      # > 2 kHz
        self._lf_mask = (freqs >= 80.0) & (freqs < 1000.0)   # 80 Hz - 1 kHz
        self._mid_mask = freqs >= 80.0       # toàn dải (bỏ < 80 Hz)
        self.reset()

    def reset(self, keep_floor: bool = False) -> None:
        floor = getattr(self, "floor_db", None)
        calibrated = getattr(self, "calibrated", False)
        self._buf = np.zeros(0, dtype=np.float32)
        self._hop_index = 0
        self._t_base: float | None = None
        self._history: deque[float] = deque(maxlen=12)
        self._floor_hist: deque[float] = deque(maxlen=300)
        self._calib: list[float] = []
        self._cand: dict | None = None
        self._ignore_until = -1.0
        self._cooldown_until = -1.0
        self._last_snap_t: float | None = None
        self.last_db = -100.0
        if keep_floor and floor is not None:
            self.floor_db = floor
            self.calibrated = calibrated
        else:
            self.floor_db = -70.0
            self.calibrated = False

    def update_config(self, cfg: SnapConfig) -> None:
        self.cfg = cfg

    def recalibrate(self) -> None:
        self.reset(keep_floor=False)

    @property
    def threshold_db(self) -> float:
        return max(self.floor_db + self.cfg.margin_db, self.cfg.min_level_dbfs)

    def stats(self) -> dict[str, float | bool]:
        return {"floor_db": round(float(self.floor_db), 1), "threshold_db": round(float(self.threshold_db), 1),
                "level_db": round(float(self.last_db), 1), "calibrated": bool(self.calibrated)}

    def suppress_for(self, t: float, seconds: float) -> None:
        """Bỏ qua mọi xung tới thời điểm t+seconds (ví dụ ngay sau khi NEXA phát âm thanh)."""
        self._ignore_until = max(self._ignore_until, t + seconds)
        self._cand = None
        self._last_snap_t = None

    def process(self, samples: np.ndarray, t0: float) -> list[SnapEvent]:
        """samples: float32 mono 16 kHz; t0: thời điểm (giây) của mẫu đầu tiên trong khối."""
        if samples.size == 0:
            return []
        if self._t_base is None or not self._buf.size:
            self._t_base = t0 - self._buf.size / SR
        self._buf = np.concatenate([self._buf, samples.astype(np.float32, copy=False)])
        events: list[SnapEvent] = []
        while self._buf.size >= HOP:
            hop = self._buf[:HOP]
            self._buf = self._buf[HOP:]
            t = self._t_base
            self._t_base += HOP / SR
            ev = self._process_hop(hop, t)
            if ev is not None:
                events.append(ev)
        return events

    def _features(self, hop: np.ndarray) -> tuple[float, float, float]:
        """Trả về (e_db, hf_ratio, hf_lf_ratio)"""
        energy = float(np.mean(hop * hop))
        e_db = 10.0 * np.log10(energy + 1e-12)
        spec = np.abs(np.fft.rfft(hop * self._window, NFFT)) ** 2
        total = float(spec[self._mid_mask].sum()) + 1e-12
        hf = float(spec[self._hf_mask].sum())
        lf = float(spec[self._lf_mask].sum()) + 1e-12
        return e_db, hf / total, hf / lf

    def _process_hop(self, hop: np.ndarray, t: float) -> SnapEvent | None:
        cfg = self.cfg
        e_db, hf_ratio, hf_lf_ratio = self._features(hop)
        self.last_db = e_db
        self._hop_index += 1

        if not self.calibrated:
            self._calib.append(e_db)
            self._history.append(e_db)
            if len(self._calib) >= max(20, int(cfg.calibration_seconds * 100)):
                self.floor_db = float(np.percentile(self._calib, 40))
                self._floor_hist.extend(self._calib[-300:])
                self.calibrated = True
                self._calib.clear()
            return None

        result: SnapEvent | None = None
        if self._cand is not None:
            result = self._update_candidate(e_db, hf_ratio, hf_lf_ratio, t)
        elif t >= self._ignore_until:
            prev = list(self._history)[-8:-1]
            pre_level = max(prev) if prev else self.floor_db
            if (e_db >= self.threshold_db and e_db - pre_level >= cfg.rise_db
                    and pre_level < self.threshold_db - 3.0):
                self._cand = {"start_t": t, "peak_db": e_db, "peak_hf": hf_ratio, "peak_hf_lf": hf_lf_ratio,
                              "peak_t": t, "hops": [e_db], "since_peak": 0}

        if self._cand is None and result is None and e_db < self.threshold_db:
            self._floor_hist.append(e_db)
            if self._hop_index % 10 == 0 and len(self._floor_hist) >= 50:
                self.floor_db = float(min(-10.0, max(-95.0, np.percentile(self._floor_hist, 30))))
        self._history.append(e_db)
        return result

    def _update_candidate(self, e_db: float, hf_ratio: float, hf_lf_ratio: float, t: float) -> SnapEvent | None:
        c = self._cand
        c["hops"].append(e_db)
        if e_db > c["peak_db"] and len(c["hops"]) <= 2:
            c["peak_db"] = e_db
            c["peak_hf"] = max(c["peak_hf"], hf_ratio)
            c["peak_hf_lf"] = max(c["peak_hf_lf"], hf_lf_ratio)
            c["peak_t"] = t
            c["since_peak"] = 0
            return None
        c["since_peak"] += 1
        if c["since_peak"] < 5:  # đợi 50 ms sau đỉnh
            return None
        self._cand = None
        peak = c["peak_db"]
        hops = c["hops"]
        width = sum(1 for v in hops if v >= peak - 6.0)
        tail = max(hops[-3:]) if len(hops) >= 3 else hops[-1]

        is_snap = (width <= self.cfg.max_width_hops          # rất ngắn
                   and tail <= peak - self.cfg.decay_db      # tắt nhanh
                   and c["peak_hf"] >= self.cfg.hf_min_ratio # nhiều năng lượng cao
                   and c["peak_hf_lf"] >= self.cfg.hf_lf_ratio)  # tỷ lệ HF/LF cao
        self._ignore_until = max(self._ignore_until, t + self.cfg.debounce_ms / 1000.0 - 0.05)
        if not is_snap:
            return None
        return self._on_snap(c["peak_t"], peak, c["peak_hf"], c["peak_hf_lf"])

    def _on_snap(self, t: float, peak_db: float, hf: float, hf_lf: float) -> SnapEvent | None:
        cfg = self.cfg
        if t < self._cooldown_until:
            return None
        if cfg.mode != "double":
            self._cooldown_until = t + cfg.cooldown_ms / 1000.0
            return SnapEvent(t, peak_db, "trigger", 1, hf, hf_lf)
        last = self._last_snap_t
        if last is not None:
            gap = (t - last) * 1000.0
            if cfg.double_min_gap_ms <= gap <= cfg.double_max_gap_ms:
                self._last_snap_t = None
                self._cooldown_until = t + cfg.cooldown_ms / 1000.0
                return SnapEvent(t, peak_db, "trigger", 2, hf, hf_lf)
        self._last_snap_t = t
        return SnapEvent(t, peak_db, "snap", 1, hf, hf_lf)
