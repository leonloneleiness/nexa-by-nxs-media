"""Ghi lại câu nói thật để làm bộ dữ liệu nghiên cứu (chỉ khi anh BẬT research.record_corpus).

Mỗi câu: một file WAV 16 kHz mono 16-bit + một dòng trong utterances.jsonl:
  id, thời điểm, mã người nói (ẩn danh), độ dài, chữ Whisper nghe được (thô và sau chuẩn hóa), loại lệnh mà
  IntentRouter nhận ra, độ tin cậy, model/thiết bị, chế độ gợi ý và các tên ngữ cảnh đã dùng.
Trường "reference" để trống: người gán nhãn điền sau bằng scripts/asr_corpus.py (export → sửa CSV → import).

Dữ liệu nằm ngoài thư mục dự án (%LOCALAPPDATA%\\NEXA\\asr_corpus) nên không lọt vào ZIP bàn giao hay git.
Không ghi tiêu đề cửa sổ, chỉ ghi tên ngữ cảnh đã lọc qua từ vựng đã biết (xem context_bias.py).
"""
from __future__ import annotations

import json
import threading
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np

from nexa.utils.logging import get_logger

log = get_logger("research")

SAMPLE_RATE = 16000


def write_wav(path: Path, audio: np.ndarray, sr: int = SAMPLE_RATE) -> None:
    pcm = (np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        sr, ch, width = wf.getframerate(), wf.getnchannels(), wf.getsampwidth()
        raw = wf.readframes(wf.getnframes())
    if width != 2:
        raise ValueError(f"{path.name}: chỉ hỗ trợ WAV 16-bit")
    x = np.frombuffer(raw, "<i2").astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


class CorpusRecorder:
    def __init__(self, config: Any, default_root: Path) -> None:
        self.config = config
        self.default_root = default_root
        self._lock = threading.Lock()
        self._count: int | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("research.record_corpus"))

    @property
    def root(self) -> Path:
        custom = str(self.config.get("research.corpus_dir") or "").strip()
        return Path(custom) if custom else self.default_root

    @property
    def manifest(self) -> Path:
        return self.root / "utterances.jsonl"

    def _existing(self) -> int:
        if self._count is None:
            try:
                with open(self.manifest, encoding="utf-8") as f:
                    self._count = sum(1 for line in f if line.strip())
            except FileNotFoundError:
                self._count = 0
        return self._count

    def record(self, audio: np.ndarray, sr: int, res: Any, route_kind: str = "", normalized: str = "",
               model: str = "") -> str | None:
        """Lưu một câu. Trả về id, hoặc None nếu đang tắt / đã đủ số câu / lỗi ghi (không làm hỏng luồng chính)."""
        if not self.enabled:
            return None
        with self._lock:
            try:
                if self._existing() >= int(self.config.get("research.max_items") or 5000):
                    return None
                now = time.time()
                day = time.strftime("%Y%m%d", time.localtime(now))
                folder = self.root / "audio" / day
                folder.mkdir(parents=True, exist_ok=True)
                uid = time.strftime("%Y%m%d-%H%M%S", time.localtime(now)) + f"-{int(now * 1000) % 1000:03d}"
                if sr != SAMPLE_RATE:
                    from math import gcd
                    from scipy.signal import resample_poly
                    g = gcd(sr, SAMPLE_RATE)
                    audio = resample_poly(audio, SAMPLE_RATE // g, sr // g)
                wav = folder / f"{uid}.wav"
                write_wav(wav, audio)
                append_jsonl(self.manifest, {
                    "id": uid,
                    "time": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(now)),
                    "speaker": str(self.config.get("research.speaker_id") or ""),
                    "audio": wav.relative_to(self.root).as_posix(),
                    "duration_s": round(float(res.duration_s), 3),
                    "hyp": res.text, "hyp_normalized": normalized, "ok": bool(res.ok), "reason": res.reason,
                    "route": route_kind, "avg_logprob": round(float(res.avg_logprob), 4),
                    "no_speech_prob": round(float(res.no_speech_prob), 4), "elapsed_s": round(float(res.elapsed_s), 3),
                    "model": model, "bias_mode": res.bias_mode, "context": list(res.context_terms),
                    "reference": "",
                })
                self._count = self._existing() + 1
                return uid
            except Exception:
                log.exception("Không ghi được câu vào bộ dữ liệu nghiên cứu")
                return None
