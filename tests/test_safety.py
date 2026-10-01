"""Kiểm thử quyền, xác nhận, dừng khẩn cấp, chống chạy trùng và thao tác tệp an toàn (thư mục tạm)."""
from __future__ import annotations

import threading
import time

import pytest

from nexa.ai.tool_registry import (Services, ToolRegistry, ToolSpec, build_registry, obj, risk_press_keys,
                                   risk_type_text)
from nexa.core.events import Risk, Source, ToolCall, ToolResult
from nexa.core.executor import ExecContext, Executor
from nexa.core.safety import Assessment, SafetyManager
from nexa.desktop.apps_and_files import FileService


def make_registry(counter, risk=Risk.LOW, needs_control=True, slow=0.0):
    reg = ToolRegistry()

    def handler(args, ctx):
        if slow:
            time.sleep(slow)
        counter.append(args)
        return ToolResult.success("ok")

    reg.register(ToolSpec("act", "Hành động", "test", obj({"n": {"type": "integer", "minimum": 0, "maximum": 9}}),
                          handler, risk=risk, needs_control=needs_control))
    return reg


@pytest.fixture
def env():
    calls = []
    safety = SafetyManager(confirm_timeout_s=1.0)
    ex = Executor(make_registry(calls, risk=Risk.HIGH), safety, com_init=False)
    ex.start()
    yield ex, safety, calls
    ex.stop()


def approve_async(safety, approve=True, delay=0.1, change=None):
    def run():
        time.sleep(delay)
        if change:
            change()
        p = safety.pending
        if p:
            safety.resolve(p.id, approve)
    threading.Thread(target=run, daemon=True).start()


def test_high_risk_waits_for_confirmation_and_runs_after_yes(env):
    ex, safety, calls = env
    approve_async(safety, True)
    r = ex.execute(ToolCall("act", {"n": 1}, Source.VOICE), safety.new_token())
    assert r.ok and calls == [{"n": 1}]


def test_denied_confirmation_does_not_run(env):
    ex, safety, calls = env
    approve_async(safety, False)
    r = ex.execute(ToolCall("act", {"n": 1}, Source.VOICE), safety.new_token())
    assert not r.ok and r.error_code == "not_confirmed" and calls == []


def test_confirmation_expires(env):
    ex, safety, calls = env
    t = time.monotonic()
    r = ex.execute(ToolCall("act", {"n": 1}, Source.VOICE), safety.new_token())
    assert not r.ok and calls == [] and time.monotonic() - t >= 0.9


def test_confirmation_bound_to_its_id_and_single_use(env):
    ex, safety, calls = env
    result = {}

    def run():
        result["r"] = ex.execute(ToolCall("act", {"n": 2}, Source.VOICE), safety.new_token())
    th = threading.Thread(target=run)
    th.start()
    time.sleep(0.1)
    p = safety.pending
    assert p is not None
    assert safety.resolve("id-khac", True) is False
    assert safety.resolve(p.id, True) is True
    th.join(2)
    assert result["r"].ok
    assert safety.resolve(p.id, True) is False  # "đồng ý" cũ không dùng lại được
    assert safety.pending is None


def test_confirmation_invalid_if_target_changes_after_approval():
    calls = []
    state = {"target": "A"}
    reg = ToolRegistry()
    reg.register(ToolSpec("act", "Xóa", "t", obj({}), lambda a, c: (calls.append(1), ToolResult.success("ok"))[1],
                          risk=Risk.HIGH, fingerprint_fn=lambda a, c: state["target"]))
    safety = SafetyManager()
    ex = Executor(reg, safety, com_init=False)
    ex.start()
    try:
        approve_async(safety, True, change=lambda: state.update(target="B"))
        r = ex.execute(ToolCall("act", {}, Source.VOICE), safety.new_token())
        assert not r.ok and r.error_code == "target_changed" and calls == []
    finally:
        ex.stop()


def test_medium_risk_needs_confirmation_only_for_ai():
    a = Assessment(Risk.MEDIUM)
    assert a.needs_confirmation(Source.AI) and not a.needs_confirmation(Source.VOICE)
    assert Assessment(Risk.HIGH).needs_confirmation(Source.GESTURE)
    assert not Assessment(Risk.LOW).needs_confirmation(Source.AI)


def test_emergency_stop_cancels_queue_and_blocks_until_resume():
    calls = []
    safety = SafetyManager()
    ex = Executor(make_registry(calls, slow=0.3), safety, com_init=False)
    ex.start()
    try:
        results = []
        tokens = [safety.new_token() for _ in range(3)]
        threads = [threading.Thread(target=lambda t=t, i=i: results.append(ex.execute(ToolCall("act", {"n": i}, Source.VOICE), t)))
                   for i, t in enumerate(tokens)]
        for th in threads:
            th.start()
            time.sleep(0.02)
        time.sleep(0.05)
        safety.on_stop(lambda reason: ex.cancel_all(reason))
        safety.emergency_stop("test")
        for th in threads:
            th.join(3)
        assert len(calls) <= 1  # chỉ bước đang chạy dở có thể xong; hàng đợi bị hủy
        assert sum(1 for r in results if not r.ok) >= 2
        # Token cũ (kết quả LLM đến muộn) không kích hoạt được executor
        r = ex.execute(ToolCall("act", {"n": 5}, Source.AI), tokens[0])
        assert not r.ok
        # Token mới cũng bị chặn cho tới khi người dùng bật lại
        r = ex.execute(ToolCall("act", {"n": 6}, Source.VOICE), safety.new_token())
        assert not r.ok and r.error_code == "control_paused"
        safety.resume_control()
        r = ex.execute(ToolCall("act", {"n": 7}, Source.VOICE), safety.new_token())
        assert r.ok
    finally:
        ex.stop()


def test_same_step_is_not_executed_twice():
    calls = []
    safety = SafetyManager()
    ex = Executor(make_registry(calls), safety, com_init=False)
    ex.start()
    try:
        call = ToolCall("act", {"n": 1}, Source.AI, task_id="t1", call_id="c1")
        again = ToolCall("act", {"n": 1}, Source.AI, task_id="t1", call_id="c1")
        assert ex.execute(call, safety.new_token()).ok
        assert ex.execute(again, safety.new_token()).ok
        assert len(calls) == 1
    finally:
        ex.stop()


def test_ai_task_lease_blocks_gesture_but_not_itself():
    calls = []
    safety = SafetyManager()
    ex = Executor(make_registry(calls), safety, com_init=False)
    ex.start()
    try:
        assert ex.acquire_control("ai:t9")
        r = ex.execute(ToolCall("act", {"n": 1}, Source.GESTURE), safety.new_token())
        assert not r.ok and r.error_code == "busy"
        r = ex.execute(ToolCall("act", {"n": 2}, Source.AI, task_id="t9"), safety.new_token())
        assert r.ok
        ex.release_control("ai:t9")
        assert ex.execute(ToolCall("act", {"n": 3}, Source.GESTURE), safety.new_token()).ok
    finally:
        ex.stop()


def test_invalid_args_rejected_before_execution():
    calls = []
    safety = SafetyManager()
    ex = Executor(make_registry(calls), safety, com_init=False)
    ex.start()
    try:
        assert ex.execute(ToolCall("act", {"n": 99}, Source.VOICE), safety.new_token()).error_code == "invalid_args"
        assert ex.execute(ToolCall("act", {"x": 1}, Source.VOICE), safety.new_token()).error_code == "invalid_args"
        assert ex.execute(ToolCall("khong_co", {}, Source.VOICE), safety.new_token()).error_code == "unknown_tool"
        assert calls == []
    finally:
        ex.stop()


# ------------------------------------------------------------------ rủi ro theo ngữ cảnh
class _WM:
    def __init__(self, proc):
        self.proc = proc
        self.api = type("A", (), {"get_title": lambda s, h: "t"})()

    def resolve_work_window(self):
        return 1, ""

    def identity(self, hwnd):
        return type("I", (), {"process_name": self.proc, "pid": 1})()


def ctx_for(proc, config):
    return ExecContext(Source.AI, SafetyManager().new_token(), services=Services(config=config, wm=_WM(proc)))


@pytest.mark.parametrize("keys,proc,risk", [
    (["alt", "f4"], "notepad.exe", Risk.HIGH),
    (["ctrl", "w"], "chrome.exe", Risk.HIGH),
    (["enter"], "zalo.exe", Risk.HIGH),
    (["ctrl", "enter"], "msedge.exe", Risk.HIGH),
    (["enter"], "powershell.exe", Risk.HIGH),
    (["win", "r"], "explorer.exe", Risk.HIGH),
    (["shift", "delete"], "notepad.exe", Risk.HIGH),
    (["delete"], "explorer.exe", Risk.HIGH),
    (["enter"], "notepad.exe", Risk.LOW),
    (["ctrl", "c"], "chrome.exe", Risk.LOW),
    (["ctrl", "s"], "notepad.exe", Risk.LOW),
])
def test_shortcut_risk_depends_on_context(config, keys, proc, risk):
    assert risk_press_keys({"keys": keys}, ctx_for(proc, config)).risk == risk


def test_typing_into_terminal_or_multiline_into_chat_is_high(config):
    assert risk_type_text({"text": "dir"}, ctx_for("cmd.exe", config)).risk == Risk.HIGH
    assert risk_type_text({"text": "chào\nbạn"}, ctx_for("zalo.exe", config)).risk == Risk.HIGH
    assert risk_type_text({"text": "chào bạn"}, ctx_for("notepad.exe", config)).risk == Risk.LOW


def test_ai_coordinate_click_needs_confirmation(config):
    reg = build_registry(config)
    spec = reg.get("mouse_click")
    a = spec.assess({"x": 10, "y": 20}, None)
    assert a.needs_confirmation(Source.AI) and not a.needs_confirmation(Source.VOICE)
    assert reg.get("delete_to_recycle_bin").assess({"path": "x"}, None).risk == Risk.HIGH
    assert reg.get("close_window").assess({}, None).risk == Risk.HIGH


# ------------------------------------------------------------------ tệp (thư mục tạm, không đụng dữ liệu thật)
def test_file_operations_stay_in_scope(config, tmp_path, monkeypatch):
    fs = FileService(config)
    root = tmp_path / "allowed"
    (root / "bao_cao.txt").write_text("x", encoding="utf-8")
    assert fs.create_folder(str(root), "Dự án").ok
    assert not fs.create_folder(str(root), "Dự án").ok                       # trùng tên
    assert not fs.create_folder(str(root), "a<b").ok                          # tên không hợp lệ
    assert not fs.create_folder(str(tmp_path), "ngoai").ok                    # ngoài phạm vi
    assert fs.rename(str(root / "bao_cao.txt"), "bao_cao_moi.txt").ok
    (root / "khac.txt").write_text("y", encoding="utf-8")
    assert fs.rename(str(root / "khac.txt"), "bao_cao_moi.txt").error_code == "exists"   # không ghi đè
    assert fs.copy(str(root / "khac.txt"), str(root / "Dự án")).ok
    assert fs.copy(str(root / "khac.txt"), str(root / "Dự án")).error_code == "exists"
    found = fs.find("bao cao")
    assert found.ok and len(found.data["results"]) == 1
    outside = tmp_path / "secret.txt"
    outside.write_text("z", encoding="utf-8")
    assert fs.open(str(outside)).error_code == "out_of_scope"
    assert fs.open(str(root / ".." / "secret.txt")).error_code == "out_of_scope"   # chống ../


def test_delete_goes_to_recycle_bin_only(config, tmp_path, monkeypatch):
    trashed = []
    import send2trash
    monkeypatch.setattr(send2trash, "send2trash", lambda p: trashed.append(p))
    fs = FileService(config)
    f = tmp_path / "allowed" / "x.txt"
    f.write_text("1", encoding="utf-8")
    assert fs.delete_to_recycle_bin(str(f)).ok
    assert trashed == [str(f.resolve())]
    assert fs.delete_to_recycle_bin(str(tmp_path / "allowed")).error_code == "protected"


def test_opening_executable_is_high_risk(config, tmp_path):
    reg = build_registry(config)
    exe = tmp_path / "allowed" / "setup.exe"
    exe.write_bytes(b"MZ")
    ctx = ExecContext(Source.VOICE, SafetyManager().new_token(), services=Services(config=config, files=FileService(config)))
    assert reg.get("open_path").assess({"path": str(exe)}, ctx).risk == Risk.HIGH
    txt = tmp_path / "allowed" / "a.txt"
    txt.write_text("a", encoding="utf-8")
    assert reg.get("open_path").assess({"path": str(txt)}, ctx).risk == Risk.LOW
