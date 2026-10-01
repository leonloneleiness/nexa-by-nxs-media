"""Chạy thử mọi ngôn ngữ: tìm trình biên dịch/thông dịch trên máy và lập kế hoạch chạy (các bước build rồi chạy).

plan_file() trả về RunPlan (các lệnh chạy lần lượt trong thư mục `root`; mọi bước trừ bước cuối là build) hoặc một
câu tiếng Việt giải thích vì sao chưa chạy được (máy thiếu công cụ nào, cài bằng lệnh gì).
Dùng chung cho chạy thử code do Gemini viết (thư mục tạm, checks.run_project) và chạy tệp trên đĩa (console_run).

Tìm công cụ: PATH trước, rồi các thư mục cài đặt quen thuộc trên Windows (Git, MSYS2/MinGW, LLVM, Go, Rust, JDK,
XAMPP, Ruby, R, Julia…) vì nhiều bộ cài không thêm vào PATH. Bỏ qua lối tắt Microsoft Store của python và bash.exe của
WSL trong System32 (không phải Git Bash, chạy trong Linux).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from nexa.code.models import LANG_LABEL, lang_for_path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class RunPlan:
    steps: list[list[str]]                 # lệnh lần lượt; mọi bước trừ bước cuối là build
    label: str                             # "Chạy main.cpp (g++)"
    lang: str = ""
    note: str = ""                         # lưu ý thêm (C# 5 của .NET Framework…)
    open_path: str = ""                    # HTML/SVG: mở bằng trình duyệt thay vì chạy lệnh
    extra_s: float = 0.0                   # bước cuối tự biên dịch (dotnet run, go run…) → cho thêm thời gian
    files: dict[str, str] = field(default_factory=dict)   # tệp phụ phải ghi trước khi chạy (đường dẫn → nội dung)

    @property
    def build_steps(self) -> list[list[str]]:
        return self.steps[:-1]


# ------------------------------------------------------------------ tìm công cụ
def _env_dir(name: str, *sub: str) -> list[Path]:
    v = os.environ.get(name, "")
    return [Path(v, *sub)] if v else []


@lru_cache(maxsize=1)
def extra_dirs() -> tuple[Path, ...]:
    pf = [Path(os.environ.get(k, "")) for k in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432") if os.environ.get(k)]
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" if os.environ.get("LOCALAPPDATA") else None
    home = Path.home()
    drive = Path(os.environ.get("SystemDrive", "C:") + "\\")
    bases = [*pf, *([local] if local else [])]
    patterns = ["Git/bin", "Git/usr/bin", "Go/bin", "nodejs", "dotnet", "PowerShell/7", "LLVM/bin",
                "Java/jdk*/bin", "Eclipse Adoptium/jdk*/bin", "Microsoft/jdk*/bin", "Zulu/zulu*/bin",
                "Amazon Corretto/jdk*/bin", "BellSoft/LibericaJDK*/bin", "R/R-*/bin", "Julia*/bin", "Elixir/bin",
                "erl*/bin", "Haskell Platform/*/bin", "Kotlin/bin", "Dart/dart-sdk/bin", "Swift/Toolchains/*/usr/bin",
                "Lua/*", "Lua", "Ruby*/bin", "PHP*", "Zig*", "WinLibs/mingw64/bin"]
    dirs: list[Path] = [*_env_dir("JAVA_HOME", "bin"), *_env_dir("GOROOT", "bin"), *_env_dir("CARGO_HOME", "bin")]
    for base in bases:
        for pat in patterns:
            dirs += sorted(base.glob(pat), reverse=True)          # jdk-21 trước jdk-17
    for pat in ["msys64/ucrt64/bin", "msys64/mingw64/bin", "msys64/clang64/bin", "MinGW/bin", "mingw64/bin",
                "TDM-GCC-64/bin", "xampp/php", "php", "tools/php*", "Ruby*/bin", "Strawberry/perl/bin", "zig*",
                "ProgramData/chocolatey/bin", "tools/*/bin", "ghcup/bin"]:
        dirs += sorted(drive.glob(pat), reverse=True)
    dirs += [home / ".cargo" / "bin", home / ".bun" / "bin", home / ".deno" / "bin", home / "scoop" / "shims",
             home / ".dotnet", home / "ghcup" / "bin", home / "AppData" / "Roaming" / "npm"]
    seen: list[Path] = []
    for d in dirs:
        if d not in seen and d.is_dir():
            seen.append(d)
    return tuple(seen)


def _bad(path: str) -> bool:
    low = path.lower().replace("/", "\\")
    return "\\windowsapps\\" in low or low.endswith("\\system32\\bash.exe")


@lru_cache(maxsize=128)
def find_tool(*names: str) -> str:
    """Đường dẫn công cụ đầu tiên tìm thấy trong `names` ("" nếu không có)."""
    for name in names:
        hit = shutil.which(name)
        if hit and not _bad(hit):
            return hit
        for d in extra_dirs():
            for ext in (".exe", ".cmd", ".bat", ""):
                p = d / f"{name}{ext}"
                if p.is_file() and not _bad(str(p)):
                    return str(p)
    return ""


def find_bash() -> str:
    for base in [os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", "")]:
        p = Path(base, "Git", "bin", "bash.exe") if base else None
        if p and p.is_file():
            return str(p)
    return find_tool("bash")


def _version_out(cmd: list[str]) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=15, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return ""
    return (p.stdout + p.stderr).decode("utf-8", "replace")


@lru_cache(maxsize=4)
def node_major(node: str) -> tuple[int, int]:
    m = re.search(r"v(\d+)\.(\d+)", _version_out([node, "--version"]))
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


@lru_cache(maxsize=2)
def dotnet_sdk_major(dotnet: str) -> int:
    majors = [int(m) for m in re.findall(r"^(\d+)\.\d+\.\d+", _version_out([dotnet, "--list-sdks"]), re.M)]
    return max(majors) if majors else 0


def framework_csc() -> str:
    windir = os.environ.get("WINDIR", r"C:\Windows")
    for fw in ("Framework64", "Framework"):
        p = Path(windir, "Microsoft.NET", fw, "v4.0.30319", "csc.exe")
        if p.is_file():
            return str(p)
    return ""


def project_python(folder: Path) -> list[str] | None:
    """Python của môi trường ảo trong dự án (.venv/venv/env), tìm ngược lên tối đa 4 cấp."""
    for d in [folder, *list(folder.parents)[:4]]:
        for name in (".venv", "venv", "env"):
            exe = d / name / "Scripts" / "python.exe"
            if exe.is_file():
                return [str(exe)]
    return None


# ------------------------------------------------------------------ thiếu công cụ
INSTALL = {
    "java": ("JDK (javac)", "EclipseAdoptium.Temurin.21.JDK"),
    "c": ("trình biên dịch C (gcc/clang)", "BrechtSanders.WinLibs.POSIX.UCRT"),
    "cpp": ("trình biên dịch C++ (g++/clang++)", "BrechtSanders.WinLibs.POSIX.UCRT"),
    "go": ("Go", "GoLang.Go"),
    "rust": ("Rust (rustc/cargo)", "Rustlang.Rustup"),
    "javascript": ("Node.js", "OpenJS.NodeJS.LTS"),
    "typescript": ("Node.js ≥ 22.6 (hoặc tsx/bun/deno)", "OpenJS.NodeJS.LTS"),
    "csharp": (".NET SDK", "Microsoft.DotNet.SDK.8"),
    "fsharp": (".NET SDK", "Microsoft.DotNet.SDK.8"),
    "php": ("PHP", ""), "ruby": ("Ruby", "RubyInstallerTeam.Ruby.3.3"), "perl": ("Perl", "StrawberryPerl.StrawberryPerl"),
    "lua": ("Lua", ""), "r": ("R (Rscript)", "RProject.R"), "julia": ("Julia", ""), "haskell": ("GHC (runghc)", ""),
    "elixir": ("Elixir", ""), "zig": ("Zig", ""), "groovy": ("Groovy", ""), "scala": ("Scala (scala-cli)", ""),
    "dart": ("Dart SDK", ""), "swift": ("Swift", ""), "kotlin": ("Kotlin (kotlinc) + JDK", ""),
    "bash": ("Git Bash", "Git.Git"), "python": ("Python", "Python.Python.3.12"), "sql": ("Python (để chạy SQLite)", ""),
}


def missing(lang: str) -> str:
    what, wid = INSTALL.get(lang, (LANG_LABEL.get(lang, lang), ""))
    msg = f"Máy chưa có {what} nên em chưa chạy thử {LANG_LABEL.get(lang, lang)} được."
    if wid:
        msg += f" Anh cài bằng: winget install --id {wid} -e (rồi khởi động lại NEXA)."
    if lang == "java" and shutil.which("java"):
        msg += " (Máy đang có Java nhưng chỉ là bản chạy JRE, không có javac để biên dịch.)"
    return msg


# ------------------------------------------------------------------ SQL: chạy bằng SQLite trong bộ nhớ
SQL_RUNNER = r'''
import sqlite3, sys
sql = open(sys.argv[1], encoding="utf-8-sig").read()
con = sqlite3.connect(":memory:")
buf, n = "", 0
for line in sql.splitlines(True):
    buf += line
    if not sqlite3.complete_statement(buf):
        continue
    stmt, buf = buf.strip(), ""
    if not stmt.rstrip(";").strip():
        continue
    n += 1
    try:
        cur = con.execute(stmt)
    except sqlite3.Error as e:
        print(f"LỖI ở câu lệnh {n}: {e}\n    {stmt[:300]}")
        sys.exit(1)
    if cur.description:
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        head = " | ".join(cols)
        print(head)
        print("-" * max(3, len(head)))
        for r in rows[:200]:
            print(" | ".join("NULL" if v is None else str(v) for v in r))
        print(f"({len(rows)} dòng)\n")
if buf.strip():
    print("Cảnh báo: câu lệnh cuối thiếu dấu ';' nên không chạy.")
con.commit()
print(f"Đã chạy {n} câu lệnh trên SQLite (cơ sở dữ liệu tạm trong bộ nhớ).")
'''

CS_PROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net{major}.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>disable</Nullable>
    <LangVersion>latest</LangVersion>
    <EnableDefaultCompileItems>false</EnableDefaultCompileItems>
    <RootNamespace>NexaRun</RootNamespace>
  </PropertyGroup>
  <ItemGroup>
{items}
  </ItemGroup>
</Project>
"""

CPP_EXTS = (".cpp", ".cc", ".cxx", ".c++")
MAIN_MARKERS = {
    "c": r"\bint\s+main\s*\(|\bvoid\s+main\s*\(",
    "cpp": r"\bint\s+main\s*\(",
    "java": r"\bstatic\s+void\s+main\s*\(",
    "csharp": r"\bstatic\s+(?:async\s+)?(?:void|int|Task(?:<int>)?)\s+Main\s*\(",
    "go": r"\bfunc\s+main\s*\(",
    "rust": r"\bfn\s+main\s*\(",
    "kotlin": r"\bfun\s+main\s*\(",
    "scala": r"\bdef\s+main\s*\(|extends\s+App\b|@main\b",
    "dart": r"\bvoid\s+main\s*\(|^main\s*\(",
    "swift": r"@main\b",
}


def has_main(lang: str, text: str) -> bool:
    pat = MAIN_MARKERS.get(lang)
    return bool(pat and re.search(pat, text, re.M))


def _read(root: Path, rel: str) -> str:
    try:
        return (root / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _q(p: Path | str) -> str:
    return str(p)


def plan_file(entry: str, root: Path, out: Path, python: list[str] | None = None,
              sources: list[str] | None = None, lang: str = "") -> RunPlan | str:
    """Kế hoạch chạy tệp `entry` (tương đối với `root`, thư mục làm việc). `out` = thư mục cho tệp biên dịch ra.
    `sources` = các tệp cùng ngôn ngữ cần biên dịch chung (C/C++/C#/Java); None = tự lấy các tệp cạnh bên."""
    lang = lang or lang_for_path(entry)
    name = Path(entry).name
    stem = Path(entry).stem
    ext = Path(entry).suffix.lower()
    exe = out / f"{re.sub(r'[^A-Za-z0-9_-]', '_', stem) or 'app'}.exe"
    label = LANG_LABEL.get(lang, lang)

    def simple(tool: str, *args: str, pre: tuple[str, ...] = (), extra: float = 0.0, note: str = "") -> RunPlan:
        return RunPlan([[tool, *pre, *args]], f"Chạy {name} ({Path(tool).stem})", lang, note, extra_s=extra)

    if lang == "python":
        py = project_python((root / entry).parent) or python
        if not py:
            return missing("python")
        return RunPlan([[*py, entry]], f"Chạy {name} (Python)", lang)

    if lang == "javascript":
        if ext == ".jsx":
            return "Tệp JSX cần bộ đóng gói (Vite/webpack) để chạy — em chưa chạy trực tiếp được."
        node = find_tool("node")
        return simple(node, entry) if node else missing(lang)

    if lang == "typescript":
        tsx = find_tool("tsx")
        if tsx:
            return simple(tsx, entry)
        bun = find_tool("bun")
        if bun:
            return simple(bun, "run", entry)
        deno = find_tool("deno")
        if deno:
            return simple(deno, "run", "-A", entry)
        node = find_tool("node")
        if node and ext == ".ts" and node_major(node) >= (22, 6):
            return RunPlan([[node, "--experimental-strip-types", "--no-warnings", entry]], f"Chạy {name} (node)", lang,
                           "Node chỉ bỏ kiểu dữ liệu, không kiểm tra kiểu như tsc.")
        return missing(lang)

    if lang in ("c", "cpp"):
        if ext in (".h", ".hpp"):
            return "Đây là tệp tiêu đề (header) — anh chạy tệp .c/.cpp có hàm main nhé."
        want = CPP_EXTS if lang == "cpp" else (".c",)
        srcs = sources if sources is not None else _siblings(root, entry, want, lang)
        srcs = [s for s in srcs if Path(s).suffix.lower() in want] or [entry]
        if lang == "cpp":
            cc = find_tool("g++", "clang++")
            flags = ["-std=c++17"]
        else:
            cc = find_tool("gcc", "clang")
            flags = []
        if cc:
            link = ["-lm"] if lang == "c" else []
            return RunPlan([[cc, *flags, "-O1", "-o", _q(exe), *srcs, *link], [_q(exe)]],
                           f"Biên dịch và chạy {name} ({Path(cc).stem})", lang)
        cl = find_tool("cl")
        if cl:
            return RunPlan([[cl, "/nologo", "/EHsc", "/utf-8", *srcs, f"/Fe{exe}", f"/Fo{out}\\"], [_q(exe)]],
                           f"Biên dịch và chạy {name} (MSVC)", lang)
        return missing(lang)

    if lang == "java":
        javac = find_tool("javac")
        if not javac:
            return missing(lang)
        java = str(Path(javac).with_name("java.exe")) if Path(javac).with_name("java.exe").is_file() else find_tool("java")
        text = _read(root, entry)
        pkg = re.search(r"^\s*package\s+([\w.]+)\s*;", text, re.M)
        main_cls = (pkg.group(1) + "." if pkg else "") + stem
        if sources is not None:
            compile_args = sources
        else:
            src_root = Path(entry).parent
            for _ in (pkg.group(1).split(".") if pkg else []):
                src_root = src_root.parent
            compile_args = ["-sourcepath", str(src_root) if str(src_root) != "" else ".", entry]
        return RunPlan([[javac, "-encoding", "UTF-8", "-d", _q(out), *compile_args],
                        [java, "-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8", "-cp", _q(out), main_cls]],
                       f"Biên dịch và chạy {name} (javac)", lang)

    if lang == "csharp":
        dotnet = find_tool("dotnet")
        major = dotnet_sdk_major(dotnet) if dotnet else 0
        proj = _find_up(root / entry, "*.csproj") if sources is None else None
        if major and proj:
            return RunPlan([[dotnet, "run", "--project", str(proj)]], f"Chạy dự án {proj.name} (dotnet run)", lang,
                           extra_s=90)
        srcs = sources if sources is not None else _siblings(root, entry, (".cs",), lang)
        if major >= 5:
            items = "\n".join(f'    <Compile Include="{(root / s).resolve()}" />' for s in srcs)
            csproj = out / "NexaRun.csproj"
            return RunPlan([[dotnet, "run", "--project", _q(csproj)]], f"Chạy {name} (dotnet run, .NET {major})", lang,
                           extra_s=90, files={_q(csproj): CS_PROJ.format(major=major, items=items)})
        csc = framework_csc()
        if csc:
            return RunPlan([[csc, "/nologo", "/utf8output", f"/out:{exe}", *srcs], [_q(exe)]],
                           f"Biên dịch và chạy {name} (csc .NET Framework)", lang,
                           "Máy chưa có .NET SDK nên dùng csc của .NET Framework — chỉ hỗ trợ C# 5 (không có "
                           "top-level statements, $\"...\", =>…). Cài .NET SDK: winget install --id Microsoft.DotNet.SDK.8 -e")
        return missing(lang)

    if lang == "go":
        go = find_tool("go")
        if not go:
            return missing(lang)
        if name.endswith("_test.go"):
            return RunPlan([[go, "test", "./..."]], "Chạy kiểm thử Go (go test)", lang, extra_s=60)
        if _find_up(root / entry, "go.mod", 3):
            parent = Path(entry).parent
            target = [str(parent) if parent.is_absolute() else "./" + parent.as_posix()]
        else:
            target = sources if sources is not None else [
                s for s in _siblings(root, entry, (".go",), lang) if not s.endswith("_test.go")]
        return RunPlan([[go, "run", *target]], f"Chạy {name} (go run)", lang, extra_s=60)

    if lang == "rust":
        cargo_toml = _find_up(root / entry, "Cargo.toml", 3)
        cargo = find_tool("cargo")
        if cargo_toml and cargo:
            return RunPlan([[cargo, "run", "-q", "--manifest-path", str(cargo_toml)]], "Chạy dự án Rust (cargo run)",
                           lang, extra_s=120)
        rustc = find_tool("rustc")
        if not rustc:
            return missing(lang)
        return RunPlan([[rustc, "--edition", "2021", "-o", _q(exe), entry], [_q(exe)]],
                       f"Biên dịch và chạy {name} (rustc)", lang)

    if lang == "kotlin":
        kotlinc = find_tool("kotlinc")
        if not kotlinc:
            return missing(lang)
        if ext == ".kts":
            return simple(kotlinc, "-script", entry, extra=60)
        jar = out / f"{stem}.jar"
        java = find_tool("java")
        return RunPlan([[kotlinc, entry, "-include-runtime", "-d", _q(jar)], [java or "java", "-jar", _q(jar)]],
                       f"Biên dịch và chạy {name} (kotlinc)", lang)

    if lang == "powershell":
        ps = find_tool("pwsh", "powershell")
        if not ps:
            return missing(lang)
        # -Command thay vì -File để ép UTF-8 cho đầu ra (PowerShell mặc định in theo bảng mã OEM)
        target = (entry if Path(entry).is_absolute() else ".\\" + entry).replace("'", "''")
        return RunPlan([[ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                         f"[Console]::OutputEncoding=[Text.Encoding]::UTF8; & '{target}'; "
                         "if ($LASTEXITCODE) { exit $LASTEXITCODE } elseif ($Error.Count) { exit 1 }"]],
                       f"Chạy {name} ({Path(ps).stem})", lang)

    if lang == "bash":
        bash = find_bash()
        return simple(bash, entry.replace("\\", "/")) if bash else missing(lang)

    if lang == "batch":
        return RunPlan([[os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str((root / entry).resolve())]],
                       f"Chạy {name} (cmd)", lang)

    if lang == "sql":
        if not python:
            return missing(lang)
        return RunPlan([[*python, "-X", "utf8", "-c", SQL_RUNNER, entry]], f"Chạy {name} trên SQLite tạm", lang,
                       "SQL chạy trên SQLite trong bộ nhớ — cú pháp riêng của MySQL/SQL Server có thể không chạy.")

    if lang in ("html", "svg") or ext == ".svg":
        return RunPlan([], f"Mở {name} trong trình duyệt", lang, open_path=str((root / entry).resolve()))

    table: dict[str, tuple[tuple[str, ...], tuple[str, ...], float]] = {
        # ngôn ngữ: (tên công cụ, tham số trước tệp, thêm thời gian)
        "php": (("php",), (), 0), "ruby": (("ruby",), (), 0), "perl": (("perl",), (), 0),
        "lua": (("lua", "lua54", "lua5.4", "luajit"), (), 0), "r": (("Rscript",), (), 0),
        "julia": (("julia",), (), 30), "haskell": (("runghc", "runhaskell"), (), 30), "elixir": (("elixir",), (), 20),
        "zig": (("zig",), ("run",), 60), "groovy": (("groovy",), (), 20), "dart": (("dart",), ("run",), 30),
        "swift": (("swift",), (), 60), "scala": (("scala-cli", "scala"), (), 60),
        "vbscript": (("cscript",), ("//nologo",), 0),
    }
    if lang == "fsharp":
        dotnet = find_tool("dotnet")
        if not (dotnet and dotnet_sdk_major(dotnet)):
            return missing(lang)
        return simple(dotnet, entry, pre=("fsi",), extra=60)
    if lang in table:
        names, pre, extra = table[lang]
        tool = find_tool(*names)
        if not tool:
            return missing(lang)
        if lang == "scala" and Path(tool).stem == "scala-cli":
            pre = ("run",)
        return simple(tool, entry, pre=pre, extra=extra)

    if lang in ("markdown", "text", "json", "yaml", "toml", "xml", "ini", "css", "scss"):
        return f"{name} là tệp {label} — không phải chương trình để chạy."
    return f"Em chưa biết cách chạy tệp {name} ({label})."


def _find_up(start: Path, pattern: str, levels: int = 4) -> Path | None:
    for d in list(start.parents)[:levels]:
        hits = sorted(d.glob(pattern))
        if hits:
            return hits[0]
    return None


def _siblings(root: Path, entry: str, exts: tuple[str, ...], lang: str) -> list[str]:
    """Tệp cùng ngôn ngữ cạnh `entry` (biên dịch chung), bỏ các tệp có hàm main khác."""
    folder = (root / entry).parent
    out = [entry]
    try:
        for p in sorted(folder.iterdir()):
            if p.suffix.lower() not in exts or p.name == Path(entry).name or not p.is_file():
                continue
            text = _read(folder, p.name)
            if has_main(lang, text) or (lang == "csharp" and _top_level_cs(text)):
                continue
            out.append(str(Path(entry).parent / p.name) if str(Path(entry).parent) != "." else p.name)
    except OSError:
        pass
    return out[:60]


def _top_level_cs(text: str) -> bool:
    """Tệp C# viết kiểu top-level statements (không có namespace/class ở đầu) — cũng là một điểm vào."""
    body = re.sub(r"//.*|/\*.*?\*/", "", text, flags=re.S)
    body = re.sub(r"^\s*(?:using\s+[^;]+;\s*)*", "", body)
    return bool(body.strip()) and not re.match(
        r"\s*(?:\[[^\]]*\]\s*)*(?:namespace|(?:public|internal|static|sealed|abstract|partial|file|\s)*"
        r"(?:class|struct|record|interface|enum))\b", body)
