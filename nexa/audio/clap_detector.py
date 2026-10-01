"""Phát hiện tiếng vỗ tay từ tín hiệu mic (16 kHz mono, xử lý theo bước 10 ms).

Không chỉ so một ngưỡng âm lượng cố định. Một xung được coi là tiếng vỗ tay khi đồng thời:
1. Mức năng lượng vượt ngưỡng thích nghi = nền ồn (đã hiệu chuẩn, cập nhật liên tục) + biên độ
   phụ thuộc độ nhạy, và vượt mức tuyệt đối tối thiểu.
2. Khởi phát đột ngột: tăng ≥ rise_db so với 20–80 ms trước đó (trước đó phải yên tĩnh).
3. Xung ngắn: số khung trong phạm vi 6 dB của đỉnh ≤ 40 ms.
4. Tắt nhanh: sau ~60–80 ms năng lượng giảm ≥ decay_db so với đỉnh (lời nói/nhạc thì kéo dài).
5. Phổ rộng: tỷ lệ năng lượng ≥ 1,5 kHz đủ lớn (loại tiếng gõ bàn/bước chân trầm).
Sau đó áp dụng debounce, chế độ một/hai tiếng (khoảng cách cấu hình được) và cooldown.
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
class ClapConfig:
    mode: str = "single"
    sensitivity: float = 0.55
    min_level_dbfs: float = -42.0
    double_min_gap_ms: int = 120
    double_max_gap_ms: int = 700
    debounce_ms: int = 110
    cooldown_ms: int = 1500
    calibration_seconds: float = 2.0
    hf_min_ratio: float = 0.28
    decay_db: float = 12.0
    max_width_hops: int = 4

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "ClapConfig":
        d = d or {}
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)

    @property
    def margin_db(self) -> float:
        s = min(1.0, max(0.0, float(self.sensitivity)))
        return 24.0 - 14.0 * s        # 24 dB (kém nhạy) … 10 dB (rất nhạy)

    @property
    def rise_db(self) -> float:
        return max(9.0, self.margin_db * 0.8)


@dataclass
class ClapEvent:
    t: float
    peak_db: float
    kind: str           # "clap" (một tiếng lẻ, dùng cho màn hình thử) | "wake" (đủ điều kiện đánh thức)
    count: int
    hf_ratio: float


class ClapDetector:
    def __init__(self, cfg: ClapConfig | None = None) -> None:
        self.cfg = cfg or ClapConfig()
        self._window = np.hanning(HOP).astype(np.float32)
        freqs = np.fft.rfftfreq(NFFT, 1.0 / SR)
        self._hf_mask = freqs >= 1500.0
        self._lf_mask = freqs >= 80.0
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
        self._last_clap_t: float | None = None
        self.last_db = -100.0
        if keep_floor and floor is not None:
            self.floor_db = floor
            self.calibrated = calibrated
        else:
            self.floor_db = -70.0
            self.calibrated = False

    def update_config(self, cfg: ClapConfig) -> None:
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
        self._last_clap_t = None

    # ----- xử lý -----
    def process(self, samples: np.ndarray, t0: float) -> list[ClapEvent]:
        """samples: float32 mono 16 kHz; t0: thời điểm (giây) của mẫu đầu tiên trong khối."""
        if samples.size == 0:
            return []
        if self._t_base is None or not self._buf.size:
            # Tính thời điểm của mẫu đầu tiên còn trong bộ đệm.
            self._t_base = t0 - self._buf.size / SR
        self._buf = np.concatenate([self._buf, samples.astype(np.float32, copy=False)])
        events: list[ClapEvent] = []
        while self._buf.size >= HOP:
            hop = self._buf[:HOP]
            self._buf = self._buf[HOP:]
            t = self._t_base
            self._t_base += HOP / SR
            ev = self._process_hop(hop, t)
            if ev is not None:
                events.append(ev)
        return events

    def _features(self, hop: np.ndarray) -> tuple[float, float]:
        energy = float(np.mean(hop * hop))
        e_db = 10.0 * np.log10(energy + 1e-12)
        spec = np.abs(np.fft.rfft(hop * self._window, NFFT)) ** 2
        total = float(spec[self._lf_mask].sum()) + 1e-12
        hf = float(spec[self._hf_mask].sum()) / total
        return e_db, hf

    def _process_hop(self, hop: np.ndarray, t: float) -> ClapEvent | None:
        cfg = self.cfg
        e_db, hf = self._features(hop)
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

        result: ClapEvent | None = None
        if self._cand is not None:
            result = self._update_candidate(e_db, hf, t)
        elif t >= self._ignore_until:
            # Mức 20–80 ms trước (bỏ khung liền trước vì sườn lên có thể bắt đầu ở đó).
            prev = list(self._history)[-8:-1]
            pre_level = max(prev) if prev else self.floor_db
            if (e_db >= self.threshold_db and e_db - pre_level >= cfg.rise_db
                    and pre_level < self.threshold_db - 3.0):
                self._cand = {"start_t": t, "peak_db": e_db, "peak_hf": hf, "peak_t": t, "hops": [e_db],
                              "since_peak": 0}
        # Cập nhật nền ồn (phân vị 30% của ~3 giây gần nhất, bỏ các khung có xung).
        if self._cand is None and result is None and e_db < self.threshold_db:
            self._floor_hist.append(e_db)
            if self._hop_index % 10 == 0 and len(self._floor_hist) >= 50:
                self.floor_db = float(min(-10.0, max(-95.0, np.percentile(self._floor_hist, 30))))
        self._history.append(e_db)
        return result

    def _update_candidate(self, e_db: float, hf: float, t: float) -> ClapEvent | None:
        c = self._cand
        c["hops"].append(e_db)
        if e_db > c["peak_db"] and len(c["hops"]) <= 3:
            c["peak_db"], c["peak_hf"], c["peak_t"] = e_db, max(c["peak_hf"], hf), t
            c["since_peak"] = 0
            return None
        c["since_peak"] += 1
        if c["since_peak"] < 7:
            return None
        # Đánh giá sau ~70 ms kể từ đỉnh.
        self._cand = None
        peak = c["peak_db"]
        hops = c["hops"]
        width = sum(1 for v in hops if v >= peak - 6.0)
        tail = max(hops[-3:])
        is_clap = (width <= self.cfg.max_width_hops and tail <= peak - self.cfg.decay_db
                   and c["peak_hf"] >= self.cfg.hf_min_ratio)
        self._ignore_until = max(self._ignore_until, t + self.cfg.debounce_ms / 1000.0 - 0.07)
        if not is_clap:
            return None
        return self._on_clap(c["peak_t"], peak, c["peak_hf"])

    def _on_clap(self, t: float, peak_db: float, hf: float) -> ClapEvent | None:
        cfg = self.cfg
        if t < self._cooldown_until:
            return None
        if cfg.mode != "double":
            self._cooldown_until = t + cfg.cooldown_ms / 1000.0
            return ClapEvent(t, peak_db, "wake", 1, hf)
        last = self._last_clap_t
        if last is not None:
            gap = (t - last) * 1000.0
            if cfg.double_min_gap_ms <= gap <= cfg.double_max_gap_ms:
                self._last_clap_t = None
                self._cooldown_until = t + cfg.cooldown_ms / 1000.0
                return ClapEvent(t, peak_db, "wake", 2, hf)
        self._last_clap_t = t
        return ClapEvent(t, peak_db, "clap", 1, hf)
