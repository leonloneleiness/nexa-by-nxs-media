"""Chạy chương trình NGAY TRONG NEXA: đầu ra hiện trực tiếp (từng dòng, tô màu) trên bảng Sinh code.

LiveRun chạy lần lượt các bước (build rồi chạy) bằng ống dẫn — không mở cửa sổ console nào. stdout/stderr đọc ở hai
luồng riêng; dòng chưa xuống hàng (lời nhắc kiểu "Nhập tên: ") vẫn hiện ngay; \r (thanh tiến độ) ghi đè dòng hiện tại.
Anh gõ vào ô nhập của NEXA → gửi vào stdin của chương trình. Dừng = diệt cả cây tiến trình.
on_change() được gọi tối đa ~10 lần/giây (luồng nền) để UI vẽ lại.
"""
from __future__ import annotations

import html
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
MAX_LINES = 4000
SHOW_LINES = 1500                  # số dòng cuối vẽ lên bảng (đầu ra rất dài vẫn mượt)
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")

# trạng thái cuối
RUNNING, OK, FAILED, BUILD_FAILED, TIMEOUT, STOPPED, NO_TESTS, PREVIEW = (
    "running", "ok", "failed", "build_failed", "timeout", "stopped", "no_tests", "preview")
STATE_LABEL = {RUNNING: "Đang chạy", OK: "Đạt", FAILED: "Lỗi", BUILD_FAILED: "Biên dịch lỗi", TIMEOUT: "Quá giờ",
               STOPPED: "Đã dừng", NO_TESTS: "Không có kiểm thử", PREVIEW: "Xem trang"}

COLORS = {"cmd": "#22d3ee", "out": "#d6e2f0", "err": "#fca5a5", "in": "#fde68a", "info": "#8fb3d1",
          "ok": "#34d399", "fail": "#fb7185", "warn": "#fbbf24", "dim": "#5b7a99"}
PASS_LINE = re.compile(r"^\s*(✔|✓|ok\b|PASS\b|--- PASS|ĐẠT\b|passed\b)|\b\d+ passed\b(?!.*failed)|^test result: ok",
                       re.I)
FAIL_LINE = re.compile(r"^\s*(✖|✗|×|not ok\b|FAIL|--- FAIL|TRƯỢT\b|LỖI\b|E\s{2,}|FAILED\b)|Traceback \(most recent|"
                       r"\b(\w*Error|Exception|panic)\b[:!]|\berror(\[E\d+\])?:|\bfatal error\b|\d+ failed\b|"
                       r"^test result: FAILED", re.I)
WARN_LINE = re.compile(r"\bwarning\b|\bcảnh báo\b|DeprecationWarning", re.I)


def line_kind(kind: str, text: str) -> str:
    """Màu cho một dòng: stderr luôn đỏ nhạt, trừ khi là dòng báo ĐẠT (pytest/node in ra stderr cũng có)."""
    if kind in ("out", "err"):
        if FAIL_LINE.search(text):
            return "fail"
        if PASS_LINE.search(text):
            return "ok"
        if WARN_LINE.search(text):
            return "warn"
    return kind


def test_summary(text: str) -> dict | None:
    """Đếm kiểm thử từ đầu ra pytest / node --test / bộ chạy của NEXA / go test -v / cargo test. None = không phải kiểm thử."""
    t = text
    m = re.search(r"^ℹ tests (\d+)$", t, re.M)
    if m:
        p = re.search(r"^ℹ pass (\d+)$", t, re.M)
        f = re.search(r"^ℹ fail (\d+)$", t, re.M)
        return {"total": int(m.group(1)), "passed": int(p.group(1)) if p else 0, "failed": int(f.group(1)) if f else 0}
    m = re.search(r"^(\d+) đạt, (\d+) trượt$", t, re.M)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return {"total": a + b, "passed": a, "failed": b}
    m = re.search(r"^test result: \w+\. (\d+) passed; (\d+) failed", t, re.M)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return {"total": a + b, "passed": a, "failed": b}
    last = [ln for ln in t.splitlines() if re.search(r"\b(passed|failed|errors?|no tests ran)\b", ln)]
    if last and re.search(r"(=+ .* =+|^\d+ (passed|failed)|no tests ran)", last[-1]):
        ln = last[-1]
        get = lambda k: int(m.group(1)) if (m := re.search(rf"(\d+) {k}", ln)) else 0  # noqa: E731
        a, b = get("passed"), get("failed") + get("errors?")
        return {"total": a + b, "passed": a, "failed": b}
    passes, fails = len(re.findall(r"^\s*--- PASS", t, re.M)), len(re.findall(r"^\s*--- FAIL", t, re.M))
    if passes or fails:
        return {"total": passes + fails, "passed": passes, "failed": fails}
    return None


@dataclass
class Line:
    kind: str
    text: str
    open: bool = False             # chưa xuống hàng (lời nhắc nhập, tiến độ \r)


@dataclass
class LiveRun:
    steps: list[list[str]]
    cwd: str
    env: dict
    title: str = ""
    lang: str = ""
    source: str = "code"                        # "code" = bản code do NEXA viết, "file" = tệp trên đĩa
    time_limit: float = 0.0                     # 0 = không giới hạn (chờ anh nhập/bấm Dừng)
    build_limit: float = 180.0
    is_test: bool = False
    shown: list[str] = field(default_factory=list)          # lệnh hiển thị (đã rút gọn đường dẫn)
    on_change: Callable[["LiveRun"], None] | None = None
    on_done: Callable[["LiveRun"], None] | None = None
    replace: list[tuple[str, str]] = field(default_factory=list)   # thay chuỗi trong đầu ra (đường dẫn thư mục tạm)
    preview_url: str = ""                       # HTML: NEXA hiện trang ngay trên bảng
    file_path: str = ""                         # tệp trên đĩa (nút "Mở trong console riêng")

    def __post_init__(self) -> None:
        self.lines: list[Line] = []
        self.dropped = 0
        self.state = RUNNING
        self.exit_code: int | None = None
        self.started = time.monotonic()
        self.finished = 0.0
        self.version = 0
        self.note = ""
        self.step_index = 0
        self._lock = threading.RLock()
        self._proc: subprocess.Popen | None = None
        self._stop = threading.Event()
        self._dirty = threading.Event()
        self._last_input = time.monotonic()
        self._thread: threading.Thread | None = None
        self._open: dict[str, int] = {}                     # luồng → chỉ số dòng đang mở
        self._cr: dict[str, bool] = {}                      # đoạn trước kết thúc bằng \r → chữ tiếp theo ghi đè
        self.summary: dict | None = None

    # ------------------------------------------------------------ vòng đời
    def start(self) -> "LiveRun":
        self._thread = threading.Thread(target=self._main, name="code-live-run", daemon=True)
        self._thread.start()
        return self

    @property
    def running(self) -> bool:
        return self.state == RUNNING

    @property
    def seconds(self) -> float:
        return round((self.finished or time.monotonic()) - self.started, 2)

    def wait(self, timeout: float | None = None) -> bool:
        if self._thread is not None:
            self._thread.join(timeout)
        return not self.running

    def stop(self) -> None:
        self._stop.set()
        proc = self._proc
        if proc is not None and proc.poll() is None:
            _kill_tree(proc.pid)

    def send(self, text: str) -> bool:
        """Gửi một dòng vào stdin của chương trình (anh gõ ở ô nhập của NEXA)."""
        proc = self._proc
        if not self.running or proc is None or proc.stdin is None or proc.poll() is not None:
            return False
        try:
            proc.stdin.write((text + "\n").encode("utf-8"))
            proc.stdin.flush()
        except OSError:
            return False
        self._last_input = time.monotonic()
        with self._lock:
            idx = self._open.pop("out", None)
            if idx is not None and idx - self.dropped >= 0:          # lời nhắc "Nhập tên: " + câu anh gõ trên cùng dòng
                ln = self.lines[idx - self.dropped]
                ln.open = False
                self.lines.insert(idx - self.dropped + 1, Line("in", text))
                for stream, open_idx in self._open.items():
                    if open_idx > idx:
                        self._open[stream] = open_idx + 1
                self._trim()
            else:
                self._add("in", text)
            self._cr.pop("out", None)
        self._changed()
        return True

    # ------------------------------------------------------------ ghi dòng
    def _add(self, kind: str, text: str) -> None:
        with self._lock:
            self.lines.append(Line(kind, text))
            self._trim()

    def _trim(self) -> None:
        """Bound retained lines and retire evicted stream cursors; caller holds lock."""
        cut = max(0, len(self.lines) - MAX_LINES)
        if cut:
            del self.lines[:cut]
            self.dropped += cut
            for stream, idx in list(self._open.items()):
                if idx < self.dropped:
                    del self._open[stream]
                    self._cr.pop(stream, None)

    def info(self, text: str, kind: str = "info") -> None:
        self._add(kind, text)
        self._changed()

    def _clean(self, text: str) -> str:
        for a, b in self.replace:
            text = text.replace(a, b)
        return ANSI.sub("", text)

    def _feed(self, stream: str, chunk: str) -> None:
        """Thêm một đoạn đầu ra: tách dòng, \r ghi đè dòng đang mở, phần chưa xuống hàng giữ 'mở'."""
        chunk = self._clean(chunk.replace("\r\n", "\n"))
        with self._lock:
            parts = chunk.split("\n")
            for i, part in enumerate(parts):
                last = i == len(parts) - 1
                idx = self._open.get(stream)
                cur = self.lines[idx - self.dropped] if idx is not None and idx - self.dropped >= 0 else None
                text = cur.text if cur is not None else ""
                for j, seg in enumerate(part.split("\r")):
                    if j == 0 and not self._cr.get(stream):
                        text += seg
                    elif seg:                                   # sau \r: chữ mới ghi đè cả dòng
                        text = seg
                    self._cr[stream] = False
                if part.endswith("\r"):
                    self._cr[stream] = True
                if cur is not None:
                    cur.text = text
                    if not last:
                        cur.open = False
                        self._open.pop(stream, None)
                elif text or not last:
                    self.lines.append(Line(stream, text, open=last))
                    if last:
                        self._open[stream] = len(self.lines) - 1 + self.dropped
                    self._trim()
        self._changed()

    def _changed(self) -> None:
        self.version += 1
        if self.running or self._thread is None:
            self._dirty.set()
        else:
            self._emit()                  # đã chạy xong (console của trang HTML vẫn ghi thêm): báo UI ngay

    # ------------------------------------------------------------ chạy
    def _pump(self, pipe: Any, stream: str) -> None:
        import codecs
        dec = codecs.getincrementaldecoder("utf-8")("replace")
        try:
            while True:
                data = pipe.read1(4096) if hasattr(pipe, "read1") else pipe.read(4096)
                if not data:
                    break
                self._feed(stream, dec.decode(data))
        except (OSError, ValueError):
            pass
        tail = dec.decode(b"", final=True)
        if tail:
            self._feed(stream, tail)

    def _notifier(self) -> None:
        while True:
            self._dirty.wait(0.5)
            if self._dirty.is_set():
                self._dirty.clear()
                self._emit()
            if not self.running:
                return
            time.sleep(0.1)

    def _emit(self) -> None:
        if self.on_change:
            try:
                self.on_change(self)
            except Exception:
                pass

    def _main(self) -> None:
        threading.Thread(target=self._notifier, name="code-live-ui", daemon=True).start()
        state, code = OK, 0
        try:
            for i, step in enumerate(self.steps):
                self.step_index = i
                last = i == len(self.steps) - 1
                if len(self.steps) > 1 or self.shown:
                    self.info("$ " + (self.shown[i] if i < len(self.shown) else " ".join(step)), "cmd")
                code, why = self._run_step(step, interactive=last, limit=self.time_limit if last else self.build_limit)
                if why:
                    state = why
                    break
                if code != 0:
                    state = FAILED if last else BUILD_FAILED
                    break
        except OSError as exc:
            state, code = FAILED, None
            self.info(f"Không chạy được lệnh: {exc}", "fail")
        if not self.steps:
            state, code = PREVIEW, None                  # chỉ hiện trang HTML, không có lệnh nào
        self.exit_code = code
        text = self.plain_text()
        summary = test_summary(text) if self.is_test else None
        if state == OK and summary is not None and summary["total"] == 0:
            state = NO_TESTS
        if state == OK and summary is not None and summary["failed"]:
            state = FAILED
        self.summary = summary
        self.note = {BUILD_FAILED: "Biên dịch lỗi — chưa chạy chương trình.",
                     TIMEOUT: f"Dừng sau {self.time_limit:.0f} s (chương trình chưa tự kết thúc — có thể là server/"
                              "vòng lặp chờ).",
                     STOPPED: "Anh đã dừng chương trình.",
                     NO_TESTS: "Không tìm thấy kiểm thử nào để chạy."}.get(state, self.note)
        self.finished = time.monotonic()
        with self._lock:
            self._open.clear()
            for ln in self.lines:
                ln.open = False
        self.state = state
        self._changed()
        if self.on_done:
            try:
                self.on_done(self)
            except Exception:
                pass

    def _run_step(self, cmd: list[str], interactive: bool, limit: float) -> tuple[int | None, str]:
        self._proc = proc = subprocess.Popen(
            cmd, cwd=self.cwd, stdin=subprocess.PIPE if interactive else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env, creationflags=NO_WINDOW)
        readers = [threading.Thread(target=self._pump, args=(proc.stdout, "out"), daemon=True),
                   threading.Thread(target=self._pump, args=(proc.stderr, "err"), daemon=True)]
        for r in readers:
            r.start()
        t0 = self._last_input = time.monotonic()
        why = ""
        while proc.poll() is None:
            if self._stop.is_set():
                why = STOPPED
            elif limit and time.monotonic() - max(t0, self._last_input) > limit:
                why = TIMEOUT                 # đếm từ lần anh nhập gần nhất: chương trình chờ nhập không bị cắt oan
            if why:
                _kill_tree(proc.pid)
                break
            time.sleep(0.05)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        for r in readers:
            r.join(timeout=2)
        if self._stop.is_set() and not why:
            why = STOPPED
        return proc.returncode, why

    # ------------------------------------------------------------ xem
    def plain_text(self) -> str:
        with self._lock:
            return "\n".join(ln.text if ln.kind != "in" else f"> {ln.text}" for ln in self.lines
                             if ln.kind not in ("cmd",) or len(self.steps) > 1)

    def output_text(self) -> str:
        """Toàn bộ đầu ra để sao chép / gửi Gemini sửa lỗi."""
        with self._lock:
            return "\n".join(("> " + ln.text) if ln.kind == "in" else ln.text for ln in self.lines)

    def render_html(self, limit: int = SHOW_LINES) -> str:
        with self._lock:
            lines = list(self.lines[-limit:])
            hidden = self.dropped + max(0, len(self.lines) - limit)
        rows = []
        if hidden:
            rows.append(f'<span style="color:{COLORS["dim"]}">… ({hidden} dòng đầu đã ẩn — bấm Sao chép để lấy đủ)</span>')
        for ln in lines:
            kind = line_kind(ln.kind, ln.text)
            text = html.escape(ln.text) or "&nbsp;"
            if ln.kind == "in":
                text = f'<span style="color:{COLORS["dim"]}">›</span> {text}'
            rows.append(f'<span style="color:{COLORS.get(kind, COLORS["out"])}">{text}</span>')
        if self.running and lines and lines[-1].open:
            rows[-1] += f'<span style="color:{COLORS["cmd"]}">▌</span>'
        return ('<div style="white-space:pre-wrap; line-height:135%">' + "<br>".join(rows) + "</div>") if rows else ""

    def waiting_input(self) -> bool:
        """Có vẻ đang chờ anh nhập: đang chạy bước cuối, dòng cuối là lời nhắc chưa xuống hàng."""
        with self._lock:
            return self.running and bool(self.lines) and self.lines[-1].open and self.lines[-1].kind == "out"

    def view(self) -> dict:
        return {"active": True, "state": self.state, "stateLabel": STATE_LABEL.get(self.state, self.state),
                "title": self.title, "lang": self.lang, "source": self.source,
                "command": "  &&  ".join(self.shown) if self.shown else "", "exitCode": -1 if self.exit_code is None
                else self.exit_code, "seconds": self.seconds, "html": self.render_html(), "lines": len(self.lines) +
                self.dropped, "summary": self.summary or {}, "note": self.note, "running": self.running,
                "waitingInput": self.waiting_input(), "previewUrl": self.preview_url, "isTest": self.is_test,
                "step": self.step_index + 1, "steps": len(self.steps), "version": self.version}


def _kill_tree(pid: int) -> None:
    try:
        import psutil
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            child.kill()
        parent.kill()
    except Exception:
        try:
            os.kill(pid, 9)
        except OSError:
            pass
