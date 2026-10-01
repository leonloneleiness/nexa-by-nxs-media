"""Kiểm thử bộ phát hiện vỗ tay bằng tín hiệu tổng hợp (không dùng mic thật)."""
from __future__ import annotations

import numpy as np
import pytest

from nexa.audio.clap_detector import SR, ClapConfig, ClapDetector

rng = np.random.default_rng(42)


def noise(sec, amp=0.003):
    return (rng.standard_normal(int(SR * sec)) * amp).astype(np.float32)


def clap(amp=0.5):
    n = int(SR * 0.06)
    t = np.arange(n) / SR
    return (rng.standard_normal(n) * amp * np.exp(-t / 0.008)).astype(np.float32)


def speech(sec=0.6, amp=0.2):
    t = np.arange(int(SR * sec)) / SR
    s = sum(np.sin(2 * np.pi * 140 * k * t) / k for k in range(1, 15))
    env = np.minimum(1, t / 0.02) * np.minimum(1, (sec - t) / 0.05)
    return (amp * s * env / 3).astype(np.float32)


def knock(amp=0.6):
    n = int(SR * 0.08)
    t = np.arange(n) / SR
    return (amp * np.sin(2 * np.pi * 90 * t) * np.exp(-t / 0.02)).astype(np.float32)


def run(sig, **cfg):
    d = ClapDetector(ClapConfig(**cfg))
    events = []
    for i in range(0, len(sig), 320):  # khối 20 ms như pipeline thật
        events += d.process(sig[i:i + 320], i / SR)
    return events, d


BG = 2.5  # giây nền để hiệu chuẩn


def test_silence_and_background_noise_no_event():
    events, d = run(np.concatenate([noise(BG), noise(3)]))
    assert events == []
    assert d.calibrated


def test_single_clap_wakes_once():
    events, _ = run(np.concatenate([noise(BG), clap(), noise(1)]))
    assert [(e.kind, e.count) for e in events] == [("wake", 1)]
    assert abs(events[0].t - BG) < 0.05


def test_speech_like_sound_rejected():
    events, _ = run(np.concatenate([noise(BG), speech(), noise(0.5), speech(1.0, 0.4), noise(1)]))
    assert events == []


def test_low_frequency_knock_rejected():
    events, _ = run(np.concatenate([noise(BG), knock(), noise(1)]))
    assert events == []


def test_sustained_loud_noise_rejected():
    events, _ = run(np.concatenate([noise(BG), noise(0.5, 0.3), noise(1)]))
    assert events == []


def test_no_detection_before_calibration():
    events, _ = run(np.concatenate([noise(0.5), clap(), noise(1)]))
    assert events == []


def test_quiet_clap_below_absolute_minimum_ignored():
    events, _ = run(np.concatenate([noise(BG), clap(0.01), noise(1)]))
    assert events == []


def test_cooldown_blocks_second_wake():
    sig = np.concatenate([noise(BG), clap(), noise(0.5), clap(), noise(2), clap(), noise(0.5)])
    events, _ = run(sig, cooldown_ms=1500)
    wakes = [e for e in events if e.kind == "wake"]
    assert len(wakes) == 2
    assert wakes[1].t - wakes[0].t > 1.5


def test_debounce_merges_echo_of_same_clap():
    sig = np.concatenate([noise(BG), clap(), noise(0.04), clap(0.3), noise(1)])
    events, _ = run(sig)
    assert len(events) == 1


def test_double_mode_requires_two_claps_in_window():
    sig = np.concatenate([noise(BG), clap(), noise(0.3), clap(), noise(1)])
    events, _ = run(sig, mode="double")
    assert [(e.kind, e.count) for e in events] == [("clap", 1), ("wake", 2)]


def test_double_mode_gap_too_long_does_not_wake():
    sig = np.concatenate([noise(BG), clap(), noise(1.2), clap(), noise(1)])
    events, _ = run(sig, mode="double", double_max_gap_ms=700)
    assert all(e.kind == "clap" for e in events)
    assert len(events) == 2


def test_double_mode_single_clap_does_not_wake():
    events, _ = run(np.concatenate([noise(BG), clap(), noise(2)]), mode="double")
    assert [e.kind for e in events] == ["clap"]


def test_suppress_for_blocks_own_sounds():
    d = ClapDetector(ClapConfig())
    sig = noise(BG)
    for i in range(0, len(sig), 320):
        d.process(sig[i:i + 320], i / SR)
    d.suppress_for(BG, 1.0)
    burst = np.concatenate([clap(), noise(0.5)])
    events = []
    for i in range(0, len(burst), 320):
        events += d.process(burst[i:i + 320], BG + i / SR)
    assert events == []


@pytest.mark.parametrize("sens,expect", [(0.0, 0), (1.0, 1)])
def test_sensitivity_changes_threshold(sens, expect):
    events, d = run(np.concatenate([noise(BG, 0.01), clap(0.15), noise(1, 0.01)]), sensitivity=sens, min_level_dbfs=-60)
    assert len([e for e in events if e.kind == "wake"]) == expect
