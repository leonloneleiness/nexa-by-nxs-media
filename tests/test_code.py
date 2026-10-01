"""Sinh code (docs/code.md): kiểm tra, chạy thử, vòng sửa lỗi, dịch vụ, lệnh nói, bảng xem. Gemini là bản giả lập."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from nexa.code import checks
from nexa.code.generator import CodeGenerator
from nexa.code.highlight import gutter_html, highlight_html
from nexa.code.intents import route_code
from nexa.code.models import CodeFile, CodeResult, safe_rel_path
from nexa.code.service import CodeService
from nexa.utils.text import fold

GOOD_PY = '''def add(a: int, b: int) -> int:
    """Cộng hai số."""
    return a + b
'''
GOOD_TEST = '''from calc import add


def test_add():
    assert add(2, 3) == 5
'''
BAD_PY = "def add(a, b)\n    return a + b\n"


def payload(content: str = GOOD_PY, test: str | None = GOOD_TEST, title: str = "Máy tính") -> dict:
    files = [{"path": "calc.py", "language": "python", "content": content}]
    if test is not None:
        files.insert(0, {"path": "test_calc.py", "language": "python", "content": test})
    return {"title": title, "language": "python", "summary": "Hàm cộng.", "files": files, "entry": "calc.py",
            "run_instructions": "python -m pytest -q", "dependencies": [], "notes": ["ghi chú"]}


class FakeGemini:
    model = "fake-model"

    def __init__(self, *responses: dict, gate: threading.Event | None = None) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []
        self.gate = gate
        self.last_model = "fake-model"

    def status(self):
        return True, ""

    def generate_json(self, prompt, schema, token, **kw):
        self.prompts.append(prompt)
        if self.gate is not None:
            while not self.gate.wait(0.02):
                token.raise_if_cancelled()
            token.raise_if_cancelled()
        return self.responses.pop(0)


class Tok:
    cancelled = False

    def raise_if_cancelled(self):
        pass


# ------------------------------------------------------------------ kiểm tra tĩnh
def test_normalize_tabs_crlf_trailing_space():
    out = checks.normalize("def f():\r\n\treturn 1   \r\n\r\n\r\n", "python")
    assert out == "def f():\n    return 1\n"


def test_check_python_syntax_and_pyflakes():
    ok, bad, warn = checks.check_files([CodeFile("a.py", "python", GOOD_PY), CodeFile("b.py", "python", BAD_PY),
                                        CodeFile("c.py", "python", "import os\n\nprint(undefined_name)\n")])
    assert ok.status == "ok"
    assert bad.status == "error" and bad.messages
    assert warn.status == "error" and any("undefined_name" in m for m in warn.messages)


def test_check_unused_import_is_warning():
    (c,) = checks.check_files([CodeFile("a.py", "python", "import os\n\nprint(1)\n")])
    assert c.status == "warning"


def test_check_json_yaml():
    j_ok, j_bad, y_bad = checks.check_files([CodeFile("a.json", "json", '{"a": 1}\n'),
                                             CodeFile("b.json", "json", '{"a": }\n'),
                                             CodeFile("c.yaml", "yaml", "a: [1, 2\n")])
    assert j_ok.status == "ok" and j_bad.status == "error" and y_bad.status == "error"


def test_missing_packages():
    files = [CodeFile("a.py", "python", "import os\nimport requests\nimport cv2\nfrom calc import add\n"),
             CodeFile("calc.py", "python", GOOD_PY)]
    miss = " ".join(checks.missing_packages(files))
    assert "opencv-python" in miss or "cv2" not in miss
    assert "os" not in miss.split() and "calc" not in miss


def test_safe_rel_path_blocks_escape():
    for p in ("../../evil.py", "C:\\Windows\\x.py", "/etc/passwd"):
        out = safe_rel_path(p, 0)
        assert ".." not in out and ":" not in out and not out.startswith("/")


# ------------------------------------------------------------------ chạy thử
def test_run_project_pytest_pass_and_fail():
    py = checks.find_python()
    assert py
    ok = checks.run_project([CodeFile("calc.py", "python", GOOD_PY), CodeFile("test_calc.py", "python", GOOD_TEST)],
                            py, timeout_s=60)
    assert ok.ok and ok.exit_code == 0, ok.output
    bad = checks.run_project([CodeFile("calc.py", "python", GOOD_PY.replace("a + b", "a - b")),
                              CodeFile("test_calc.py", "python", GOOD_TEST)], py, timeout_s=60)
    assert not bad.ok and bad.exit_code not in (0, None)


def test_run_project_mini_runner(monkeypatch):
    monkeypatch.setattr(checks, "_has_pytest", lambda python: False)
    py = checks.find_python()
    rep = checks.run_project([CodeFile("calc.py", "python", GOOD_PY), CodeFile("test_calc.py", "python", GOOD_TEST)],
                             py, timeout_s=60)
    assert rep.ok, rep.output


def test_run_project_timeout_kills():
    rep = checks.run_project([CodeFile("main.py", "python", "import time\n\ntime.sleep(60)\n")],
                             checks.find_python(), timeout_s=2)
    assert rep.timed_out and not rep.ok and rep.seconds < 20


def test_run_project_strips_secrets(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-value")
    rep = checks.run_project([CodeFile("main.py", "python",
                                       "import os\n\nprint(os.environ.get('GEMINI_API_KEY', 'none'))\n")],
                             checks.find_python(), timeout_s=30)
    assert "super-secret-value" not in rep.output


# ------------------------------------------------------------------ generator
def test_parse_orders_entry_first_tests_last(config):
    res = CodeGenerator(FakeGemini(), config).parse(payload(), "cộng")
    assert [f.path for f in res.files] == ["calc.py", "test_calc.py"]
    assert res.language == "python" and res.title == "Máy tính"


def test_parse_dedupes_paths(config):
    data = payload()
    data["files"] = [{"path": "a.py", "content": "x = 1\n"}, {"path": "a.py", "content": "y = 2\n"}]
    res = CodeGenerator(FakeGemini(), config).parse(data, "p")
    assert len({f.path for f in res.files}) == 2


def test_generate_repairs_syntax_error(config):
    gem = FakeGemini(payload(BAD_PY), payload(GOOD_PY))
    res = CodeGenerator(gem, config).generate("viết hàm cộng", "python", Tok())
    assert res.check_status == "ok" and res.rounds == 2
    assert len(gem.prompts) == 2 and "lỗi" in gem.prompts[1]


def test_repair_keeps_old_when_not_better(config):
    config.set("code.repair_rounds", 1)
    gem = FakeGemini(payload(BAD_PY), payload(BAD_PY + BAD_PY))
    res = CodeGenerator(gem, config).generate("viết hàm cộng", "python", Tok())
    assert res.check_status == "error" and res.files[0].content.startswith("def add(a, b)\n")


def test_refine_links_parent(config):
    gen = CodeGenerator(FakeGemini(payload(), payload(title="Máy tính v2")), config)
    base = gen.generate("viết hàm cộng", "python", Tok())
    new = gen.refine(base, "thêm hàm trừ", Tok(), run_output="FAILED test_x")
    assert new.parent == base.id and new.title == "Máy tính v2"
    assert "FAILED test_x" in gen.gemini.prompts[-1] and "thêm hàm trừ" in gen.gemini.prompts[-1]


# ------------------------------------------------------------------ service
def _svc(config, tmp_path, gem, events=None):
    events = events if events is not None else []
    svc = CodeService(config, notify=lambda k, d: events.append((k, d)), gemini=gem, history_dir=tmp_path / "hist")
    return svc, events


def test_service_generate_history_and_save(config, tmp_path):
    svc, events = _svc(config, tmp_path, FakeGemini(payload()))
    said = []
    svc.on_message = lambda t, s: said.append(t)
    ok, _ = svc.generate("viết hàm cộng hai số")
    assert ok
    svc._thread.join(30)
    assert svc.job()["state"] == "done" and svc.current is not None
    kinds = [k for k, _ in events]
    assert kinds[0] == "code_open" and "code_result" in kinds and said
    hist = svc.history()
    assert len(hist) == 1 and svc.load(hist[0]["id"]).files[0].content == GOOD_PY
    ok, where = svc.save(folder=str(tmp_path / "out"))
    assert ok and (Path(where) / "calc.py").read_text(encoding="utf-8") == GOOD_PY
    ok2, where2 = svc.save(folder=str(tmp_path / "out"))
    assert ok2 and where2 != where                 # không ghi đè bản đã lưu
    assert svc.delete(hist[0]["id"]) and svc.history() == []


def test_service_cancel(config, tmp_path):
    gate = threading.Event()
    svc, _ = _svc(config, tmp_path, FakeGemini(payload(), gate=gate))
    assert svc.generate("viết hàm cộng hai số")[0]
    assert not svc.generate("việc thứ hai cùng lúc")[0]      # chỉ một việc một lúc
    assert svc.cancel()
    svc._thread.join(10)
    assert svc.job()["state"] == "cancelled" and svc.current is None


def test_service_emergency_lock(config, tmp_path):
    svc, _ = _svc(config, tmp_path, FakeGemini(payload()))
    svc.on_emergency("test")
    assert not svc.generate("viết hàm cộng hai số")[0]
    svc.on_resume_control()
    assert svc.generate("viết hàm cộng hai số")[0]
    svc._thread.join(30)


def test_all_text_headers():
    res = CodeResult("x", "p", "t", "python", "s", [CodeFile("a.py", "python", "a = 1\n"),
                                                   CodeFile("b.js", "javascript", "let b = 2;\n")])
    txt = CodeService.all_text(res)
    assert "# ===== a.py =====" in txt and "// ===== b.js =====" in txt
    assert CodeService.all_text(CodeResult("y", "p", "t", "python", "s", [res.files[0]])) == "a = 1\n"


def test_result_roundtrip():
    res = CodeResult("x", "p", "t", "python", "s", [CodeFile("a.py", "python", GOOD_PY)])
    res.checks = checks.check_files(res.files)
    back = CodeResult.from_dict(res.to_dict())
    assert back.files[0].content == GOOD_PY and back.check_status == res.check_status


# ------------------------------------------------------------------ lệnh nói
@pytest.mark.parametrize("text,lang", [
    ("viết code python đọc file csv và tính tổng cột", "python"),
    ("tạo script powershell dọn thư mục Temp", "powershell"),
    ("viết hàm javascript kiểm tra email hợp lệ", "javascript"),
    ("giúp tôi viết API REST bằng FastAPI", "python"),
    ("sinh code đọc cảm biến", None),
])
def test_route_generate(text, lang):
    r = route_code(text, fold(text))
    assert r is not None and r[1][0][0] == "generate_code", text
    assert r[1][0][1]["prompt"] == text and r[1][0][1].get("language") == lang


@pytest.mark.parametrize("text,tool", [
    ("mở bảng sinh code", "open_code_panel"), ("hủy viết code", "cancel_code_job"),
    ("chạy thử code", "run_code_tests"), ("sửa code thêm xử lý lỗi khi file không tồn tại", "refine_code"),
])
def test_route_other_code_tools(text, tool):
    r = route_code(text, fold(text))
    assert r is not None and r[1][0][0] == tool


@pytest.mark.parametrize("text", ["tạo thư mục code", "tạo file python", "viết email cho sếp", "mở chrome",
                                  "tạo mô hình 3d con rồng", "tạo file main.py trong vs code",
                                  "tạo file mới trong Visual Studio Code"])
def test_route_not_code(text):
    assert route_code(text, fold(text)) is None


def test_router_keeps_3d_and_old_commands():
    from nexa.ai.intent_router import IntentRouter
    router = IntentRouter(viewer_active=lambda: False, part_known=lambda p: False)
    assert router.route("tạo mô hình 3d con rồng").calls[0][0] == "generate_3d_model"
    assert router.route("tạo thư mục báo cáo").calls[0][0] == "create_folder"
    assert router.route("viết code python tính giai thừa").calls[0][0] == "generate_code"


def test_registry_has_code_tools(config):
    from nexa.ai.tool_registry import build_registry
    reg = build_registry(config)
    for name in ("generate_code", "refine_code", "get_code_status", "cancel_code_job", "open_code_panel",
                 "run_code_tests"):
        spec = reg.get(name)
        assert spec is not None and not spec.needs_control, name


# ------------------------------------------------------------------ hiển thị
def test_highlight_and_gutter():
    h = highlight_html("def f():\n    return '<b>'\n", "python")
    assert h.startswith("<pre") and "&lt;b&gt;" in h and "color" in h
    assert highlight_html("x", "khong-co-ngon-ngu").startswith("<pre")
    g = gutter_html(12)
    assert " 1\n" in g and "12" in g


def test_result_view(config, tmp_path):
    pytest.importorskip("PySide6")
    from nexa.ui.code_bridge import result_view
    res = CodeGenerator(FakeGemini(), config).parse(payload(), "cộng")
    res.checks = checks.check_files(res.files)
    v = result_view(res)
    assert v["checkStatus"] == "ok" and v["files"][0]["check"]["label"] == "Đạt"
    assert v["totalLines"] == sum(f.lines for f in res.files) and v["files"][0]["html"].startswith("<pre")
    assert result_view(None) == {}
