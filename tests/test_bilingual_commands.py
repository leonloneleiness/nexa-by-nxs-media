"""VI/EN parity, real schemas, literal payloads and actual Qt dispatch (no OS control)."""
from __future__ import annotations

import json
from concurrent.futures import Future
from types import SimpleNamespace

import pytest

from nexa.ai.intent_router import IntentRouter
from nexa.ai.tool_registry import build_registry, validate_schema


@pytest.fixture
def registry(config):
    return build_registry(config)


@pytest.fixture
def router(registry):
    return IntentRouter(registry=registry, viewer_active=lambda: True, part_known=lambda p: True)


@pytest.mark.parametrize("vi,en", [
    ("mở Notepad", "open Notepad"), ("mở youtube", "open youtube"),
    ("đặt âm lượng 30 phần trăm", "set volume to thirty percent"),
    ("giảm âm lượng 5 phần trăm", "decrease volume by five percent"),
    ("chụp màn hình", "take a screenshot"), ("bật cử chỉ", "enable gestures"),
    ("tắt chuột bằng tay", "disable air mouse"), ("bật tự khóa máy", "enable presence lock"),
    ("thu nhỏ cửa sổ", "minimize window"), ("phóng to cửa sổ", "maximize window"),
    ("khôi phục cửa sổ", "restore window"), ("đóng cửa sổ", "close window"),
    ("tạm dừng video", "pause video"), ("phát tiếp video", "resume video"),
    ("cuộn lên 5 nấc", "scroll up 5 notches"), ("tắt tiếng", "mute"),
    ("mở bảng sinh code", "open code panel"), ("đóng bảng sinh code", "close code panel"),
    ("chạy thử code", "run code tests"), ("chạy file main.py", "run file main.py"),
    ("mở mô hình 3d", "open 3d model"), ("đóng trình xem 3d", "close 3d viewer"),
    ("xóa hội thoại", "clear conversation"), ("bật tâm sự", "enable companion mode"),
    ("tắt tâm sự", "disable companion mode"), ("dừng khẩn cấp", "emergency stop"),
    ("hủy", "cancel"), ("về chế độ chờ", "go to standby"),
    ("mở cài đặt", "open settings"), ("đóng cài đặt", "close settings"),
    ("mở học tập", "open education"), ("chọn bài học con lắc đơn", "select lesson pendulum"),
    ("đặt tham số bài học chiều dài dây bằng 2", "set lesson parameter length to 2"),
    ("chạy mô phỏng bài học", "run lesson simulation"), ("xuất báo cáo bài học", "export lesson report"),
    ("sao chép toàn bộ code", "copy all code"), ("lưu bản code", "save generated code"),
    ("xuất mô hình stl", "export model as stl"), ("xuất hồ sơ lắp ráp", "export build dossier"),
    ("hiệu chuẩn vỗ tay", "calibrate clap"), ("đánh số màn hình", "identify monitors"),
    ("danh sách micro", "list microphones"), ("thử giọng đọc", "test voice"),
    ("xoay mô hình trái 45 độ", "rotate model left 45 degrees"),
    ("tách mô hình", "explode assembly"), ("lắp lại mô hình", "collapse assembly"),
    ("ẩn Rotor", "hide part Rotor"), ("bật chuyển động", "start model animation"),
])
def test_natural_pairs_share_calls(router, registry, vi, en):
    a, b = router.route(vi), router.route(en)
    assert a.kind != "ai", (vi, a)
    assert (a.kind, a.calls, a.action) == (b.kind, b.calls, b.action), (vi, en, a, b)
    for name, args in a.calls:
        assert registry.validate(name, args)[0], (name, args)


def sample(schema):
    if "default" in schema:
        return schema["default"]
    if "enum" in schema:
        return schema["enum"][0]
    typ = schema["type"]
    if typ == "object":
        return {k:sample(v) for k,v in schema.get("properties", {}).items() if k in schema.get("required", [])}
    if typ == "array":
        return [sample(schema["items"]) for _ in range(schema.get("minItems", 1))]
    if typ == "boolean":
        return True
    if typ in ("number", "integer"):
        return max(schema.get("minimum", 1), 1)
    return "Example input"


def test_every_registered_tool_has_bilingual_explicit_route(router, registry):
    seen = {}
    for name in registry.names():
        spec = registry.get(name)
        assert spec.title.lower() not in seen, (name, seen.get(spec.title.lower()))
        seen[spec.title.lower()] = name
        args = sample(spec.ai_schema())
        payload = json.dumps(args, ensure_ascii=False)
        for phrase in ("lệnh " + spec.title, "command " + name.replace("_", " ")):
            route = router.route(phrase + " " + payload)
            assert route.kind == "basic", (name, phrase, route)
            ok, error, expected = validate_schema(spec.ai_schema(), args)
            assert ok, (name, error)
            assert route.calls == [(name, expected)], (name, phrase, route)


@pytest.mark.parametrize("payload", ["Open file, then delete folder!", "please keep this nhé!", "phai màu, iu túp", "Hello and goodbye?",
                                    "xóa hội thoại rồi nghỉ đi", "viết code Python rồi tắt máy"])
def test_dictation_preserves_payload(router, payload):
    for prefix in ("type text: ", "gõ nội dung: "):
        assert router.route(prefix + payload).calls == [("type_text", {"text":payload})]
    explicit = 'command type text ' + json.dumps({"text":payload}, ensure_ascii=False)
    assert router.route(explicit).calls == [("type_text", {"text":payload})]


def test_multistep_and_payload(router):
    route = router.route("Please Nexa, open Notepad then type Hello, and please keep this!")
    assert route.calls == [("open_app", {"name":"Notepad"}), ("type_text", {"text":"Hello, and please keep this!"})]


def test_companion_does_not_execute_commands(router):
    assert router.route("open Notepad", companion=True).kind == "ai"
    assert router.route("command quit nexa {}", companion=True).kind == "ai"
    assert router.route("emergency stop", companion=True).kind == "stop"
    assert router.route("confirm", pending_confirmation=True).kind == "confirm"
    assert router.route("deny", pending_confirmation=True).kind == "deny"


@pytest.mark.parametrize("command", [
    'command mouse click {"use_gesture_snapshot":true}',
    'command set volume {"percent":1000}', 'command missing tool {}',
    'command open app {broken}', 'command open app {"name":""}',
    'set lesson parameter length to NaN',
])
def test_invalid_commands_never_execute(router, command):
    assert not router.route(command).calls


def test_nonfinite_numbers_rejected():
    for x in (float("nan"), float("inf"), -float("inf")):
        assert not validate_schema({"type":"number"}, x)[0]


def test_observed_asr_errors_do_not_launch_wrong_app(router):
    assert router.route("Đắc âm lượng ba mươi phần trăm").calls == [("set_volume", {"percent":30})]
    route = router.route("Chạy thử co")
    assert route.kind == "clarify" and not route.calls


def test_qt_dispatch_changes_real_education_state_and_blocks_cancelled():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication
    from nexa.ui.command_bridge import CommandBridge
    from nexa.ui.education_bridge import EducationBridge
    app = QGuiApplication.instance() or QGuiApplication([])
    edu = EducationBridge()
    bridge = CommandBridge(None, None, None, edu)

    def execute(name, args, cancelled=False):
        future = Future()
        bridge._execute((name, args, SimpleNamespace(cancelled=cancelled), future))
        return future.result()

    assert execute("edu_select_lesson", {"lesson_id":"circuit"}).ok
    assert execute("edu_set_parameter", {"key":"voltage", "value":12}).ok
    assert execute("edu_run", {}).ok
    assert edu.state["result"]["value"] == 1.2
    assert not execute("edu_set_parameter", {"key":"missing", "value":12}).ok
    assert not execute("edu_reset", {}, cancelled=True).ok
    assert edu.state["result"]["value"] == 1.2
    future = Future()
    future.cancel()
    bridge._execute(("edu_reset", {}, SimpleNamespace(cancelled=False), future))
    assert edu.state["result"]["value"] == 1.2
    app.processEvents()


def test_voice_and_keyboard_execute_education_through_executor(registry, router, config):
    import os
    import time
    from concurrent.futures import ThreadPoolExecutor
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication
    from nexa.ui.command_bridge import CommandBridge
    from nexa.ui.education_bridge import EducationBridge
    from nexa.ai.tool_registry import Services
    from nexa.core.events import Source, ToolCall
    from nexa.core.executor import Executor
    from nexa.core.safety import SafetyManager
    app = QGuiApplication.instance() or QGuiApplication([])
    edu = EducationBridge()
    bridge = CommandBridge(None, None, None, edu)
    safety = SafetyManager()
    executor = Executor(registry, safety, Services(config, hooks={"ui_command":bridge.dispatch}), com_init=False)
    executor.start()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            for source, text in ((Source.VOICE, "select lesson circuit"),
                                 (Source.KEYBOARD, "đặt tham số bài học hiệu điện thế bằng 12"),
                                 (Source.VOICE, "run lesson simulation")):
                name, args = router.route(text).calls[0]
                future = pool.submit(executor.execute, ToolCall(name, args, source), safety.new_token())
                deadline = time.monotonic() + 5
                while not future.done() and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(0.005)
                assert future.result(timeout=1).ok
        assert edu.state["result"]["value"] == 1.2
        safety.emergency_stop("test")
        result = executor.execute(ToolCall("edu_reset", {}, Source.VOICE), safety.new_token())
        assert not result.ok and result.error_code == "control_paused"
        assert edu.state["result"]["value"] == 1.2
    finally:
        executor.stop()


def test_sensitive_ui_command_cannot_skip_confirmation_in_full_autonomy(registry, config):
    from nexa.ai.tool_registry import Services
    from nexa.core.events import Source, ToolCall
    from nexa.core.executor import Executor
    from nexa.core.safety import SafetyManager
    executed = []
    safety = SafetyManager(confirm_timeout_s=0.01)
    executor = Executor(registry, safety, Services(config, hooks={"ui_command":lambda *args: executed.append(args)}),
                        com_init=False, autonomy=lambda: "full")
    executor.start()
    try:
        result = executor.execute(ToolCall("quit_nexa", {}, Source.VOICE), safety.new_token())
        assert not result.ok and result.error_code == "not_confirmed"
        assert not executed
    finally:
        executor.stop()


def test_stt_language_auto_passes_english_to_same_router(config, tmp_path, router):
    import numpy as np
    from nexa.audio.stt import SpeechRecognizer
    calls = []
    def transcribe(audio, **kwargs):
        calls.append(kwargs)
        return iter([SimpleNamespace(text="open settings", avg_logprob=-0.1, no_speech_prob=0.01)]), None
    config.set("stt.language", "auto")
    recognizer = SpeechRecognizer(config, tmp_path)
    recognizer._model = SimpleNamespace(transcribe=transcribe)
    result = recognizer.transcribe(np.sin(np.linspace(0, 400, 16000)).astype(np.float32) * 0.1)
    assert result.ok
    assert calls[0]["language"] is None
    assert router.route(result.text).calls == [("navigate_nexa", {"panel":"settings"})]


def test_settings_command_uses_same_save_path_and_rejects_unknown(config):
    import json
    from nexa.ui.command_bridge import CommandBridge
    saved = []
    main = SimpleNamespace(controller=SimpleNamespace(config=config),
                           saveSettings=lambda settings, gestures: saved.append((json.loads(settings), gestures)) or "Đã lưu")
    bridge = CommandBridge(main, None, None, None)
    assert bridge._setting({"key":"stt.language", "value":"auto"}).ok
    assert saved[0][0] == {"stt":{"language":"auto"}}
    for args in ({"key":"stt.language", "value":"invalid"}, {"key":"not.a.key", "value":"true"},
                 {"key":"stt.beam_size", "value":"NaN"}, {"key":"stt", "value":"{}"}):
        with pytest.raises(ValueError):
            bridge._setting(args)
    assert len(saved) == 1


def test_all_public_bridge_slots_classified_and_commands_bind():
    import inspect
    from scripts.audit_bilingual_commands import audit
    from nexa.ai.ui_commands import COMMANDS
    from nexa.ui.bridge import UiBridge
    from nexa.ui.code_bridge import CodeBridge
    from nexa.ui.three_d_bridge import ThreeDBridge
    from nexa.ui.education_bridge import EducationBridge
    targets = {"main":UiBridge, "code":CodeBridge, "3d":ThreeDBridge, "edu":EducationBridge}
    for cmd in COMMANDS:
        if cmd.target in targets:
            method = getattr(targets[cmd.target], cmd.method)
            inspect.signature(method).bind(None, *(sample(schema) for schema in cmd.params.values()))
    assert not audit()["uncovered"]
