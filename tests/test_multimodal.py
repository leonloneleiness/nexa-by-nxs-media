from types import SimpleNamespace
import time

import numpy as np
import pytest

from nexa.core.events import Source, ToolCall, ToolResult
from nexa.core.multimodal import MultimodalCoordinator, SpeechContext
from nexa.audio.stt import SpeechRecognizer


@pytest.mark.parametrize("offset", [-0.5, 0.0, 0.5, 1.5])
@pytest.mark.parametrize("applied", [False, True])
def test_capture_time_not_decode_arrival(config, offset, applied):
    fusion = MultimodalCoordinator(config, clock=lambda: 18)
    ctx = SpeechContext(10, 11)
    action = fusion.observe("youtube_pause", {}, 10 + offset, applied=applied)
    calls, why = fusion.reconcile([("youtube_pause", {})], ctx)
    assert not why and action.consumed
    assert calls == ([] if applied else [("youtube_pause", {})])


def test_conflict_stale_and_distinct_targets(config):
    fusion = MultimodalCoordinator(config)
    ctx = SpeechContext(10, 11, project_id="A")
    fusion.observe("zoom_3d_view", {"direction": "out"}, 10.3, "B")
    fusion.observe("zoom_3d_view", {"direction": "out"}, 4, "A")
    calls = [("zoom_3d_view", {"direction": "in"})]
    assert fusion.reconcile(calls, ctx) == (calls, "")
    conflict = fusion.observe("zoom_3d_view", {"direction": "out"}, 10.3, "A")
    result, why = fusion.reconcile(calls, ctx)
    assert not result and "trái nhau" in why and conflict.consumed


def test_target_bound_before_delayed_decode_and_ambiguous(config):
    fusion = MultimodalCoordinator(config)
    ctx = SpeechContext(10, 11, project_id="A")
    fusion.target(10.4, "A", "rotor")
    fusion.target(15, "A", "wing")
    assert fusion.resolve_target(ctx) == "rotor"
    fusion.target(10.8, "A", "wing")
    assert fusion.resolve_target(ctx) == ""


def test_cancel_and_timeout_release_pending(config):
    now = [10.0]
    fusion = MultimodalCoordinator(config, clock=lambda: now[0])
    ctx = SpeechContext(10, 11)
    fusion.begin(ctx)
    assert fusion.waiting()
    now[0] = 31
    assert not fusion.waiting()
    fusion.clear()
    assert fusion.reconcile([("youtube_pause", {})], ctx)[1]


def test_guard_commits_success_only_and_does_not_dedupe_same_source(config):
    fusion = MultimodalCoordinator(config)
    gesture = ToolCall("youtube_pause", source=Source.GESTURE, input_started_at=10)
    voice = ToolCall("youtube_pause", source=Source.VOICE, input_started_at=10, input_ended_at=11)
    fusion.commit(gesture, ToolResult.failure("failed"))
    assert fusion.guard(voice) is None
    fusion.commit(gesture, ToolResult.success("ok"))
    assert fusion.guard(voice).data["no_op"]
    assert fusion.guard(gesture) is None
    voice.name = "youtube_resume"
    assert fusion.guard(voice).error_code == "multimodal_conflict"


def test_disabled(config):
    config.set("multimodal.enabled", False)
    fusion = MultimodalCoordinator(config)
    fusion.begin(SpeechContext(time.monotonic()))
    assert not fusion.waiting()


@pytest.mark.parametrize("text,tool", [
    ("zoom cái này lên", "focus_3d_part"), ("phóng to cái này", "focus_3d_part"),
    ("zoom this in", "focus_3d_part"), ("rotate sang trái", "rotate_3d_view"),
    ("reset view", "reset_3d_view"), ("pause", "youtube_pause"),
])
def test_mixed_commands(config, text, tool):
    from nexa.ai.intent_router import IntentRouter
    from nexa.ai.tool_registry import build_registry
    router = IntentRouter(registry=build_registry(config), viewer_active=lambda: True)
    route = router.route(text)
    assert route.kind == "basic" and route.calls[0][0] == tool


def test_retry_timing_includes_second_decode(config, tmp_path, monkeypatch):
    now = [0.0]
    monkeypatch.setattr("nexa.audio.stt.time.monotonic", lambda: now[0])
    rec = SpeechRecognizer(config, tmp_path)
    calls = []
    def transcribe(audio, **kwargs):
        calls.append(kwargs)
        now[0] += 0.3 if len(calls) == 1 else 0.7
        return iter([SimpleNamespace(text="mở Chrome", avg_logprob=-1 if len(calls) == 1 else -0.2,
                                     no_speech_prob=0.1)]), SimpleNamespace(language="vi", language_probability=0.9)
    rec._model = SimpleNamespace(transcribe=transcribe)
    result = rec.transcribe(np.ones(16000, dtype=np.float32) * 0.1)
    assert result.retried and result.elapsed_s == pytest.approx(1.0)
    assert result.retry_elapsed_s == pytest.approx(0.7)
    assert calls[1]["beam_size"] > calls[0]["beam_size"]


def test_clear_short_command_does_not_retry(config, tmp_path):
    rec = SpeechRecognizer(config, tmp_path)
    calls = []
    def decode(audio, **kwargs):
        calls.append(kwargs)
        return iter([SimpleNamespace(text="pause", avg_logprob=-0.1, no_speech_prob=0.01)]), None
    rec._model = SimpleNamespace(transcribe=decode)
    assert rec.transcribe(np.ones(16000, dtype=np.float32) * 0.1).ok
    assert len(calls) == 1


def test_executor_dedupes_once_and_rejects_changed_project(config):
    from nexa.ai.tool_registry import build_registry
    from nexa.core.executor import Executor
    from nexa.core.safety import SafetyManager
    registry = build_registry(config)
    count = []
    registry.get("zoom_3d_view").handler = lambda args, ctx: (count.append(args) or ToolResult.success("ok"))
    safety = SafetyManager()
    executor = Executor(registry, safety, SimpleNamespace(three_d=SimpleNamespace(
        viewer=SimpleNamespace(project=SimpleNamespace(id="A")))), com_init=False)
    executor.multimodal = MultimodalCoordinator(config)
    executor.start()
    try:
        for source in (Source.GESTURE, Source.VOICE):
            result = executor.execute(ToolCall("zoom_3d_view", {"direction": "in"}, source,
                input_started_at=10, input_ended_at=11, target_id="A"), safety.new_token())
            assert result.ok
        assert len(count) == 1 and result.data["no_op"]
        result = executor.execute(ToolCall("zoom_3d_view", {}, Source.VOICE, target_id="B"), safety.new_token())
        assert result.error_code == "target_changed" and len(count) == 1
    finally:
        executor.stop()


def test_report_uses_real_labels_and_preserves_missing_measurements():
    from scripts.report_multimodal_trials import summarize
    rows = [dict(language="mixed", noise="quiet", mode="voice_hand", expected_action="zoom", actual_action="zoom",
                 expected_target="A", actual_target="B", response_ms="", false_activation="0"),
            dict(language="mixed", noise="quiet", mode="voice_hand", expected_action="zoom", actual_action="zoom",
                 expected_target="A", actual_target="A", response_ms="750", false_activation="0")]
    group = summarize(rows)["groups"][0]
    assert group["task_accuracy"] == group["target_accuracy"] == 0.5
    assert group["latency_samples"] == 1 and group["p95_response_ms"] == 750
    assert summarize([])["groups"] == []


def test_exact_part_id_bypasses_fuzzy_resolution():
    from nexa.three_d.part_resolver import resolve
    parts = [SimpleNamespace(id="rotor_front_left", name_vi="Cánh quạt", name_en="Rotor", aliases=[])]
    assert resolve(parts, "rotor_front_left").part_ids == ["rotor_front_left"]
