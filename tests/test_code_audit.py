"""Regression coverage for audit issues 6/7 and non-executing compiler checks."""
import io
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexa.code import checks, live_run
from nexa.code.models import CodeFile, CodeResult
from nexa.code.service import CodeService
from test_code import FakeGemini, payload


def result():
    return CodeResult("old", "prompt", "Title", "python", "summary",
                      [CodeFile("main.py", "python", "print(1)\n")])


@pytest.mark.parametrize("kind", ["generate", "refine"])
def test_cancel_during_final_dependency_check(config, tmp_path, monkeypatch, kind):
    events, spoken = [], []
    svc = CodeService(config, lambda k, d: events.append(k), FakeGemini(payload()),
                      history_dir=tmp_path / "hist")
    old = result()
    svc.current = old
    svc.on_message = lambda *args: spoken.append(args)
    entered, release = threading.Event(), threading.Event()

    def dependencies(files):
        entered.set()
        assert release.wait(5)
        return []

    monkeypatch.setattr(checks, "missing_packages", dependencies)
    try:
        assert getattr(svc, kind)("write a function")[0]
        assert entered.wait(5)
        assert svc.cancel()
    finally:
        release.set()
        if svc._thread:
            svc._thread.join(10)
    assert not svc.busy
    assert svc.job()["state"] == "cancelled"
    assert svc.current is old and svc.history() == []
    assert "code_result" not in events and "code_history" not in events and not spoken


def test_publication_wins_late_cancel_and_reentrant_callback(config, tmp_path, monkeypatch):
    svc = CodeService(config, gemini=FakeGemini(payload()), history_dir=tmp_path / "hist")
    entered, release = threading.Event(), threading.Event()
    store = svc._store
    callback_cancels = []

    def blocked_store(res):
        entered.set()
        assert release.wait(5)
        store(res)

    def notify(kind, data):
        svc.job()  # UI callbacks must not run under the publication lock.
        if kind == "code_result":
            callback_cancels.append(svc.cancel())

    monkeypatch.setattr(svc, "_store", blocked_store)
    svc._notify = notify
    try:
        assert svc.generate("write a function")[0]
        assert entered.wait(5)
        assert not svc.cancel()
        svc._token.cancel("external cancellation after commitment")
    finally:
        release.set()
        if svc._thread:
            svc._thread.join(10)
    assert not svc.busy and svc.job()["state"] == "done"
    assert len(svc.history()) == 1 and callback_cancels == [False]
    # The next job must not inherit the previous publication commitment.
    svc.generator.gemini = FakeGemini(payload(), gate=threading.Event())
    assert svc.generate("another function")[0]
    assert svc.cancel()
    svc._thread.join(10)
    assert svc.job()["state"] == "cancelled" and len(svc.history()) == 1


def console(tmp_path):
    run = live_run.LiveRun([], str(tmp_path), {})
    run._proc = SimpleNamespace(stdin=io.BytesIO(), poll=lambda: None)
    return run


@pytest.mark.parametrize("err_first", [False, True])
def test_input_preserves_both_streams(tmp_path, err_first):
    run = console(tmp_path)
    streams = [("out", "Name: "), ("err", "warning: ")]
    for stream, text in reversed(streams) if err_first else streams:
        run._feed(stream, text)
    assert run.send("Alice")
    run._feed("err", "detail\n")
    run._feed("out", "Hello\n")
    assert [(ln.kind, ln.text) for ln in run.lines if ln.kind == "in"] == [("in", "Alice")]
    assert any(ln.kind == "err" and ln.text == "warning: detail" for ln in run.lines)
    assert any(ln.kind == "out" and ln.text == "Hello" for ln in run.lines)
    assert run._proc.stdin.getvalue() == b"Alice\n"


def test_input_insertion_and_eviction_stay_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(live_run, "MAX_LINES", 3)
    run = console(tmp_path)
    run.info("old")
    run._feed("out", "Name: \r")
    run._feed("err", "warning: ")
    assert run.send("Alice")
    assert len(run.lines) == 3 and run.dropped == 1
    run._feed("err", "detail\n")
    assert run.lines[-1].text == "warning: detail"
    for i in range(10):
        run._feed("out", f"Prompt {i}: ")
        assert run.send(str(i))
        assert len(run.lines) <= 3
        assert all(0 <= idx - run.dropped < len(run.lines) for idx in run._open.values())
    run._feed("err", "evicted\r")
    for i in range(4):
        run.info(str(i))
    assert "err" not in run._open and "err" not in run._cr
    run._feed("err", "fresh\n")
    assert run.lines[-1].text == "fresh" and len(run.lines) == 3


@pytest.mark.parametrize("lang,path", [("typescript", "a.ts"), ("c", "a.c"), ("cpp", "a.cpp"),
                                       ("php", "a.php"), ("ruby", "a.rb"), ("lua", "a.lua")])
def test_missing_checkers_are_explicitly_skipped(monkeypatch, lang, path):
    monkeypatch.setattr(checks.shutil, "which", lambda name: None)
    monkeypatch.setattr(checks, "_run_tool", lambda *a: pytest.fail("must not install or run anything"))
    check, = checks.check_files([CodeFile(path, lang, "")])
    assert check.status == "skipped" and check.tool and check.messages


@pytest.mark.parametrize("lang,name,flag", [("c", "gcc", "-fsyntax-only"),
                                           ("cpp", "clang++", "-fsyntax-only"),
                                           ("c", "cl", "/Zs"), ("cpp", "cl", "/Zs")])
def test_native_syntax_commands(monkeypatch, lang, name, flag):
    monkeypatch.setattr(checks.shutil, "which", lambda n: name if n == name else None)

    def tool(cmd, root, timeout):
        assert flag in cmd and Path(cmd[-1]).is_absolute()
        assert (root / "inc.h").exists()
        assert not any(arg in cmd for arg in ("-o", "-c", "/link"))
        if name == "cl":
            assert ("/TP" if lang == "cpp" else "/TC") in cmd
        else:
            assert cmd[cmd.index("-x") + 1] == ("c++" if lang == "cpp" else "c")
        return 1, "main: syntax error"

    monkeypatch.setattr(checks, "_run_tool", tool)
    a, b = checks.check_files([CodeFile("main.cpp" if lang == "cpp" else "main.c", lang, "bad"),
                               CodeFile("inc.h", "text", "")])
    assert a.status == "error" and a.messages and b.status == "skipped"


@pytest.mark.parametrize("exit_code,status", [(0, "ok"), (1, "error"), (None, "skipped")])
def test_typescript_checks_group_without_project_or_emit(monkeypatch, exit_code, status):
    monkeypatch.setattr(checks, "_typescript_command", lambda: ["tsc"])
    calls = []

    def tool(cmd, root, timeout):
        calls.append(cmd)
        assert "--noEmit" in cmd and "--pretty" in cmd
        assert "--project" not in cmd and "--build" not in cmd
        assert cmd[-2:] == [str(root / "src/a.ts"), str(root / "src/b.tsx")]
        assert (root / "tsconfig.json").exists()
        return exit_code, str(root / "src/a.ts") + "(1,1): error TS2322: incompatible types"

    monkeypatch.setattr(checks, "_run_tool", tool)
    results = checks.check_files([CodeFile("src/a.ts", "typescript", "export const a = 1"),
                                  CodeFile("tsconfig.json", "json", '{"compilerOptions":{"outDir":"bad"}}'),
                                  CodeFile("src/b.tsx", "typescript", "import {a} from './a'")])
    assert len(calls) == 1
    assert [r.status for r in results] == [status, "ok", status]
    if exit_code == 1:
        assert "TS2322" in " ".join(results[0].messages)


def test_windows_tsc_shim_uses_node_without_shell(tmp_path, monkeypatch):
    shim = tmp_path / "tsc.cmd"
    entry = tmp_path / "node_modules/typescript/bin/tsc"
    entry.parent.mkdir(parents=True)
    entry.write_text("compiler placeholder")
    monkeypatch.setattr(checks.shutil, "which", lambda n: str(shim) if n == "tsc" else "node")
    assert checks._typescript_command() == ["node", str(entry)]
    entry.unlink()
    assert checks._typescript_command() == []


def test_checker_timeout_and_preload_environment(tmp_path, monkeypatch):
    for name in ("NODE_OPTIONS", "RUBYOPT", "CL", "JDK_JAVAC_OPTIONS"):
        monkeypatch.setenv(name, "untrusted preload")

    def run(cmd, **kwargs):
        assert not kwargs.get("shell")
        assert all(n not in kwargs["env"] for n in ("NODE_OPTIONS", "RUBYOPT", "CL", "JDK_JAVAC_OPTIONS"))
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(checks.subprocess, "run", run)
    monkeypatch.setattr(checks.shutil, "which", lambda n: "gcc" if n == "gcc" else None)
    check, = checks.check_files([CodeFile("a.c", "c", "int a;")])
    assert check.status == "skipped" and check.messages


def test_java_disables_annotation_processors(tmp_path, monkeypatch):
    monkeypatch.setattr(checks.shutil, "which", lambda n: "javac")

    def tool(cmd, root, timeout):
        assert "-proc:none" in cmd
        return 0, ""

    monkeypatch.setattr(checks, "_run_tool", tool)
    check, = checks.check_files([CodeFile("A.java", "java", "class A {}")])
    assert check.status == "ok"


@pytest.mark.parametrize("lang,path,good,bad", [
    ("typescript", "a.ts", "export const a: number = 1; throw new Error('not executed');", "export const a: = ;"),
    ("c", "a.c", "int main(void) { return 21; }", "int main( {"),
    ("cpp", "a.cpp", "int main() { return 21; }", "int main( {"),
    ("php", "a.php", "<?php throw new Exception('not executed');", "<?php function ( {"),
    ("ruby", "a.rb", "raise 'not executed'", "def ("),
    ("lua", "a.lua", "error('not executed')", "function ("),
])
def test_installed_compiler_valid_and_invalid(lang, path, good, bad):
    available = checks._typescript_command() if lang == "typescript" else any(
        checks.shutil.which(name) for name in {
            "c": ("clang", "gcc", "cl"), "cpp": ("clang++", "g++", "cl"),
            "php": ("php",), "ruby": ("ruby",), "lua": ("luac",),
        }[lang])
    if not available:
        pytest.skip(f"No installed {lang} checker")
    ok, = checks.check_files([CodeFile(path, lang, good)])
    assert ok.status == "ok", ok.messages
    error, = checks.check_files([CodeFile(path, lang, bad)])
    assert error.status == "error" and error.messages
