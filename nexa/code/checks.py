"""Chuẩn hóa định dạng, kiểm tra tĩnh và chạy thử code do Gemini viết.

- Kiểm tra tĩnh KHÔNG chạy code: Python (compile + pyflakes), JavaScript (node --check), JSON/YAML/TOML (parser),
  TypeScript (tsc --noEmit), C/C++ (syntax-only), PHP/Ruby/Lua (parse-only),
  PowerShell (parser), Go (gofmt -e), Java (javac -proc:none). Thiếu công cụ: báo "chưa kiểm tra".
- Chạy thử (run_project) THỰC SỰ chạy code trên máy nên chỉ gọi khi anh bấm "Chạy thử": thư mục tạm riêng, không stdin,
  không cửa sổ console, biến môi trường chứa KEY/TOKEN/SECRET/PASSWORD bị bỏ, quá hạn thì diệt cả cây tiến trình.
  Đây KHÔNG phải sandbox hệ thống — code vẫn có quyền của tài khoản Windows hiện tại.
- Lệnh chạy cho từng ngôn ngữ (Python, JS/TS, C/C++, C#, Java, Go, Rust, PHP, Ruby, Perl, Lua, R, Dart, Kotlin,
  PowerShell, batch, bash, SQL…, kể cả bước biên dịch) nằm ở runners.py; thiếu công cụ thì báo lệnh winget để cài.
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from nexa.code import runners
from nexa.code.models import CodeFile, FileCheck, RunReport
from nexa.code.runners import RunPlan
from nexa.utils.logging import get_logger

log = get_logger("code.checks")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MAX_OUTPUT = 12_000


# ------------------------------------------------------------------ định dạng
def normalize(content: str, lang: str) -> str:
    """LF, bỏ khoảng trắng cuối dòng, Python: tab đầu dòng → 4 dấu cách; đúng một dòng trống cuối tệp."""
    text = (content or "").replace("\r\n", "\n").replace("\r", "\n").replace("﻿", "")
    lines = text.split("\n")
    if lang != "markdown":
        lines = [ln.rstrip() for ln in lines]
    if lang == "python":
        lines = [_expand_indent(ln) for ln in lines]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines) + "\n" if lines else ""


def _expand_indent(line: str) -> str:
    m = re.match(r"[ \t]*", line)
    lead = m.group(0) if m else ""
    return lead.expandtabs(4) + line[len(lead):] if "\t" in lead else line


# ------------------------------------------------------------------ kiểm tra tĩnh
PYFLAKES_ERRORS = {
    "UndefinedName", "UndefinedLocal", "UndefinedExport", "DuplicateArgument", "ReturnOutsideFunction",
    "YieldOutsideFunction", "ContinueOutsideLoop", "BreakOutsideLoop", "DefaultExceptNotLast",
    "TwoStarredExpressions", "TooManyExpressionsInStarredAssignment", "StringDotFormatMissingArgument",
    "PercentFormatMissingArgument", "ForwardAnnotationSyntaxError", "ImportStarNotPermitted",
}


def check_python(f: CodeFile) -> FileCheck:
    res = FileCheck(f.path, "ok", "compile + pyflakes")
    try:
        compile(f.content, f.path, "exec", dont_inherit=True)
    except SyntaxError as exc:
        res.status = "error"
        res.messages.append(f"Dòng {exc.lineno}: lỗi cú pháp — {exc.msg}")
        return res
    try:
        from pyflakes import api as pf_api
        from pyflakes import reporter as pf_reporter
    except ImportError:
        res.tool = "compile"
        return res

    class _Rep(pf_reporter.Reporter):
        def __init__(self) -> None:
            self.items: list[tuple[bool, str]] = []

        def unexpectedError(self, filename, msg):  # noqa: N802 (API của pyflakes)
            self.items.append((True, str(msg)))

        def syntaxError(self, filename, msg, lineno, offset, text):  # noqa: N802
            self.items.append((True, f"Dòng {lineno}: lỗi cú pháp — {msg}"))

        def flake(self, message):
            err = type(message).__name__ in PYFLAKES_ERRORS
            self.items.append((err, f"Dòng {message.lineno}: {message.message % message.message_args}"))

    rep = _Rep()
    pf_api.check(f.content, f.path, rep)
    for err, msg in rep.items:
        res.messages.append(msg)
        if err:
            res.status = "error"
        elif res.status == "ok":
            res.status = "warning"
    return res


def check_json(f: CodeFile) -> FileCheck:
    try:
        json.loads(f.content)
        return FileCheck(f.path, "ok", "json")
    except json.JSONDecodeError as exc:
        return FileCheck(f.path, "error", "json", [f"Dòng {exc.lineno}: {exc.msg}"])


def check_yaml(f: CodeFile) -> FileCheck:
    import yaml
    try:
        list(yaml.safe_load_all(f.content))
        return FileCheck(f.path, "ok", "yaml")
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f"Dòng {mark.line + 1}: " if mark is not None else ""
        return FileCheck(f.path, "error", "yaml", [where + str(getattr(exc, "problem", exc))])


def check_toml(f: CodeFile) -> FileCheck:
    import tomllib
    try:
        tomllib.loads(f.content)
        return FileCheck(f.path, "ok", "toml")
    except tomllib.TOMLDecodeError as exc:
        return FileCheck(f.path, "error", "toml", [str(exc)])


def _run_tool(cmd: list[str], cwd: Path, timeout: float = 20.0) -> tuple[int | None, str]:
    # Runtime preload hooks may execute code even for a syntax-only command.
    env = {k: v for k, v in os.environ.items() if k.upper() not in {
        "NODE_OPTIONS", "RUBYOPT", "RUBYLIB", "LUA_INIT", "LUA_INIT_5_4", "LUA_INIT_5_3",
        "JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "JDK_JAVAC_OPTIONS",
        "CL", "_CL_", "CLASSPATH",
    }}
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
                           creationflags=NO_WINDOW, env=env)
    except subprocess.TimeoutExpired:
        return None, "quá thời gian kiểm tra"
    except OSError as exc:
        return None, str(exc)
    out = (p.stdout + b"\n" + p.stderr).decode("utf-8", "replace").strip()
    return p.returncode, out


def _write_all(files: Iterable[CodeFile], root: Path) -> None:
    for f in files:
        dest = root / f.path
        dest.parent.mkdir(parents=True, exist_ok=True)
        # PowerShell 5 đọc tệp không có BOM theo bảng mã ANSI → chữ Việt vỡ; tệp .bat/.cmd cần CRLF
        dest.write_text(f.content, encoding="utf-8-sig" if f.language == "powershell" else "utf-8",
                        newline="\r\n" if f.language in ("batch", "powershell") else "\n")


def _first_lines(text: str, n: int = 6) -> list[str]:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[:n]


def check_javascript(f: CodeFile, root: Path) -> FileCheck:
    node = shutil.which("node")
    if not node:
        return FileCheck(f.path, "skipped", "node", ["Máy chưa có Node.js nên chưa kiểm tra cú pháp."])
    if Path(f.path).suffix.lower() == ".jsx":
        return FileCheck(f.path, "skipped", "node", ["JSX cần bộ biên dịch (Babel/esbuild) — chưa kiểm tra."])
    code, out = _run_tool([node, "--check", f.path], root)
    if code == 0:
        return FileCheck(f.path, "ok", "node --check")
    out = out.replace(str(root) + os.sep, "")
    msgs = [ln for ln in _first_lines(out, 12) if not ln.startswith("Node.js v") and not ln.lstrip().startswith("at ")]
    return FileCheck(f.path, "error" if code is not None else "skipped", "node --check", msgs[:6])


PS_PARSE = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8;$e=$null;$t=$null;[void][System.Management.Automation.Language.Parser]::ParseFile("
            "(Resolve-Path -LiteralPath $args[0]).Path,[ref]$t,[ref]$e);"
            "foreach($x in $e){'L' + $x.Extent.StartLineNumber + ': ' + $x.Message}")


def check_powershell(f: CodeFile, root: Path) -> FileCheck:
    ps = shutil.which("powershell") or shutil.which("pwsh")
    if not ps:
        return FileCheck(f.path, "skipped", "powershell", ["Không tìm thấy PowerShell."])
    script = root / "__nexa_psparse.ps1"
    script.write_text("param([string]$p)\n" + PS_PARSE.replace("$args[0]", "$p"), encoding="utf-8-sig")
    try:
        code, out = _run_tool([ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script),
                               f.path], root)
    finally:
        script.unlink(missing_ok=True)
    if code is None:
        return FileCheck(f.path, "skipped", "powershell parser", [out])
    msgs = [re.sub(r"^L(\d+):", lambda m: f"Dòng {m.group(1)}:", ln) for ln in _first_lines(out, 6)]
    return FileCheck(f.path, "error" if msgs else "ok", "powershell parser", msgs)


def check_go(f: CodeFile, root: Path) -> FileCheck:
    gofmt = shutil.which("gofmt")
    if not gofmt:
        return FileCheck(f.path, "skipped", "gofmt", ["Máy chưa có Go nên chưa kiểm tra cú pháp."])
    code, out = _run_tool([gofmt, "-e", "-l", f.path], root)
    if code == 0:
        return FileCheck(f.path, "ok", "gofmt -e")
    return FileCheck(f.path, "error" if code is not None else "skipped", "gofmt -e", _first_lines(out))


def check_java(files: list[CodeFile], root: Path) -> list[FileCheck]:
    javac = shutil.which("javac")
    if not javac:
        return [FileCheck(f.path, "skipped", "javac", ["Máy chưa có JDK (javac) nên chưa biên dịch thử."]) for f in files]
    out_dir = root / "__nexa_classes"
    code, out = _run_tool([javac, "-proc:none", "-encoding", "UTF-8", "-d", str(out_dir),
                           *[str(root / f.path) for f in files]], root, 60)
    shutil.rmtree(out_dir, ignore_errors=True)
    res = []
    for f in files:
        mine = [ln for ln in out.splitlines() if ln.replace("\\", "/").startswith(f.path)]
        if code == 0:
            res.append(FileCheck(f.path, "ok", "javac"))
        else:
            res.append(FileCheck(f.path, "error" if mine or code is not None else "skipped", "javac",
                                 (mine or _first_lines(out))[:6]))
    return res


def _compiler_result(f: CodeFile, tool: str, code: int | None, out: str, root: Path) -> FileCheck:
    out = out.replace(str(root) + os.sep, "").replace(root.as_posix() + "/", "")
    status = "skipped" if code is None else "ok" if code == 0 else "error"
    messages = _first_lines(out[:MAX_OUTPUT]) if code != 0 else []
    if code != 0 and not messages:
        messages = [f"{tool}: kiểm tra không hoàn tất (exit={code})."]
    return FileCheck(f.path, status, tool, messages)


def _typescript_command() -> list[str]:
    """Use only an installed compiler; never npx or a package install/build hook."""
    tsc = shutil.which("tsc")
    if not tsc:
        return []
    if Path(tsc).suffix.lower() in (".cmd", ".bat", ".ps1"):
        # npm's Windows shim requires a shell. Invoke its installed JS entry
        # directly instead, so generated filenames never become shell text.
        entry = Path(tsc).parent / "node_modules" / "typescript" / "bin" / "tsc"
        node = shutil.which("node")
        return [node, str(entry)] if node and entry.is_file() else []
    return [tsc]


def check_typescript(files: list[CodeFile], root: Path) -> list[FileCheck]:
    cmd = _typescript_command()
    tool = "tsc --noEmit"
    if not cmd:
        return [FileCheck(f.path, "skipped", tool, ["Không tìm thấy TypeScript (tsc) đã cài."]) for f in files]
    # Explicit roots bypass tsconfig.json, including generated build settings.
    # Check the whole group so imports between generated files resolve.
    code, out = _run_tool([*cmd, "--noEmit", "--pretty", "false", "--incremental", "false",
                           "--target", "ES2020", "--module", "ESNext", "--moduleResolution", "node",
                           "--jsx", "preserve", *[str(root / f.path) for f in files]], root, 60)
    results = []
    for f in files:
        result = _compiler_result(f, tool, code, out, root)
        if code not in (None, 0):
            result.messages.insert(0, "Nhóm TypeScript không đạt (gồm kiểm tra kiểu và thư viện phụ thuộc).")
        results.append(result)
    return results


def check_native(f: CodeFile, root: Path) -> FileCheck:
    cpp = f.language == "cpp"
    names = ("clang++", "g++") if cpp else ("clang", "gcc")
    compiler = next((p for name in names if (p := shutil.which(name))), None)
    if compiler:
        tool = Path(compiler).name + " -fsyntax-only"
        cmd = [compiler, "-fsyntax-only", "-x", "c++" if cpp else "c",
               "-std=c++17" if cpp else "-std=c11", "-I", str(root), str(root / f.path)]
    elif compiler := shutil.which("cl"):
        tool = "cl /Zs"
        cmd = [compiler, "/nologo", "/Zs", "/TP" if cpp else "/TC", "/I" + str(root)]
        if cpp:
            cmd.append("/std:c++17")
        cmd.append(str(root / f.path))
    else:
        return FileCheck(f.path, "skipped", "C/C++ syntax", ["Không tìm thấy clang, GCC hoặc MSVC (cl)."])
    code, out = _run_tool(cmd, root, 60)
    return _compiler_result(f, tool, code, out, root)


PARSE_TOOLS = {
    "php": ("php", ["-n", "-l"]),  # -n ignores php.ini and its extensions
    "ruby": ("ruby", ["--disable-gems", "-c"]),
    "lua": ("luac", ["-p"]),
}


def check_parse_tool(f: CodeFile, root: Path) -> FileCheck:
    name, flags = PARSE_TOOLS[f.language]
    exe = shutil.which(name)
    tool = " ".join([name, *flags])
    if not exe:
        return FileCheck(f.path, "skipped", tool, [f"Không tìm thấy {name} đã cài."])
    code, out = _run_tool([exe, *flags, str(root / f.path)], root)
    return _compiler_result(f, tool, code, out, root)


NOT_CHECKED = {
    "csharp": "Cần dotnet build trong một dự án — chưa kiểm tra tự động.",
}


def check_files(files: list[CodeFile]) -> list[FileCheck]:
    """Kiểm tra tĩnh mọi tệp; trả đúng thứ tự tệp."""
    results: dict[str, FileCheck] = {}
    with tempfile.TemporaryDirectory(prefix="nexa_code_check_") as tmp:
        root = Path(tmp)
        _write_all(files, root)
        java = [f for f in files if f.language == "java"]
        if java:
            for c in check_java(java, root):
                results[c.path] = c
        typescript = [f for f in files if f.language == "typescript"]
        if typescript:
            try:
                for c in check_typescript(typescript, root):
                    results[c.path] = c
            except Exception as exc:
                for f in typescript:
                    results[f.path] = FileCheck(f.path, "skipped", "tsc --noEmit",
                                                [f"Bộ kiểm tra gặp lỗi: {type(exc).__name__}"])
        for f in files:
            if f.path in results:
                continue
            try:
                if f.language == "python":
                    c = check_python(f)
                elif f.language == "javascript":
                    c = check_javascript(f, root)
                elif f.language == "json":
                    c = check_json(f)
                elif f.language == "yaml":
                    c = check_yaml(f)
                elif f.language == "toml":
                    c = check_toml(f)
                elif f.language == "powershell":
                    c = check_powershell(f, root)
                elif f.language == "go":
                    c = check_go(f, root)
                elif f.language in ("c", "cpp"):
                    c = check_native(f, root)
                elif f.language in PARSE_TOOLS:
                    c = check_parse_tool(f, root)
                else:
                    c = FileCheck(f.path, "skipped", "", [NOT_CHECKED.get(f.language, "Không kiểm tra tự động loại tệp này.")])
            except Exception as exc:     # một bộ kiểm tra hỏng không được làm hỏng cả bản code
                log.exception("Kiểm tra %s lỗi", f.path)
                c = FileCheck(f.path, "skipped", "", [f"Bộ kiểm tra gặp lỗi: {type(exc).__name__}"])
            results[f.path] = c
    return [results[f.path] for f in files]


# ------------------------------------------------------------------ thư viện ngoài
PIP_NAMES = {
    "cv2": "opencv-python", "PIL": "Pillow", "yaml": "PyYAML", "sklearn": "scikit-learn", "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv", "win32api": "pywin32", "win32con": "pywin32", "win32gui": "pywin32",
    "win32com": "pywin32", "pythoncom": "pywin32", "dateutil": "python-dateutil", "jwt": "PyJWT",
    "serial": "pyserial", "usb": "pyusb", "Crypto": "pycryptodome", "docx": "python-docx", "pptx": "python-pptx",
    "magic": "python-magic", "google": "google-api-python-client", "attr": "attrs", "OpenSSL": "pyOpenSSL",
    "fitz": "PyMuPDF", "telegram": "python-telegram-bot", "skimage": "scikit-image",
}
JS_BUILTINS = {
    "assert", "async_hooks", "buffer", "child_process", "cluster", "console", "constants", "crypto", "dgram", "dns",
    "domain", "events", "fs", "http", "http2", "https", "inspector", "module", "net", "os", "path", "perf_hooks",
    "process", "punycode", "querystring", "readline", "repl", "stream", "string_decoder", "sys", "timers", "tls",
    "trace_events", "tty", "url", "util", "v8", "vm", "wasi", "worker_threads", "zlib", "test",
}


def python_imports(content: str) -> set[str]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            out.add(node.module.split(".")[0])
    return out


def missing_packages(files: list[CodeFile]) -> list[str]:
    """Thư viện ngoài mà code import nhưng môi trường Python/Node của NEXA chưa có (gợi ý lệnh cài)."""
    import importlib.util
    local = set()
    for f in files:
        p = Path(f.path)
        local.add(p.stem)
        local.update(p.parts[:-1])
    need: list[str] = []
    std = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}
    for f in files:
        if f.language != "python":
            continue
        for mod in sorted(python_imports(f.content)):
            if mod in std or mod in local:
                continue
            try:
                found = importlib.util.find_spec(mod) is not None
            except (ImportError, ValueError):
                found = False
            name = PIP_NAMES.get(mod, mod)
            if not found and f"pip install {name}" not in need:
                need.append(f"pip install {name}")
    js_re = re.compile(r"""(?:require\(\s*|\bfrom\s+|^\s*import\s+)['"]([^'"./][^'"]*)['"]""", re.M)
    for f in files:
        if f.language not in ("javascript", "typescript"):
            continue
        for m in js_re.finditer(f.content):
            spec = m.group(1)
            if spec.startswith("node:"):
                continue
            pkg = "/".join(spec.split("/")[:2]) if spec.startswith("@") else spec.split("/")[0]
            if pkg in JS_BUILTINS:
                continue
            if f"npm install {pkg}" not in need:
                need.append(f"npm install {pkg}")
    return need


# ------------------------------------------------------------------ chạy thử (chỉ khi anh bấm)
def find_python(configured: str = "") -> list[str] | None:
    if configured:
        return [configured]
    if not getattr(sys, "frozen", False):
        return [sys.executable]
    py = shutil.which("py")
    if py:
        return [py, "-3"]
    exe = shutil.which("python")
    if exe and "windowsapps" not in exe.lower():     # bỏ lối tắt Microsoft Store
        return [exe]
    return None


@lru_cache(maxsize=8)
def _has_pytest(python: tuple[str, ...]) -> bool:
    code, _ = _run_tool([*python, "-c", "import pytest"], Path(tempfile.gettempdir()), 20)
    return code == 0


MINI_RUNNER = r'''
import importlib, inspect, sys, traceback, unittest
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
failed = passed = 0
for path in sorted(Path.cwd().rglob("*.py")):
    if not (path.name.startswith("test_") or path.stem.endswith("_test")):
        continue
    rel = path.relative_to(Path.cwd()).with_suffix("")
    name = ".".join(rel.parts)
    sys.path.insert(0, str(path.parent))
    try:
        mod = importlib.import_module(name)
    except Exception:
        failed += 1
        print(f"LỖI khi import {name}:"); traceback.print_exc()
        continue
    for attr, fn in sorted(vars(mod).items()):
        if attr.startswith("test") and inspect.isfunction(fn) and fn.__module__ == mod.__name__:
            try:
                fn(); passed += 1; print(f"ĐẠT  {name}.{attr}")
            except Exception:
                failed += 1; print(f"TRƯỢT {name}.{attr}"); traceback.print_exc()
    suite = unittest.defaultTestLoader.loadTestsFromModule(mod)
    if suite.countTestCases():
        r = unittest.TextTestRunner(stream=sys.stdout, verbosity=1).run(suite)
        failed += len(r.failures) + len(r.errors); passed += r.testsRun - len(r.failures) - len(r.errors)
print(f"\n{passed} đạt, {failed} trượt")
sys.exit(1 if failed or not passed else 0)
'''

SECRET_ENV = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL", re.I)


def _is_test(path: str) -> bool:
    name = Path(path).name.lower()
    return name.startswith("test_") or name.endswith(("_test.py", ".test.js", ".test.mjs", ".test.cjs", ".spec.js"))


BUILD_DIR = "__nexa_build"
# thứ tự ưu tiên ngôn ngữ khi một bản code có nhiều loại tệp (tệp cấu hình/HTML/CSS không phải "chương trình")
RUN_ORDER = ["python", "javascript", "typescript", "go", "rust", "java", "kotlin", "csharp", "cpp", "c", "php", "ruby",
             "perl", "lua", "r", "julia", "haskell", "elixir", "fsharp", "dart", "swift", "scala", "groovy", "zig",
             "powershell", "bash", "batch", "vbscript", "sql"]
ENTRY_NAMES = ("main", "app", "index", "program", "run", "start", "__main__")


def plan_run(files: list[CodeFile], python: list[str] | None, root: Path | None = None) -> tuple[RunPlan | None, str]:
    """(kế hoạch, ghi chú). Kế hoạch None = không chạy thử được; ghi chú giải thích vì sao.
    Python/JavaScript có tệp kiểm thử thì chạy kiểm thử; còn lại chạy tệp chính (main) bằng công cụ trên máy.
    `root` = thư mục đã ghi sẵn các tệp (run_project); None = chỉ xem có chạy được không (ghi ra thư mục tạm)."""
    if root is None:
        with tempfile.TemporaryDirectory(prefix="nexa_code_plan_") as tmp:
            _write_all(files, Path(tmp))
            return plan_run(files, python, Path(tmp))
    py = [f for f in files if f.language == "python"]
    js = [f for f in files if f.language == "javascript" and Path(f.path).suffix.lower() != ".jsx"]
    if py and any(_is_test(f.path) for f in py):
        if python is None:
            return None, "Không tìm thấy Python để chạy thử (đặt code.python_path trong Cài đặt)."
        if _has_pytest(tuple(python)):
            return RunPlan([[*python, "-m", "pytest", "-q", "-p", "no:cacheprovider"]], "Chạy kiểm thử bằng pytest",
                           "python"), "Chạy kiểm thử bằng pytest"
        note = "Chạy kiểm thử (máy chưa có pytest: dùng bộ chạy đơn giản của NEXA)"
        return RunPlan([[*python, "__nexa_runner.py"]], note, "python"), note
    if js and not py and any(_is_test(f.path) for f in js):
        node = runners.find_tool("node")
        if not node:
            return None, runners.missing("javascript")
        # ghi rõ tệp kiểm thử: mẫu mặc định của node --test KHÔNG gồm test_*.js → "tests 0" mà vẫn báo đạt
        tests = [f.path for f in js if _is_test(f.path)]
        return RunPlan([[node, "--test", *tests]], "Chạy kiểm thử bằng node --test", "javascript"), \
            "Chạy kiểm thử bằng node --test"
    go = [f for f in files if f.language == "go"]
    if go and not py and not js and any(f.path.endswith("_test.go") for f in go):
        tool = runners.find_tool("go")
        if not tool:
            return None, runners.missing("go")
        return RunPlan([[tool, "test", "-v", "./..."]], "Chạy kiểm thử Go (go test)", "go", extra_s=60), \
            "Chạy kiểm thử Go"
    langs = [lang for lang in RUN_ORDER if any(f.language == lang for f in files)]
    if not langs:
        if any(f.language in ("html", "svg") for f in files):
            return None, "Trang HTML: anh bấm Lưu rồi mở tệp trong trình duyệt để xem (em không mở từ thư mục tạm)."
        return None, "Bản code này không có tệp chương trình nào để chạy thử."
    lang = langs[0]
    group = [f for f in files if f.language == lang]
    entry = _entry(group, lang)
    if entry is None:
        return None, "Không có tệp kiểm thử hay tệp chạy chính (main) để chạy thử."
    sources = [f.path for f in group if not _is_test(f.path)] if lang in ("c", "cpp", "csharp", "java") else None
    if lang in ("c", "cpp", "csharp", "java"):
        sources = [s for s in sources if s == entry.path or not _is_entry_like(group, s, lang)]
    if lang == "go":
        sources = [f.path for f in group if not f.path.endswith("_test.go")
                   and Path(f.path).parent == Path(entry.path).parent]
    plan = runners.plan_file(entry.path, root, root / BUILD_DIR, python, sources, lang)
    if isinstance(plan, str):
        return None, plan
    if plan.open_path:
        return None, "Trang HTML: anh bấm Lưu rồi mở tệp trong trình duyệt để xem."
    note = plan.label + (f". {plan.note}" if plan.note else "")
    return plan, note


def _is_entry_like(group: list[CodeFile], path: str, lang: str) -> bool:
    f = next(x for x in group if x.path == path)
    return runners.has_main(lang, f.content) or (lang == "csharp" and runners._top_level_cs(f.content))


def _entry(files: list[CodeFile], lang: str) -> CodeFile | None:
    cands = [f for f in files if not _is_test(f.path)]
    if lang == "python":
        for n in ("main.py", "app.py", "__main__.py"):
            for f in cands:
                if Path(f.path).name.lower() == n:
                    return f
        for f in cands:
            if "__main__" in f.content:
                return f
        return cands[0] if len(cands) == 1 else None
    for n in ENTRY_NAMES:
        for f in cands:
            if Path(f.path).stem.lower() == n:
                return f
    if lang in runners.MAIN_MARKERS:
        mains = [f for f in cands if runners.has_main(lang, f.content)]
        if mains:
            return mains[0]
        if lang == "csharp":
            top = [f for f in cands if runners._top_level_cs(f.content)]
            if top:
                return top[0]
    return cands[0] if len(cands) == 1 else None


def _kill_tree(pid: int) -> None:
    try:
        import psutil
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
    except Exception:
        pass


BUILD_TIMEOUT_S = 180.0


def run_env() -> dict[str, str]:
    """Môi trường cho code chạy thử: bỏ biến chứa KEY/TOKEN/SECRET/PASSWORD, ép UTF-8, tắt màu/telemetry."""
    env = {k: v for k, v in os.environ.items() if not SECRET_ENV.search(k)}
    env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", NO_COLOR="1", FORCE_COLOR="0",
               DOTNET_NOLOGO="1", DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1")
    return env


def decode_output(raw: bytes) -> str:
    """UTF-8; không hợp lệ thì theo bảng mã OEM của console (chương trình .NET Framework/cmd in ra ống theo OEM)."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode("oem")
        except (LookupError, UnicodeDecodeError):
            return raw.decode("utf-8", "replace")


def shown_command(cmd: list[str]) -> str:
    return " ".join(Path(c).name if i == 0 else (c if len(c) < 200 else "<script>") for i, c in enumerate(cmd))


def _run_step(cmd: list[str], root: Path, env: dict, limit: float, cancelled) -> tuple[int | None, bytes, bool]:
    """(mã thoát, đầu ra, quá giờ). Đọc stdout ở luồng riêng để chương trình in nhiều không bị nghẽn."""
    import threading
    proc = subprocess.Popen(cmd, cwd=str(root), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env=env, creationflags=NO_WINDOW)
    chunks: list[bytes] = []

    def _pump() -> None:
        assert proc.stdout is not None
        total = 0
        for chunk in iter(lambda: proc.stdout.read(4096), b""):
            if total < MAX_OUTPUT * 4:
                chunks.append(chunk)
            total += len(chunk)
    reader = threading.Thread(target=_pump, daemon=True)
    reader.start()
    t0 = time.monotonic()
    timed_out = False
    while proc.poll() is None:
        if cancelled() or time.monotonic() - t0 > limit:
            timed_out = not cancelled()
            _kill_tree(proc.pid)
            break
        time.sleep(0.05)
    proc.wait(timeout=5)
    reader.join(timeout=2)
    return proc.returncode, b"".join(chunks), timed_out


def prepare_project(files: list[CodeFile], python: list[str] | None,
                    root: Path | None = None) -> tuple[Path, RunPlan | None, str]:
    """Ghi bản code ra thư mục tạm riêng + lập kế hoạch chạy. Kế hoạch None → thư mục đã được xóa, ghi chú nói vì sao.
    Người gọi tự xóa `root` khi chạy xong."""
    root = Path(root or tempfile.mkdtemp(prefix="nexa_code_run_"))
    try:
        _write_all(files, root)
        plan, note = plan_run(files, python, root)
        if plan is None:
            shutil.rmtree(root, ignore_errors=True)
            return root, None, note
        if any("__nexa_runner.py" in step for step in plan.steps):
            (root / "__nexa_runner.py").write_text(MINI_RUNNER, encoding="utf-8")
        (root / BUILD_DIR).mkdir(exist_ok=True)
        for path, text in plan.files.items():
            Path(path).write_text(text, encoding="utf-8")
        return root, plan, note
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise


def shown_steps(plan: RunPlan, root: Path) -> list[str]:
    """Lệnh để hiện cho anh xem: tên chương trình, bỏ đường dẫn thư mục tạm."""
    return [shown_command(c).replace(str(root) + os.sep, "").replace(str(root), ".") for c in plan.steps]


def run_project(files: list[CodeFile], python: list[str] | None, timeout_s: float = 30.0,
                cancelled=lambda: False) -> RunReport:
    shown = ""
    root = Path(tempfile.mkdtemp(prefix="nexa_code_run_"))
    try:
        root, plan, note = prepare_project(files, python, root)
        if plan is None:
            return RunReport(False, "", None, "", 0.0, note=note)
        shown = " && ".join(shown_command(c) for c in plan.steps)
        env = run_env()
        t0 = time.monotonic()
        outputs: list[str] = []
        code: int | None = 0
        timed_out = False
        extra_note = plan.note
        for i, step in enumerate(plan.steps):
            last = i == len(plan.steps) - 1
            limit = timeout_s + plan.extra_s if last else BUILD_TIMEOUT_S
            code, raw, timed_out = _run_step(step, root, env, limit, cancelled)
            text = decode_output(raw).replace("\r\n", "\n").strip()
            if len(plan.steps) > 1:
                outputs.append(f"$ {shown_command(step)}" + (f"\n{text}" if text else ""))
            elif text:
                outputs.append(text)
            if timed_out or cancelled() or code != 0:
                if not last and code not in (0, None) and not timed_out:
                    extra_note = "Biên dịch lỗi — chưa chạy chương trình." + (f" {plan.note}" if plan.note else "")
                break
        secs = time.monotonic() - t0
        out = "\n".join(outputs)
        out = out.replace(str(root) + os.sep, "").replace(str(root), ".")
        shown = shown.replace(str(root) + os.sep, "").replace(str(root), ".")
        if len(out) > MAX_OUTPUT:
            out = out[:MAX_OUTPUT // 3] + "\n…(lược bớt)…\n" + out[-MAX_OUTPUT * 2 // 3:]
        note = extra_note
        if timed_out:
            note = f"Dừng sau {timeout_s:.0f} s (chương trình chưa tự kết thúc — có thể là server/vòng lặp chờ)."
        elif cancelled():
            note = "Anh đã hủy lần chạy."
        return RunReport(code == 0 and not timed_out and not cancelled(), shown, code, out.strip(), round(secs, 2),
                         timed_out, note)
    except OSError as exc:
        return RunReport(False, shown, None, str(exc), 0.0, note="Không chạy được lệnh.")
    finally:
        shutil.rmtree(root, ignore_errors=True)
