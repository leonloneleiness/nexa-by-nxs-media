"""Chạy thử mọi ngôn ngữ: kế hoạch chạy theo công cụ có trên máy, lệnh giọng nói "chạy thử file X", chạy tệp đang mở
trong VS Code, cửa sổ console riêng. Không cài/không gọi trình biên dịch thật (trừ Python có sẵn)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexa.ai.intent_router import IntentRouter
from nexa.code import runners
from nexa.code.runners import RunPlan
from nexa.core.events import ToolResult

FAKE_TOOLS = {"g++": r"C:\msys64\ucrt64\bin\g++.exe", "gcc": r"C:\msys64\ucrt64\bin\gcc.exe",
              "javac": r"C:\jdk\bin\javac.exe", "java": r"C:\jdk\bin\java.exe", "go": r"C:\Go\bin\go.exe",
              "rustc": r"C:\cargo\bin\rustc.exe", "node": r"C:\nodejs\node.exe", "php": r"C:\php\php.exe",
              "powershell": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"}


@pytest.fixture
def tools(monkeypatch):
    avail = dict(FAKE_TOOLS)
    monkeypatch.setattr(runners, "find_tool", lambda *names: next((avail[n] for n in names if n in avail), ""))
    monkeypatch.setattr(runners, "node_major", lambda node: (24, 1))
    monkeypatch.setattr(runners, "dotnet_sdk_major", lambda d: 0)
    return avail


def test_cpp_compiles_then_runs(tools, tmp_path):
    (tmp_path / "main.cpp").write_text("int main(){}")
    plan = runners.plan_file("main.cpp", tmp_path, tmp_path / "out")
    assert isinstance(plan, RunPlan) and len(plan.steps) == 2
    assert plan.steps[0][0].endswith("g++.exe") and "-std=c++17" in plan.steps[0]
    assert plan.steps[1] == [str(tmp_path / "out" / "main.exe")]


def test_java_package_main_class(tools, tmp_path):
    src = tmp_path / "src" / "app"
    src.mkdir(parents=True)
    (src / "Main.java").write_text("package app;\npublic class Main { public static void main(String[] a){} }")
    plan = runners.plan_file("src/app/Main.java", tmp_path, tmp_path / "out")
    assert plan.steps[0][0].endswith("javac.exe") and plan.steps[1][-1] == "app.Main"


def test_go_rust_ts_php_plans(tools, tmp_path):
    for name in ("main.go", "main.rs", "app.ts", "index.php"):
        (tmp_path / name).write_text("x")
    assert runners.plan_file("main.go", tmp_path, tmp_path / "o").steps[0][:2] == [FAKE_TOOLS["go"], "run"]
    assert len(runners.plan_file("main.rs", tmp_path, tmp_path / "o").steps) == 2
    assert "--experimental-strip-types" in runners.plan_file("app.ts", tmp_path, tmp_path / "o").steps[0]
    assert runners.plan_file("index.php", tmp_path, tmp_path / "o").steps[0][0] == FAKE_TOOLS["php"]


def test_missing_toolchain_says_how_to_install(tools, tmp_path):
    tools.clear()
    (tmp_path / "main.cpp").write_text("int main(){}")
    msg = runners.plan_file("main.cpp", tmp_path, tmp_path / "o")
    assert isinstance(msg, str) and "winget install" in msg


def test_powershell_batch_html(tools, tmp_path):
    for name in ("a.ps1", "b.bat", "c.html"):
        (tmp_path / name).write_text("x")
    ps = runners.plan_file("a.ps1", tmp_path, tmp_path / "o").steps[0]
    assert "UTF8" in ps[-1] and ".\\a.ps1" in ps[-1]
    bat = runners.plan_file("b.bat", tmp_path, tmp_path / "o").steps[0]
    assert Path(bat[-1]).is_absolute()
    html = runners.plan_file("c.html", tmp_path, tmp_path / "o")
    assert html.steps == [] and html.open_path.endswith("c.html")


def test_markdown_is_not_a_program(tools, tmp_path):
    (tmp_path / "README.md").write_text("# x")
    assert isinstance(runners.plan_file("README.md", tmp_path, tmp_path / "o"), str)


# ------------------------------------------------------------------ lệnh giọng nói
@pytest.mark.parametrize("heard,args", [
    ("chạy thử file main.py", {"name": "main.py"}),
    ("Chạy thử file main.py trong VS Code giúp tôi", {"name": "main.py"}),
    ("chạy main chấm py", {"name": "main chấm py"}),
    ("chạy thử tệp tính tổng.cpp đi", {"name": "tính tổng.cpp"}),
    ("run file app.ts", {"name": "app.ts"}),
    ("chạy file đang mở trong VS Code", {}),
    ("chạy thử file này", {}),
    ("chạy thử code trong VS Code", {}),
])
def test_router_run_file(heard, args):
    assert IntentRouter().route(heard).calls == [("run_file", args)]


@pytest.mark.parametrize("heard", ["chạy thử code", "chạy thử code vừa tạo", "chạy thử chương trình"])
def test_router_generated_code_still_uses_run_code_tests(heard):
    assert IntentRouter().route(heard).calls == [("run_code_tests", {})]


def test_router_run_new_file_is_not_run_file():
    assert IntentRouter().route("chạy thử file mới").calls != [("run_file", {"name": "mới"})]


# ------------------------------------------------------------------ FileService app="run"
class _Cfg:
    def get(self, key, default=None):
        return {"files.search_limit": 50}.get(key, default)


def test_file_service_run_uses_hook(tmp_path, monkeypatch):
    from nexa.desktop.apps_and_files import FileService
    import nexa.desktop.office as office
    (tmp_path / "proj").mkdir()
    (tmp_path / "proj" / "tinh_tong.cpp").write_text("int main(){}")
    monkeypatch.setattr(office, "vscode_workspaces", lambda: [])
    fs = FileService(_Cfg())
    monkeypatch.setattr(FileService, "roots", property(lambda self: [tmp_path]))
    monkeypatch.setattr(fs, "check", lambda p: Path(p))
    ran = []
    fs.run_hook = lambda p: (ran.append(p), ToolResult.success("ok", verified=True))[1]
    r = fs.open_by_name("tính tổng chấm cpp", "file", app="run")
    assert r.ok, r.message
    assert ran == [tmp_path / "proj" / "tinh_tong.cpp"]
    fs.run_hook = None
    assert fs.open_by_name("tinh_tong.cpp", "file", app="run").error_code == "unavailable"


# ------------------------------------------------------------------ tệp đang mở trong VS Code
def test_vscode_active_file_from_title(tmp_path, monkeypatch):
    import nexa.desktop.office as office
    ws = tmp_path / "NEXA"
    (ws / "nexa").mkdir(parents=True)
    (ws / "nexa" / "app.py").write_text("x")
    (ws / "node_modules").mkdir()
    (ws / "node_modules" / "app.py").write_text("x")                  # thư mục bỏ qua
    monkeypatch.setattr(office, "vscode_workspaces", lambda: [ws])
    api = SimpleNamespace(enum_windows=lambda: [1, 2], is_visible=lambda h: True,
                          get_title=lambda h: {1: "Zalo", 2: "● app.py - NEXA - Visual Studio Code"}[h])
    path, dirty, why = office.vscode_active_file(api)
    assert path == ws / "nexa" / "app.py" and dirty and not why
    api.get_title = lambda h: {1: "Zalo", 2: "NEXA - Visual Studio Code"}[h]
    assert office.vscode_active_file(api)[0] is None
    api.get_title = lambda h: "Zalo"
    assert "không thấy" in office.vscode_active_file(api)[2]


def test_run_file_tool_without_name_runs_active_vscode_file(tmp_path, monkeypatch):
    from nexa.code import tools as code_tools
    import nexa.desktop.office as office
    f = tmp_path / "main.py"
    f.write_text("print(1)")
    monkeypatch.setattr(office, "vscode_active_file", lambda api=None: (f, True, ""))
    calls = []
    svc = SimpleNamespace(enabled=True, current=None, run_file=lambda p: (calls.append(p), (True, "Em đang chạy"))[1])
    ctx = SimpleNamespace(services=SimpleNamespace(code=svc), token=SimpleNamespace(cancelled=False))
    r = code_tools.h_run_file({}, ctx)
    assert r.ok and calls == [f] and "chưa được lưu" in r.message
    r = code_tools.h_run({}, ctx)                                       # chưa có bản code do NEXA viết
    assert r.ok and calls == [f, f]


# ------------------------------------------------------------------ CodeService.run_file → console riêng
def test_service_run_file_opens_console(config, tmp_path, monkeypatch):
    from nexa.code import console_run
    from nexa.code.service import CodeService
    f = tmp_path / "hello.py"
    f.write_text("print('xin chào')")
    launched = {}

    class Proc:
        def poll(self):
            return 0

    def fake_launch(steps, cwd, title, env):
        launched.update(steps=steps, cwd=cwd, title=title, env=env)
        return Proc(), tmp_path / "missing" / "result.json"
    monkeypatch.setattr(console_run, "launch", fake_launch)
    monkeypatch.setenv("NEXA_TEST_SECRET_TOKEN", "abc")
    svc = CodeService(config, history_dir=tmp_path / "hist")
    ok, msg = svc.run_file_console(f)
    assert ok and "cửa sổ riêng" in msg
    assert launched["steps"][-1][-1] == "hello.py" and launched["cwd"] == tmp_path
    assert "NEXA_TEST_SECRET_TOKEN" not in launched["env"]            # không lộ khóa cho code chạy thử
    assert not svc.run_file_console(tmp_path / "khong_co.py")[0]
    assert not svc.run_file(tmp_path / "khong_co.py")[0]


def test_console_main_runs_steps_and_writes_result(tmp_path, monkeypatch, capsys):
    import json

    from nexa.code import console_run
    monkeypatch.setattr(console_run, "_prepare_console", lambda title: None)
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    spec = tmp_path / "spec.json"
    result = tmp_path / "result.json"
    spec.write_text(json.dumps({"title": "t.py", "cwd": str(tmp_path), "result": str(result),
                                "steps": [[sys.executable, "-c", "import sys; sys.exit(0)"],
                                          [sys.executable, "-c", "import sys; sys.exit(3)"]]}), encoding="utf-8")
    assert console_run.console_main(str(spec)) == 1
    data = json.loads(result.read_text(encoding="utf-8"))
    assert data["exit_code"] == 3 and not data["build_failed"]
    spec.write_text(json.dumps({"title": "t.c", "cwd": str(tmp_path), "result": str(result),
                                "steps": [[sys.executable, "-c", "import sys; sys.exit(1)"], ["never-run"]]}),
                    encoding="utf-8")
    console_run.console_main(str(spec))
    assert json.loads(result.read_text(encoding="utf-8"))["build_failed"]
    assert "Biên dịch lỗi" in capsys.readouterr().out


def test_runner_command_uses_console_python():
    from nexa.code import console_run
    cmd = console_run.runner_command(Path("s.json"))
    assert cmd[-2:] == [console_run.FLAG, "s.json"] and os.path.basename(cmd[0]).lower() != "pythonw.exe"
