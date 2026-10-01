"""Cầu nối Python ⇄ QML cho bảng Sinh code (context property `nexaCode`).

Nhận sự kiện "code_*" của CodeService qua post(kind, data) (luồng bất kỳ) → tín hiệu queued về luồng GUI.
Clipboard chỉ được ghi trong copyFile/copyAll — tức là khi anh bấm nút; không có đường nào tự sao chép.
"""
from __future__ import annotations

import os
import time
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtGui import QGuiApplication

from nexa.code.highlight import gutter_html, highlight_html
from nexa.code.models import LANG_LABEL, CodeResult
from nexa.utils.logging import get_logger

log = get_logger("ui.code")

LANG_CHOICES = [("", "Tự chọn"), ("python", "Python"), ("javascript", "JavaScript"), ("typescript", "TypeScript"),
                ("java", "Java"), ("csharp", "C#"), ("cpp", "C++"), ("go", "Go"), ("rust", "Rust"), ("php", "PHP"),
                ("kotlin", "Kotlin"), ("sql", "SQL"), ("powershell", "PowerShell"), ("bash", "Bash"),
                ("html", "HTML/CSS"), ("yaml", "YAML"), ("dockerfile", "Dockerfile")]
STATUS_LABEL = {"ok": "Đạt", "warning": "Cảnh báo", "error": "Lỗi", "skipped": "Chưa kiểm tra"}


def result_view(res: CodeResult | None) -> dict:
    if res is None:
        return {}
    checks = {c.path: c for c in res.checks}
    files = []
    for f in res.files:
        c = checks.get(f.path)
        files.append({
            "path": f.path, "language": f.language, "label": LANG_LABEL.get(f.language, f.language),
            "lines": f.lines, "chars": len(f.content), "html": highlight_html(f.content, f.language),
            "gutter": gutter_html(f.lines),
            "check": {"status": c.status if c else "skipped", "label": STATUS_LABEL.get(c.status if c else "skipped"),
                      "tool": c.tool if c else "", "messages": list(c.messages) if c else []},
        })
    run = None
    if res.run is not None:
        run = {"ok": res.run.ok, "command": res.run.command, "exitCode": -1 if res.run.exit_code is None
               else res.run.exit_code, "output": res.run.output, "seconds": res.run.seconds,
               "timedOut": res.run.timed_out, "note": res.run.note}
    return {
        "id": res.id, "title": res.title, "prompt": res.prompt, "language": res.language,
        "languageLabel": LANG_LABEL.get(res.language, res.language), "summary": res.summary, "files": files,
        "runInstructions": res.run_instructions, "dependencies": res.dependencies, "notes": res.notes,
        "missing": res.missing_packages, "checkStatus": res.check_status,
        "checkLabel": STATUS_LABEL.get(res.check_status, ""), "run": run, "model": res.model, "rounds": res.rounds,
        "created": time.strftime("%H:%M %d/%m", time.localtime(res.created)) if res.created else "",
        "totalLines": sum(f.lines for f in res.files),
    }


class CodeBridge(QObject):
    _incoming = Signal(str, object)
    panelChanged = Signal()
    jobChanged = Signal()
    resultChanged = Signal()
    historyChanged = Signal()
    runChanged = Signal()
    showView = Signal(str)                    # "code" | "run" | "web": bảng tự chuyển sang kết quả khi bắt đầu chạy
    gestureChanged = Signal()
    gestureScroll = Signal(float)             # cử chỉ hai ngón: px (dương = cuộn xuống) cho vùng đang xem
    toast = Signal(str, bool)

    def __init__(self, controller: Any, web_preview: bool = False) -> None:
        super().__init__()
        self.controller = controller
        self.svc = controller.code
        cfg = getattr(controller, "config", None)
        want = cfg.get("code.html_preview", True) if cfg is not None else True
        self._web = bool(web_preview and want is not False)
        self.svc.html_preview = self._web
        self._run: dict = {"active": False}
        self._open = False
        self._job: dict = self.svc.job()
        self._result: dict = {}
        self._history: list = []
        self._draft = {"prompt": "", "language": ""}
        self._gesture: dict = {"state": "IDLE", "label": "", "progress": 0.0}
        self._incoming.connect(self._handle)

    # ----- nhận từ controller (mọi luồng) -----
    def post(self, kind: str, data: dict) -> None:
        self._incoming.emit(kind, data)

    @Slot(str, object)
    def _handle(self, kind: str, data: dict) -> None:
        if kind == "code_job":
            self._job = dict(data)
            self.jobChanged.emit()
            if data.get("state") == "failed" and data.get("message"):
                self.toast.emit(str(data["message"]), True)
        elif kind == "code_result":
            try:
                self._result = result_view(self.svc.current)
            except Exception:
                log.exception("Không dựng được bản xem code")
                self._result = {}
            self.resultChanged.emit()
        elif kind == "code_history":
            self._refresh_history()
        elif kind == "code_run":
            live = self.svc.live
            try:
                self._run = live.view() if live is not None else {"active": False}
            except Exception:
                log.exception("Không dựng được bảng kết quả chạy")
                return
            self.runChanged.emit()
        elif kind == "code_open":
            if data.get("view"):
                self.showView.emit(str(data["view"]))
            if data.get("prompt"):
                self._draft = {"prompt": str(data["prompt"]), "language": str(data.get("language") or "")}
            if not self._open:
                self._open = True
                self._refresh_history()
                self._panel_mode(True)
            self.panelChanged.emit()
        elif kind == "code_close":
            if self._open:
                self.closePanel()
        elif kind == "code_gesture":
            k = data.get("kind")
            if k == "scroll":
                if self._open:
                    self.gestureScroll.emit(float(data.get("dy") or 0.0))
            elif k == "hud":
                self._gesture = {"state": str(data.get("state") or "IDLE"), "label": str(data.get("label") or ""),
                                 "progress": float(data.get("progress") or 0.0)}
                self.gestureChanged.emit()
        elif kind == "code_toast":
            self.toast.emit(str(data.get("text", "")), bool(data.get("error")))

    def _panel_mode(self, open_: bool) -> None:
        setter = getattr(self.svc, "set_panel_open", None)
        if setter is None:
            return
        try:
            setter(open_)
        except Exception:
            log.exception("Không đổi được chế độ cử chỉ của bảng code")

    def _refresh_history(self) -> None:
        try:
            self._history = self.svc.history()
            for h in self._history:
                h["languageLabel"] = LANG_LABEL.get(h.get("language", ""), h.get("language", ""))
                h["when"] = time.strftime("%H:%M %d/%m", time.localtime(h.get("created") or 0))
        except Exception:
            log.exception("Không đọc được lịch sử code")
            self._history = []
        self.historyChanged.emit()

    # ----- thuộc tính cho QML -----
    @Property(bool, notify=panelChanged)
    def panelOpen(self) -> bool:
        return self._open

    @Property("QVariantMap", notify=panelChanged)
    def draft(self) -> dict:
        return dict(self._draft)

    @Property("QVariantMap", notify=jobChanged)
    def job(self) -> dict:
        return dict(self._job)

    @Property(bool, notify=jobChanged)
    def busy(self) -> bool:
        return self._job.get("state") == "running"

    @Property("QVariantMap", notify=resultChanged)
    def result(self) -> dict:
        return self._result

    @Property("QVariantList", notify=historyChanged)
    def history(self) -> list:
        return self._history

    @Property("QVariantMap", notify=gestureChanged)
    def gesture(self) -> dict:
        return dict(self._gesture)

    @Property("QVariantMap", notify=runChanged)
    def run(self) -> dict:
        return self._run

    @Property(bool, constant=True)
    def webPreview(self) -> bool:
        return self._web

    @Property("QVariantList", constant=True)
    def languages(self) -> list:
        return [{"key": k, "label": v} for k, v in LANG_CHOICES]

    # ----- thao tác của anh -----
    @Slot()
    def openPanel(self) -> None:
        self._handle("code_open", {})

    @Slot()
    def closePanel(self) -> None:
        self._open = False
        self._panel_mode(False)
        self.panelChanged.emit()

    @Slot(str)
    def setView(self, view: str) -> None:
        """Bảng đổi khung (code / kết quả / trang) → service biết búng tay nên chạy hay tắt."""
        setter = getattr(self.svc, "set_panel_view", None)
        if setter is not None:
            setter(view)

    @Slot(str, str)
    def generate(self, prompt: str, language: str) -> None:
        self._draft = {"prompt": prompt, "language": language}
        ok, msg = self.svc.generate(prompt, language, source="keyboard")
        if not ok:
            self.toast.emit(msg, True)

    @Slot(str)
    def refine(self, instruction: str) -> None:
        ok, msg = self.svc.refine(instruction, self._result.get("id", ""))
        if not ok:
            self.toast.emit(msg, True)

    @Slot()
    def fixRunErrors(self) -> None:
        ok, msg = self.svc.refine("", self._result.get("id", ""), use_run_output=True)
        if not ok:
            self.toast.emit(msg, True)

    @Slot()
    def cancel(self) -> None:
        if not self.svc.cancel("Người dùng hủy"):
            self.toast.emit("Không có việc nào đang chạy.", False)

    @Slot()
    def runTests(self) -> None:
        ok, msg = self.svc.run_tests(self._result.get("id", ""))
        if not ok:
            self.toast.emit(msg, True)

    @Slot()
    def stopRun(self) -> None:
        if not self.svc.stop_run():
            self.toast.emit("Không có chương trình nào đang chạy.", False)

    @Slot()
    def rerun(self) -> None:
        ok, msg = self.svc.rerun()
        if not ok:
            self.toast.emit(msg, True)

    @Slot(str)
    def sendInput(self, text: str) -> None:
        if not self.svc.send_input(text):
            self.toast.emit("Chương trình không còn chờ nhập nữa.", True)

    @Slot()
    def runInConsole(self) -> None:
        ok, msg = self.svc.run_live_in_console()
        self.toast.emit(msg, not ok)

    @Slot()
    def copyRunOutput(self) -> None:
        live = self.svc.live
        if live is None:
            self.toast.emit("Chưa có kết quả chạy để sao chép.", True)
            return
        QGuiApplication.clipboard().setText(live.output_text())
        self.toast.emit("Đã sao chép toàn bộ kết quả chạy.", False)

    @Slot(int, str, int, str)
    def webConsole(self, level: int, message: str, line: int, source: str) -> None:
        self.svc.web_console(level, message, line, source)

    def _res(self) -> CodeResult | None:
        rid = self._result.get("id", "")
        cur = self.svc.current
        if cur is not None and cur.id == rid:
            return cur
        return self.svc.load(rid) if rid else None

    @Slot(int)
    def copyFile(self, index: int) -> None:
        res = self._res()
        if res is None or not 0 <= index < len(res.files):
            self.toast.emit("Không có tệp để sao chép.", True)
            return
        f = res.files[index]
        QGuiApplication.clipboard().setText(f.content)
        self.toast.emit(f"Đã sao chép {f.path} ({f.lines} dòng).", False)

    @Slot()
    def copyAll(self) -> None:
        res = self._res()
        if res is None:
            self.toast.emit("Không có code để sao chép.", True)
            return
        QGuiApplication.clipboard().setText(self.svc.all_text(res))
        self.toast.emit(f"Đã sao chép toàn bộ {len(res.files)} tệp.", False)

    @Slot()
    def save(self) -> None:
        ok, where = self.svc.save(self._result.get("id", ""))
        if not ok:
            self.toast.emit(where, True)
            return
        self.toast.emit(f"Đã lưu vào {where}", False)
        try:
            os.startfile(where)          # noqa: S606 — mở thư mục vừa lưu trong Explorer
        except OSError:
            pass

    @Slot(str)
    def openHistory(self, rid: str) -> None:
        if not self.svc.open(rid):
            self.toast.emit("Không mở được bản code này.", True)

    @Slot(str)
    def deleteHistory(self, rid: str) -> None:
        self.svc.delete(rid)
