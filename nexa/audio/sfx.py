"""Hiệu ứng âm thanh ngắn, tạo procedural bằng NumPy (không phụ thuộc tệp ngoài).

scripts/generate_sounds.py ghi các âm này ra assets/sounds/*.wav; nếu tệp tồn tại thì dùng tệp.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 24000


def _env(n: int, attack: float = 0.01, release: float = 0.25) -> np.ndarray:
    t = np.arange(n) / SR
    dur = n / SR
    a = np.clip(t / max(attack, 1e-3), 0, 1)
    r = np.clip((dur - t) / max(release, 1e-3), 0, 1)
    return a * r


def _tone(freqs: list[float], dur: float, gain: float = 0.25, sweep: float = 0.0) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for i, f in enumerate(freqs):
        inst = f * (1 + sweep * t / dur)
        phase = 2 * np.pi * np.cumsum(inst) / SR
        out += np.sin(phase) / (i + 1)
    out *= _env(n, 0.01, dur * 0.6)
    return (gain * out / max(1e-6, np.max(np.abs(out)))).astype(np.float32)


def synth(name: str) -> np.ndarray:
    if name == "wake":
        a = _tone([392, 784, 1175], 0.18, 0.22, sweep=0.5)
        b = _tone([523, 1046, 1568], 0.35, 0.25, sweep=0.2)
        return np.concatenate([a, b])
    if name == "sleep":
        return _tone([660, 330], 0.45, 0.2, sweep=-0.45)
    if name == "confirm":
        return np.concatenate([_tone([880], 0.08, 0.18), np.zeros(int(SR * 0.04), np.float32), _tone([1320], 0.1, 0.18)])
    if name == "error":
        return _tone([220, 233], 0.35, 0.2)
    if name == "listen":
        return _tone([988], 0.09, 0.14, sweep=0.2)
    return np.zeros(1, np.float32)


def write_wav(path: Path, samples: np.ndarray, sr: int = SR) -> None:
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        width = wf.getsampwidth()
        raw = wf.readframes(wf.getnframes())
    if width == 2:
        x = np.frombuffer(raw, "<i2").astype(np.float32) / 32768.0
    elif width == 4:
        x = np.frombuffer(raw, "<i4").astype(np.float32) / 2147483648.0
    elif width == 1:
        x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) / 128.0
    else:
        raise ValueError("Định dạng WAV không hỗ trợ")
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def load(name: str, assets_dir: Path) -> tuple[np.ndarray, int]:
    path = assets_dir / "sounds" / f"{name}.wav"
    if path.exists():
        try:
            return read_wav(path)
        except Exception:
            pass
    return synth(name), SR
