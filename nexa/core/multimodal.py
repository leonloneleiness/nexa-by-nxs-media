"""Bounded capture-time history for voice/gesture arbitration (no hardware or AI)."""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from nexa.core.events import Source, ToolCall, ToolResult


@dataclass
class SpeechContext:
    start: float
    end: float = 0.0
    mode: str = "system"
    project_id: str = ""
    selected: str = ""
    terms: tuple[str, ...] = ()
    epoch: int = 0
    confirmed: bool = False
    executing: bool = False


@dataclass
class Action:
    at: float
    name: str
    args: dict
    source: Source
    target: str
    applied: bool = False
    consumed: bool = False


def signature(name: str, args: dict) -> tuple[str, str]:
    """Only explicitly compatible command families may be merged."""
    if name in ("youtube_pause", "youtube_resume"):
        return "media", name
    # Window actions keep snapshot validation; matching names alone is not enough.
    if name in ("explode_3d_assembly", "collapse_3d_assembly"):
        return "assembly", name
    if name in ("zoom_3d_view", "rotate_3d_view", "scroll"):
        return name, str(args.get("direction", ""))
    if name == "set_3d_motion":
        return "motion", str(bool(args.get("on")))
    return "", ""


class MultimodalCoordinator:
    def __init__(self, config: Any, clock=time.monotonic) -> None:
        self.config, self.clock = config, clock
        self._lock = threading.RLock()
        self.execution_lock = threading.RLock()
        self._actions: deque[Action] = deque(maxlen=512)
        self._targets: deque[tuple[float, str, str]] = deque(maxlen=256)
        self._pending: dict[int, SpeechContext] = {}
        self.epoch = 0

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("multimodal.enabled", True))

    @property
    def window(self) -> float:
        return max(0.1, min(2.0, float(self.config.get("multimodal.window_s", 0.8))))

    def clear(self) -> None:
        with self._lock:
            self.epoch += 1
            self._pending.clear()
            self._actions.clear()
            self._targets.clear()

    def begin(self, context: SpeechContext) -> None:
        with self._lock:
            context.epoch = self.epoch
            self._pending[id(context)] = context

    def finish(self, context: SpeechContext | None) -> None:
        with self._lock:
            if context is not None:
                self._pending.pop(id(context), None)

    def waiting(self) -> bool:
        with self._lock:
            now = self.clock()
            limit = float(self.config.get("multimodal.max_pending_s", 20.0))
            for key, ctx in list(self._pending.items()):
                if now - ctx.start > limit:
                    self._pending.pop(key, None)
            return self.enabled and bool(self._pending)

    def target(self, at: float, project: str, selected: str) -> None:
        with self._lock:
            self._targets.append((at, project, selected))

    def resolve_target(self, ctx: SpeechContext) -> str:
        with self._lock:
            hits = [(t, part) for t, project, part in self._targets
                    if project == ctx.project_id and ctx.start - self.window <= t <= ctx.end + self.window]
            ids = {part for _, part in hits if part}
            if ctx.selected:
                ids.add(ctx.selected)
            # Multiple different targets in one phrase are deliberately ambiguous.
            if len(ids) > 1:
                return ""
            if hits:
                return max(hits)[1]
            return ctx.selected

    def observe(self, name: str, args: dict, at: float, target: str = "",
                source: Source = Source.GESTURE, applied: bool = False) -> Action:
        action = Action(at, name, dict(args), source, target, applied)
        with self._lock:
            self._actions.append(action)
        return action

    def reconcile(self, calls: list[tuple[str, dict]], ctx: SpeechContext) -> tuple[list, str]:
        """Consume held equivalents; omit already applied equivalents; reject contradictions."""
        if not self.enabled:
            return calls, ""
        with self._lock:
            if ctx.epoch != self.epoch:
                return [], "Lượt điều khiển đã bị hủy. Anh nói lại lệnh giúp em."
            nearby = [a for a in self._actions if a.source == Source.GESTURE and not a.consumed
                      and ctx.start - self.window <= a.at <= ctx.end + self.window
                      and a.target == ctx.project_id]
            matched: list[Action] = []
            remaining = []
            conflict = False
            for name, args in calls:
                family, operation = signature(name, args)
                same = []
                for action in nearby:
                    af, ao = signature(action.name, action.args)
                    if family and family == af:
                        matched.append(action)
                        if operation != ao:
                            conflict = True
                        else:
                            same.append(action)
                if not any(a.applied for a in same):
                    remaining.append((name, dict(args)))
            for action in matched:
                action.consumed = True
            if conflict:
                return [], "Lời nói và cử chỉ đang trái nhau. Anh xác nhận thực hiện theo lời nói nhé?"
            return remaining, ""

    def guard(self, call: ToolCall) -> ToolResult | None:
        """Called on the executor thread, so a successful action is committed before the next check."""
        if not self.enabled or call.source not in (Source.VOICE, Source.GESTURE):
            return None
        stamp = call.input_started_at
        if stamp is None:
            return None
        family, operation = signature(call.name, call.args)
        if not family:
            return None
        end = call.input_ended_at if call.input_ended_at is not None else stamp
        with self._lock:
            for a in reversed(self._actions):
                if not a.applied or a.source == call.source or a.target != call.target_id:
                    continue
                if not stamp - self.window <= a.at <= end + self.window:
                    continue
                af, ao = signature(a.name, a.args)
                if af == family:
                    if ao == operation:
                        return ToolResult.success("Đã gộp lời nói và cử chỉ thành một thao tác.", no_op=True)
                    return ToolResult.failure("Lời nói và cử chỉ trái nhau; anh thực hiện lại một lệnh rõ ràng nhé.",
                                              "multimodal_conflict")
        return None

    def commit(self, call: ToolCall, result: ToolResult) -> None:
        if result.ok and not result.data.get("no_op") and call.input_started_at is not None:
            self.observe(call.name, call.args, call.input_ended_at or call.input_started_at,
                         call.target_id, call.source, applied=True)
