"""Execute allowlisted UI commands on the Qt thread, with acknowledgement.

A queued command that times out or is cancelled cannot execute later. Existing
slots remain the single implementation used by buttons and commands.
"""
from __future__ import annotations

from concurrent.futures import Future, TimeoutError
import json
import math

from PySide6.QtCore import QObject, Signal, Slot

from nexa.ai.ui_commands import COMMANDS
from nexa.core.events import ToolResult


class CommandBridge(QObject):
    requested = Signal(object)

    def __init__(self, main, code, three_d, edu):
        super().__init__()
        self.targets = {"main":main, "code":code, "3d":three_d, "edu":edu}
        self.commands = {cmd.name:cmd for cmd in COMMANDS}
        self.requested.connect(self._execute)

    def dispatch(self, name, args, token):
        future = Future()
        self.requested.emit((name, args, token, future))
        try:
            return future.result(timeout=15)
        except TimeoutError:
            future.cancel()
            return ToolResult.failure("Giao diện chưa phản hồi; chưa xác minh kết quả / UI timeout.", "timeout")

    @Slot(object)
    def _execute(self, request):
        name, args, token, future = request
        if not future.set_running_or_notify_cancel():
            return
        if token.cancelled:
            future.set_result(ToolResult.failure("Đã hủy / Cancelled.", "cancelled"))
            return
        cmd = self.commands.get(name)
        if cmd is None:
            future.set_result(ToolResult.failure("Unknown UI command.", "unknown_tool"))
            return
        messages = []
        def capture(message, error):
            messages.append((message, error))
        target = self.targets.get(cmd.target)
        try:
            if target is not None:
                target.toast.connect(capture)
            if cmd.target == "settings":
                result = self._setting(args)
            elif name == "bind_media_target":
                result = target.controller.media.bind_by_id(args["target_id"])
            elif name == "set_monitor_roles":
                ok, message = target.controller.monitors.set_roles(args["src"], args["dst"])
                target.monitorsChanged.emit()
                result = ToolResult.success(message) if ok else ToolResult.failure(message)
            elif name == "apply_3d_part_action":
                ok, message = target.svc.viewer.apply_ids(args["action"], args["ids"])
                result = ToolResult.success(message) if ok else ToolResult.failure(message)
            elif cmd.target == "navigation":
                result = self._navigate(cmd.method, args)
            else:
                if cmd.target == "edu":
                    self.targets["edu"].open = True
                if name in ("export_product_media", "export_build_dossier", "refresh_build_dossier"):
                    project = target.svc.viewer.project
                    if project is None:
                        raise ValueError("Chưa mở mô hình / Open a model first.")
                    if name == "export_build_dossier" and not args.get("project_id"):
                        args = dict(args, project_id=project.id)
                    if name == "export_product_media" and target._vals["media"]["busy"]:
                        raise ValueError("Đang xuất ảnh/video / Media export is busy.")
                if name == "generate_3d_references":
                    from PySide6.QtCore import QUrl
                    from pathlib import Path
                    # Accept local paths as well as the file URLs used by the picker.
                    refs = {k:(v if v.startswith("file:") else QUrl.fromLocalFile(str(Path(v).resolve())).toString())
                            for k,v in args["references"].items()}
                    args = dict(args, references=refs)
                value = getattr(target, cmd.method)(*(args[k] for k in cmd.params))
                errors = [message for message, error in messages if error]
                if errors or value is False:
                    result = ToolResult.failure("; ".join(errors) or "Thao tác thất bại / Operation failed.")
                else:
                    # Background slots acknowledge dispatch, not eventual job completion.
                    message = str(value) if value is not None else (messages[-1][0] if messages else cmd.vi + " / " + cmd.en)
                    if cmd.background:
                        message = "Đã gửi yêu cầu / Request dispatched: " + message
                    # String-returning legacy slots may encode an error instead of raising.
                    failed = isinstance(value, str) and any(s in value.lower() for s in ("thất bại", "lỗi:", "chưa đồng ý", "chưa nhập"))
                    result = (ToolResult.failure(message) if failed else
                              ToolResult.success(message, verified=not cmd.background, in_progress=cmd.background))
            future.set_result(result)
        except Exception as exc:
            future.set_result(ToolResult.failure(str(exc)))
        finally:
            if target is not None:
                target.toast.disconnect(capture)

    def _setting(self, args):
        main = self.targets["main"]
        config = main.controller.config
        scope = args.get("scope", "settings")
        from nexa.utils.config import DEFAULTS
        source = DEFAULTS if scope == "settings" else config.gestures
        parts = args["key"].split(".")
        current = source
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                raise ValueError("Không có mục cấu hình này / Unknown setting.")
            current = current[part]
        if isinstance(current, dict) or any(word in args["key"].lower() for word in ("password", "api_key", "secret", "token")):
            raise ValueError("Chọn một mục cấu hình cụ thể; mã bí mật nhập trong Cài đặt / Use Settings for credentials.")
        raw = args["value"]
        try:
            value = json.loads(raw)
        except ValueError:
            value = raw
        if current is not None:
            if isinstance(current, bool):
                valid = isinstance(value, bool)
            elif isinstance(current, (int, float)):
                valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
                if isinstance(current, int):
                    valid = valid and isinstance(value, int)
            else:
                valid = isinstance(value, type(current))
            if not valid:
                raise ValueError("Kiểu giá trị không hợp lệ / Invalid value type.")
        elif value is not None and not isinstance(value, (str, int, float)):
            raise ValueError("Kiểu giá trị không hợp lệ / Invalid value type.")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Giá trị phải hữu hạn / Value must be finite.")
        if args["key"] == "stt.language" and value not in ("auto", "vi", "en"):
            raise ValueError("Ngôn ngữ phải là auto, vi hoặc en.")
        patch = value
        for part in reversed(parts):
            patch = {part:patch}
        message = main.saveSettings(json.dumps(patch) if scope == "settings" else "{}",
                                    json.dumps(patch) if scope == "gestures" else "")
        return ToolResult.success(message)

    def _navigate(self, action, args):
        main, code, model, edu = (self.targets[k] for k in ("main", "code", "3d", "edu"))
        if action == "code_view":
            code.openPanel()
            code.setView(args["view"])
            code.showView.emit(args["view"])
        elif action == "compact":
            main.commandNavigation.emit("compact", "on" if args["enabled"] else "off")
        else:
            panel, opened = args["panel"], action == "open"
            if panel == "edu":
                edu.open = opened
            elif panel == "code":
                code.openPanel() if opened else code.closePanel()
            elif panel == "3d":
                model.workspace = opened
                if not opened:
                    model.closeViewer()
            else:
                if panel in ("build", "media") and model.svc.viewer.project is None:
                    raise ValueError("Chưa mở mô hình / Open a model first.")
                if panel in ("build", "media") and opened:
                    code.closePanel()
                    edu.close()
                    main.commandNavigation.emit("compact", "off")
                    if not model.viewerOpen:
                        model.openModel(model.svc.viewer.project.id)
                main.commandNavigation.emit(action, panel)
        return ToolResult.success("Đã gửi yêu cầu giao diện / UI request dispatched.", verified=False)
