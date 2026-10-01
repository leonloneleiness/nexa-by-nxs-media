"""Tô màu cú pháp bằng Pygments (theme One Dark) → HTML inline-style mà Qt rich text hiển thị được."""
from __future__ import annotations

import html

from nexa.utils.logging import get_logger

log = get_logger("code.highlight")

BG = "#282c34"
FG = "#abb2bf"
GUTTER_FG = "#5c6370"
STYLE = "one-dark"
FONT = "Consolas, 'Cascadia Mono', 'Courier New', monospace"
MAX_HIGHLIGHT_CHARS = 300_000      # tệp quá lớn: hiện chữ trơn cho nhanh

# tên chuẩn của NEXA → lexer Pygments
LEXER = {
    "python": "python", "javascript": "javascript", "typescript": "typescript", "java": "java", "csharp": "csharp",
    "cpp": "cpp", "c": "c", "go": "go", "rust": "rust", "php": "php", "ruby": "ruby", "kotlin": "kotlin",
    "swift": "swift", "sql": "sql", "powershell": "powershell", "bash": "bash", "batch": "batch", "html": "html",
    "css": "css", "scss": "scss", "json": "json", "yaml": "yaml", "toml": "toml", "xml": "xml",
    "markdown": "markdown", "docker": "docker", "vue": "html", "dart": "dart", "ini": "ini", "text": "text",
}


def _pre(body: str) -> str:
    # white-space:pre giữ nguyên thụt lề; màu nền do QML vẽ, ở đây chỉ đặt màu chữ mặc định
    return f'<pre style="margin:0; color:{FG}; font-family:{FONT}; white-space:pre">{body}</pre>'


def highlight_html(code: str, lang: str) -> str:
    if not code:
        return _pre("")
    body = ""
    if len(code) <= MAX_HIGHLIGHT_CHARS:
        try:
            from pygments import highlight
            from pygments.formatters import HtmlFormatter
            from pygments.lexers import get_lexer_by_name
            from pygments.util import ClassNotFound
            try:
                lexer = get_lexer_by_name(LEXER.get(lang, lang or "text"), stripnl=False, ensurenl=False)
            except ClassNotFound:
                lexer = get_lexer_by_name("text", stripnl=False, ensurenl=False)
            fmt = HtmlFormatter(noclasses=True, nowrap=True, style=STYLE)
            body = highlight(code, lexer, fmt)
        except Exception:                  # thiếu Pygments/theme: vẫn hiện chữ trơn
            log.exception("Không tô màu được (%s)", lang)
            body = ""
    if not body:
        body = html.escape(code)
    return _pre(body.rstrip("\n"))


def gutter_html(line_count: int) -> str:
    """Cột số dòng cùng kiểu <pre> với phần code để các dòng thẳng hàng."""
    n = max(1, line_count)
    width = len(str(n))
    nums = "\n".join(str(i).rjust(width) for i in range(1, n + 1))
    return f'<pre style="margin:0; color:{GUTTER_FG}; font-family:{FONT}; white-space:pre">{nums}</pre>'
