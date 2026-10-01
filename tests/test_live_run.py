"""Kết quả chạy thử hiện NGAY TRONG NEXA: LiveRun (đầu ra trực tiếp, lời nhắc nhập, \\r tiến độ, dừng, quá giờ, đếm
kiểm thử), CodeService.run_tests / run_file chạy trên bảng, console của trang HTML. Chỉ chạy Python của NEXA."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from nexa.code import live_run
from nexa.code.live_run import LiveRun
from nexa.code.live_run import test_summary as summarize
from nexa.code.models import CodeFile, CodeResult

PY = sys.executable


def _run(code: str, tmp_path: Path, **kw) -> LiveRun:
    f = tmp_path / "prog.py"
    f.write_text(code, encoding="utf-8")
    kw.setdefault("time_limit", 20)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    return LiveRun([[PY, "-u", str(f)]], str(tmp_path), env, title="prog.py", **kw)


def _until(pred, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return False


def test_output_stderr_and_exit_code(tmp_path):
    r = _run("import sys\nprint('xin chào')\nprint('hỏng', file=sys.stderr)\nsys.exit(3)\n", tmp_path).start()
    assert r.wait(15)
    assert r.state == live_run.FAILED and r.exit_code == 3
    text = r.plain_text()
    assert "xin chào" in text and "hỏng" in text
    assert any(ln.kind == "err" and "hỏng" in ln.text for ln in r.lines)


def test_prompt_waits_then_input_is_echoed(tmp_path):
    r = _run("n = input('Nhap ten: ')\nprint('Chao', n)\n", tmp_path).start()
    assert _until(r.waiting_input)
    assert r.view()["waitingInput"] is True
    assert r.send("Son")
    assert r.wait(15) and r.state == live_run.OK
    text = r.plain_text()
    assert "Nhap ten:" in text and "Son" in text and "Chao Son" in text
    assert any(ln.kind == "in" and "Son" in ln.text for ln in r.lines)


def test_carriage_return_progress_overwrites_line(tmp_path):
    r = _run("import sys\nfor p in (10, 50, 100):\n    sys.stdout.write(f'\\r{p}%')\n    sys.stdout.flush()\nprint()\n",
             tmp_path).start()
    assert r.wait(15)
    outs = [ln.text for ln in r.lines if ln.kind == "out"]
    assert "100%" in outs and "10%" not in outs


def test_stop_kills_program(tmp_path):
    r = _run("import time\nprint('bat dau', flush=True)\ntime.sleep(60)\n", tmp_path, time_limit=0).start()
    assert _until(lambda: "bat dau" in r.plain_text())
    r.stop()
    assert r.wait(10) and r.state == live_run.STOPPED


def test_timeout(tmp_path):
    r = _run("import time\ntime.sleep(30)\n", tmp_path, time_limit=1).start()
    assert r.wait(15) and r.state == live_run.TIMEOUT and r.note


def test_render_html_escapes_output(tmp_path):
    r = LiveRun([], str(tmp_path), {})
    r.info("<script>alert(1)</script> & co")
    html = r.render_html()
    assert "<script>" not in html and "&lt;script&gt;" in html and "&amp;" in html


def test_test_summary_formats():
    node = "✔ cộng\n✖ trừ\nℹ tests 2\nℹ suites 0\nℹ pass 1\nℹ fail 1\n"
    assert summarize(node) == {"total": 2, "passed": 1, "failed": 1}
    assert summarize("...\n3 đạt, 0 trượt\n") == {"total": 3, "passed": 3, "failed": 0}
    assert summarize("==== 4 passed, 1 failed in 0.1s ====") == {"total": 5, "passed": 4, "failed": 1}
    assert summarize("test result: ok. 2 passed; 0 failed; 0 ignored") == {"total": 2, "passed": 2, "failed": 0}
    assert summarize("--- PASS: TestA (0.00s)\n--- FAIL: TestB (0.00s)\n")["failed"] == 1
    assert summarize("hello world") is None


def test_zero_tests_is_not_a_pass(tmp_path):
    r = _run("print('ℹ tests 0')\nprint('ℹ pass 0')\nprint('ℹ fail 0')\n", tmp_path, is_test=True).start()
    assert r.wait(15)
    assert r.state == live_run.NO_TESTS


def test_node_test_gets_test_files_explicitly():
    from nexa.code import checks
    files = [CodeFile("index.html", "html", "<p>x</p>"), CodeFile("app.js", "javascript", "export const a = 1\n"),
             CodeFile("test_app.js", "javascript", "import test from 'node:test'\n")]
    plan, _ = checks.plan_run(files, [PY])
    if plan is None:      # máy không có node → không kiểm được lệnh
        return
    cmd = plan.steps[-1]
    assert "--test" in cmd and cmd[-1].endswith("test_app.js")


def test_view_dict_keys(tmp_path):
    v = LiveRun([], str(tmp_path), {}, title="t", preview_url="file:///x.html").view()
    for k in ("active", "state", "stateLabel", "html", "running", "waitingInput", "previewUrl", "summary",
              "step", "steps", "exitCode", "seconds"):
        assert k in v


# ---------- CodeService: chạy trên bảng NEXA ----------

def _svc(config, tmp_path):
    from nexa.code.service import CodeService
    svc = CodeService(config, history_dir=tmp_path / "hist")
    events = []
    svc._notify = lambda kind, data: events.append((kind, data))       # type: ignore[method-assign]
    return svc, events


def test_service_run_tests_live_stores_report(config, tmp_path):
    svc, events = _svc(config, tmp_path)
    res = CodeResult("r1", "p", "Chào", "python", "s", [CodeFile("main.py", "python", "print('xin chào NEXA')\n")])
    svc.current = res
    svc._store(res)
    ok, _ = svc.run_tests("r1")
    assert ok and svc.live is not None
    assert ("code_open", {"view": "run"}) in events
    assert svc.live.wait(30)
    assert _until(lambda: res.run is not None)
    assert res.run.ok and "xin chào NEXA" in res.run.output
    assert any(k == "code_result" and d.get("keepView") for k, d in events)


def test_service_run_file_live_with_input(config, tmp_path):
    svc, events = _svc(config, tmp_path)
    f = tmp_path / "hoi.py"
    f.write_text("x = input('So: ')\nprint(int(x) * 2)\n", encoding="utf-8")
    ok, msg = svc.run_file(f)
    assert ok and "trong NEXA" in msg
    r = svc.live
    assert r.source == "file" and r.time_limit == 0
    assert _until(r.waiting_input, 20)
    assert svc.send_input("21")
    assert r.wait(20) and r.state == live_run.OK and "42" in r.plain_text()
    assert not svc.stop_run()                                      # đã xong → không có gì để dừng


def test_service_run_file_console_option(config, tmp_path, monkeypatch):
    svc, _ = _svc(config, tmp_path)
    config.set("code.run_file_in", "console")
    called = {}
    monkeypatch.setattr(svc, "run_file_console", lambda p: called.setdefault("p", p) and (True, "console"))
    f = tmp_path / "a.py"
    f.write_text("print(1)")
    assert svc.run_file(f) == (True, "console") and called["p"] == f


def test_service_html_preview_and_web_console(config, tmp_path):
    svc, _ = _svc(config, tmp_path)
    svc.html_preview = True
    f = tmp_path / "index.html"
    f.write_text("<h1>Xin chào</h1>", encoding="utf-8")
    ok, msg = svc.run_file(f)
    assert ok and svc.live.preview_url.startswith("file:")
    assert svc.live.wait(5) and svc.live.state == live_run.PREVIEW
    svc.web_console(2, "Uncaught ReferenceError: x is not defined", 3, "file:///C:/p/app.js")
    text = svc.live.plain_text()
    assert "ReferenceError" in text and "app.js:3" in text
