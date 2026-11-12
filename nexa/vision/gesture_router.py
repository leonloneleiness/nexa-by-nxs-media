"""Ánh xạ sự kiện cử chỉ -> tool call trong tool registry chung. KHÔNG gọi Gemini.

Chạy trong luồng riêng với hàng đợi rất ngắn: nếu executor đang bận, sự kiện cũ bị bỏ thay vì dồn lại.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Any, Callable

from nexa.core.events import GestureEvent, Source, ToolCall, ToolResult, new_task_id
from nexa.vision.gesture_state_machine import GestureSignal
from nexa.utils.logging import get_logger

log = get_logger("gesture.router")

EVENT_TOOLS: dict[GestureEvent, str] = {
    GestureEvent.MOVE_WINDOW_TO_MONITOR_2: "move_window_to_monitor_2",
    GestureEvent.MINIMIZE_ACTIVE_WINDOW: "minimize_window",
    GestureEvent.RESTORE_LAST_MINIMIZED_WINDOW: "restore_last_minimized",
    GestureEvent.YOUTUBE_PAUSE: "youtube_pause",
    GestureEvent.YOUTUBE_RESUME: "youtube_resume",
    GestureEvent.SCROLL_UP: "scroll",
}


def signal_to_call(sig: GestureSignal, invert_scroll: bool = False) -> ToolCall:
    name = EVENT_TOOLS[sig.event]
    args: dict[str, Any] = {}
    if sig.event in (GestureEvent.MOVE_WINDOW_TO_MONITOR_2, GestureEvent.MINIMIZE_ACTIVE_WINDOW):
        args = {"use_gesture_snapshot": True}
    elif sig.event == GestureEvent.SCROLL_UP:
        args = {"direction": "down" if invert_scroll else "up", "notches": max(1, int(sig.amount)),
                "use_gesture_snapshot": True}
    return ToolCall(name=name, args=args, source=Source.GESTURE, task_id=new_task_id("gesture"),
                    snapshot=sig.snapshot)


class GestureRouter:
    def __init__(self, executor: Any, safety: Any, config: Any,
                 on_result: Callable[[GestureSignal, ToolResult], None] | None = None) -> None:
        self.executor = executor
        self.safety = safety
        self.config = config
        self.on_result = on_result
        self.multimodal = None
        self.can_interact = lambda: True
        self._q: "queue.Queue[GestureSignal | None]" = queue.Queue(maxsize=3)
        self._running = True
        self._thread = threading.Thread(target=self._worker, name="nexa-gesture-exec", daemon=True)
        self._thread.start()

    def submit(self, sig: GestureSignal) -> None:
        if not self.can_interact():
            return
        if self.multimodal is not None:
            call = signal_to_call(sig, bool(self.config.gesture("scroll.invert_scroll", False)))
            sig.detail["fusion_action"] = self.multimodal.observe(call.name, call.args, sig.t)
            sig.detail["fusion_epoch"] = self.multimodal.epoch
        if self.safety.control_paused:
            self._report(sig, ToolResult.failure("Điều khiển đang tạm dừng (dừng khẩn cấp).", "control_paused"))
            return
        try:
            self._q.put_nowait(sig)
        except queue.Full:
            # Luôn ưu tiên sự kiện mới nhất; không dồn cử chỉ cũ.
            try:
                dropped = self._q.get_nowait()
                log.info("Bỏ cử chỉ cũ %s vì hàng đợi đầy", dropped.event.value if dropped else "")
            except queue.Empty:
                pass
            self._q.put_nowait(sig)

    def clear(self) -> None:
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                return

    def stop(self) -> None:
        self._running = False
        self.clear()
        self._q.put_nowait(None)

    def _worker(self) -> None:
        while self._running:
            sig = self._q.get()
            if sig is None:
                break
            while self._running and self.multimodal is not None and self.multimodal.waiting():
                time.sleep(0.02)
            if not self._running or not self.can_interact() or self.safety.control_paused:
                continue
            if self.multimodal is not None and sig.detail.get("fusion_epoch") != self.multimodal.epoch:
                continue
            action = sig.detail.get("fusion_action")
            if action is not None and action.consumed:
                continue
            if time.monotonic() - sig.t > float(self.config.get("multimodal.gesture_max_age_s", 2.0)):
                continue
            invert = bool(self.config.gesture("scroll.invert_scroll", False))
            call = signal_to_call(sig, invert)
            call.input_started_at = call.input_ended_at = sig.t
            token = self.safety.new_token("gesture")
            result = self.executor.execute(call, token, snapshot=sig.snapshot, timeout_s=10)
            self._report(sig, result)

    def _report(self, sig: GestureSignal, result: ToolResult) -> None:
        if self.on_result:
            try:
                self.on_result(sig, result)
            except Exception:
                log.exception("Listener kết quả cử chỉ lỗi")
