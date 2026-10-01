"""Cầu nối Python ⇄ QML.

Controller gọi `post(kind, data)` từ bất kỳ luồng nào; tín hiệu `_incoming` (queued connection)
chuyển sự kiện về luồng GUI trước khi cập nhật thuộc tính QML. Các thao tác chậm (kiểm tra Gemini,
quét camera, bật camera) chạy trong luồng nền.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

from nexa.core.events import Source
from nexa.utils.logging import get_logger

log = get_logger("ui")

MAX_MESSAGES = 200
MAX_TASKS = 60
STATS_INTERVAL_MS = 1500
MAX_TIMELINE = 260


class CameraImageProvider(QQuickImageProvider):
    def __init__(self, controller) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.controller = controller

    def requestImage(self, id_: str, size, requested_size):  # noqa: N802 - API Qt
        _seq, frame = self.controller.gestures.preview()
        if frame is None:
            img = QImage(320, 240, QImage.Format.Format_RGB888)
            img.fill(0x050B18)
            return img
        h, w = frame.shape[:2]
        rgb = frame[:, :, ::-1].copy()
        img = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
        return img


def _prop(type_, name: str, notify_signal):
    """Thuộc tính QML chỉ đọc lấy từ self._vals; notify phải là CHÍNH đối tượng Signal."""
    def getter(self):
        return self._vals[name]
    return Property(type_, getter, notify=notify_signal)


class UiBridge(QObject):
    _incoming = Signal(str, object)
    stateChanged = Signal()
    levelsChanged = Signal()
    messagesChanged = Signal()
    timelineChanged = Signal()
    tasksChanged = Signal()
    statusChanged = Signal()
    confirmationChanged = Signal()
    gestureChanged = Signal()
    miscChanged = Signal()
    clapChanged = Signal()
    geminiTestFinished = Signal(bool, str)
    toast = Signal(str, bool)
    calibrationFinished = Signal(str)
    cameraFrame = Signal(int)
    monitorsChanged = Signal()
    mediaTargetsChanged = Signal()
    raiseWindow = Signal()
    statsChanged = Signal()

    def __init__(self, controller, overlay=None, hud=None) -> None:
        super().__init__()
        self.controller = controller
        self.overlay = overlay
        self.hud = hud
        self._vals: dict[str, Any] = {
            "state": "INITIALIZING", "stateLabel": "Đang khởi tạo", "stateDetail": "",
            "micLevel": 0.0, "outLevel": 0.0, "outBands": [0.0] * 8, "heardText": "", "statusText": "",
            "messages": [], "tasks": [], "timeline": [], "status": {}, "confirmation": {"active": False},
            "gestureStatus": {}, "controlPaused": False, "cameraOn": False, "airMouse": False, "compact": False,
            "visionSending": False, "mediaStatus": {}, "foreground": "", "lastClap": {},
            "listeningSpeech": False, "gestureLast": {}, "attentionStatus": {},
        }
        self._frame_counter = 0
        self._incoming.connect(self._handle)
        self._stats = None
        self._stats_vals: dict[str, Any] = {}
        self._stats_timer = None
        self._library_inventory = None
        from PySide6.QtCore import QCoreApplication, QTimer
        if QCoreApplication.instance() is not None:
            self._stats_timer = QTimer(self)
            self._stats_timer.setInterval(STATS_INTERVAL_MS)
            self._stats_timer.timeout.connect(self._sample_stats)
            self._stats_timer.start()
            QTimer.singleShot(0, self._sample_stats)

    # ----- vòng thông số quanh quả cầu (CPU / RAM / GPU / độ trễ AI) -----
    def _sample_stats(self) -> None:
        if not self.controller.config.get("ui.stats_ring"):
            if self._stats_vals:
                self._stats_vals = {}
                self.statsChanged.emit()
            return
        try:
            if self._stats is None:
                from nexa.ui.sysstats import SysStats
                self._stats = SysStats()
            provider = getattr(self.controller, "provider", None)
            self._stats_vals = self._stats.sample(getattr(provider, "last_latency_ms", 0.0))
            self._stats_vals.update(self._stats.device_sample())
        except Exception:
            log.debug("Không đo được thông số máy", exc_info=True)
            self._stats_vals = {}
            if self._stats_timer is not None:
                self._stats_timer.stop()
        self.statsChanged.emit()

    @Property("QVariantMap", notify=statsChanged)
    def sysStats(self) -> dict:
        return self._stats_vals

    @Property(str, constant=True)
    def appVersion(self) -> str:
        from nexa import __version__
        return __version__

    @Property("QVariantList", constant=True)
    def libraries(self) -> list:
        if self._library_inventory is None:
            from nexa.ui.device_telemetry import library_inventory
            self._library_inventory = library_inventory()
        return self._library_inventory

    # ----- nhận từ controller (mọi luồng) -----
    def post(self, kind: str, data: dict) -> None:
        self._incoming.emit(kind, data)

    @Slot(str, object)
    def _handle(self, kind: str, data: dict) -> None:
        v = self._vals
        if kind == "state":
            v["state"], v["stateLabel"], v["stateDetail"] = data["state"], data["label"], data.get("detail", "")
            if data["state"] != "LISTENING":
                v["listeningSpeech"] = False
            if self.hud is not None:
                self.hud.state(data["state"])
            self.stateChanged.emit()
        elif kind == "mic_level":
            v["micLevel"] = float(data["value"])
            self.levelsChanged.emit()
        elif kind == "out_level":
            v["outLevel"] = float(data["value"])
            if self.hud is not None:
                self.hud.levels(level=v["outLevel"])
            self.levelsChanged.emit()
        elif kind == "out_bands":
            v["outBands"] = list(data["value"])
            if self.hud is not None:
                self.hud.levels(bands=v["outBands"])
            self.levelsChanged.emit()
        elif kind == "subtitle":
            if self.hud is not None:
                self.hud.subtitle(data.get("text", ""))
        elif kind == "speech_start":
            v["listeningSpeech"] = True
            self.stateChanged.emit()
        elif kind == "heard":
            v["heardText"] = data.get("text") or ("(" + data.get("reason", "không nghe rõ") + ")")
            v["listeningSpeech"] = False
            self.stateChanged.emit()
        elif kind in ("user_message", "assistant_message"):
            role = "user" if kind == "user_message" else "assistant"
            msg = {"role": role, "text": data["text"], "source": data.get("source", ""), "time": time.strftime("%H:%M:%S")}
            v["messages"] = (v["messages"] + [msg])[-MAX_MESSAGES:]
            self._timeline_add(dict(msg, kind="msg"))
            self.messagesChanged.emit()
        elif kind == "clear_chat":
            v["messages"] = []
            v["timeline"] = []
            self.messagesChanged.emit()
            self.timelineChanged.emit()
        elif kind == "task":
            v["tasks"] = ([data] + v["tasks"])[:MAX_TASKS]
            self._timeline_task(data)
            if self.hud is not None:
                self.hud.task(data)
            self.tasksChanged.emit()
        elif kind == "status":
            v["status"] = data
            v["controlPaused"] = bool(data.get("control_paused"))
            self.statusChanged.emit()
        elif kind == "status_text":
            v["statusText"] = data.get("text", "")
            self.miscChanged.emit()
        elif kind == "confirmation":
            if data.get("active") and data.get("preview"):
                data = dict(data, previewUrl=QUrl.fromLocalFile(data["preview"]).toString())
            v["confirmation"] = data
            self.confirmationChanged.emit()
        elif kind == "gesture_status":
            v["gestureStatus"] = data
            self._frame_counter += 1
            self.gestureChanged.emit()
            self.cameraFrame.emit(self._frame_counter)
        elif kind == "attention_status":
            v["attentionStatus"] = data
            self.gestureChanged.emit()
        elif kind == "gesture_result":
            v["gestureLast"] = dict(data, time=time.strftime("%H:%M:%S"))
            self.gestureChanged.emit()
        elif kind == "camera":
            v["cameraOn"] = bool(data.get("on"))
            if not v["cameraOn"]:
                v["airMouse"] = False
            if data.get("error") and not data.get("on"):
                self.toast.emit(data["error"], True)
            self.miscChanged.emit()
        elif kind == "air_mouse":
            v["airMouse"] = bool(data.get("on"))
            self.miscChanged.emit()
        elif kind == "control_paused":
            v["controlPaused"] = bool(data.get("paused"))
            self.statusChanged.emit()
        elif kind == "vision_sending":
            v["visionSending"] = bool(data.get("active"))
            self.miscChanged.emit()
        elif kind == "media":
            v["mediaStatus"] = data
            self.miscChanged.emit()
        elif kind == "media_targets":
            self.mediaTargetsChanged.emit()
        elif kind == "foreground":
            v["foreground"] = f"{data.get('process', '')} — {data.get('title', '')}"
            self.miscChanged.emit()
        elif kind == "clap":
            v["lastClap"] = dict(data, time=time.strftime("%H:%M:%S"))
            self.clapChanged.emit()
        elif kind == "raise_window":
            self.raiseWindow.emit()
        elif kind == "quit":
            from PySide6.QtGui import QGuiApplication
            QGuiApplication.quit()
        elif kind == "mic_error":
            self.toast.emit(data.get("text", ""), True)
        elif kind == "stt_status":
            if data.get("error"):
                self.toast.emit(data["error"], True)
        elif kind == "overlay":
            if self.overlay is not None:
                self.overlay.handle(data)
            if data.get("kind") == "toast":
                self.toast.emit(data.get("text", ""), bool(data.get("error")))

    # ----- dòng thời gian hội thoại: tin nhắn + thẻ tác vụ xen giữa -----
    def _timeline_add(self, item: dict) -> None:
        self._vals["timeline"] = (self._vals["timeline"] + [item])[-MAX_TIMELINE:]
        self.timelineChanged.emit()

    def _timeline_task(self, data: dict) -> None:
        """Một bước tác vụ = một thẻ: các sự kiện sau (đang chạy → xong/lỗi) cập nhật đúng thẻ đó."""
        key = f"{data.get('task_id', '')}/{data.get('step_id', '')}/{data.get('tool', '')}"
        card = {"kind": "task", "key": key, "title": data.get("title", ""), "status": data.get("status", ""),
                "text": data.get("message", ""), "source": data.get("source", ""),
                "time": data.get("time") or time.strftime("%H:%M:%S")}
        tl = self._vals["timeline"]
        for i in range(len(tl) - 1, max(-1, len(tl) - 40), -1):
            if tl[i].get("key") == key:
                self._vals["timeline"] = tl[:i] + [card] + tl[i + 1:]
                self.timelineChanged.emit()
                return
        self._timeline_add(card)

    # ----- thuộc tính QML -----
    state = _prop(str, "state", stateChanged)
    stateLabel = _prop(str, "stateLabel", stateChanged)
    stateDetail = _prop(str, "stateDetail", stateChanged)
    heardText = _prop(str, "heardText", stateChanged)
    listeningSpeech = _prop(bool, "listeningSpeech", stateChanged)
    micLevel = _prop(float, "micLevel", levelsChanged)
    outLevel = _prop(float, "outLevel", levelsChanged)
    outBands = _prop("QVariantList", "outBands", levelsChanged)
    messages = _prop("QVariantList", "messages", messagesChanged)
    timeline = _prop("QVariantList", "timeline", timelineChanged)
    tasks = _prop("QVariantList", "tasks", tasksChanged)
    status = _prop("QVariantMap", "status", statusChanged)
    controlPaused = _prop(bool, "controlPaused", statusChanged)
    confirmation = _prop("QVariantMap", "confirmation", confirmationChanged)
    gestureStatus = _prop("QVariantMap", "gestureStatus", gestureChanged)
    gestureLast = _prop("QVariantMap", "gestureLast", gestureChanged)
    attentionStatus = _prop("QVariantMap", "attentionStatus", gestureChanged)
    statusText = _prop(str, "statusText", miscChanged)
    cameraOn = _prop(bool, "cameraOn", miscChanged)
    airMouse = _prop(bool, "airMouse", miscChanged)
    visionSending = _prop(bool, "visionSending", miscChanged)
    mediaStatus = _prop("QVariantMap", "mediaStatus", miscChanged)
    foreground = _prop(str, "foreground", miscChanged)
    lastClap = _prop("QVariantMap", "lastClap", clapChanged)

    def _get_compact(self) -> bool:
        return self._vals["compact"]

    def _set_compact(self, value: bool) -> None:
        if self._vals["compact"] != bool(value):
            self._vals["compact"] = bool(value)
            self.miscChanged.emit()

    compact = Property(bool, _get_compact, _set_compact, notify=miscChanged)

    @Property(str, constant=True)
    def smokeOpen(self) -> str:
        """Chỉ dùng cho kiểm thử khói: NEXA_SMOKE_OPEN=settings|gestures mở sẵn màn hình tương ứng."""
        import os
        return os.environ.get("NEXA_SMOKE_OPEN", "")

    @Property(str, notify=miscChanged)
    def effects(self) -> str:
        return self.controller.config.get("ui.effects") or "full"

    @Property(bool, notify=miscChanged)
    def showFps(self) -> bool:
        return bool(self.controller.config.get("ui.show_fps"))

    # ----- hành động -----
    @Slot()
    def wake(self) -> None:
        self.controller.wake("manual")

    @Slot()
    def pushToTalk(self) -> None:
        self.controller.push_to_talk()

    @Slot(str)
    def sendText(self, text: str) -> None:
        self.controller.submit_text(text, Source.KEYBOARD)

    @Slot()
    def stop(self) -> None:
        self.controller.emergency_stop("Nút DỪNG")

    @Slot()
    def resumeControl(self) -> None:
        self.controller.resume_control()

    @Slot()
    def cancelTask(self) -> None:
        self.controller.cancel_task()

    @Slot()
    def sleep(self) -> None:
        self.controller.go_standby("Vỗ tay để đánh thức")

    @Slot(str, float, float, float, float)
    def confirm(self, confirm_id: str, x: float, y: float, w: float, h: float) -> None:
        crop = [x, y, w, h] if w > 0 and h > 0 else None
        self.controller.resolve_confirmation(confirm_id, True, crop)

    @Slot(str)
    def deny(self, confirm_id: str) -> None:
        self.controller.resolve_confirmation(confirm_id, False)

    @Slot()
    def toggleGestures(self) -> None:
        target = not self.controller.gestures.running
        threading.Thread(target=lambda: self._toggle_gestures(target), daemon=True).start()

    def _toggle_gestures(self, on: bool) -> None:
        r = self.controller.set_gesture_mode(on)
        self.post("overlay", {"kind": "toast", "text": r.message, "error": not r.ok})

    @Slot()
    def toggleAirMouse(self) -> None:
        target = not self.controller.gestures.mouse_mode
        threading.Thread(target=lambda: self._toggle_air_mouse(target), daemon=True).start()

    def _toggle_air_mouse(self, on: bool) -> None:
        r = self.controller.set_air_mouse(on)
        self.post("overlay", {"kind": "toast", "text": r.message, "error": not r.ok})

    # ----- chú ý qua webcam: tự khóa khi rời máy, chọn màn hình theo hướng quay đầu -----
    def _run_toast(self, fn) -> None:
        def run() -> None:
            r = fn()
            self.post("overlay", {"kind": "toast", "text": r.message, "error": not r.ok})
            self.post("attention_status", self.controller.attention.status())
        threading.Thread(target=run, daemon=True).start()

    @Slot()
    def refreshAttention(self) -> None:
        self.post("attention_status", self.controller.attention.status())

    @Slot(bool)
    def setPresence(self, on: bool) -> None:
        self._run_toast(lambda: self.controller.set_presence(bool(on)))

    @Slot(str)
    def setHeadTarget(self, mode: str) -> None:
        self._run_toast(lambda: self.controller.set_head_target(mode))

    @Slot()
    def calibrateHead(self) -> None:
        self._run_toast(self.controller.calibrate_head)

    @Slot(bool)
    def setPreviewEnabled(self, on: bool) -> None:
        self.controller.gestures.preview_enabled = bool(on)

    @Property(bool, notify=miscChanged)
    def showLandmarks(self) -> bool:
        return bool(self.controller.config.get("gestures.show_landmarks"))

    @Slot(bool)
    def setShowLandmarks(self, on: bool) -> None:
        self.controller.config.set("gestures.show_landmarks", bool(on))
        self.controller.config.save()
        self.miscChanged.emit()

    @Slot()
    def clearConversation(self) -> None:
        self.controller.provider.clear_history()
        self._vals["messages"] = []
        self._vals["timeline"] = []
        self.messagesChanged.emit()
        self.timelineChanged.emit()
        self.toast.emit("Đã xóa hội thoại trong phiên.", False)

    @Slot()
    def quit(self) -> None:
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.quit()

    # ----- Settings -----
    @Slot(result=str)
    def settingsJson(self) -> str:
        data = self.controller.config.snapshot()
        return json.dumps(data, ensure_ascii=False)

    @Slot(result=str)
    def gesturesJson(self) -> str:
        return json.dumps(self.controller.config.gestures, ensure_ascii=False)

    @Slot(str, str, result=str)
    def saveSettings(self, settings_json: str, gestures_json: str) -> str:
        try:
            patch = json.loads(settings_json) if settings_json else {}
            gpatch = json.loads(gestures_json) if gestures_json else None
        except json.JSONDecodeError as exc:
            return f"Dữ liệu cài đặt không hợp lệ: {exc}"
        msg = self.controller.apply_settings(patch, gpatch)
        self.miscChanged.emit()
        return msg

    # --- Tự mở khóa khi vỗ tay: mã đi thẳng qua pipe tới dịch vụ, KHÔNG qua settings.yaml ---
    @Slot(str, result=str)
    def setUnlockPassword(self, password: str) -> str:
        if not password:
            return "Chưa nhập mã."
        try:
            from nexa.desktop import unlock
            if not unlock.ping():
                return "Chưa cài/khởi động dịch vụ mở khóa. Bấm 'Cài dịch vụ' trước."
            return "Đã lưu mã mở khóa." if unlock.set_password(password) else "Lưu mã thất bại."
        except Exception as exc:
            return f"Lỗi: {exc}"

    @Slot(result=str)
    def clearUnlockPassword(self) -> str:
        try:
            from nexa.desktop import unlock
            return "Đã xóa mã đã lưu." if unlock.clear_password() else "Xóa mã thất bại."
        except Exception as exc:
            return f"Lỗi: {exc}"

    @Slot(result=str)
    def installUnlockService(self) -> str:
        try:
            from nexa.desktop import admin, unlock
            if admin.is_admin():
                return "Đã cài và khởi động dịch vụ." if unlock.install_service() else "Cài dịch vụ thất bại."
            # Chưa có quyền admin: mở UAC chạy lại NEXA với sentinel cài dịch vụ rồi thoát.
            if unlock.elevate_and_run("--nexa-install-unlock-service"):
                return "Đang cài dịch vụ (cửa sổ quyền quản trị) — bấm Làm mới để xem trạng thái."
            return "Anh chưa đồng ý cấp quyền quản trị nên chưa cài được dịch vụ."
        except Exception as exc:
            return f"Lỗi: {exc}"

    @Slot(result=str)
    def uninstallUnlockService(self) -> str:
        try:
            from nexa.desktop import admin, unlock
            if admin.is_admin():
                return "Đã gỡ dịch vụ." if unlock.uninstall_service() else "Gỡ dịch vụ thất bại."
            if unlock.elevate_and_run("--nexa-uninstall-unlock-service"):
                return "Đang gỡ dịch vụ (cửa sổ quyền quản trị)."
            return "Anh chưa đồng ý cấp quyền quản trị."
        except Exception as exc:
            return f"Lỗi: {exc}"

    @Slot(result=str)
    def unlockServiceStatus(self) -> str:
        try:
            from nexa.desktop import unlock
            return json.dumps(unlock.service_status(), ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"installed": False, "running": False, "error": str(exc)})

    @Slot(result="QVariantList")
    def inputDevices(self) -> list:
        from nexa.audio.pipeline import AudioPipeline
        try:
            return [d["name"] for d in AudioPipeline.list_input_devices(self.controller.config.get("audio.preferred_hostapi") or "MME")]
        except Exception as exc:
            return [f"(lỗi: {exc})"]

    @Slot(result="QVariantList")
    def outputDevices(self) -> list:
        from nexa.audio.pipeline import AudioPipeline
        try:
            return [d["name"] for d in AudioPipeline.list_output_devices(self.controller.config.get("audio.preferred_hostapi") or "MME")]
        except Exception as exc:
            return [f"(lỗi: {exc})"]

    @Slot(result="QVariantList")
    def cameras(self) -> list:
        if self.controller.gestures.running:
            idx = self.controller.config.get("gestures.camera_index")
            return [{"index": idx, "name": f"Camera {idx} (đang dùng)"}]
        from nexa.vision.camera import list_cameras
        return list_cameras()

    @Slot(result="QVariantList")
    def sttModels(self) -> list:
        from nexa.audio.stt import SUPPORTED_MODELS
        return SUPPORTED_MODELS

    @Slot(result="QVariantList")
    def ttsBackends(self) -> list:
        return self.controller.tts.describe_backends()

    @Slot(result="QVariantList")
    def winrtVoices(self) -> list:
        return self.controller.tts.winrt_voices()

    @Slot()
    def testTts(self) -> None:
        self.controller.tts.speak("Chào anh Sơn, đây là giọng nói thử của Nexa.")

    @Slot()
    def testGemini(self) -> None:
        def run() -> None:
            ok, msg = self.controller.test_gemini()
            self.geminiTestFinished.emit(ok, msg)
        threading.Thread(target=run, daemon=True).start()

    @Slot(str, bool, result=str)
    def setApiKey(self, key: str, persist: bool) -> str:
        return self.controller.set_api_key(key, persist)

    @Slot(bool)
    def setCloudVision(self, on: bool) -> None:
        self.controller.config.set_cloud_screen_vision(bool(on))
        self.controller.push_status()

    @Slot(str)
    def setGeminiModel(self, model: str) -> None:
        self.controller.config.set_gemini_model(model)
        self.controller.config.save()
        self.controller.push_status()

    # ----- màn hình -----
    @Slot(result="QVariantList")
    def monitors(self) -> list:
        return self.controller.monitors.describe()

    @Slot(result="QVariantList")
    def edgeVoices(self) -> list:
        from nexa.audio.tts import EDGE_VOICES
        return EDGE_VOICES

    @Slot(result="QVariantList")
    def voiceEffects(self) -> list:
        from nexa.audio.voice_fx import EFFECTS
        return list(EFFECTS)

    @Slot()
    def testHud(self) -> None:
        """Nút "Xem thử HUD" trong Cài đặt: một câu phụ đề + một thẻ kết quả, không phát âm thanh."""
        if self.hud is None:
            return
        self.hud.subtitle("Dạ, đây là phụ đề HUD của Nexa.")
        self.hud.task({"status": "done", "title": "Xem thử HUD", "message": "Thẻ kết quả tự ẩn sau vài giây."})
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2500, lambda: self.hud.subtitle(""))

    @Slot()
    def identifyMonitors(self) -> None:
        if self.overlay is not None:
            self.overlay.identify(self.controller.monitors.describe())

    @Slot(str, str, result=str)
    def setMonitorRoles(self, src: str, dst: str) -> str:
        ok, msg = self.controller.monitors.set_roles(src, dst)
        self.monitorsChanged.emit()
        return msg

    # ----- YouTube -----
    @Slot(result="QVariantList")
    def mediaTargets(self) -> list:
        return self.controller.media_targets()

    @Slot(str, result=str)
    def bindMedia(self, target_id: str) -> str:
        return self.controller.media.bind_by_id(target_id).message

    @Slot()
    def refreshMedia(self) -> None:
        threading.Thread(target=lambda: (self.controller.bridge.refresh(), self.mediaTargetsChanged.emit()),
                         daemon=True).start()

    # ----- vỗ tay -----
    @Slot(bool)
    def setClapTest(self, on: bool) -> None:
        self.controller.clap_test = bool(on)

    @Slot()
    def recalibrateClap(self) -> None:
        self.controller.audio.clap.recalibrate()
        self.toast.emit("Đang hiệu chuẩn tiếng ồn nền 2 giây — anh giữ yên lặng.", False)

    @Slot(result="QVariantMap")
    def clapStats(self) -> dict:
        return self.controller.audio.clap.stats()

    # ----- cử chỉ -----
    @Slot(str)
    def calibrateGesture(self, step: str) -> None:
        if not self.controller.gestures.running:
            self.calibrationFinished.emit("Anh bật chế độ cử chỉ trước khi hiệu chuẩn.")
            return
        self.controller.gestures.calibrate(step, lambda msg: self.calibrationFinished.emit(msg))

    @Slot(result=str)
    def logPath(self) -> str:
        from nexa.utils.config import LOG_DIR
        return str(Path(LOG_DIR) / "nexa.log")
