"""Luồng mic duy nhất của NEXA.

- AudioPipeline là thành phần DUY NHẤT mở mic. Callback của sounddevice chỉ sao chép khối âm
  thanh vào hàng đợi hữu hạn (không gọi model, không gọi mạng).
- Worker chuyển về mono 16 kHz, rồi phân phối cho: đồng hồ mức âm (UI), ClapDetector, và
  UtteranceSegmenter (VAD tách câu) khi đang ở chế độ nghe.
- Khi NEXA đang phát âm thanh (TTS/hiệu ứng), đầu vào bị "mute" + thêm đuôi chống vọng để
  âm thanh của chính ứng dụng không kích hoạt lại vỗ tay hoặc bị nhận thành lệnh.
- Không ghi âm thanh thô ra đĩa.
"""
from __future__ import annotations

import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from math import gcd
from typing import Any, Callable

import numpy as np

from nexa.audio.clap_detector import ClapConfig, ClapDetector, ClapEvent
from nexa.audio.snap_detector import SnapConfig, SnapDetector, SnapEvent
from nexa.utils.logging import get_logger

log = get_logger("audio")

TARGET_SR = 16000
BLOCK_MS = 20
SNAP_CLAP_WINDOW_S = 0.35   # một cú búng tay cũng làm ClapDetector kêu: gộp hai sự kiện gần nhau
CLAP_HOLD_S = 0.15          # khi đang nghe búng tay, giữ sự kiện vỗ tay chờ xem có phải búng tay không


def to_mono(block: np.ndarray) -> np.ndarray:
    if block.ndim == 1:
        return block.astype(np.float32, copy=False)
    return block.mean(axis=1).astype(np.float32)


def resample(x: np.ndarray, sr_in: int, sr_out: int = TARGET_SR) -> np.ndarray:
    if sr_in == sr_out or x.size == 0:
        return x.astype(np.float32, copy=False)
    from scipy.signal import resample_poly
    g = gcd(int(sr_in), int(sr_out))
    return resample_poly(x, sr_out // g, sr_in // g).astype(np.float32)


@dataclass
class VadConfig:
    start_margin_db: float = 10.0
    end_margin_db: float = 6.0
    min_speech_ms: int = 250
    end_silence_ms: int = 800
    max_utterance_s: float = 12.0
    listen_timeout_s: float = 8.0
    pre_roll_ms: int = 300
    # Nền ồn "động" trong lúc ghi: phân vị thấp của 1,5 s gần nhất. Lời nói có khoảng lặng giữa các âm tiết còn nhạc
    # thì không, nên khi anh nói xong mà nhạc vẫn phát, nền động = mức nhạc → vẫn chốt câu (trước đây ghi đủ 12 s).
    rec_floor_window_ms: int = 1500
    rec_floor_percentile: float = 20.0

    @classmethod
    def from_dict(cls, d: dict | None) -> "VadConfig":
        d = d or {}
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


class UtteranceSegmenter:
    """VAD dựa trên năng lượng dải lời nói (150–3800 Hz) so với nền ồn thích nghi."""

    def __init__(self, cfg: VadConfig) -> None:
        self.cfg = cfg
        self.floor_db = -60.0
        self._floor_hist: deque[float] = deque(maxlen=150)
        self.state = "idle"          # idle | waiting | recording
        self._pre: deque[np.ndarray] = deque()
        self._chunks: list[np.ndarray] = []
        self._voiced_ms = 0.0
        self._gap_ms = 0.0
        self._started_at = 0.0
        self._rec_started = 0.0
        self._last_voice = 0.0
        self._rec_hist: deque[float] = deque(maxlen=75)

    def start(self, t: float) -> None:
        self.state = "waiting"
        self._started_at = t
        self._pre.clear()
        self._chunks = []
        self._voiced_ms = 0.0
        self._gap_ms = 0.0

    def stop(self) -> None:
        self.state = "idle"
        self._pre.clear()
        self._chunks = []

    @staticmethod
    def band_db(x: np.ndarray) -> float:
        if x.size < 32:
            return -100.0
        spec = np.abs(np.fft.rfft(x * np.hanning(x.size))) ** 2
        freqs = np.fft.rfftfreq(x.size, 1.0 / TARGET_SR)
        band = spec[(freqs >= 150) & (freqs <= 3800)].sum()
        return float(10 * np.log10(band / (x.size ** 2) + 1e-12))  # thang tương đối, chỉ so với nền ồn

    def process(self, x: np.ndarray, t: float) -> tuple[str, Any] | None:
        """x: khối 16 kHz. Trả về ('speech_start', None) | ('utterance', audio) | ('timeout', None) | None."""
        e = self.band_db(x)
        block_ms = 1000.0 * x.size / TARGET_SR
        if self.state != "recording":
            self._floor_hist.append(e)
            if len(self._floor_hist) >= 10:
                self.floor_db = float(np.percentile(self._floor_hist, 25))
        if self.state == "idle":
            return None
        if self.state == "waiting":
            self._pre.append(x)
            while len(self._pre) * BLOCK_MS > self.cfg.pre_roll_ms + self.cfg.min_speech_ms:
                self._pre.popleft()
            if e > self.floor_db + self.cfg.start_margin_db:
                self._voiced_ms += block_ms
                self._gap_ms = 0.0
            else:
                self._gap_ms += block_ms
                if self._gap_ms > 60:
                    self._voiced_ms = 0.0
            if self._voiced_ms >= self.cfg.min_speech_ms:
                self.state = "recording"
                self._chunks = list(self._pre)
                self._pre.clear()
                self._rec_started = t
                self._last_voice = t
                self._rec_hist = deque(maxlen=max(10, int(self.cfg.rec_floor_window_ms / BLOCK_MS)))
                return ("speech_start", None)
            if t - self._started_at > self.cfg.listen_timeout_s:
                self.state = "idle"
                return ("timeout", None)
            return None
        # recording
        self._chunks.append(x)
        self._rec_hist.append(e)
        floor = self.floor_db
        if len(self._rec_hist) >= self._rec_hist.maxlen // 3:
            floor = max(floor, float(np.percentile(self._rec_hist, self.cfg.rec_floor_percentile)))
        if e > floor + self.cfg.end_margin_db:
            self._last_voice = t
        if (t - self._last_voice) * 1000.0 >= self.cfg.end_silence_ms or t - self._rec_started >= self.cfg.max_utterance_s:
            audio = np.concatenate(self._chunks) if self._chunks else np.zeros(0, np.float32)
            self.state = "idle"
            self._chunks = []
            return ("utterance", audio)
        return None


class AudioPipeline:
    def __init__(self, config: Any,
                 on_clap: Callable[[ClapEvent], None] | None = None,
                 on_level: Callable[[float], None] | None = None,
                 on_utterance: Callable[[np.ndarray], None] | None = None,
                 on_speech_start: Callable[[], None] | None = None,
                 on_listen_timeout: Callable[[], None] | None = None,
                 on_error: Callable[[str], None] | None = None,
                 on_snap: Callable[[SnapEvent], None] | None = None,
                 snap_gate: Callable[[], bool] | None = None) -> None:
        self.config = config
        self.on_clap = on_clap
        self.on_snap = on_snap
        self.snap_gate = snap_gate
        self.on_level = on_level
        self.on_utterance = on_utterance
        self.on_speech_start = on_speech_start
        self.on_listen_timeout = on_listen_timeout
        self.on_error = on_error
        self.clap = ClapDetector(ClapConfig.from_dict(config.get("audio.clap")))
        self.snap = SnapDetector(SnapConfig.from_dict(config.get("audio.snap")))
        self._held_claps: list[ClapEvent] = []
        self._last_snap_t = -1e9
        self.segmenter = UtteranceSegmenter(VadConfig.from_dict(config.get("audio.vad")))
        self._q: "queue.Queue[tuple[np.ndarray, float]]" = queue.Queue(maxsize=150)
        self._stream = None
        self._last_block_t = time.monotonic()
        self._thread: threading.Thread | None = None
        self._running = False
        self._lock = threading.RLock()
        self._mute_depth = 0
        self._mute_until = 0.0
        self._listen_request: float | None = None
        self.sample_rate = TARGET_SR
        self.channels = 1
        self.device_name = ""
        self.overflows = 0
        self.dropped = 0
        self.error = ""
        self.level_db = -100.0
        self._last_level_emit = 0.0

    # ----- thiết bị -----
    @staticmethod
    def list_input_devices(preferred_hostapi: str = "MME") -> list[dict[str, Any]]:
        import sounddevice as sd
        apis = sd.query_hostapis()
        out, seen = [], set()
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] <= 0:
                continue
            api = apis[d["hostapi"]]["name"]
            if preferred_hostapi and api != preferred_hostapi:
                continue
            if d["name"] in seen:
                continue
            seen.add(d["name"])
            out.append({"index": i, "name": d["name"], "hostapi": api, "channels": d["max_input_channels"],
                        "default_samplerate": d["default_samplerate"]})
        return out

    @staticmethod
    def list_output_devices(preferred_hostapi: str = "MME") -> list[dict[str, Any]]:
        import sounddevice as sd
        apis = sd.query_hostapis()
        out, seen = [], set()
        for i, d in enumerate(sd.query_devices()):
            if d["max_output_channels"] <= 0:
                continue
            api = apis[d["hostapi"]]["name"]
            if preferred_hostapi and api != preferred_hostapi:
                continue
            if d["name"] in seen:
                continue
            seen.add(d["name"])
            out.append({"index": i, "name": d["name"], "hostapi": api})
        return out

    @staticmethod
    def find_device(name: str | None, kind: str, preferred_hostapi: str = "MME") -> int | None:
        if not name:
            return None
        import sounddevice as sd
        apis = sd.query_hostapis()
        key = "max_input_channels" if kind == "input" else "max_output_channels"
        candidates = []
        for i, d in enumerate(sd.query_devices()):
            if d[key] > 0 and d["name"] == name:
                candidates.append((0 if apis[d["hostapi"]]["name"] == preferred_hostapi else 1, i))
        return sorted(candidates)[0][1] if candidates else None

    def _choose_format(self, device: int | None) -> tuple[int, int]:
        import sounddevice as sd
        info = sd.query_devices(device, "input")
        for sr in (TARGET_SR, int(info["default_samplerate"]), 48000, 44100):
            for ch in (1, min(2, int(info["max_input_channels"]))):
                try:
                    sd.check_input_settings(device=device, samplerate=sr, channels=ch, dtype="float32")
                    return sr, ch
                except Exception:
                    continue
        raise RuntimeError("Mic không hỗ trợ định dạng float32 nào phù hợp")

    # ----- vòng đời -----
    def start(self) -> bool:
        import sounddevice as sd
        with self._lock:
            if self._running:
                return True
            try:
                pref = self.config.get("audio.preferred_hostapi") or "MME"
                device = self.find_device(self.config.get("audio.input_device"), "input", pref)
                self.sample_rate, self.channels = self._choose_format(device)
                info = sd.query_devices(device, "input")
                self.device_name = info["name"]
                blocksize = int(self.sample_rate * BLOCK_MS / 1000)
                self._stream = sd.InputStream(device=device, samplerate=self.sample_rate, channels=self.channels,
                                              dtype="float32", blocksize=blocksize, callback=self._callback)
                self._stream.start()
            except Exception as exc:
                self.error = f"Không mở được mic: {exc}"
                log.error(self.error)
                if self.on_error:
                    self.on_error(self.error)
                return False
            self.error = ""
            self._last_block_t = time.monotonic()
            self._running = True
            self._thread = threading.Thread(target=self._worker, name="nexa-audio", daemon=True)
            self._thread.start()
            log.info("Mic: %s @ %d Hz, %d kênh", self.device_name, self.sample_rate, self.channels)
            return True

    def stop(self) -> None:
        with self._lock:
            self._running = False
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def restart(self) -> bool:
        self.stop()
        self.clap = ClapDetector(ClapConfig.from_dict(self.config.get("audio.clap")))
        self.snap = SnapDetector(SnapConfig.from_dict(self.config.get("audio.snap")))
        self._held_claps = []
        self.segmenter = UtteranceSegmenter(VadConfig.from_dict(self.config.get("audio.vad")))
        return self.start()

    def update_clap_config(self) -> None:
        self.clap.update_config(ClapConfig.from_dict(self.config.get("audio.clap")))
        self.snap.update_config(SnapConfig.from_dict(self.config.get("audio.snap")))

    def _snap_active(self) -> bool:
        if not self.on_snap or self.config.get("audio.snap.enabled") is False:
            return False
        try:
            return bool(self.snap_gate()) if self.snap_gate else True
        except Exception:
            return False

    def _detect_transients(self, x: np.ndarray, t0: float) -> None:
        """Chạy song song ClapDetector và SnapDetector; một cú búng tay chỉ sinh sự kiện búng tay."""
        snap_events = self.snap.process(x, t0)      # luôn chạy để giữ mức nền đã hiệu chuẩn
        clap_events = self.clap.process(x, t0)
        active = self._snap_active()
        for ev in snap_events:
            if ev.kind != "trigger" or not active:
                continue
            self._last_snap_t = ev.t
            self._held_claps = [c for c in self._held_claps if abs(c.t - ev.t) > SNAP_CLAP_WINDOW_S]
            self.on_snap(ev)
        for ev in clap_events:
            if abs(ev.t - self._last_snap_t) <= SNAP_CLAP_WINDOW_S:
                continue
            if active:
                self._held_claps.append(ev)
            elif self.on_clap:
                self.on_clap(ev)
        t_end = t0 + x.size / TARGET_SR
        due = [c for c in self._held_claps if t_end - c.t >= CLAP_HOLD_S or not active]
        if due:
            self._held_claps = [c for c in self._held_claps if c not in due]
            for ev in due:
                if self.on_clap:
                    self.on_clap(ev)

    @property
    def running(self) -> bool:
        return self._running

    def stalled(self, seconds: float) -> bool:
        """Mic đang mở nhưng không có khối âm thanh nào trong `seconds` giây gần nhất."""
        return self._running and time.monotonic() - self._last_block_t > seconds

    # ----- callback (luồng âm thanh thời gian thực: chỉ sao chép) -----
    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ARG002
        if status and status.input_overflow:
            self.overflows += 1
        item = (indata.copy(), time.monotonic())
        self._last_block_t = item[1]
        try:
            self._q.put_nowait(item)
        except queue.Full:
            try:
                self._q.get_nowait()
            except queue.Empty:
                pass
            self.dropped += 1
            try:
                self._q.put_nowait(item)
            except queue.Full:
                pass

    # ----- điều khiển chế độ -----
    def mute(self) -> None:
        """Chặn đầu vào (lồng được) trong lúc NEXA phát âm thanh."""
        with self._lock:
            self._mute_depth += 1
            self.segmenter.stop()

    def unmute(self, tail_ms: int | None = None) -> None:
        with self._lock:
            self._mute_depth = max(0, self._mute_depth - 1)
            tail = (tail_ms if tail_ms is not None else int(self.config.get("audio.echo_tail_ms") or 400)) / 1000.0
            self._mute_until = max(self._mute_until, time.monotonic() + tail)

    @property
    def muted(self) -> bool:
        return self._mute_depth > 0 or time.monotonic() < self._mute_until

    def listen(self) -> None:
        """Bắt đầu chờ một câu nói (sau khi hết mute)."""
        with self._lock:
            self._listen_request = time.monotonic()

    def set_conversation_mode(self, enabled: bool) -> None:
        """Chờ khoảng ngừng dài hơn khi tâm sự; không thay đổi cấu hình mic đã lưu."""
        cfg = VadConfig.from_dict(self.config.get("audio.vad"))
        if enabled:
            cfg.end_silence_ms = max(cfg.end_silence_ms, 1400)
            cfg.max_utterance_s = max(cfg.max_utterance_s, 60.0)
        with self._lock:
            self.segmenter.cfg = cfg

    def cancel_listen(self) -> None:
        with self._lock:
            self._listen_request = None
            self.segmenter.stop()

    @property
    def listening(self) -> bool:
        return self._listen_request is not None or self.segmenter.state != "idle"

    # ----- worker -----
    def _worker(self) -> None:
        while self._running:
            try:
                block, t_cb = self._q.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self._handle(block, t_cb)
            except Exception:
                log.exception("Lỗi xử lý âm thanh")

    def _handle(self, block: np.ndarray, t_cb: float) -> None:
        x = resample(to_mono(block), self.sample_rate)
        t0 = t_cb - x.size / TARGET_SR
        rms = float(np.sqrt(np.mean(x * x) + 1e-12))
        self.level_db = 20 * np.log10(rms)
        now = time.monotonic()
        if self.on_level and now - self._last_level_emit > 0.033:
            self._last_level_emit = now
            self.on_level(0.0 if self.muted else min(1.0, max(0.0, (self.level_db + 60) / 50)))
        if self.muted:
            # Không cho clap detector thấy âm thanh của chính NEXA; bỏ ứng viên đang dở.
            self.clap.suppress_for(t0, x.size / TARGET_SR)
            self.snap.suppress_for(t0, x.size / TARGET_SR)
            self._held_claps = []
            return
        self._detect_transients(x, t0)
        with self._lock:
            req = self._listen_request
            if req is not None and self.segmenter.state == "idle":
                self._listen_request = None
                self.segmenter.start(now)
        if self.segmenter.state == "idle":
            return
        result = self.segmenter.process(x, now)
        if result is None:
            return
        kind, audio = result
        if kind == "speech_start" and self.on_speech_start:
            self.on_speech_start()
        elif kind == "utterance" and self.on_utterance:
            self.on_utterance(audio)
        elif kind == "timeout" and self.on_listen_timeout:
            self.on_listen_timeout()
