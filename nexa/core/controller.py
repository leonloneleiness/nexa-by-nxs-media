"""Bộ điều phối trung tâm của NEXA.

Mọi đầu vào (giọng nói, bàn phím, nút nhấn để nói) đi qua CÙNG một hàng đợi lệnh và bộ xử lý:
    văn bản -> IntentRouter -> (lệnh cơ bản | Gemini) -> Executor -> phản hồi (chữ + giọng nói)
Cử chỉ đi qua GestureRouter -> cùng Executor/tool registry (không qua Gemini).

Controller không đụng tới Qt; mọi cập nhật giao diện được gửi qua `notify(kind, data)` và lớp UI
tự chuyển về luồng chính.
"""
from __future__ import annotations

import queue
import threading
import time
import uuid
from typing import Any, Callable

import numpy as np

from nexa import DISPLAY_NAME
from nexa.ai.gemini_provider import AIError, GeminiProvider
from nexa.ai.intent_router import IntentRouter
from nexa.ai.prompts import context_note
from nexa.ai.screen_vision import ScreenVision
from nexa.ai.tool_registry import Services, build_registry
from nexa.audio.pipeline import AudioPipeline
from nexa.audio.stt import SpeechRecognizer
from nexa.audio.tts import TTSManager
from nexa.core.events import STATE_LABELS_VI, AppState, Source, TaskEvent, ToolCall, ToolResult, new_task_id
from nexa.core.executor import Executor
from nexa.core.safety import Cancelled, PendingConfirmation, SafetyManager
from nexa.core.state_machine import StateMachine
from nexa.utils.config import ASSETS_DIR, MODELS_DIR, Config
from nexa.utils.logging import get_logger
from nexa.utils.text import truncate

log = get_logger("controller")

Notify = Callable[[str, dict], None]

SHORT_GREETING = "Dạ, em nghe."
UNCLEAR_PROMPT = "Em nghe chưa rõ, anh nói lại giúp em."
WAIT_PROMPT = "Dạ, anh chờ em chút."
GEMINI_BUSY_PROMPT = "Máy chủ Gemini đang quá tải, anh hỏi lại sau giúp em nhé."
WAIT_PROMPT_AFTER_S = 2.0      # Gemini chưa trả lời sau chừng này giây thì báo cho anh biết em vẫn đang làm
# Loại câu vẫn chạy dù Whisper kém chắc chắn: đã khớp đúng mẫu lệnh nên không phải đoán.
TRUSTED_ROUTES = {"basic", "stop", "cancel", "confirm", "deny", "sleep", "internal"}
# Lệnh làm anh muốn NGHE âm thanh: sau các lệnh này không vặn nhỏ ứng dụng khác nữa trong phiên hiện tại.
MEDIA_START_TOOLS = {"play_youtube", "youtube_resume", "open_url"}
# Câu hay nói: tổng hợp sẵn lúc khởi động để khi cần phát ngay, không chờ dịch vụ giọng online (~2 s).
PREWARM_PHRASES = [SHORT_GREETING, UNCLEAR_PROMPT, WAIT_PROMPT, GEMINI_BUSY_PROMPT, "Dạ.", "Xong rồi ạ.",
                   "Em đã dừng.", "Đã tạm dừng.", "Đã phát tiếp.", "Đã mở video đầu tiên.", "Đã mở Visual Studio Code.", "Đã thu nhỏ cửa sổ.", "Đã chụp màn hình.",
                   "Em chưa làm được."]


def brief_speech(message: str, max_len: int = 90) -> str:
    """Bản đọc ngắn của MỘT thông báo: bỏ phần sau ': ' (tên video/cửa sổ) và ngoặc đơn, giữ câu đầu.

    "Đã mở video đầu tiên: Tóc Tiên - Ngày Mai (Official MV) ft. Hoàng Touliver." → "Đã mở video đầu tiên."
    """
    import re
    t = (message or "").split(": ", 1)[0]
    t = re.sub(r"\s*\([^)]*\)", "", t).strip()
    t = re.split(r"(?<=[.!?])\s+", t)[0].rstrip(" ,;")
    if t and t[-1] not in ".!?":
        t += "."
    return truncate(t, max_len)


def _ms_since_last_input() -> int | None:
    """Số ms kể từ lần gõ phím/di chuột/nhấp gần nhất của người dùng (GetLastInputInfo)."""
    import ctypes
    from ctypes import wintypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
    try:
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        return int((ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF)
    except Exception:
        return None


class Controller:
    def __init__(self, config: Config, notify: Notify) -> None:
        self.config = config
        self._notify_cb = notify
        self.session_id = uuid.uuid4().hex[:8]
        self.sm = StateMachine()
        self.safety = SafetyManager()
        self.sm.add_listener(self._on_state)

        # ----- Desktop -----
        from nexa.desktop.apps_and_files import AppLauncher, FileService, Screenshotter
        from nexa.desktop.bridge_server import BridgeServer
        from nexa.desktop.input_control import InputController
        from nexa.desktop.media import BridgeBackend, GsmtcBackend, MediaController, MediaTarget
        from nexa.desktop.monitors import MonitorManager
        from nexa.desktop.sleep_guard import ButtonRemap, SleepGuard
        from nexa.desktop.system import MediaDucker, VolumeControl
        from nexa.desktop.win32api import Win32Api
        from nexa.desktop.window_history import WindowHistory
        from nexa.desktop.windows import WindowManager
        self._MediaTarget = MediaTarget
        self.api = Win32Api()
        self.monitors = MonitorManager(self.api, config)
        self.history = WindowHistory(self.session_id)
        self.wm = WindowManager(self.api, self.monitors, self.history)
        self.input = InputController(get_foreground=self.api.get_foreground)
        self.apps = AppLauncher(config, self.wm)
        self.bridge = BridgeServer(on_event=self._on_bridge_event)
        backends: dict[str, Any] = {"bridge": BridgeBackend(self.bridge)}
        try:
            backends["gsmtc"] = GsmtcBackend()
        except Exception:
            log.exception("GSMTC không khả dụng")
        from nexa.desktop.youtube_ads import AutoSkipper
        self.ad_skipper = AutoSkipper(self.wm)
        self.media = MediaController(backends, preferred=config.get("media.backend") or "auto")
        self.media.listeners.append(lambda st: self.notify("media", st))

        # ----- AI -----
        from nexa.utils.config import LOCAL_DATA_DIR
        self.provider = GeminiProvider(config, state_path=LOCAL_DATA_DIR / "gemini_state.json")
        self.vision = ScreenVision(config, self.provider, notify=self.notify)
        self.services = Services(config=config, wm=self.wm, monitors=self.monitors, input=self.input, apps=self.apps,
                                 files=FileService(config), shots=Screenshotter(config), volume=VolumeControl(),
                                 media=self.media, vision=self.vision,
                                 hooks={"set_gesture_mode": self.set_gesture_mode, "set_air_mouse": self.set_air_mouse,
                                        "ad_skipper": self.ad_skipper, "quit": self.request_quit,
                                        "guard_sleep": self.guard_sleep},
                                 notify=lambda kind, data: self.notify("overlay", dict(data, kind=kind)))
        self.registry = build_registry(config)
        self.executor = Executor(self.registry, self.safety, self.services,
                                 autonomy=lambda: (self.config.get("safety.autonomy") or "standard"))
        self.executor.add_listener(self._on_task_event)
        self.executor.add_confirm_hook(self._on_confirm_hook)
        # ----- Mô hình 3D (nexa/three_d): job chạy nền, token gắn epoch an toàn (dừng khẩn cấp/hủy tự hủy job) -----
        from nexa.three_d.service import ThreeDService
        self.three_d = ThreeDService(config, notify=self.notify, gemini=self.provider,
                                     token_factory=lambda: self.safety.new_token("3d"))
        self.three_d.on_message = lambda text, spoken: self.reply(text, spoken=spoken)
        self.three_d.on_resume = lambda tpl: setattr(self, "_resume", tpl)
        self.three_d.on_viewer_mode = self._on_viewer_mode
        self.services.three_d = self.three_d
        # ----- Sinh code (nexa/code): việc nền, hiện trên bảng Sinh code để anh xem trước; không tự sao chép/chạy -----
        from nexa.code.service import CodeService
        self.code = CodeService(config, notify=self.notify, gemini=self.provider,
                                token_factory=lambda: self.safety.new_token("code"))
        self.code.on_message = lambda text, spoken: self.reply(text, spoken=spoken)
        self.code.on_panel_mode = self._on_code_panel
        self.services.code = self.code
        self.services.files.run_hook = self._run_file_hook
        # Cửa sổ NEXA mở ra (ứng dụng, web, tệp, console chạy thử) được xếp CẠNH NEXA — không che/ẩn NEXA.
        from nexa.desktop.side_by_side import SideBySide
        self.services.side_by_side = SideBySide(config, self.api)
        self.router = IntentRouter(app_exists=lambda n: self.apps.resolve(n)[0] is not None,
                                   viewer_active=lambda: self.three_d.viewer_active, part_known=self._part_known,
                                   routine_for=self._routine_for)

        # ----- Cử chỉ -----
        from nexa.vision.engine import GestureEngine
        from nexa.vision.gesture_router import GestureRouter
        self.gesture_router = GestureRouter(self.executor, self.safety, config, on_result=self._on_gesture_result)
        from nexa.vision.air_mouse import AirMouse, InputMouseOutput, MouseParams
        self._monitor_cache: tuple[float, list, Any] = (-1e9, [], None)
        self.air_mouse = AirMouse(MouseParams.from_config(config.gestures), InputMouseOutput(self.input),
                                  monitors=lambda: self._monitor_rects()[0], primary=lambda: self._monitor_rects()[1],
                                  can_control=lambda: not self.safety.control_paused
                                  and self.executor.control_owner is None)
        self.gestures = GestureEngine(config, MODELS_DIR, self.wm, self.gesture_router,
                                      on_status=lambda st: self.notify("gesture_status", st),
                                      air_mouse=self.air_mouse,
                                      on_failsafe=lambda: self.emergency_stop("Chuột vào góc màn hình (fail-safe)"))
        # ----- Chú ý qua webcam: có ngồi ở máy + đang nhìn màn hình nào (nexa/core/attention.py) -----
        from nexa.core.attention import AttentionService
        self.attention = AttentionService(
            config, self.wm, self.monitors, self.media, notify=self.notify,
            input_idle_s=lambda: (None if (ms := _ms_since_last_input()) is None else ms / 1000.0),
            can_act=lambda: not self.safety.control_paused and self.executor.control_owner is None,
            camera_running=lambda: self.gestures.running,
            move_cursor=lambda x, y: self.input.move(x, y), cursor_pos=self.api.cursor_pos)
        self.gestures.face_consumer = self.attention
        self.gestures.before_snapshot = self.attention.before_gesture
        self.services.hooks.update({"set_presence": self.set_presence, "set_head_target": self.set_head_target,
                                    "calibrate_head": self.calibrate_head})

        # ----- Âm thanh -----
        from nexa.audio.context_bias import ContextBias, win32_windows_provider
        from nexa.research.corpus import CorpusRecorder
        self.stt_bias = ContextBias(config, win32_windows_provider(self.api))
        self.stt = SpeechRecognizer(config, MODELS_DIR, bias=self.stt_bias)
        self.corpus = CorpusRecorder(config, LOCAL_DATA_DIR / "asr_corpus")
        self.tts = TTSManager(config, ASSETS_DIR, on_start=self._tts_start, on_end=self._tts_end,
                              on_level=lambda v: self.notify("out_level", {"value": v}),
                              on_bands=lambda b: self.notify("out_bands", {"value": b}),
                              on_chunk=lambda t: self.notify("subtitle", {"text": t}),
                              on_status=lambda s: (self.notify("status_text", {"text": s}), self.push_status()),
                              on_idle=self._tts_idle)
        self.audio = AudioPipeline(config, on_clap=self._on_clap,
                                   on_level=lambda v: self.notify("mic_level", {"value": v}),
                                   on_utterance=self._on_utterance, on_speech_start=self._on_speech_start,
                                   on_listen_timeout=self._on_listen_timeout,
                                   on_error=lambda e: self.notify("mic_error", {"text": e}),
                                   on_snap=self._on_snap,
                                   snap_gate=lambda: self.code.panel_open or self.three_d.viewer.is_open)

        self.safety.on_stop(self._on_emergency)
        self.safety.on_confirmation(self._on_confirmation)

        self._stt_q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=2)
        self._cmd_q: "queue.Queue[tuple[str, Source] | None]" = queue.Queue(maxsize=8)
        self._running = False
        self._awake = False
        self._greeted = False
        # Nhạc/video lọt vào mic làm nghe sai: vặn nhỏ ứng dụng khác trong lúc nghe. Sau lệnh mở/phát nhạc thì
        # thôi vặn nhỏ ở các lượt nghe tiếp theo của phiên (để anh nghe được thứ vừa mở).
        self.ducker = MediaDucker(float(config.get("audio.duck_level") or 0.2)) \
            if config.get("audio.duck_media", True) else None
        self._duck_session = False
        # Vừa mở nhạc/video: vẫn vặn nhỏ khi nghe lệnh tiếp (nhạc to làm nghe sai và không biết anh nói xong),
        # nhưng hết một lượt chờ không ai nói thì về chế độ chờ để trả nhạc về âm lượng cũ.
        self._media_playing = False
        self._media_ignored = 0
        self._resume: str | None = None
        self._ai_thread: threading.Thread | None = None
        self._ai_token = None
        self._ai_busy = threading.Event()
        self._basic_busy = threading.Event()
        self._last_activity = time.monotonic()
        self._then_standby = False
        self._companion = False
        self.clap_test = False
        # Ngủ canh gác: máy không tự ngủ để NEXA còn nghe vỗ tay (xem nexa/desktop/sleep_guard.py).
        from nexa.utils.config import LOCAL_DATA_DIR as _data_dir
        self.sleep_guard = SleepGuard(on_resumed=self._on_system_resumed, on_display=self._on_display_state,
                                      buttons=ButtonRemap(_data_dir / "power_buttons_backup.json"))
        self._guard_asleep = False          # NEXA đã tắt màn hình theo lệnh "cho máy ngủ"
        self._no_lock_applied = False       # đã nhờ dịch vụ tắt yêu cầu mật khẩu khi thức dậy
        self._unlock_waiter: threading.Thread | None = None
        self.hotkeys = None
        self._threads: list[threading.Thread] = []

    # ================================================================ vòng đời
    def start(self) -> None:
        self._running = True
        self.executor.start()
        if not self.bridge.start():
            self.notify("status_text", {"text": self.bridge.error})
        self._start_hotkeys()
        for target, name in ((self._stt_worker, "nexa-stt"), (self._cmd_worker, "nexa-cmd"),
                             (self._foreground_poller, "nexa-fg")):
            t = threading.Thread(target=target, name=name, daemon=True)
            t.start()
            self._threads.append(t)
        if not self.audio.start():
            self.notify("status_text", {"text": self.audio.error + " — anh vẫn có thể dùng ô nhập lệnh và nút Đánh thức."})
        threading.Thread(target=self._load_stt, name="nexa-stt-load", daemon=True).start()
        # Tổng hợp trước các câu hay dùng để lần nói đầu không phải chờ mạng.
        self.tts.prewarm([self.config.get("session.greeting") or "Chào anh Sơn, em là Nexa. Em sẵn sàng.",
                          *PREWARM_PHRASES])
        self._apply_sleep_guard()
        threading.Thread(target=self._mic_watchdog, name="nexa-mic-watchdog", daemon=True).start()
        self.sm.set(AppState.STANDBY, "Đang chờ tiếng vỗ tay")
        ok, reason = self.provider.status()
        self.notify("status_text", {"text": f"{DISPLAY_NAME} sẵn sàng. " + (
            f"AI: {reason}." if ok else f"Chế độ lệnh cơ bản ({reason})")})
        self.push_status()
        if self.config.get("youtube.auto_skip_ads"):
            self.ad_skipper.start()
            log.info("Tự bỏ qua quảng cáo YouTube: BẬT")
        if self.config.get("gestures.enabled_on_start"):
            threading.Thread(target=lambda: self.set_gesture_mode(True), daemon=True).start()

    def request_quit(self) -> None:
        """Thoát NEXA (dùng khi khởi động lại với quyền quản trị)."""
        self.notify("quit", {})

    def shutdown(self) -> None:
        log.info("Đang tắt NEXA…")
        self._running = False
        self.safety.cancel_current("shutdown")
        try:
            self._cmd_q.put_nowait(None)
        except queue.Full:
            pass
        if self.ducker is not None:
            self.ducker.stop()
        self.ad_skipper.stop()
        if self._no_lock_applied:
            # Trả lại yêu cầu mật khẩu khi thức dậy trước khi thoát.
            try:
                from nexa.desktop import unlock
                if unlock.set_no_lock(False):
                    self._no_lock_applied = False
            except Exception:
                log.exception("Không trả lại được yêu cầu mật khẩu khi thức")
        for fn in (self.sleep_guard.disable, self.three_d.shutdown, self.code.shutdown, self.gestures.stop, self.audio.stop, self.tts.shutdown,
                   self.gesture_router.stop, self.executor.stop, self.bridge.stop, self.provider.shutdown,
                   self.input.release_all):
            try:
                fn()
            except Exception:
                log.exception("Lỗi khi tắt %s", getattr(fn, "__qualname__", fn))
        if self.hotkeys:
            self.hotkeys.stop()
        log.info("NEXA đã tắt")

    def _start_hotkeys(self) -> None:
        from nexa.core.hotkeys import GlobalHotkeys
        self.hotkeys = GlobalHotkeys({
            "emergency_stop": (self.config.get("hotkeys.emergency_stop") or "ctrl+alt+escape",
                               lambda: self.emergency_stop("Phím tắt Ctrl+Alt+Esc")),
            "wake": (self.config.get("hotkeys.wake") or "ctrl+alt+n", lambda: self.wake("hotkey")),
        })
        self.hotkeys.start()
        for name, err in self.hotkeys.failed.items():
            self.notify("status_text", {"text": f"Không đăng ký được phím tắt {name}: {err}"})

    def _load_stt(self) -> None:
        self.notify("stt_status", {"loading": True, "text": "Đang nạp model nhận dạng giọng nói…"})
        ok = self.stt.load(on_status=lambda s: self.notify("status_text", {"text": s}))
        self.notify("stt_status", {"loading": False, "ready": ok, "model": self.stt.model_name, "error": self.stt.error})
        self.push_status()

    # ================================================================ thông báo UI
    def notify(self, kind: str, data: dict | None = None) -> None:
        try:
            self._notify_cb(kind, data or {})
        except Exception:
            log.exception("notify lỗi")

    def push_status(self) -> None:
        ai_ok, ai_reason = self.provider.status()
        self.notify("status", {
            "mic": {"ok": self.audio.running, "device": self.audio.device_name, "error": self.audio.error,
                    "sample_rate": self.audio.sample_rate},
            "camera": {"on": self.gestures.running, "error": self.gestures.error},
            "air_mouse": {"on": self.gestures.mouse_mode},
            "ai": {"ok": ai_ok, "reason": ai_reason, "model": self.provider.model, "usage": dict(self.provider.usage),
                   "calls": self.provider.calls, "key": self.config.gemini_key_status(),
                   "vision": self.config.cloud_screen_vision, "turns": self.provider.history_turns},
            "stt": {"ready": self.stt.ready, "loading": self.stt.loading, "model": self.stt.model_name,
                    "error": self.stt.error},
            "tts": {"backend": self.tts.active_backend, "chain": self.tts.chain(), "error": self.tts.last_error},
            "bridge": {"connected": self.bridge.connected, "browsers": self.bridge.browsers(), "error": self.bridge.error},
            "control_paused": self.safety.control_paused,
            "autonomy": self.config.get("safety.autonomy") or "standard",
            "hotkeys": dict(self.hotkeys.registered) if self.hotkeys else {},
            "awake": self._awake,
            "sleep_guard": {"enabled": self.sleep_guard.enabled, "error": self.sleep_guard.error,
                            "keep_display": self.sleep_guard.keep_display},
            "companion": self._companion,
            "three_d": self.three_d.status(),
            "code": self.code.status(),
        })

    def _on_task_event(self, ev: TaskEvent) -> None:
        spec = self.registry.get(ev.tool)
        self.notify("task", {"tool": ev.tool, "title": spec.title if spec else ev.tool, "status": ev.status,
                             "message": truncate(ev.message, 160), "source": ev.source.value,
                             "task_id": ev.task_id, "step_id": ev.step_id, "time": time.strftime("%H:%M:%S", time.localtime(ev.ts))})

    def _on_state(self, old: AppState, new: AppState, detail: str) -> None:
        self.notify("state", {"state": new.value, "label": STATE_LABELS_VI[new], "detail": detail})

    # ================================================================ đánh thức / ngủ
    def _on_clap(self, ev) -> None:
        self.notify("clap", {"kind": ev.kind, "count": ev.count, "peak_db": round(ev.peak_db, 1),
                             "stats": self.audio.clap.stats()})
        if self.clap_test:
            return
        # Màn hình đang tắt (hẹn giờ Windows, nút nguồn, "cho máy ngủ"): vỗ tay luôn bật lại, kể cả khi NEXA
        # chưa kịp về chế độ chờ.
        screen_off = self.sleep_guard.enabled and self.sleep_guard.display_off
        # Máy đang khóa (kể cả khi bấm Win+L nên màn hình vẫn sáng): vẫn cho vỗ tay để mở khóa.
        locked = False
        if ev.kind == "wake" and self.sm.state != AppState.STANDBY and not screen_off:
            from nexa.desktop.sleep_guard import session_locked
            locked = session_locked() is True
        if ev.kind == "wake" and (self.sm.state == AppState.STANDBY or screen_off or locked):
            since_input = _ms_since_last_input()
            if since_input is not None and since_input < 400:
                # Tiếng gõ phím/nhấp chuột sát mic rất giống tiếng vỗ tay; khi đang thao tác thì bỏ qua.
                log.info("Bỏ qua xung giống vỗ tay: có thao tác bàn phím/chuột %d ms trước", since_input)
                self.notify("clap", {"kind": "ignored", "count": 0, "peak_db": round(ev.peak_db, 1),
                                     "stats": self.audio.clap.stats()})
                return
            log.info("Phát hiện %d tiếng vỗ tay (%.1f dBFS)", ev.count, ev.peak_db)
            away_s = float(self.config.get("power.away_after_s") or 300)
            if self.sleep_guard.enabled and (self._guard_asleep or screen_off or locked
                                             or (since_input or 0) >= away_s * 1000):
                self._wake_from_away()
            else:
                self.wake("clap")

    def _on_snap(self, ev) -> None:
        """Búng tay (mic): bảng Sinh code đang mở → chạy thử; viewer 3D đang mở → bật/tắt chuyển động.
        Cả hai đều đóng thì pipeline không gọi tới."""
        self.notify("snap", {"source": "mic", "peak_db": round(ev.peak_db, 1), "stats": self.audio.snap.stats()})
        if self.clap_test:
            return
        since_input = _ms_since_last_input()
        if since_input is not None and since_input < 400:
            log.info("Bỏ qua xung giống búng tay: có thao tác bàn phím/chuột %d ms trước", since_input)
            return
        log.info("Phát hiện búng tay (%.1f dBFS)", ev.peak_db)
        if self.code.panel_open:
            self.code.gesture_run("mic")
        else:
            self.three_d.toggle_animation("mic")

    # ----- ngủ canh gác -----
    def _apply_sleep_guard(self) -> None:
        """Bật/tắt ngủ canh gác theo cài đặt; khi bật thì nút nguồn/nút ngủ chỉ tắt màn hình (trả lại khi tắt/thoát)."""
        if self.config.get("power.clap_wake_guard"):
            keep_display = bool(self.config.get("power.keep_display_awake", False))
            ok = self.sleep_guard.enable(
                remap_buttons=keep_display or bool(self.config.get("power.button_turns_off_display", True)),
                lid=keep_display or bool(self.config.get("power.lid_keep_awake", False)),
                keep_display=keep_display)
            if not ok:
                self.notify("status_text", {"text": self.sleep_guard.error or "Chưa bật được giữ máy thức."})
        else:
            self.sleep_guard.disable()   # cũng trả lại hành động nút nguồn nếu lần trước NEXA bị tắt ngang
        self._apply_no_lock()

    def _apply_no_lock(self) -> None:
        """Khi canh gác + bật 'không đòi mật khẩu khi thức': nhờ dịch vụ SYSTEM tắt console-lock; ngược lại trả lại."""
        want = bool(self.config.get("power.no_lock", False)) and bool(self.config.get("power.clap_wake_guard"))
        if want == self._no_lock_applied:
            return
        try:
            from nexa.desktop import unlock
            if want and not unlock.ping():
                self.notify("status_text", {"text": "Chưa cài dịch vụ mở khóa nên chưa tắt được yêu cầu mật khẩu. "
                                                    "Vào Cài đặt > Tự mở khóa để cài dịch vụ."})
                return
            if unlock.set_no_lock(want):
                self._no_lock_applied = want
                log.info("Đòi mật khẩu khi thức dậy: %s", "TẮT" if want else "BẬT lại")
        except Exception:
            log.exception("Áp dụng no_lock lỗi")

    def _on_display_state(self, state: int) -> None:
        from nexa.desktop.sleep_guard import DISPLAY_OFF
        if state == DISPLAY_OFF and self.sm.state == AppState.STANDBY:
            self.notify("status_text", {"text": "Màn hình đã tắt — NEXA vẫn canh, anh vỗ tay là em bật lại."})

    def _mic_watchdog(self) -> None:
        """Sau khi máy thức dậy hoặc tai nghe Bluetooth kết nối lại, luồng mic có thể im hẳn: mở lại mic."""
        lost_at: float | None = None        # mic do watchdog mở lại mà hỏng: thử lại mỗi 30 giây
        while self._running:
            time.sleep(5.0)
            if not self._running:
                return
            if self.audio.running and self.audio.stalled(5.0):
                log.warning("Mic không gửi âm thanh hơn 5 giây — mở lại mic")
                ok = self.audio.restart()
                lost_at = None if ok else time.monotonic()
                self.notify("status_text", {"text": "Đã mở lại mic." if ok else self.audio.error})
            elif lost_at is not None and not self.audio.running and time.monotonic() - lost_at >= 30:
                if self.audio.start():
                    lost_at = None
                    log.info("Đã mở lại mic")
                    self.notify("status_text", {"text": "Đã mở lại mic."})
                else:
                    lost_at = time.monotonic()

    def _away_greeting(self) -> str:
        from nexa.desktop.sleep_guard import away_greeting
        return (self.config.get("power.wake_greeting") or "").strip() or away_greeting(time.localtime().tm_hour)

    def guard_sleep(self) -> ToolResult | None:
        """Lệnh "cho máy ngủ" khi đang bật ngủ canh gác: tắt màn hình thay vì ngủ thật. None = không áp dụng."""
        if not self.sleep_guard.enabled:
            return None
        if self.sleep_guard.keep_display:
            return ToolResult.success("Chế độ giữ máy và màn hình thức đang bật. Anh tắt mục này trong Cài đặt nếu muốn cho máy nghỉ.",
                                      verified=True, guard=True)

        def later() -> None:
            # Đợi NEXA đọc xong câu trả lời rồi mới tắt màn hình và về chế độ chờ.
            deadline = time.monotonic() + 15
            time.sleep(1.0)
            while self.tts.speaking and time.monotonic() < deadline:
                time.sleep(0.2)
            time.sleep(0.5)
            self.go_standby("Ngủ canh gác — vỗ tay để bật máy")
            self._guard_asleep = True
            if self.config.get("power.screen_off", True):
                from nexa.desktop.sleep_guard import display_off
                display_off()

        threading.Thread(target=later, name="nexa-guard-sleep", daemon=True).start()
        return ToolResult.success("Em tắt màn hình và canh máy cho anh. Anh vỗ tay là em bật lại.", verified=True,
                                  guard=True)

    def _wake_from_away(self) -> None:
        """Vỗ tay khi anh đi vắng/màn hình đã tắt: bật màn hình, đợi mở khóa nếu cần, rồi mở NEXA và chào."""
        from nexa.desktop.sleep_guard import display_on, session_locked
        self._guard_asleep = False
        if not display_on(self.sleep_guard.monitor):
            log.warning("Đã thử mọi cách nhưng Windows chưa báo màn hình sáng")
        if session_locked():
            self._wait_for_unlock(prompt=True)
            return
        self.notify("raise_window", {})
        self.wake("clap", greeting=self._away_greeting())

    def _wait_for_unlock(self, prompt: bool) -> None:
        """Máy đang khóa: nếu bật 'tự mở khóa' và dịch vụ chạy thì nhờ nó gõ mã; nếu không, nhắc anh mở tay."""
        if self._unlock_waiter is not None and self._unlock_waiter.is_alive():
            return
        from nexa.desktop.sleep_guard import session_locked

        auto = bool(self.config.get("power.auto_unlock", False))
        auto_ok = False
        if auto:
            try:
                from nexa.desktop import unlock
                auto_ok = unlock.ping()
            except Exception:
                log.exception("Không kiểm tra được dịch vụ mở khóa")
                auto_ok = False

        if not auto_ok and prompt and self.tts.chain():
            self.tts.speak("Chào anh Sơn. Máy đang khóa, anh mở khóa giúp em nhé.")

        def wait() -> None:
            # Khi tự mở khóa: nhờ dịch vụ gõ mã, chờ ~8s xác nhận; sai/không vào thì quay lại nhắc anh.
            if auto_ok:
                try:
                    from nexa.desktop import unlock
                    if unlock.request_unlock():
                        log.info("Đã nhờ dịch vụ gõ mã mở khóa — chờ máy vào desktop")
                        deadline = time.monotonic() + 8
                        while self._running and time.monotonic() < deadline:
                            if session_locked() is False:
                                break
                            time.sleep(0.5)
                        else:
                            log.warning("Tự mở khóa chưa vào được — nhắc anh mở tay")
                            if self.tts.chain():
                                self.tts.speak("Em thử mở khóa chưa được, anh mở giúp em nhé.")
                    else:
                        log.warning("Dịch vụ mở khóa không nhận lệnh — nhắc anh mở tay")
                except Exception:
                    log.exception("Gọi tự mở khóa lỗi")

            deadline = time.monotonic() + 30 * 60
            while self._running and time.monotonic() < deadline:
                if session_locked() is False:
                    time.sleep(1.0)   # để màn hình desktop hiện ra hẳn
                    log.info("Máy đã mở khóa — mở NEXA và chào")
                    self.notify("raise_window", {})
                    if self.sm.state == AppState.STANDBY:
                        self.wake("unlock", greeting=self._away_greeting())
                    return
                time.sleep(1.0)

        self._unlock_waiter = threading.Thread(target=wait, name="nexa-unlock-wait", daemon=True)
        self._unlock_waiter.start()

    def _on_system_resumed(self, gap_s: float) -> None:
        """Máy vừa ngủ thật (gập nắp, nút nguồn, Start → Sleep…): trong lúc đó NEXA bị Windows đóng băng."""
        minutes = max(1, round(gap_s / 60))
        if self._guard_asleep and self.config.get("power.screen_off", True):
            # Chính lệnh tắt màn hình đã đưa máy vào Modern Standby: lần sau không tắt màn hình nữa.
            self.config.set("power.screen_off", False)
            self.config.save()
            log.warning("Tắt màn hình làm máy ngủ thật — đã chuyển power.screen_off = false")
            self.notify("status_text", {"text": "Trên máy này tắt màn hình làm máy ngủ thật, nên từ giờ 'cho máy ngủ' "
                                                "chỉ về chế độ chờ; màn hình tự tắt theo hẹn giờ Windows."})
        else:
            self.notify("status_text", {"text": f"Máy vừa ngủ thật khoảng {minutes} phút — lúc đó NEXA không nghe "
                                                "được tiếng vỗ tay."})
        self._guard_asleep = False
        from nexa.desktop.sleep_guard import session_locked
        if session_locked() and self.sm.state == AppState.STANDBY:
            self._wait_for_unlock(prompt=False)

    def wake(self, source: str = "manual", greet: bool = True, greeting: str | None = None) -> None:
        if not self._running:
            return
        if self.sm.state != AppState.STANDBY:
            if source in ("manual", "hotkey", "ptt"):
                self.push_to_talk()
            return
        self._awake = True
        self._last_activity = time.monotonic()
        self._duck(True)
        self.sm.set(AppState.WAKING, source)
        threading.Thread(target=self._wake_sequence, args=(greet, greeting), name="nexa-wake", daemon=True).start()

    def _wake_sequence(self, greet: bool, greeting: str | None = None) -> None:
        self.tts.play_sfx("wake", wait=True)
        if greet:
            # Lời chào đầy đủ chỉ lần đầu (hoặc khi anh quay lại sau lúc vắng); các lần sau chỉ "Dạ, em nghe.".
            greeting = greeting or (SHORT_GREETING if self._greeted else (
                self.config.get("session.greeting") or "Chào anh Sơn, em là Nexa. Em sẵn sàng."))
            self._greeted = True
            self.notify("assistant_message", {"text": greeting})
            if self.tts.chain():
                self.sm.set(AppState.SPEAKING)
                self.tts.speak(greeting, wait=True, timeout=20)
        self._listen()

    def _listen(self) -> None:
        if not self._awake or not self._running:
            return
        if self.tts.speaking:
            return  # sẽ nghe tiếp khi TTS rảnh (_tts_idle)
        if self._ai_busy.is_set() or self._basic_busy.is_set():
            self.audio.listen()   # vẫn nghe để nhận "dừng lại"/"hủy"/"đồng ý"
            return
        if self.safety.pending is not None:
            self.sm.set(AppState.CONFIRMING)
        else:
            self.sm.set(AppState.LISTENING, "Tâm sự — em đang nghe anh" if self._companion else "")
        self._duck()
        self.audio.listen()

    def _duck(self, new_session: bool = False) -> None:
        if self.ducker is None:
            return
        if new_session:
            self._duck_session = True
        if self._duck_session:
            self.ducker.duck()

    def _unduck(self, end_session: bool = False) -> None:
        if end_session:
            self._duck_session = False
        if self.ducker is not None:
            self.ducker.restore()

    def go_standby(self, reason: str = "") -> None:
        self._awake = False
        self._companion = False
        self.audio.set_conversation_mode(False)
        self._media_playing = False
        self._media_ignored = 0
        self._resume = None
        self.audio.cancel_listen()
        self._unduck(end_session=True)
        self.sm.set(AppState.STANDBY, reason or "Đang chờ tiếng vỗ tay")
        self.tts.play_sfx("sleep")
        self.push_status()

    def push_to_talk(self) -> None:
        """Nút 'Nhấn để nói': nghe ngay một câu (không phát lời chào)."""
        if self.sm.state == AppState.STANDBY:
            self._awake = True
            self._last_activity = time.monotonic()
            self.sm.set(AppState.LISTENING, "Nhấn để nói")
            self._duck(True)
            self.audio.cancel_listen()
            self.audio.listen()
            return
        if self.tts.speaking:
            self.tts.stop()
        self._awake = True
        self._last_activity = time.monotonic()
        self.audio.cancel_listen()
        self.sm.set(AppState.LISTENING, "Nhấn để nói")
        self._duck(True)
        self.audio.listen()

    # ================================================================ âm thanh -> văn bản
    def _on_speech_start(self) -> None:
        self._last_activity = time.monotonic()
        self.stt_bias.refresh_async()     # tên ứng dụng đang mở → gợi ý cho Whisper khi anh nói xong
        self.attention.capture_for_voice()   # màn hình anh đang nhìn lúc bắt đầu nói
        self.notify("speech_start", {})

    def _on_utterance(self, audio: np.ndarray) -> None:
        self._unduck()        # anh nói xong: trả âm lượng để nghe được kết quả lệnh
        try:
            self._stt_q.put_nowait(audio)
        except queue.Full:
            log.warning("STT đang bận, bỏ một câu")

    def _on_listen_timeout(self) -> None:
        if not self._awake:
            return
        idle = time.monotonic() - self._last_activity
        free = not self._ai_busy.is_set() and not self._basic_busy.is_set() and self.safety.pending is None
        companion = getattr(self, "_companion", False)
        if free and self._media_playing and not companion:
            log.info("Đang phát nhạc, không có lệnh mới — về chế độ chờ để trả âm lượng")
            self.go_standby("Đang phát nhạc — vỗ tay khi cần em")
            return
        timeout = (self.config.get("session.conversation_idle_timeout_s") or 300) if companion else (self.config.get("session.idle_timeout_s") or 60)
        if idle >= float(timeout) and free:
            log.info("Không hoạt động %.0fs — về chế độ chờ", idle)
            self.go_standby("Hết thời gian chờ — vỗ tay để đánh thức")
            return
        self.audio.listen()

    def _stt_worker(self) -> None:
        while self._running:
            try:
                audio = self._stt_q.get(timeout=0.5)
            except queue.Empty:
                continue
            if not self.stt.ready:
                self.notify("heard", {"text": "", "reason": "Model nhận dạng chưa sẵn sàng"})
                self._listen()
                continue
            busy = self._ai_busy.is_set() or self._basic_busy.is_set()
            if not busy:
                self.sm.set(AppState.THINKING, "Đang nhận dạng")
            try:
                res = self.stt.transcribe(audio)
            except Exception as exc:
                log.exception("STT lỗi")
                res = None
                self.notify("heard", {"text": "", "reason": f"Lỗi nhận dạng: {exc}"})
            if res is not None and self.corpus.enabled and not self._companion:
                self._record_corpus(audio, res)
            if res is None or not res.ok:
                if res is not None:
                    self.notify("heard", {"text": "", "reason": res.reason})
                self._listen()
                continue
            log.info("Nghe được (%.1fs, xử lý %.1fs, tin cậy %.2f): %s", res.duration_s, res.elapsed_s,
                     res.avg_logprob, "[tâm sự]" if self._companion else res.text)
            self.notify("heard", {"text": res.text})
            if self._media_noise(res):
                self._media_ignored += 1
                log.info("Đang phát nhạc: bỏ qua câu không phải lệnh (có thể là lời bài hát lọt vào mic)")
                if self._media_ignored >= 2:
                    self.go_standby("Đang phát nhạc — vỗ tay khi cần em")
                else:
                    self._listen()
                continue
            self._media_ignored = 0
            if self._unclear(res):
                log.info("Câu nghe không rõ và không khớp lệnh nào — hỏi lại thay vì đoán")
                self.reply(f"Em nghe chưa rõ (\"{truncate(res.text, 40)}\"). Anh nói lại giúp em.",
                           spoken=UNCLEAR_PROMPT)
                continue
            self.submit_text(res.text, Source.VOICE)

    def _record_corpus(self, audio: np.ndarray, res) -> None:
        """Chế độ thu dữ liệu nghiên cứu (research.record_corpus): lưu câu nói + kết quả nhận dạng để gán nhãn sau."""
        kind, normalized = "", ""
        if res.ok:
            from nexa.ai.intent_router import apply_stt_fixes
            try:
                normalized = apply_stt_fixes(res.text)
                kind = self.router.route(res.text, pending_confirmation=self.safety.pending is not None).kind
            except Exception:
                pass
        self.corpus.record(audio, 16000, res, route_kind=kind, normalized=normalized, model=self.stt.model_name)

    def _media_noise(self, res) -> bool:
        """Vừa mở nhạc: câu không phải lệnh nhiều khả năng là lời bài hát/tiếng nhạc lọt vào mic — không gửi Gemini."""
        if getattr(self, "_companion", False) or not self._media_playing:
            return False
        from nexa.utils.text import fold
        if fold(res.text).strip().startswith(("nexa", "nec xa", "nech xa")):
            return False                     # anh gọi tên: chắc chắn đang nói với NEXA
        try:
            kind = self.router.route(res.text, pending_confirmation=self.safety.pending is not None).kind
            if kind in TRUSTED_ROUTES:
                return False
            return not self.router._looks_like_command(self.router._clean(res.text).fold)
        except Exception:
            return False

    def _unclear(self, res) -> bool:
        """Whisper không chắc VÀ câu không phải lệnh cơ bản nhận ra được → nhiều khả năng là nghe sai."""
        threshold = float(self.config.get("stt.min_confidence_logprob") or -0.9)
        if res.avg_logprob >= threshold:
            return False
        try:
            kind = self.router.route(res.text, pending_confirmation=self.safety.pending is not None).kind
        except Exception:
            return False
        return kind not in TRUSTED_ROUTES

    # ================================================================ xử lý lệnh
    def submit_text(self, text: str, source: Source = Source.KEYBOARD) -> None:
        text = (text or "").strip()
        if not text:
            return
        if source == Source.KEYBOARD and not self._awake:
            self._awake = True
            if self.sm.state == AppState.STANDBY:
                self.sm.set(AppState.THINKING, "Lệnh bàn phím")
        try:
            self._cmd_q.put_nowait((text, source))
        except queue.Full:
            self.notify("status_text", {"text": "Hàng đợi lệnh đang đầy."})

    def _cmd_worker(self) -> None:
        while self._running:
            item = self._cmd_q.get()
            if item is None:
                break
            text, source = item
            try:
                self._process(text, source)
            except Exception as exc:
                log.exception("Lỗi xử lý lệnh")
                self.sm.set(AppState.ERROR, str(exc))
                self.reply(f"Em gặp lỗi khi xử lý: {truncate(str(exc), 120)}")

    def _process(self, text: str, source: Source) -> None:
        self._last_activity = time.monotonic()
        self.notify("user_message", {"text": text, "source": source.value})
        busy = self._ai_busy.is_set() or self._basic_busy.is_set()
        route = self.router.route(text, pending_confirmation=self.safety.pending is not None, resume=self._resume,
                                  companion=self._companion)
        if route.kind not in ("clarify",):
            self._resume = None

        if route.kind == "stop":
            self.emergency_stop("Lệnh 'Dừng lại'")
            return
        if route.kind in ("confirm", "deny"):
            if not self.safety.resolve_current(route.kind == "confirm"):
                self.reply("Hiện không có hành động nào chờ xác nhận.")
            return
        if route.kind == "cancel":
            cancelled = self.cancel_task()
            self.reply(route.reply if cancelled or self.safety.pending else "Dạ, không có tác vụ nào đang chạy.")
            return
        if busy and self._ai_busy.is_set() and not self._basic_busy.is_set():
            # Anh nói lệnh mới trong lúc Gemini còn đang nghĩ (thường vì câu trước nghe sai): câu mới thay câu cũ.
            log.info("Lệnh mới thay cho yêu cầu Gemini đang chờ: %s", "[tâm sự]" if self._companion else truncate(text, 60))
            if self._ai_token is not None:
                self._ai_token.cancel("Lệnh mới của anh")
            if self._ai_thread is not None:
                self._ai_thread.join(timeout=2.0)
            busy = self._ai_busy.is_set() or self._basic_busy.is_set()
        if busy:
            self.reply("Em đang làm tác vụ trước. Anh nói 'hủy' hoặc 'dừng lại' nếu muốn dừng.", speak=False)
            return
        if route.kind == "sleep":
            self.reply(route.reply, then_standby=True)
            return
        if route.kind == "internal" and route.action in ("companion_on", "companion_off"):
            self._companion = route.action == "companion_on"
            self.audio.set_conversation_mode(self._companion)
            self.push_status()
            self.reply("Em đang nghe anh. Hôm nay anh muốn kể em nghe chuyện gì?" if self._companion
                       else "Em đã trở lại chế độ điều khiển máy tính.")
            return
        if route.kind == "internal" and route.action == "clear_history":
            self.provider.clear_history()
            self.notify("clear_chat", {})
            self.reply(route.reply)
            return
        if route.kind == "clarify":
            self._resume = route.resume
            self.reply(route.reply)
            return
        if source == Source.VOICE:
            self.attention.apply_for_voice()    # lệnh tác động lên màn hình anh nhìn lúc nói
        if route.kind == "basic":
            threading.Thread(target=self._run_basic, args=(route.calls, source, text), name="nexa-basic", daemon=True).start()
            return
        ai_ok, ai_reason = self.provider.status()
        if route.kind == "chat" and not ai_ok:
            self.reply(route.reply)
            return
        if not ai_ok:
            if self._companion:
                self.reply(f"Em chưa kết nối được AI để trò chuyện ({ai_reason}). Anh kiểm tra kết nối trong Cài đặt → AI nhé.")
                return
            self.reply(f"Chế độ lệnh cơ bản: em chưa hiểu yêu cầu này ({ai_reason}). Anh có thể nói: "
                       "mở Notepad, tìm trên web…, đặt âm lượng 30 phần trăm, chụp màn hình.")
            return
        self._ai_busy.set()
        self._ai_thread = threading.Thread(target=self._run_ai, args=(text,), name="nexa-ai", daemon=True)
        self._ai_thread.start()

    def _routine_for(self, folded: str) -> str | None:
        from nexa.desktop.routines import load_routines, match_routine
        return match_routine(folded, load_routines(self.config))

    def _run_basic(self, calls: list[tuple[str, dict]], source: Source, text: str = "") -> None:
        self._basic_busy.set()
        token = self.safety.new_token("basic")
        task_id = new_task_id("cmd")
        messages: list[str] = []
        spoken_own: list[str] = []          # câu đọc ngắn do chính tool soạn (data["spoken"]), ưu tiên hơn brief_speech
        ok_all = True
        # Chuỗi nhiều bước giữ quyền điều khiển để cử chỉ không chen vào làm sai đích.
        leased = len(calls) > 1 and self.executor.acquire_control("user")
        if any(name in MEDIA_START_TOOLS for name, _ in calls):
            self._media_playing = True
        try:
            for name, args in calls:
                if token.cancelled:
                    messages.append("Đã hủy các bước còn lại.")
                    ok_all = False
                    break
                self.sm.set(AppState.EXECUTING, self.registry.get(name).title if self.registry.get(name) else name)
                result = self.executor.execute(ToolCall(name, dict(args), source, task_id), token)
                messages.append(result.message)
                if result.data.get("spoken"):
                    spoken_own.append(str(result.data["spoken"]))
                if not result.ok:
                    ok_all = False
                    if result.error_code in ("ambiguous", "needs_input") and result.data.get("resume"):
                        # "UAV có bốn cánh quạt. Anh muốn xem cánh trước trái…?" → câu trả lời tiếp theo ghép vào lệnh
                        self._resume = str(result.data["resume"])
                    break
        finally:
            if leased:
                self.executor.release_control("user")
            self._basic_busy.clear()
        reply = " ".join(m for m in messages if m) if len(calls) > 1 else (messages[0] if messages else "")
        # Cho Gemini biết lệnh cơ bản vừa chạy để các câu sau ("mở video đầu tiên"…) có ngữ cảnh.
        self.provider.add_note(f"Anh Sơn vừa nói '{truncate(text, 80)}' → NEXA đã chạy lệnh cơ bản: {truncate(reply, 160)}")
        reply = reply or ("Xong rồi ạ." if ok_all else "Em chưa làm được.")
        # Màn hình hiện đủ câu; loa chỉ đọc bản ngắn (bỏ tên video/cửa sổ dài) để anh ra lệnh tiếp nhanh hơn.
        spoken = " ".join(brief_speech(m) for m in messages[-2:] if m) if ok_all and messages else truncate(reply, 140)
        if spoken_own and len(calls) == 1:
            spoken = spoken_own[0]
        self.reply(reply, spoken=spoken or reply)
        self.push_status()

    def _run_ai(self, text: str) -> None:
        companion = self._companion
        token = self.safety.new_token("ai")
        self._ai_token = token
        task_id = new_task_id("ai")
        owner = f"ai:{task_id}"
        if not companion:
            self.executor.acquire_control(owner)
        self.sm.set(AppState.THINKING, "Gemini")
        step = [0]

        def still_waiting() -> None:
            if not token.cancelled and self._ai_token is token and not self.tts.speaking:
                self.tts.speak(WAIT_PROMPT)
        waiter = threading.Timer(WAIT_PROMPT_AFTER_S, still_waiting)
        waiter.daemon = True
        waiter.start()

        def execute_tool(fc) -> dict:
            if companion:
                return {"ok": False, "message": "Chế độ tâm sự không thao tác máy tính."}
            step[0] += 1
            if token.cancelled:
                return {"ok": False, "message": "Tác vụ đã bị hủy.", "error_code": "cancelled"}
            spec = self.registry.get(fc.name)
            if fc.name in MEDIA_START_TOOLS:
                self._media_playing = True
            self.sm.set(AppState.EXECUTING, spec.title if spec else fc.name)
            call = ToolCall(fc.name, dict(fc.args or {}), Source.AI, task_id,
                            call_id=getattr(fc, "id", None) or f"{task_id}-{step[0]}")
            result = self.executor.execute(call, token)
            if not token.cancelled:
                self.sm.set(AppState.THINKING, "Gemini")
            return result.to_model_payload()

        try:
            hwnd, _ = self.wm.resolve_work_window() if not companion else (None, None)
            active = ""
            if hwnd:
                ident = self.wm.identity(hwnd)
                active = f"{ident.process_name if ident else ''} — {truncate(self.api.get_title(hwnd), 60)}"
            extra = ""
            proj = self.three_d.viewer.project
            if proj is not None:
                extra = (f"trình xem 3D đang mở '{proj.name}' ({len(proj.parts)} bộ phận"
                         f"{', đang tách' if self.three_d.viewer.exploded else ''}) — dùng các công cụ *_3d_*")
            if companion:
                result = self.provider.converse(text, [], execute_tool, token, companion=True)
            else:
                ctx = context_note(active, len(self.monitors.refresh()), self.gestures.running, extra)
                result = self.provider.converse(text, self.registry.gemini_declarations(), execute_tool, token, ctx)
            if token.cancelled:
                return
            self.reply(result.text)
        except Cancelled:
            if not self.safety.control_paused:
                self.reply("Em đã hủy yêu cầu.", speak=False)
        except AIError as exc:
            if exc.kind in ("server", "timeout"):
                # Lỗi phía máy chủ Google (quá tải), không phải máy anh: nói rõ và nhắc lệnh cơ bản vẫn dùng được.
                self.reply(f"Máy chủ Gemini của Google đang quá tải ({exc.message}) nên em chưa trả lời được câu này. "
                           "Các lệnh điều khiển máy như mở ứng dụng, mở file, âm lượng vẫn chạy bình thường.",
                           spoken=GEMINI_BUSY_PROMPT)
            else:
                self.reply(f"Chế độ lệnh cơ bản: {exc.message}")
        except Exception as exc:
            log.exception("Lỗi luồng AI")
            self.reply(f"Em gặp lỗi khi xử lý với Gemini: {truncate(str(exc), 100)}")
        finally:
            waiter.cancel()
            if not companion:
                self.executor.release_control(owner)
            self._ai_busy.clear()
            self._ai_token = None
            self.push_status()
            self._listen()

    def cancel_task(self) -> bool:
        active = self._ai_busy.is_set() or self._basic_busy.is_set() or self.safety.pending is not None
        if self._ai_token is not None:
            self._ai_token.cancel("Người dùng hủy")
        self.safety.cancel_current("Người dùng hủy")
        self.executor.cancel_all("Người dùng hủy")
        if self.three_d.cancel_jobs("Người dùng hủy"):
            active = True
        if self.code.cancel("Người dùng hủy"):
            active = True
        return active

    # ================================================================ phản hồi
    def reply(self, text: str, speak: bool = True, then_standby: bool = False, spoken: str | None = None) -> None:
        text = (text or "").strip()
        if text:
            self.notify("assistant_message", {"text": text})
        self._then_standby = then_standby
        say = (spoken or text).strip()
        if speak and say and self.tts.chain():
            if not (self._ai_busy.is_set() or self._basic_busy.is_set()):
                self.sm.set(AppState.SPEAKING)
            self.tts.speak(say)
            return
        self._after_reply()

    def _after_reply(self) -> None:
        self._last_activity = time.monotonic()
        if getattr(self, "_then_standby", False):
            self._then_standby = False
            self.go_standby("Vỗ tay để đánh thức")
            return
        if self._awake:
            self._listen()
        elif self.sm.state != AppState.STANDBY:
            self.sm.set(AppState.STANDBY)

    def _tts_start(self) -> None:
        self.audio.mute()

    def _tts_end(self) -> None:
        self.audio.unmute()

    def _tts_idle(self, kind: str) -> None:
        if kind == "speech":
            self._after_reply()

    # ================================================================ an toàn
    def emergency_stop(self, reason: str = "Dừng khẩn cấp") -> None:
        self.safety.emergency_stop(reason)

    def _on_emergency(self, reason: str) -> None:
        if self._ai_token is not None:
            self._ai_token.cancel(reason)
        self.executor.cancel_all(reason)
        self.input.release_all()
        self.tts.stop()
        self.gesture_router.clear()
        self.three_d.on_emergency(reason)            # hủy job 3D (kết quả đến muộn không mở) + khóa tương tác viewer
        self.code.on_emergency(reason)               # hủy việc viết/chạy thử code (diệt tiến trình chạy thử)
        self.gestures.set_mouse_mode(False)          # dừng khẩn cấp tắt hẳn chuột bằng tay (không tự bật lại khi tiếp tục)
        self.gestures.pause_events(True)
        self.notify("control_paused", {"paused": True, "reason": reason})
        self.notify("assistant_message", {"text": f"Đã dừng khẩn cấp ({reason}). Điều khiển tạm khóa — "
                                                  "anh bấm 'Tiếp tục điều khiển' khi muốn dùng lại."})
        if self._awake:
            self.sm.set(AppState.LISTENING, "Đã dừng khẩn cấp")
            self.audio.listen()
        self.push_status()

    def resume_control(self) -> None:
        self.safety.resume_control()
        self.gestures.pause_events(False)
        self.three_d.on_resume_control()
        self.code.on_resume_control()
        self.notify("control_paused", {"paused": False})
        self.push_status()

    def _on_confirm_hook(self, waiting: bool) -> None:
        if waiting:
            self.sm.set(AppState.CONFIRMING)
            self.audio.listen()
        elif self.sm.state == AppState.CONFIRMING:
            self.sm.set(AppState.EXECUTING)

    def _on_confirmation(self, pending: PendingConfirmation | None) -> None:
        if pending is None:
            self.notify("confirmation", {"active": False})
            return
        data = {"active": True, "id": pending.id, "description": pending.description, "tool": pending.call.name,
                "timeout": round(pending.remaining()), "preview": pending.preview.get("image_path", ""),
                "preview_width": pending.preview.get("width", 0), "preview_height": pending.preview.get("height", 0)}
        self.notify("confirmation", data)
        self.tts.play_sfx("confirm")
        if self.tts.chain():
            self.tts.speak("Anh xác nhận giúp em: " + truncate(pending.description, 140))

    def resolve_confirmation(self, confirm_id: str, approved: bool, crop: list[float] | None = None) -> bool:
        return self.safety.resolve(confirm_id, approved, extra={"crop": crop} if crop else None)

    # ================================================================ cử chỉ / media / bridge
    def set_gesture_mode(self, enabled: bool) -> ToolResult:
        if enabled:
            ok, msg = self.gestures.start()
            if ok and self.safety.control_paused:
                self.gestures.pause_events(True)
                msg += " (Điều khiển đang tạm khóa sau dừng khẩn cấp.)"
        else:
            self.gestures.stop("người dùng tắt")
            self.attention.camera_stopped()
            ok, msg = True, "Đã tắt điều khiển bằng tay và camera."
        self.notify("camera", {"on": self.gestures.running, "error": self.gestures.error})
        self.push_status()
        return ToolResult.success(msg, verified=self.gestures.running == enabled) if ok else ToolResult.failure(msg, "camera")

    # ----- chú ý qua webcam -----
    def _ensure_camera(self) -> str:
        if self.gestures.running:
            return ""
        r = self.set_gesture_mode(True)
        return "" if r.ok else r.message

    def set_presence(self, enabled: bool) -> ToolResult:
        """Nhận biết anh có ngồi ở máy: rời máy thì dừng video + khóa máy, có người phía sau thì ẩn cửa sổ nhạy cảm."""
        self.config.set("attention.presence_enabled", bool(enabled))
        self.config.save()
        self.attention.camera_stopped()             # bắt đầu lại từ "đang ngồi"
        if not enabled:
            return ToolResult.success("Đã tắt tự khóa máy khi anh rời đi.", verified=True)
        err = self._ensure_camera()
        if err:
            return ToolResult.failure(f"Đã bật tự khóa máy nhưng camera chưa chạy: {err}", "camera")
        a = self.config.get("attention") or {}
        return ToolResult.success(f"Đã bật: anh rời máy khoảng {int(a.get('away_after_s', 45))} giây thì em dừng video "
                                  "và khóa máy; có người nhìn từ phía sau thì em ẩn cửa sổ nhạy cảm.", verified=True)

    def set_head_target(self, mode: str) -> ToolResult:
        mode = mode if mode in ("off", "commands", "auto") else "commands"
        self.config.set("attention.head_target", mode)
        self.config.save()
        if mode == "off":
            return ToolResult.success("Đã tắt chọn màn hình theo hướng quay đầu.", verified=True)
        err = self._ensure_camera()
        if err:
            return ToolResult.failure(f"Camera chưa chạy: {err}", "camera")
        if not self.attention.head.ready:
            return ToolResult.success("Đã bật chọn màn hình theo hướng nhìn, nhưng cần hiệu chuẩn trước: anh nói "
                                      "'hiệu chỉnh hướng nhìn'.", verified=True)
        return ToolResult.success("Đã bật: " + ("focus tự theo màn hình anh nhìn." if mode == "auto" else
                                                "lệnh giọng nói và cử chỉ tác động lên màn hình anh đang nhìn."),
                                  verified=True)

    def calibrate_head(self) -> ToolResult:
        err = self._ensure_camera()
        if err:
            return ToolResult.failure(f"Cần camera để hiệu chuẩn: {err}", "camera")

        def done(ok: bool, msg: str) -> None:
            self.notify("head_calibration", {"ok": ok, "message": msg})
            self.notify("overlay", {"kind": "toast", "text": msg, "error": not ok})
            self.notify("assistant_message", {"text": msg})
        ok, msg = self.attention.calibrate(done)
        return ToolResult.success(msg, verified=False) if ok else ToolResult.failure(msg, "calibration")

    def set_air_mouse(self, enabled: bool) -> ToolResult:
        """Chuột bằng tay: cần camera cử chỉ; bật thì tự bật camera nếu chưa bật."""
        if enabled:
            if self.safety.control_paused:
                return ToolResult.failure("Điều khiển đang tạm khóa sau dừng khẩn cấp; anh bấm 'Tiếp tục điều khiển' "
                                          "trước đã.", "control_paused")
            if getattr(getattr(self, "three_d", None), "viewer_active", False) is True:
                return ToolResult.failure("Đang mở trình xem 3D: cử chỉ tay đang điều khiển mô hình. Anh đóng trình xem "
                                          "3D rồi bật chuột bằng tay nhé.", "viewer_active")
            if getattr(getattr(self, "code", None), "panel_open", False) is True:
                return ToolResult.failure("Đang mở bảng Sinh code: cử chỉ tay đang dùng để lưu, chạy thử và cuộn code. "
                                          "Anh đóng bảng Sinh code rồi bật chuột bằng tay nhé.", "code_panel_open")
            if not self.gestures.running:
                r = self.set_gesture_mode(True)
                if not r.ok:
                    return r
            self.gestures.set_mouse_mode(True)
            msg = ("Đã bật chuột bằng tay: di chuyển tay để di con trỏ, chụm ngón cái với ngón trỏ để click, "
                   "chụm giữ rồi kéo để kéo thả, chụm ngón cái với ngón giữa để click phải, hai ngón để cuộn, "
                   "nắm tay để nhấc tay. Sáu cử chỉ lệnh tạm ngưng tới khi anh tắt chuột bằng tay.")
        else:
            self.gestures.set_mouse_mode(False)
            msg = "Đã tắt chuột bằng tay; sáu cử chỉ lệnh hoạt động lại." if self.gestures.running else \
                "Đã tắt chuột bằng tay."
        self.notify("air_mouse", {"on": self.gestures.mouse_mode})
        self.push_status()
        return ToolResult.success(msg, verified=self.gestures.mouse_mode == enabled)

    def _run_file_hook(self, path: Any) -> ToolResult:
        """FileService.open_by_name(app="run") tìm được tệp → chạy thử trong console riêng cạnh NEXA."""
        if not self.code.enabled:
            return ToolResult.failure("Tính năng code đang tắt (code.enabled).", "unavailable")
        ok, msg = self.code.run_file(path)
        if not ok:
            return ToolResult.failure(msg, "failed")
        return ToolResult.success(msg, verified=True, in_progress=True, path=str(path))

    # ----- mô hình 3D -----
    def _part_known(self, text: str) -> bool:
        """IntentRouter hỏi: tên này có phải bộ phận của mô hình đang mở không (để không bắt nhầm lệnh khác)."""
        try:
            return self.three_d.viewer.resolve(text, allow_multiple=True).status != "not_found"
        except Exception:
            return False

    def _on_viewer_mode(self, on: bool) -> None:
        """Mở viewer → chế độ cử chỉ VIEWER_3D độc quyền (tạm ngưng chuột bằng tay và sáu cử chỉ hệ thống).
        Đóng viewer → về trạng thái an toàn: sáu cử chỉ lệnh, chuột bằng tay vẫn TẮT (anh tự bật lại nếu cần)."""
        if on and self.gestures.mouse_mode:
            self.gestures.set_mouse_mode(False)
            self.notify("air_mouse", {"on": False})
            self.notify("overlay", {"kind": "toast", "text": "Đã tạm tắt chuột bằng tay khi mở trình xem 3D."})
        self._route_gestures()
        if on and not self.gestures.running and self.config.get("three_d.viewer_auto_camera") and \
                not self.safety.control_paused:
            threading.Thread(target=lambda: self.set_gesture_mode(True), name="nexa-3d-camera", daemon=True).start()
        self.notify("3d_mode", {"on": on, "camera": self.gestures.running})
        self.push_status()

    def _on_code_panel(self, on: bool) -> None:
        """Mở bảng Sinh code → chế độ cử chỉ CODE độc quyền (nắm tay = lưu, búng tay = chạy thử, hai ngón = cuộn).
        Đóng bảng → trả camera cho viewer 3D (nếu còn mở) hoặc sáu cử chỉ lệnh; chuột bằng tay vẫn TẮT."""
        if on and self.gestures.mouse_mode:
            self.gestures.set_mouse_mode(False)
            self.notify("air_mouse", {"on": False})
            self.notify("overlay", {"kind": "toast", "text": "Đã tạm tắt chuột bằng tay khi mở bảng Sinh code."})
        self._route_gestures()
        if on and not self.gestures.running and self.config.get("code.gesture.auto_camera") and \
                not self.safety.control_paused:
            threading.Thread(target=lambda: self.set_gesture_mode(True), name="nexa-code-camera", daemon=True).start()
        self.notify("code_gesture", {"kind": "mode", "on": on, "camera": self.gestures.running})
        self.push_status()

    def _route_gestures(self) -> None:
        """Camera phục vụ đúng một chế độ: bảng Sinh code (đang hiện, che viewer 3D) > viewer 3D > sáu cử chỉ lệnh."""
        if self.code.panel_open:
            self.gestures.set_viewer_mode(True, self.code.feed_gesture, name="code")
        elif self.three_d.viewer.is_open:
            self.gestures.set_viewer_mode(True, self.three_d.feed_gesture, name="3d")
        else:
            self.gestures.set_viewer_mode(False)

    def _monitor_rects(self) -> tuple[list, Any]:
        """Hình chữ nhật các màn hình (đọc lại tối đa 2 giây/lần: chuột bằng tay hỏi mỗi khung hình)."""
        t, rects, primary = self._monitor_cache
        now = time.monotonic()
        if now - t > 2.0:
            try:
                mons = self.monitors.refresh()
                rects = [tuple(m.rect) for m in mons]
                primary = next((tuple(m.rect) for m in mons if m.primary), None)
            except Exception:
                log.exception("Không đọc được danh sách màn hình cho chuột bằng tay")
            self._monitor_cache = (now, rects, primary)
        return rects, primary

    def _on_gesture_result(self, sig, result: ToolResult) -> None:
        self.notify("gesture_result", {"event": sig.event.value, "ok": result.ok, "message": result.message,
                                       "code": result.error_code or "", "no_op": bool(result.data.get("no_op"))})
        if not result.ok and result.error_code not in ("history_empty",):
            self.notify("overlay", {"kind": "toast", "text": result.message, "error": True})
        elif result.error_code == "history_empty":
            self.notify("overlay", {"kind": "toast", "text": result.message})

    def _on_bridge_event(self, ev: dict) -> None:
        self.media.on_bridge_event(ev)
        if ev.get("type") == "bind":
            tab = self.bridge.tab(ev["key"])
            if tab and tab.video_id:
                r = self.media.bind(self._MediaTarget("bridge", tab.key, tab.video_id, tab.title, tab.browser))
                self.notify("overlay", {"kind": "toast", "text": r.message})
                self.notify("assistant_message", {"text": r.message})
        if ev.get("type") in ("connected", "disconnected", "bind", "tab_closed"):
            self.push_status()
        self.notify("media_targets", {})

    def media_targets(self) -> list[dict]:
        return [t.to_dict() for t in self.media.list_targets()]

    # ================================================================ tiện ích
    def _foreground_poller(self) -> None:
        last = None
        while self._running:
            try:
                self.wm.remember_external_foreground()
                ident = self.wm.last_external
                if ident is not None and ident != last:
                    last = ident
                    self.notify("foreground", {"title": truncate(self.api.get_title(ident.hwnd), 60),
                                               "process": ident.process_name})
            except Exception:
                pass
            time.sleep(0.4)

    def apply_settings(self, patch: dict, gestures_patch: dict | None = None) -> str:
        before = self.config.snapshot()
        self.config.update(patch)
        self.config.save()
        if gestures_patch:
            self.config.update_gestures(gestures_patch)
            self.config.save_gestures()
            self.gestures.reload_params()
        self.attention.reload()
        after = self.config.snapshot()
        msgs = ["Đã lưu cài đặt."]
        if before["audio"].get("input_device") != after["audio"].get("input_device") or \
                before["audio"].get("preferred_hostapi") != after["audio"].get("preferred_hostapi"):
            msgs.append("Mic: " + ("đã mở lại." if self.audio.restart() else self.audio.error))
        else:
            self.audio.update_clap_config()
        self.audio.set_conversation_mode(self._companion)
        if before.get("power") != after.get("power"):
            self._apply_sleep_guard()
        if before["stt"].get("model") != after["stt"].get("model"):
            self.stt.unload()
            threading.Thread(target=self._load_stt, daemon=True).start()
            msgs.append("Đang nạp model nhận dạng mới.")
        self.media.preferred = after.get("media", {}).get("backend") or "auto"
        if "code" in patch or gestures_patch:
            self.code.reload_gesture_params()
        if "three_d" in patch:
            self.three_d.reload_params()
            if self.config.config_warnings:
                msgs.append("Mô hình 3D: " + "; ".join(self.config.config_warnings[:3]))
        self.push_status()
        return " ".join(msgs)

    def test_gemini(self) -> tuple[bool, str]:
        ok, msg = self.provider.test_connection()
        self.push_status()
        return ok, msg

    def set_api_key(self, key: str, persist: bool) -> str:
        from nexa.utils.config import is_placeholder_secret
        if is_placeholder_secret(key):
            return "Key trống hoặc là giá trị mẫu."
        self.config.store_api_key(key, persist)
        self.push_status()
        return "Đã lưu key vào .env cục bộ." if persist else "Đã đặt key cho phiên này (không lưu ra đĩa)."
