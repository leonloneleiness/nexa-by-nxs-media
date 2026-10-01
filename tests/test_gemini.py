"""Kiểm thử GeminiProvider bằng client GIẢ (dùng kiểu dữ liệu thật của google-genai, không gọi mạng)."""
from __future__ import annotations

import logging
import re
import threading
from pathlib import Path

import httpx
import pytest
from google.genai import errors, types

from nexa.ai.gemini_provider import AIError, GeminiProvider
from nexa.ai.tool_registry import Services, build_registry
from nexa.core.events import Source, ToolCall
from nexa.core.executor import Executor
from nexa.core.safety import Cancelled, SafetyManager

KEY = "AIzaSyTEST_" + "k" * 28


def text_resp(text):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(text=text)]))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=10, candidates_token_count=5,
                                                                  total_token_count=15))


def call_resp(name, args, call_id="call-1"):
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(
        role="model", parts=[types.Part(function_call=types.FunctionCall(id=call_id, name=name, args=args))]))])


class FakeModels:
    def __init__(self, script):
        self.script = list(script)
        self.requests = []

    def generate_content(self, model, contents, config):
        self.requests.append({"model": model, "contents": list(contents), "config": config})
        item = self.script.pop(0)
        if callable(item):
            item = item()
        if isinstance(item, Exception):
            raise item
        return item


class FakeClient:
    def __init__(self, script):
        self.models = FakeModels(script)


def provider(config, script, key=KEY):
    config.store_api_key(key, persist=False)
    client = FakeClient(script)
    p = GeminiProvider(config, client_factory=lambda k, t: client)
    return p, client


def no_tools(fc):
    raise AssertionError("không được gọi công cụ")


def test_companion_retains_context_without_tools(config):
    p, client = provider(config, [text_resp("Anh muốn kể thêm không?"), text_resp("Em đang nghe anh.")])
    p.converse("Hôm nay anh buồn", [], no_tools, SafetyManager().new_token(), companion=True)
    p.converse("Vì công việc", [], no_tools, SafetyManager().new_token(), companion=True)
    request = client.models.requests[-1]
    assert request["config"].tools is None
    assert "kỹ sư phần mềm" in request["config"].system_instruction
    assert any("Hôm nay anh buồn" in (part.text or "") for item in request["contents"] for part in item.parts)
    assert p.history_turns == 2
    p.clear_history()
    assert p.history_turns == 0


def test_companion_rejects_unexpected_tool_calls(config):
    p, _ = provider(config, [call_resp("open_app", {"name": "notepad"})])
    result = p.converse("Kể chuyện nhé", [], no_tools, SafetyManager().new_token(), companion=True)
    assert "thoát chế độ tâm sự" in result.text
    assert p.history_turns == 0


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def test_placeholder_or_missing_key_means_basic_mode(config):
    p = GeminiProvider(config, client_factory=lambda k, t: None)
    assert p.status()[0] is False
    config.store_api_key("YOUR_NEW_GEMINI_API_KEY", persist=False)
    ok, reason = p.status()
    assert not ok and "mẫu" in reason


def test_text_reply_and_usage(config):
    p, c = provider(config, [text_resp("Dạ, em chào anh Sơn.")])
    r = p.converse("xin chào", [], no_tools, SafetyManager().new_token())
    assert r.text == "Dạ, em chào anh Sơn."
    assert p.usage["total"] == 15
    cfg = c.models.requests[0]["config"]
    assert cfg.automatic_function_calling.disable is True
    assert "anh Sơn" in cfg.system_instruction


def test_tool_call_loop_preserves_call_id(config):
    p, c = provider(config, [call_resp("set_volume", {"percent": 30}, "id-42"), text_resp("Đã đặt 30%.")])
    seen = []

    def exec_tool(fc):
        seen.append((fc.name, dict(fc.args)))
        return {"ok": True, "verified": True, "message": "Đã đặt âm lượng 30%."}

    decls = build_registry(config).gemini_declarations()
    r = p.converse("giảm âm lượng", decls, exec_tool, SafetyManager().new_token())
    assert seen == [("set_volume", {"percent": 30})]
    assert r.text == "Đã đặt 30%."
    second = c.models.requests[1]["contents"]
    fr = second[-1].parts[0].function_response
    assert fr.id == "id-42" and fr.name == "set_volume" and fr.response["output"]["ok"] is True
    # Nội dung model (function call) được nối nguyên vẹn vào lịch sử.
    assert second[-2].parts[0].function_call.id == "id-42"


def test_invalid_schema_from_model_is_not_executed(config):
    """Gemini đề xuất tham số sai -> executor từ chối, công cụ thật không chạy, lỗi được trả lại model."""
    class Vol:
        calls = 0

        def set(self, p):
            Vol.calls += 1

    safety = SafetyManager()
    ex = Executor(build_registry(config), safety, Services(config=config, volume=Vol()), com_init=False)
    ex.start()
    try:
        p, c = provider(config, [call_resp("set_volume", {"percent": 500}), call_resp("xoa_o_cung", {}, "c2"),
                                 call_resp("set_volume", {"percent": 20, "use_gesture_snapshot": True}, "c3"),
                                 text_resp("Em không làm được.")])
        token = safety.new_token()

        def exec_tool(fc):
            return ex.execute(ToolCall(fc.name, dict(fc.args), Source.AI, "t1", call_id=fc.id), token).to_model_payload()

        r = p.converse("âm lượng 500", build_registry(config).gemini_declarations(), exec_tool, token)
        assert Vol.calls == 0
        payloads = [req["contents"][-1].parts[0].function_response.response for req in c.models.requests[1:]]
        assert payloads[0]["error"]["error_code"] == "invalid_args"
        assert payloads[1]["error"]["error_code"] == "unknown_tool"
        assert payloads[2]["error"]["error_code"] == "invalid_args"  # trường nội bộ bị từ chối với AI
        assert r.text == "Em không làm được."
    finally:
        ex.stop()


def test_auth_error_is_not_retried_and_disables_key(config):
    err = errors.ClientError(400, {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.",
                                             "status": "INVALID_ARGUMENT"}})
    p, c = provider(config, [err, text_resp("không tới đây")])
    with pytest.raises(AIError) as ei:
        p.converse("hi", [], no_tools, SafetyManager().new_token())
    assert ei.value.kind == "auth"
    assert len(c.models.requests) == 1
    assert p.status()[0] is False
    assert p.history_turns == 0  # lượt lỗi được hoàn tác, lịch sử không bị hỏng


def test_model_not_found_reports_and_does_not_switch_model(config):
    err = errors.ClientError(404, {"error": {"code": 404, "message": "models/x is not found", "status": "NOT_FOUND"}})
    config.set("ai.model", "gemini-khong-ton-tai")
    p, c = provider(config, [err])
    with pytest.raises(AIError) as ei:
        p.converse("hi", [], no_tools, SafetyManager().new_token())
    assert ei.value.kind == "not_found" and "gemini-khong-ton-tai" in ei.value.message
    assert [r["model"] for r in c.models.requests] == ["gemini-khong-ton-tai"]


def test_rate_limit_retried_with_limit(config):
    e429 = errors.ClientError(429, {"error": {"code": 429, "message": "Resource exhausted", "status": "RESOURCE_EXHAUSTED"}})
    config.set("ai.max_retries", 2)
    p, c = provider(config, [e429, e429, e429, text_resp("x")])
    with pytest.raises(AIError) as ei:
        p.converse("hi", [], no_tools, SafetyManager().new_token())
    assert ei.value.kind in ("rate_limit", "quota")
    assert len(c.models.requests) == 3  # 1 lần + 2 lần thử lại, không vô hạn


def test_server_error_retry_does_not_duplicate_tool(config):
    e503 = errors.ServerError(503, {"error": {"code": 503, "message": "overloaded", "status": "UNAVAILABLE"}})
    p, c = provider(config, [call_resp("take_screenshot", {"scope": "all"}), e503, text_resp("Đã chụp.")])
    count = []

    def exec_tool(fc):
        count.append(fc.name)
        return {"ok": True, "verified": True, "message": "Đã chụp."}

    r = p.converse("chụp màn hình", build_registry(config).gemini_declarations(), exec_tool, SafetyManager().new_token())
    assert r.text == "Đã chụp."
    assert count == ["take_screenshot"]  # retry chỉ gửi lại request, không chạy lại công cụ
    assert len(c.models.requests) == 3


def test_timeout_is_classified(config):
    config.set("ai.max_retries", 1)
    p, c = provider(config, [httpx.ReadTimeout("timeout"), httpx.ReadTimeout("timeout")])
    with pytest.raises(AIError) as ei:
        p.converse("hi", [], no_tools, SafetyManager().new_token())
    assert ei.value.kind == "timeout" and len(c.models.requests) == 2


def test_network_error_classified(config):
    config.set("ai.max_retries", 0)
    p, c = provider(config, [httpx.ConnectError("no network")])
    with pytest.raises(AIError) as ei:
        p.converse("hi", [], no_tools, SafetyManager().new_token())
    assert ei.value.kind == "network"


def test_cancel_while_waiting_drops_late_result(config):
    gate = threading.Event()

    def slow():
        gate.wait(3)
        return call_resp("set_volume", {"percent": 10})

    p, c = provider(config, [slow])
    safety = SafetyManager()
    token = safety.new_token()
    executed = []
    threading.Timer(0.2, lambda: safety.emergency_stop("test")).start()
    with pytest.raises(Cancelled):
        p.converse("x", build_registry(config).gemini_declarations(), lambda fc: executed.append(fc), token)
    gate.set()
    assert executed == []
    assert p.history_turns == 0


def test_step_limit_stops_loop(config, monkeypatch):
    monkeypatch.setenv("NEXA_MAX_TOOL_STEPS", "2")
    p, c = provider(config, [call_resp("get_time", {}, f"c{i}") for i in range(5)])
    r = p.converse("lặp", build_registry(config).gemini_declarations(),
                   lambda fc: {"ok": True, "verified": True, "message": "ok"}, SafetyManager().new_token())
    assert r.stopped == "step_limit"
    assert len(c.models.requests) == 3
    assert p.history_turns == 0


def test_history_trimmed_at_turn_boundaries(config):
    config.set("ai.max_history_turns", 2)
    p, c = provider(config, [text_resp(str(i)) for i in range(4)])
    for i in range(4):
        p.converse(f"câu {i}", [], no_tools, SafetyManager().new_token())
    assert p.history_turns == 2
    first = c.models.requests[-1]["contents"][0]
    assert first.role == "user" and "câu 2" in first.parts[0].text


def test_screen_vision_disabled_blocks_capture_and_declaration(config, monkeypatch):
    monkeypatch.setenv("NEXA_CLOUD_SCREEN_VISION", "false")
    reg = build_registry(config)
    assert "describe_screen" not in [d["name"] for d in reg.gemini_declarations()]

    class Shots:
        def grab_image(self, rect):
            raise AssertionError("không được chụp màn hình khi tính năng tắt")

    safety = SafetyManager()
    ex = Executor(reg, safety, Services(config=config, shots=Shots()), com_init=False)
    ex.start()
    try:
        r = ex.execute(ToolCall("describe_screen", {"question": "có gì"}, Source.VOICE), safety.new_token())
        assert not r.ok and r.error_code == "vision_disabled"
        assert safety.pending is None
        r = ex.execute(ToolCall("describe_screen", {"question": "có gì"}, Source.AI), safety.new_token())
        assert not r.ok  # AI cũng không gọi được
    finally:
        ex.stop()
    monkeypatch.setenv("NEXA_CLOUD_SCREEN_VISION", "true")
    assert "describe_screen" in [d["name"] for d in build_registry(config).gemini_declarations()]


def test_image_prepare_crop_and_mime(tmp_path):
    from PIL import Image
    from nexa.ai.screen_vision import prepare_image
    path = tmp_path / "s.png"
    Image.new("RGB", (4000, 2000), "navy").save(path)
    data, mime, size = prepare_image(str(path), [100, 100, 2000, 1000])
    assert mime == "image/png" and max(size) <= 1600 and size == (1600, 800)


def test_key_never_appears_in_logs(config, caplog, tmp_path):
    from nexa.utils.logging import RedactingFilter, register_secret
    register_secret(KEY)
    logger = logging.getLogger("nexa.test")
    handler = logging.FileHandler(tmp_path / "t.log", encoding="utf-8")
    handler.addFilter(RedactingFilter())
    logger.addHandler(handler)
    logger.warning("key=%s và url https://x/?key=%s", KEY, KEY)
    handler.close()
    logger.removeHandler(handler)
    text = (tmp_path / "t.log").read_text(encoding="utf-8")
    assert KEY not in text and "[ĐÃ ẨN]" in text


def test_repository_contains_no_real_keys():
    root = Path(__file__).resolve().parents[1]
    pattern = re.compile(r"AIza[0-9A-Za-z_\-]{35}")
    skip = {".venv", "models", "logs", "__pycache__", ".pytest_cache", "build", "dist", "release"}
    offenders = []
    for p in root.rglob("*"):
        if any(part in skip for part in p.parts) or not p.is_file() or p.name == ".env":
            continue
        if p.suffix.lower() in (".png", ".wav", ".task", ".zip", ".exe", ".bin"):
            continue
        try:
            if pattern.search(p.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(str(p))
        except OSError:
            continue
    assert offenders == []
    example = (root / ".env.example").read_text(encoding="utf-8")
    assert "GEMINI_API_KEY=YOUR_NEW_GEMINI_API_KEY" in example


def test_request_budget_caps_total_wait_including_retries(config):
    """Lỗi 22:19: Gemini treo 30 s rồi 504, rồi thử lại — anh phải chờ gần một phút. Giờ có hạn tổng."""
    import time as _time
    e504 = errors.ServerError(504, {"error": {"code": 504, "message": "deadline", "status": "DEADLINE_EXCEEDED"}})

    def slow_504():
        _time.sleep(0.8)
        return e504
    config.set("ai.max_retries", 5)
    config.set("ai.retry_base_s", 0.1)
    config.set("ai.request_budget_s", 2.0)
    p, c = provider(config, [slow_504] * 6)
    t = _time.monotonic()
    with pytest.raises(AIError):
        p.converse("hi", [], no_tools, SafetyManager().new_token())
    assert _time.monotonic() - t < 2.6
    assert len(c.models.requests) < 6                  # không dùng hết 5 lần thử lại


def test_hanging_request_stops_at_budget(config):
    import time as _time
    config.set("ai.max_retries", 2)
    config.set("ai.request_budget_s", 1.5)
    p, c = provider(config, [lambda: _time.sleep(5) or text_resp("muộn")])
    t = _time.monotonic()
    with pytest.raises(AIError) as ei:
        p.converse("hi", [], no_tools, SafetyManager().new_token())
    assert ei.value.kind == "timeout" and _time.monotonic() - t < 2.2


def test_overloaded_primary_switches_to_fallback_model_immediately(config):
    """2026-09-23: 3.5-flash-lite 504 liên tục trong khi 3.6-flash vẫn trả lời — đổi model ngay, không thử lại cùng model."""
    e504 = errors.ServerError(504, {"error": {"code": 504, "message": "deadline", "status": "DEADLINE_EXCEEDED"}})
    config.set("ai.fallback_models", ["model-du-phong"])
    p, c = provider(config, [e504, text_resp("Paris."), text_resp("Lần hai.")])
    r = p.converse("Thủ đô Pháp?", [], no_tools, SafetyManager().new_token())
    assert r.text == "Paris."
    used = [q["model"] for q in c.models.requests]
    assert used[0] == p.model and used[1] == "model-du-phong"
    p.converse("Câu tiếp theo", [], no_tools, SafetyManager().new_token())
    assert c.models.requests[-1]["model"] == "model-du-phong"      # model chính đang "nghỉ": không gọi lại


def test_working_model_is_remembered_across_restarts(config, tmp_path):
    """Log 2026-09-24: mỗi lần mở NEXA, câu đầu lại chờ ~7 s model chính quá tải. Giờ nhớ model chạy được."""
    e504 = errors.ServerError(504, {"error": {"code": 504, "message": "deadline", "status": "DEADLINE_EXCEEDED"}})
    config.set("ai.fallback_models", ["model-du-phong"])
    config.store_api_key(KEY, persist=False)
    state = tmp_path / "gemini_state.json"
    c1 = FakeClient([e504, text_resp("Paris.")])
    p1 = GeminiProvider(config, client_factory=lambda k, t: c1, state_path=state)
    p1.converse("Thủ đô Pháp?", [], no_tools, SafetyManager().new_token())
    c2 = FakeClient([text_resp("Ngay.")])
    p2 = GeminiProvider(config, client_factory=lambda k, t: c2, state_path=state)     # "mở lại NEXA"
    assert p2.converse("hi", [], no_tools, SafetyManager().new_token()).text == "Ngay."
    assert [q["model"] for q in c2.models.requests] == ["model-du-phong"]


def test_corrupt_state_file_is_ignored(config, tmp_path):
    state = tmp_path / "gemini_state.json"
    state.write_text("{không phải json", encoding="utf-8")
    p = GeminiProvider(config, client_factory=lambda k, t: None, state_path=state)
    assert p.active_model == p.model


def test_hanging_primary_gives_fallback_a_chance_within_budget(config):
    import time as _time
    config.set("ai.fallback_models", ["model-du-phong"])
    config.set("ai.attempt_timeout_s", 0.5)
    config.set("ai.request_budget_s", 5)
    p, c = provider(config, [lambda: _time.sleep(3) or text_resp("muộn"), text_resp("Kịp.")])
    t = _time.monotonic()
    r = p.converse("hi", [], no_tools, SafetyManager().new_token())
    assert r.text == "Kịp." and _time.monotonic() - t < 1.5
