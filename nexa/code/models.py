"""Kiểu dữ liệu của tính năng sinh code: tệp, kết quả kiểm tra, bản code hoàn chỉnh (lưu được ra JSON)."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath
from typing import Any

# phần mở rộng → ngôn ngữ (tên chuẩn dùng cho kiểm tra, tô màu và chú thích)
EXT_LANG = {
    ".py": "python", ".pyw": "python", ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript", ".java": "java", ".cs": "csharp",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".h": "c", ".c": "c", ".go": "go", ".rs": "rust",
    ".php": "php", ".rb": "ruby", ".kt": "kotlin", ".swift": "swift", ".sql": "sql", ".ps1": "powershell",
    ".psm1": "powershell", ".sh": "bash", ".bat": "batch", ".cmd": "batch", ".html": "html", ".htm": "html",
    ".css": "css", ".scss": "scss", ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".xml": "xml", ".md": "markdown", ".dockerfile": "docker", ".vue": "vue", ".dart": "dart", ".txt": "text",
    ".ini": "ini", ".env": "text", ".pl": "perl", ".pm": "perl", ".lua": "lua", ".r": "r", ".jl": "julia",
    ".hs": "haskell", ".ex": "elixir", ".exs": "elixir", ".fsx": "fsharp", ".fs": "fsharp", ".vbs": "vbscript",
    ".zig": "zig", ".groovy": "groovy", ".kts": "kotlin", ".scala": "scala", ".sc": "scala", ".svg": "svg",
}
LANG_ALIASES = {
    "py": "python", "python3": "python", "js": "javascript", "node": "javascript", "nodejs": "javascript",
    "ts": "typescript", "c#": "csharp", "cs": "csharp", "dotnet": "csharp", "c++": "cpp", "golang": "go",
    "ps": "powershell", "ps1": "powershell", "pwsh": "powershell", "sh": "bash", "shell": "bash", "yml": "yaml",
    "htm": "html", "dockerfile": "docker", "tsx": "typescript", "jsx": "javascript", "auto": "",
}
LANG_LABEL = {
    "python": "Python", "javascript": "JavaScript", "typescript": "TypeScript", "java": "Java", "csharp": "C#",
    "cpp": "C++", "c": "C", "go": "Go", "rust": "Rust", "php": "PHP", "ruby": "Ruby", "kotlin": "Kotlin",
    "swift": "Swift", "sql": "SQL", "powershell": "PowerShell", "bash": "Bash", "batch": "Batch", "html": "HTML",
    "css": "CSS", "scss": "SCSS", "json": "JSON", "yaml": "YAML", "toml": "TOML", "xml": "XML",
    "markdown": "Markdown", "docker": "Dockerfile", "vue": "Vue", "dart": "Dart", "text": "Văn bản", "ini": "INI",
    "perl": "Perl", "lua": "Lua", "r": "R", "julia": "Julia", "haskell": "Haskell", "elixir": "Elixir",
    "fsharp": "F#", "vbscript": "VBScript", "zig": "Zig", "groovy": "Groovy", "scala": "Scala", "svg": "SVG",
}
# tiền tố chú thích một dòng (dùng khi "sao chép tất cả" ghép nhiều tệp)
COMMENT = {
    "python": "#", "bash": "#", "powershell": "#", "yaml": "#", "toml": "#", "ruby": "#", "docker": "#", "perl": "#", "r": "#", "julia": "#", "elixir": "#",
    "lua": "--", "haskell": "--", "vbscript": "'", "ini": ";",
    "sql": "--", "batch": "REM", "text": "#", "markdown": "<!--", "html": "<!--", "xml": "<!--", "vue": "<!--",
    "css": "/*", "scss": "//",
}


def norm_lang(name: str) -> str:
    s = (name or "").strip().lower()
    return LANG_ALIASES.get(s, s)


def lang_for_path(path: str, fallback: str = "") -> str:
    p = PurePosixPath(path.lower())
    if p.name == "dockerfile":
        return "docker"
    if p.name in ("makefile",):
        return "text"
    return EXT_LANG.get(p.suffix, norm_lang(fallback) or "text")


def comment_line(lang: str, text: str) -> str:
    pre = COMMENT.get(lang, "//")
    if pre == "<!--":
        return f"<!-- {text} -->"
    if pre == "/*":
        return f"/* {text} */"
    return f"{pre} {text}"


_BAD_PART = re.compile(r'[<>:"|?*\x00-\x1f]')


def safe_rel_path(path: str, index: int = 0) -> str:
    """Đường dẫn tương đối an toàn (không tuyệt đối, không '..', không ký tự cấm của Windows)."""
    raw = (path or "").replace("\\", "/").strip().lstrip("/")
    parts = [_BAD_PART.sub("_", p).strip(" .") for p in raw.split("/")]
    parts = [p for p in parts if p and p not in (".", "..")]
    if parts and re.fullmatch(r"[A-Za-z]_?", parts[0]) and len(parts) > 1:   # "C:/..." → bỏ ổ đĩa
        parts = parts[1:]
    return "/".join(parts)[:180] or f"file_{index + 1}.txt"


@dataclass
class CodeFile:
    path: str
    language: str
    content: str

    @property
    def lines(self) -> int:
        return self.content.count("\n") + (0 if self.content.endswith("\n") or not self.content else 1)


@dataclass
class FileCheck:
    path: str
    status: str = "skipped"          # ok | warning | error | skipped
    tool: str = ""                   # tên công cụ kiểm tra (ast+pyflakes, node --check…)
    messages: list[str] = field(default_factory=list)


@dataclass
class RunReport:
    ok: bool
    command: str
    exit_code: int | None
    output: str
    seconds: float
    timed_out: bool = False
    note: str = ""


@dataclass
class CodeResult:
    id: str
    prompt: str
    title: str
    language: str
    summary: str
    files: list[CodeFile]
    run_instructions: str = ""
    dependencies: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    checks: list[FileCheck] = field(default_factory=list)
    missing_packages: list[str] = field(default_factory=list)
    run: RunReport | None = None
    created: float = 0.0
    model: str = ""
    rounds: int = 1                  # số lượt Gemini (viết + sửa)
    parent: str = ""                 # bản gốc khi đây là bản chỉnh sửa

    @property
    def check_status(self) -> str:
        st = {c.status for c in self.checks}
        if "error" in st:
            return "error"
        if "warning" in st:
            return "warning"
        if "ok" in st:
            return "ok"
        return "skipped"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CodeResult":
        d = dict(d)
        d["files"] = [CodeFile(**f) for f in d.get("files") or []]
        d["checks"] = [FileCheck(**c) for c in d.get("checks") or []]
        d["run"] = RunReport(**d["run"]) if d.get("run") else None
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in known})
