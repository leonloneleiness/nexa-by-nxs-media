"""CodeService: một việc nền tại một thời điểm (viết / chỉnh sửa / chạy thử), lịch sử bản code, lưu ra thư mục.

Thông báo cho UI qua notify("code_job" | "code_result" | "code_history" | "code_open" | "code_toast" | "code_run" |
"code_gesture", dict).
"code_run" = bảng kết quả chạy (self.live, live_run.LiveRun) có thay đổi — UI đọc self.live.view().
KHÔNG tự sao chép gì vào clipboard và KHÔNG tự chạy code — chạy thử chỉ khi anh bấm (run_tests).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
import time
import unicodedata
import zlib
from pathlib import Path
from typing import Any, Callable

from nexa.code import checks, live_run
from nexa.code.generator import CodeGenerator, CodeGenError
from nexa.code.models import LANG_LABEL, CodeResult, RunReport, comment_line
from nexa.utils.config import LOCAL_DATA_DIR, known_folder
from nexa.utils.logging import get_logger

log = get_logger("code.service")


class _Token:
    """Token hủy tối giản khi controller không cấp token của SafetyManager (test/độc lập)."""

    def __init__(self) -> None:
        self._ev = threading.Event()
        self.reason = ""

    def cancel(self, reason: str = "cancelled") -> None:
        self.reason = reason
        self._ev.set()

    @property
    def cancelled(self) -> bool:
        return self._ev.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise CodeCancelled(self.reason)


class CodeCancelled(Exception):
    pass


def slugify(text: str, n: int = 40) -> str:
    s = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s[:n].strip("-") or "code"


class CodeService:
    SNAP_DEBOUNCE_S = 1.2                               # camera + mic cùng bắt một cái búng → chỉ tính một lần

    def __init__(self, config: Any, notify: Callable[[str, dict], None] | None = None, gemini: Any = None,
                 token_factory: Callable[[], Any] | None = None, history_dir: Path | None = None) -> None:
        self.config = config
        self._notify = notify or (lambda k, d: None)
        self.generator = CodeGenerator(gemini, config)
        self.token_factory = token_factory or _Token
        self.history_dir = Path(history_dir or (LOCAL_DATA_DIR / "code_history"))
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._token: Any = None
        self._job: dict = {"state": "idle", "kind": "", "message": "", "progress": 0.0, "started": 0.0}
        self.current: CodeResult | None = None
        self.locked = False
        self.live: live_run.LiveRun | None = None       # lần chạy đang hiện trên bảng kết quả
        self._rerun: Callable[[], tuple[bool, str]] | None = None
        self.html_preview = False                        # UI có QtWebEngine → trang HTML hiện ngay trong NEXA
        self._consoles: list[Any] = []          # cửa sổ chạy thử tệp đang mở (dừng khẩn cấp thì đóng hết)
        # do controller gắn: phản hồi (chữ, câu đọc)
        self.on_message: Callable[[str, str], None] | None = None
        # cử chỉ khi bảng Sinh code mở (nexa/code/gesture_controller.py): nắm tay = lưu, búng tay = chạy thử, hai ngón = cuộn
        from nexa.code.gesture_controller import CodeGestureParams, CodeGestureStateMachine
        self.gesture_sm = CodeGestureStateMachine(CodeGestureParams.from_config(config))
        self._gesture_lock = threading.Lock()
        self.panel_open = False
        self.panel_view = "code"                        # khung bảng đang hiện: "code" | "run" | "web"
        self._last_snap_t = -1e9
        self.on_panel_mode: Callable[[bool], None] | None = None      # controller: bật/tắt chế độ cử chỉ CODE
        self._gesture_saved: dict[str, tuple[int, str]] = {}           # id → (crc nội dung, thư mục đã lưu bằng cử chỉ)

    def cfg(self, key: str, default: Any) -> Any:
        v = self.config.get(f"code.{key}") if self.config is not None else None
        return default if v is None else v

    @property
    def enabled(self) -> bool:
        return bool(self.cfg("enabled", True))

    # ------------------------------------------------------------ trạng thái việc nền
    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def job(self) -> dict:
        with self._lock:
            return dict(self._job)

    def _set_job(self, **kw: Any) -> None:
        with self._lock:
            self._job.update(kw)
            snap = dict(self._job)
        self._notify("code_job", snap)

    def _start(self, kind: str, message: str, work: Callable[[Any], None]) -> tuple[bool, str]:
        if not self.enabled:
            return False, "Tính năng sinh code đang tắt (code.enabled)."
        if self.locked:
            return False, "NEXA đang dừng khẩn cấp — nói 'tiếp tục điều khiển' trước đã."
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False, "Em đang bận một việc code khác — anh đợi xong hoặc bấm Hủy."
            token = self.token_factory()
            self._token = token
            self._job = {"state": "running", "kind": kind, "message": message, "progress": 0.05,
                         "started": time.time()}
            self._thread = threading.Thread(target=self._run, args=(kind, work, token), name=f"code-{kind}",
                                            daemon=True)
        self._notify("code_job", self.job())
        self._thread.start()
        return True, message

    def _run(self, kind: str, work: Callable[[Any], None], token: Any) -> None:
        try:
            work(token)
            if token.cancelled:
                raise CodeCancelled(getattr(token, "reason", "") or "đã hủy")
            self._set_job(state="done", progress=1.0, message="Xong.")
        except CodeCancelled as exc:
            self._set_job(state="cancelled", message=f"Đã hủy ({exc})." if str(exc) else "Đã hủy.")
        except Exception as exc:  # lỗi Gemini/mạng/khác — báo cho anh, không làm sập NEXA
            if token.cancelled:
                self._set_job(state="cancelled", message="Đã hủy.")
                return
            log.exception("Việc code (%s) lỗi", kind)
            msg = _friendly_error(exc)
            self._set_job(state="failed", message=msg)
            if kind != "run":
                self._say(f"Không tạo được code: {msg}", "Em chưa tạo được code, anh xem chi tiết trên bảng.")

    def cancel(self, reason: str = "Người dùng hủy") -> bool:
        with self._lock:
            tok = self._token if self._thread is not None and self._thread.is_alive() else None
        if tok is None:
            return False
        tok.cancel(reason)
        return True

    def _progress(self, token: Any) -> Callable[[str, float], None]:
        def cb(msg: str, p: float) -> None:
            if token.cancelled:
                raise CodeCancelled(getattr(token, "reason", "") or "đã hủy")
            self._set_job(message=msg, progress=round(float(p), 3))
        return cb

    def _say(self, text: str, spoken: str) -> None:
        if self.on_message:
            try:
                self.on_message(text, spoken)
            except Exception:
                log.exception("on_message lỗi")

    # ------------------------------------------------------------ viết / chỉnh sửa / chạy thử
    def generate(self, prompt: str, language: str = "", source: str = "keyboard") -> tuple[bool, str]:
        prompt = (prompt or "").strip()
        if len(prompt) < 4:
            return False, "Anh mô tả rõ hơn cần code gì nhé."
        ok, why = self.generator.ready()
        if not ok:
            return False, f"Chưa gọi được Gemini: {why}" if why else "Chưa gọi được Gemini."

        def work(token: Any) -> None:
            res = self.generator.generate(prompt, language, token, self._progress(token))
            self._publish(res, announce=True)
        self._notify("code_open", {"prompt": prompt, "language": language})
        return self._start("generate", "Gemini đang viết code…", work)

    def open_panel(self) -> None:
        self._notify("code_open", {})

    def close_panel(self) -> bool:
        """Đóng bảng Sinh code (lệnh giọng nói). Trả về False nếu bảng vốn không mở."""
        was = self.panel_open
        self._notify("code_close", {})
        return was

    def refine(self, instruction: str, result_id: str = "", use_run_output: bool = False) -> tuple[bool, str]:
        base = self._resolve(result_id)
        if base is None:
            return False, "Chưa có bản code nào để chỉnh sửa."
        instruction = (instruction or "").strip()
        run_out = ""
        if use_run_output and base.run is not None and not base.run.ok:
            run_out = f"$ {base.run.command}\n{base.run.output}\n{base.run.note}".strip()
            instruction = instruction or "Sửa code để lần chạy thử trên đạt (sửa code, không sửa kiểm thử cho qua trừ khi kiểm thử sai)."
        if not instruction:
            return False, "Anh nhập yêu cầu chỉnh sửa trước đã."

        def work(token: Any) -> None:
            res = self.generator.refine(base, instruction, token, run_out, self._progress(token))
            self._publish(res, announce=True)
        return self._start("refine", "Gemini đang chỉnh sửa code…", work)

    # ------------------------------------------------------------ chạy thử NGAY TRONG NEXA (live_run)
    def _live_env(self) -> dict:
        env = checks.run_env()
        env["PYTHONUNBUFFERED"] = "1"                 # lời nhắc input() hiện ngay trên bảng
        return env

    def _live_begin(self, run: live_run.LiveRun, rerun: Callable[[], tuple[bool, str]]) -> None:
        old = self.live
        if old is not None and old.running:
            old.stop()
        run.on_change = lambda r: self._notify("code_run", {}) if r is self.live else None
        self.live = run
        self._rerun = rerun
        self._notify("code_run", {})                     # dữ liệu lần chạy trước → bảng biết có trang HTML để xem
        self.panel_view = "run"
        self._notify("code_open", {"view": "run"})
        run.start()

    def _preview_dir(self, res: CodeResult) -> Path:
        return Path(tempfile.gettempdir()) / "nexa_preview" / re.sub(r"[^A-Za-z0-9_-]", "", res.id or "code")

    @staticmethod
    def _html_entry(paths: list[str]) -> str:
        html = [p for p in paths if Path(p).suffix.lower() in (".html", ".htm")]
        for p in html:
            if Path(p).name.lower() in ("index.html", "index.htm"):
                return p
        return html[0] if html else ""

    def run_tests(self, result_id: str = "") -> tuple[bool, str]:
        """Bấm "▶ Chạy thử": chạy bản code trong thư mục tạm, đầu ra hiện trực tiếp trên bảng; trang HTML hiện ngay
        trong NEXA (kèm chạy kiểm thử nếu có)."""
        if self.locked:
            return False, "NEXA đang dừng khẩn cấp — nói 'tiếp tục điều khiển' trước đã."
        res = self._resolve(result_id)
        if res is None:
            return False, "Chưa có bản code nào để chạy thử."
        python = checks.find_python(str(self.cfg("python_path", "") or ""))
        preview, pdir = "", Path(".")
        entry_html = self._html_entry([f.path for f in res.files]) if self.html_preview else ""
        if entry_html:
            pdir = self._preview_dir(res)
            shutil.rmtree(pdir, ignore_errors=True)
            try:
                checks._write_all(res.files, pdir)
            except OSError as exc:
                return False, f"Không dựng được trang xem trước: {exc}"
            preview = (pdir / entry_html).as_uri()
        try:
            root, plan, note = checks.prepare_project(res.files, python)
        except OSError as exc:
            return False, f"Không chuẩn bị được thư mục chạy thử: {exc}"
        if plan is None and not preview:
            return False, note
        title = f"{res.title or 'Bản code'}"
        lang = LANG_LABEL.get(plan.lang if plan else "html", plan.lang if plan else "HTML")
        if plan is None:
            run = live_run.LiveRun([], str(pdir), {}, title=title, lang=lang,
                                   source="code", preview_url=preview)
        else:
            run = live_run.LiveRun(plan.steps, str(root), self._live_env(), title=title, lang=lang, source="code",
                                   time_limit=float(self.cfg("run_timeout_s", 30)) + plan.extra_s,
                                   build_limit=checks.BUILD_TIMEOUT_S, is_test="kiểm thử" in plan.label,
                                   shown=checks.shown_steps(plan, root), preview_url=preview,
                                   replace=[(str(root) + os.sep, ""), (str(root), ".")])
            run.note = plan.note
        if preview:
            run.info("Trang đang hiện trong NEXA — lỗi/console.log của trang sẽ hiện ở đây.", "info")

        def done(r: live_run.LiveRun) -> None:
            if plan is not None:
                shutil.rmtree(root, ignore_errors=True)
                out = r.output_text()
                if len(out) > checks.MAX_OUTPUT:
                    out = out[:checks.MAX_OUTPUT // 3] + "\n…(lược bớt)…\n" + out[-checks.MAX_OUTPUT * 2 // 3:]
                res.run = RunReport(r.state == live_run.OK, " && ".join(r.shown), r.exit_code, out.strip(),
                                    r.seconds, r.state == live_run.TIMEOUT, r.note)
                self._store(res)
                if self.current is not None and self.current.id == res.id:
                    self.current = res
                self._notify("code_result", {"id": res.id, "keepView": True})
            if r is self.live and r.state != live_run.PREVIEW:
                self._announce_run(r)
        run.on_done = done
        self._live_begin(run, lambda: self.run_tests(res.id))
        return True, f"{note or 'Đang mở trang'}…" if plan else "Đang hiện trang trong NEXA."

    def _announce_run(self, r: live_run.LiveRun) -> None:
        name = r.title
        s = r.summary or {}
        tests = f" — {s.get('passed', 0)}/{s.get('total', 0)} kiểm thử đạt" if s.get("total") else ""
        st = r.state
        if st == live_run.OK:
            text, spoken = f"{name}: chạy xong, không lỗi{tests} ({r.seconds:.1f} s).", "Chạy xong, không có lỗi."
        elif st == live_run.BUILD_FAILED:
            text, spoken = f"{name}: biên dịch lỗi — anh xem chi tiết trên bảng kết quả.", "Biên dịch bị lỗi anh ạ."
        elif st == live_run.STOPPED:
            return
        elif st == live_run.NO_TESTS:
            text, spoken = f"{name}: không tìm thấy kiểm thử nào để chạy.", "Không có kiểm thử nào chạy được."
        elif st == live_run.TIMEOUT:
            text, spoken = f"{name}: {r.note}", "Chương trình chạy quá giờ nên em đã dừng."
        else:
            code = f"mã lỗi {r.exit_code}" if r.exit_code not in (None, 0) else "lỗi"
            text = f"{name}: kết thúc với {code}{tests} ({r.seconds:.1f} s) — anh xem thông báo lỗi trên bảng kết quả."
            spoken = "Chương trình báo lỗi, anh xem bảng kết quả nhé."
        self._notify("code_toast", {"text": text, "error": st != live_run.OK})
        self._say(text, spoken)

    def stop_run(self) -> bool:
        r = self.live
        if r is None or not r.running:
            return False
        r.stop()
        return True

    def send_input(self, text: str) -> bool:
        r = self.live
        return bool(r is not None and r.send(text))

    def rerun(self) -> tuple[bool, str]:
        return self._rerun() if self._rerun else (False, "Chưa có lần chạy nào để chạy lại.")

    def web_console(self, level: int, message: str, line: int = 0, source: str = "") -> None:
        """console.log / lỗi JavaScript của trang HTML đang xem trong NEXA → bảng kết quả."""
        r = self.live
        if r is None or not r.preview_url:
            return
        where = f"  ({Path(source).name}:{line})" if source and line else ""
        r.info(f"[console] {message}{where}", {0: "out", 1: "warn"}.get(int(level), "fail"))

    def run_file(self, path: Path) -> tuple[bool, str]:
        """Chạy thử một tệp trên đĩa (mọi ngôn ngữ có công cụ trên máy): đầu ra hiện NGAY TRONG NEXA, anh nhập dữ liệu ở
        ô nhập trên bảng. Không giới hạn thời gian; bấm Dừng (hoặc dừng khẩn cấp) để diệt.
        code.run_file_in: console → dùng cửa sổ console riêng như trước (chương trình cần terminal thật)."""
        from nexa.code import runners
        if str(self.cfg("run_file_in", "nexa")).lower() == "console":
            return self.run_file_console(path)
        if self.locked:
            return False, "NEXA đang dừng khẩn cấp — nói 'tiếp tục điều khiển' trước đã."
        path = Path(path)
        if not path.is_file():
            return False, f"Không thấy tệp {path}."
        python = checks.find_python(str(self.cfg("python_path", "") or ""))
        out = Path(tempfile.gettempdir()) / "nexa_run_build" / \
            f"{slugify(path.stem, 24)}-{zlib.crc32(str(path).encode()):08x}"
        plan = runners.plan_file(path.name, path.parent, out, python)
        if isinstance(plan, str):
            return False, plan
        lang = LANG_LABEL.get(plan.lang, plan.lang)
        if plan.open_path:
            if not self.html_preview:
                try:
                    os.startfile(plan.open_path)      # type: ignore[attr-defined]
                except OSError as exc:
                    return False, f"Không mở được {path.name}: {exc}"
                return True, f"Đã mở {path.name} trong trình duyệt."
            run = live_run.LiveRun([], str(path.parent), {}, title=path.name, lang=lang or "HTML", source="file",
                                   preview_url=Path(plan.open_path).as_uri())
            run.info("Trang đang hiện trong NEXA — lỗi/console.log của trang sẽ hiện ở đây.", "info")
            self._live_begin(run, lambda: self.run_file(path))
            return True, f"Em đang hiện trang {path.name} ngay trong NEXA."
        try:
            out.mkdir(parents=True, exist_ok=True)
            for fp, text in plan.files.items():
                Path(fp).write_text(text, encoding="utf-8")
        except OSError as exc:
            return False, f"Không chuẩn bị được thư mục build: {exc}"
        run = live_run.LiveRun(plan.steps, str(path.parent), self._live_env(), title=path.name, lang=lang,
                               source="file", time_limit=0, shown=[checks.shown_command(c) for c in plan.steps],
                               replace=[(str(out) + os.sep, ""), (str(out), ".")])
        run.note = plan.note
        run.file_path = str(path)
        run.on_done = lambda r: self._announce_run(r) if r is self.live else None
        self._live_begin(run, lambda: self.run_file(path))
        msg = f"Em đang {plan.label[0].lower() + plan.label[1:]} — kết quả hiện ngay trong NEXA; chương trình hỏi gì " \
              "anh gõ vào ô nhập trên bảng."
        if plan.note:
            msg += f" Lưu ý: {plan.note}"
        return True, msg

    def run_live_in_console(self) -> tuple[bool, str]:
        """Nút "Mở trong console riêng": chạy lại tệp đang xem bằng cửa sổ console thật (chương trình C/C++ đệm đầu ra
        khi chạy qua ống, hoặc cần màn hình terminal)."""
        r = self.live
        fp = getattr(r, "file_path", "") if r is not None else ""
        if not fp:
            return False, "Chỉ mở console riêng được với tệp trên đĩa."
        if r.running:
            r.stop()
        return self.run_file_console(Path(fp))

    def run_file_console(self, path: Path) -> tuple[bool, str]:
        """Chạy thử một tệp trên đĩa (mọi ngôn ngữ có công cụ trên máy) trong cửa sổ console riêng.
        Không giới hạn thời gian (chương trình có thể chờ anh nhập); dừng khẩn cấp sẽ đóng cửa sổ đó."""
        from nexa.code import console_run, runners
        if self.locked:
            return False, "NEXA đang dừng khẩn cấp — nói 'tiếp tục điều khiển' trước đã."
        path = Path(path)
        if not path.is_file():
            return False, f"Không thấy tệp {path}."
        python = checks.find_python(str(self.cfg("python_path", "") or ""))
        out = Path(tempfile.gettempdir()) / "nexa_run_build" / \
            f"{slugify(path.stem, 24)}-{zlib.crc32(str(path).encode()):08x}"
        plan = runners.plan_file(path.name, path.parent, out, python)
        if isinstance(plan, str):
            return False, plan
        if plan.open_path:
            try:
                os.startfile(plan.open_path)      # type: ignore[attr-defined]
            except OSError as exc:
                return False, f"Không mở được {path.name}: {exc}"
            return True, f"Đã mở {path.name} trong trình duyệt."
        try:
            out.mkdir(parents=True, exist_ok=True)
            for fp, text in plan.files.items():
                Path(fp).write_text(text, encoding="utf-8")
            proc, result = console_run.launch(plan.steps, path.parent, path.name, checks.run_env())
        except OSError as exc:
            return False, f"Không mở được cửa sổ chạy thử: {exc}"
        self._consoles = [p for p in self._consoles if p.poll() is None] + [proc]
        threading.Thread(target=self._watch_console, args=(proc, result, path.name), name="code-console",
                         daemon=True).start()
        msg = (f"Em đang {plan.label[0].lower() + plan.label[1:]} trong cửa sổ riêng bên cạnh — chương trình hỏi gì "
               "anh nhập ở cửa sổ đó.")
        if plan.note:
            msg += f" Lưu ý: {plan.note}"
        return True, msg

    def _watch_console(self, proc: Any, result: Path, name: str) -> None:
        """Đợi cửa sổ chạy thử in kết quả (trước khi anh nhấn Enter đóng) rồi báo lại một câu ngắn."""
        while not result.exists() and proc.poll() is None:
            time.sleep(0.3)
        time.sleep(0.1)
        try:
            data = json.loads(result.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return                                  # cửa sổ bị đóng giữa chừng / dừng khẩn cấp: không báo gì
        finally:
            shutil.rmtree(result.parent, ignore_errors=True)
        code, secs = data.get("exit_code"), float(data.get("seconds") or 0)
        if data.get("interrupted"):
            return
        if data.get("build_failed"):
            text, spoken = f"{name}: biên dịch lỗi, anh xem chi tiết trong cửa sổ chạy thử.", "Biên dịch bị lỗi anh ạ."
        elif code == 0:
            text, spoken = f"{name} chạy xong, không lỗi ({secs:.1f} s).", "Chạy xong, không có lỗi."
        else:
            text = f"{name} kết thúc với mã lỗi {code} ({secs:.1f} s) — anh xem thông báo lỗi trong cửa sổ chạy thử."
            spoken = "Chương trình báo lỗi, anh xem cửa sổ chạy thử nhé."
        self._notify("code_toast", {"text": text, "error": code != 0})
        self._say(text, spoken)

    def _publish(self, res: CodeResult, announce: bool) -> None:
        self.current = res
        self._store(res)
        self._notify("code_result", {"id": res.id})
        self._notify("code_history", {})
        if announce:
            text, spoken = describe(res)
            self._say(text, spoken)

    # ------------------------------------------------------------ lịch sử
    def _path(self, rid: str) -> Path:
        return self.history_dir / f"{re.sub(r'[^A-Za-z0-9_-]', '', rid)}.json"

    def _store(self, res: CodeResult) -> None:
        try:
            self.history_dir.mkdir(parents=True, exist_ok=True)
            tmp = self._path(res.id).with_suffix(".tmp")
            tmp.write_text(json.dumps(res.to_dict(), ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self._path(res.id))
            keep = int(self.cfg("history_limit", 30))
            olds = sorted(self.history_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[keep:]
            for p in olds:
                p.unlink(missing_ok=True)
        except OSError:
            log.exception("Không lưu được lịch sử code")

    def history(self) -> list[dict]:
        out = []
        if not self.history_dir.exists():
            return out
        for p in sorted(self.history_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            out.append({"id": d.get("id", p.stem), "title": d.get("title", ""), "language": d.get("language", ""),
                        "created": d.get("created", 0.0), "files": len(d.get("files") or [])})
        return out

    def load(self, rid: str) -> CodeResult | None:
        try:
            return CodeResult.from_dict(json.loads(self._path(rid).read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return None

    def open(self, rid: str) -> bool:
        res = self.load(rid)
        if res is None:
            return False
        self.current = res
        self._notify("code_result", {"id": res.id})
        return True

    def delete(self, rid: str) -> bool:
        p = self._path(rid)
        if not p.exists():
            return False
        p.unlink(missing_ok=True)
        if self.current is not None and self.current.id == rid:
            self.current = None
            self._notify("code_result", {"id": ""})
        self._notify("code_history", {})
        return True

    def _resolve(self, rid: str) -> CodeResult | None:
        if not rid or (self.current is not None and self.current.id == rid):
            return self.current
        return self.load(rid)

    # ------------------------------------------------------------ sao chép / lưu (chỉ khi anh bấm)
    @staticmethod
    def all_text(res: CodeResult) -> str:
        if len(res.files) == 1:
            return res.files[0].content
        parts = []
        for f in res.files:
            parts.append(comment_line(f.language, f"===== {f.path} =====") + "\n" + f.content)
        return "\n".join(parts)

    def save(self, result_id: str = "", folder: str = "") -> tuple[bool, str]:
        res = self._resolve(result_id)
        if res is None:
            return False, "Chưa có bản code nào để lưu."
        root = Path(folder or str(self.cfg("save_dir", "") or "") or known_folder("Documents") / "NEXA Code")
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(res.created or time.time()))
        dest = root / f"{slugify(res.title)}-{stamp}"
        n = 2
        while dest.exists():             # không bao giờ ghi đè thư mục cũ
            dest = root / f"{slugify(res.title)}-{stamp}-{n}"
            n += 1
        try:
            for f in res.files:
                p = (dest / f.path).resolve()
                if dest.resolve() not in p.parents:
                    continue
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(f.content, encoding="utf-8", newline="\r\n" if f.language in ("batch", "powershell")
                             else "\n")
            readme = dest / "NEXA_README.txt"
            if not (dest / "README.md").exists():
                readme.write_text(f"{res.title}\n\n{res.summary}\n\nYêu cầu: {res.prompt}\n\nCách chạy:\n"
                                  f"{res.run_instructions}\n", encoding="utf-8")
        except OSError as exc:
            return False, f"Không lưu được: {exc}"
        return True, str(dest)

    # ------------------------------------------------------------ cử chỉ (bảng Sinh code đang mở)
    def set_panel_open(self, open_: bool) -> None:
        """UI báo bảng Sinh code mở/đóng → controller chuyển camera sang chế độ cử chỉ CODE (hoặc trả lại)."""
        open_ = bool(open_)
        if open_ == self.panel_open:
            return
        self.panel_open = open_
        self.panel_view = "code"
        with self._gesture_lock:
            self.gesture_sm.reset("mở bảng code" if open_ else "đóng bảng code")
        if not open_:
            self._notify("code_gesture", {"kind": "hud", "state": "IDLE", "label": "", "progress": 0.0})
        if self.on_panel_mode:
            try:
                self.on_panel_mode(open_)
            except Exception:
                log.exception("on_panel_mode lỗi")

    def reload_gesture_params(self) -> None:
        from nexa.code.gesture_controller import CodeGestureParams
        with self._gesture_lock:
            self.gesture_sm.update_params(CodeGestureParams.from_config(self.config))

    def feed_gesture(self, obs: Any, t_frame: float | None = None) -> list:
        """Gọi từ luồng camera khi ở chế độ cử chỉ CODE."""
        with self._gesture_lock:
            events = self.gesture_sm.update(obs)
        for ev in events:
            if ev.kind == "save":
                self.gesture_save()
            elif ev.kind == "run":
                self.gesture_run("camera")
            elif ev.kind == "scroll":
                self._notify("code_gesture", {"kind": "scroll", "dy": round(ev.dy, 1)})
            elif ev.kind == "hud":
                self._notify("code_gesture", {"kind": "hud", "state": ev.state, "label": ev.label,
                                              "progress": ev.progress})
        return events

    def gesture_save(self) -> tuple[bool, str]:
        """Nắm tay: lưu bản code đang xem (không mở Explorer — cửa sổ đó sẽ che NEXA). Nắm lại khi code chưa đổi thì
        không tạo thêm thư mục trùng."""
        res = self.current
        if res is None:
            ok, msg = False, "Chưa có bản code nào để lưu."
        else:
            crc = zlib.crc32(self.all_text(res).encode("utf-8"))
            prev = self._gesture_saved.get(res.id)
            if prev is not None and prev[0] == crc and Path(prev[1]).is_dir():
                ok, msg = True, f"Bản này đã lưu rồi: {prev[1]}"
            else:
                ok, where = self.save(res.id)
                if ok:
                    self._gesture_saved[res.id] = (crc, where)
                msg = f"Đã lưu code vào {where}" if ok else where
        log.info("Cử chỉ nắm tay → lưu code: %s", msg)
        self._notify("code_toast", {"text": msg, "error": not ok})
        self._say(msg, "Em đã lưu code." if ok and not msg.startswith("Bản này") else
                  ("Bản này đã lưu rồi anh." if ok else "Chưa có code để lưu anh ạ."))
        return ok, msg

    def set_panel_view(self, view: str) -> None:
        """UI báo bảng đang hiện khung nào ("code" | "run" | "web") → búng tay biết nên chạy hay tắt."""
        self.panel_view = str(view or "code")

    def gesture_run(self, source: str = "camera") -> tuple[bool, str]:
        """Búng tay kiểu công tắc: đang ở màn hình code → chạy thử (lần chạy gần nhất là tệp trên đĩa thì chạy lại
        tệp đó); đang xem kết quả / trang → dừng chương trình và trở về màn hình code.
        Hai lần búng sát nhau (camera + mic cùng bắt một cái búng) chỉ tính một."""
        now = time.monotonic()
        if now - self._last_snap_t < self.SNAP_DEBOUNCE_S:
            log.info("Bỏ qua búng tay (%s): trùng lần búng vừa rồi", source)
            return False, "trùng"
        self._last_snap_t = now
        if self.panel_view != "code":
            stopped = self.stop_run()
            self.panel_view = "code"
            self._notify("code_open", {"view": "code"})
            msg = "Đã tắt chạy thử, về màn hình code." if stopped else "Về màn hình code."
            log.info("Cử chỉ búng tay (%s) → %s", source, msg)
            self._notify("code_toast", {"text": msg, "error": False})
            return True, msg
        r = self.live
        if r is not None and r.source == "file":
            ok, msg = self.rerun()
        elif self.current is not None:
            ok, msg = self.run_tests(self.current.id)
        else:
            ok, msg = self.rerun()
        log.info("Cử chỉ búng tay (%s) → chạy thử: %s", source, msg)
        if not ok:
            self._notify("code_toast", {"text": msg, "error": True})
        return ok, msg

    # ------------------------------------------------------------ an toàn
    def on_emergency(self, reason: str) -> None:
        self.locked = True
        with self._gesture_lock:
            self.gesture_sm.lock(True)
        for proc in self._consoles:
            if proc.poll() is None:
                checks._kill_tree(proc.pid)
        self._consoles = []
        self.stop_run()
        if self.cancel(f"dừng khẩn cấp: {reason}"):
            log.warning("Dừng khẩn cấp: hủy việc code đang chạy")

    def on_resume_control(self) -> None:
        self.locked = False
        with self._gesture_lock:
            self.gesture_sm.lock(False)

    def status(self) -> dict:
        return {"enabled": self.enabled, "job": self.job(), "current": self.current.id if self.current else ""}

    def shutdown(self) -> None:
        self.stop_run()
        self.cancel("tắt NEXA")


def describe(res: CodeResult) -> tuple[str, str]:
    """(câu trả lời chữ, câu đọc ngắn) khi một bản code xong."""
    lang = LANG_LABEL.get(res.language, res.language)
    n = len(res.files)
    files = f"{n} tệp" if n > 1 else res.files[0].path
    st = res.check_status
    if st == "ok":
        chk = "đã qua kiểm tra cú pháp"
    elif st == "warning":
        chk = "qua kiểm tra cú pháp, còn vài cảnh báo nhỏ"
    elif st == "error":
        chk = "vẫn còn lỗi mà trình kiểm tra phát hiện — anh xem kỹ trước khi dùng"
    else:
        chk = "chưa kiểm tra tự động được với ngôn ngữ này"
    text = f"Xong «{res.title}» ({lang}, {files}), {chk}. Code đang hiện trên bảng để anh xem trước; " \
           "chỉ khi anh bấm Sao chép em mới đưa vào clipboard."
    if res.missing_packages:
        text += " Cần cài thêm: " + "; ".join(res.missing_packages[:4]) + "."
    spoken = f"Code {res.title} đã xong, anh xem trên bảng nhé." if st != "error" else \
        "Code đã xong nhưng còn lỗi, anh xem kỹ trên bảng nhé."
    return text, spoken


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, CodeGenError):
        return str(exc)
    code = getattr(exc, "code", "")
    msg = str(getattr(exc, "message", "") or exc) or type(exc).__name__
    if code in ("quota", "rate_limit") or "429" in msg or "RESOURCE_EXHAUSTED" in msg:
        return "Gemini đang hết hạn mức miễn phí, anh thử lại sau ít phút."
    if code == "timeout" or "timed out" in msg.lower():
        return "Gemini phản hồi quá lâu, anh thử lại hoặc chia yêu cầu nhỏ hơn."
    return msg[:300]
