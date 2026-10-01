"""Executor tuần tự: mọi thao tác lên máy tính đi qua đúng một luồng.

Trách nhiệm:
- Kiểm tra schema, quyền, trạng thái dừng khẩn cấp và khóa điều khiển (lease).
- Hỏi xác nhận cho hành động rủi ro và kiểm tra lại đích trước khi chạy.
- Chống chạy trùng: kết quả mỗi (task_id, step/call id) được lưu; gửi lại cùng khóa sẽ
  nhận kết quả cũ thay vì thực hiện lần nữa.
- Hủy hàng đợi khi dừng khẩn cấp; tác vụ đến muộn không được chạy.
"""
from __future__ import annotations

import queue
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any, Callable

from nexa.core.events import Source, TaskEvent, ToolCall, ToolResult
from nexa.core.safety import CancelToken, SafetyManager
from nexa.utils.logging import get_logger

log = get_logger("executor")


@dataclass
class ExecContext:
    source: Source
    token: CancelToken
    services: Any = None
    snapshot: Any = None
    task_id: str = ""
    confirmed: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class _WorkItem:
    call: ToolCall
    ctx: ExecContext
    future: Future


class Executor:
    def __init__(self, registry, safety: SafetyManager, services: Any = None,
                 queue_size: int = 32, com_init: bool = True,
                 autonomy: Callable[[], str] | None = None) -> None:
        self.registry = registry
        self.autonomy = autonomy or (lambda: "standard")
        self.safety = safety
        self.services = services
        self._queue: "queue.Queue[_WorkItem | None]" = queue.Queue(maxsize=queue_size)
        self._thread: threading.Thread | None = None
        self._running = False
        self._com_init = com_init
        self._listeners: list[Callable[[TaskEvent], None]] = []
        self._confirm_hooks: list[Callable[[bool], None]] = []
        self._cache: "OrderedDict[tuple[str, str], ToolResult]" = OrderedDict()
        self._cache_lock = threading.Lock()
        self._owner: str | None = None
        self._owner_lock = threading.Lock()
        self._busy = threading.Event()

    # ----- vòng đời -----
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker, name="nexa-executor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self.cancel_all("shutdown")
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._thread:
            self._thread.join(timeout=3)

    def add_listener(self, fn: Callable[[TaskEvent], None]) -> None:
        self._listeners.append(fn)

    def add_confirm_hook(self, fn: Callable[[bool], None]) -> None:
        """fn(True) khi bắt đầu chờ xác nhận, fn(False) khi xong."""
        self._confirm_hooks.append(fn)

    # ----- khóa điều khiển -----
    @property
    def control_owner(self) -> str | None:
        with self._owner_lock:
            return self._owner

    def acquire_control(self, owner: str) -> bool:
        with self._owner_lock:
            if self._owner is None or self._owner == owner:
                self._owner = owner
                return True
            return False

    def release_control(self, owner: str) -> None:
        with self._owner_lock:
            if self._owner == owner:
                self._owner = None

    def force_release_control(self) -> None:
        with self._owner_lock:
            self._owner = None

    @staticmethod
    def owner_key(call: ToolCall) -> str:
        if call.source == Source.AI:
            return f"ai:{call.task_id}"
        if call.source == Source.GESTURE:
            return "gesture"
        return "user"

    # ----- API chính -----
    def execute(self, call: ToolCall, token: CancelToken, snapshot: Any = None,
                timeout_s: float = 60.0) -> ToolResult:
        """Chạy một tool call qua toàn bộ kiểm tra. Chặn luồng gọi (không gọi từ luồng GUI)."""
        spec = self.registry.get(call.name)
        if spec is None:
            return self._reject(call, ToolResult.failure(f"Công cụ '{call.name}' không tồn tại.", "unknown_tool"))
        ok, err, args = self.registry.validate(call.name, call.args, source=call.source)
        if not ok:
            return self._reject(call, ToolResult.failure(f"Tham số không hợp lệ: {err}", "invalid_args"))
        call.args = args

        cached = self._cached(call)
        if cached is not None:
            log.info("Bỏ qua chạy lại %s (%s) — dùng kết quả đã có", call.name, call.idempotency_key)
            return cached

        if token.cancelled:
            return self._reject(call, ToolResult.failure("Tác vụ đã bị hủy.", "cancelled"))
        if self.safety.control_paused and not spec.allowed_when_paused:
            return self._reject(call, ToolResult.failure(
                "Quyền điều khiển đang tạm dừng sau lệnh dừng khẩn cấp. Anh bấm 'Tiếp tục điều khiển' để bật lại.",
                "control_paused"))

        owner = self.owner_key(call)
        if spec.needs_control:
            current = self.control_owner
            if current is not None and current != owner:
                who = "tác vụ tự động" if current.startswith("ai:") else (
                    "cử chỉ" if current == "gesture" else "lệnh khác")
                return self._reject(call, ToolResult.failure(
                    f"Đang có {who} giữ quyền điều khiển. Anh chờ xong hoặc nói 'dừng lại' để hủy.", "busy"))

        ctx = ExecContext(source=call.source, token=token, services=self.services,
                          snapshot=snapshot if snapshot is not None else call.snapshot, task_id=call.task_id)

        if spec.precheck is not None:
            blocked = spec.precheck(args, ctx)
            if blocked is not None:
                return self._reject(call, blocked)

        assessment = spec.assess(args, ctx)
        needs_confirm = assessment.needs_confirmation(call.source)
        if needs_confirm and not spec.always_confirm and self.autonomy() == "full":
            # Người dùng đã trao toàn quyền: tự duyệt nhưng vẫn ghi vết để xem lại.
            description = spec.describe(args, ctx, assessment)
            log.info("Toàn quyền — tự duyệt: %s", description)
            self._emit(call, "auto_approved", "Tự duyệt (toàn quyền): " + description)
            needs_confirm = False
        if needs_confirm:
            fingerprint = spec.fingerprint(args, ctx)
            description = spec.describe(args, ctx, assessment)
            preview = spec.preview(args, ctx) if spec.preview else {}
            pending = self.safety.request_confirmation(call, description, fingerprint, preview=preview)
            self._emit(call, "confirming", description)
            for hook in self._confirm_hooks:
                hook(True)
            try:
                approved = self.safety.wait_confirmation(pending, token)
            finally:
                for hook in self._confirm_hooks:
                    hook(False)
            if not approved:
                reason = "Tác vụ đã bị hủy." if token.cancelled else "Anh chưa xác nhận nên em không thực hiện."
                return self._finish(call, ToolResult.failure(reason, "not_confirmed"), cache=True)
            if spec.fingerprint(args, ctx) != fingerprint:
                return self._finish(call, ToolResult.failure(
                    "Đối tượng đã thay đổi sau khi anh xác nhận nên em hủy để an toàn.", "target_changed"), cache=True)
            ctx.confirmed = True
            ctx.extra.update(pending.preview)
            ctx.extra.update(pending.extra)

        future: Future = Future()
        item = _WorkItem(call, ctx, future)
        try:
            self._queue.put(item, timeout=2.0)
        except queue.Full:
            return self._reject(call, ToolResult.failure("Hàng đợi thao tác đang đầy, anh thử lại sau.", "queue_full"))
        self._emit(call, "queued", spec.title)

        deadline = time.monotonic() + timeout_s
        while True:
            try:
                return future.result(timeout=0.1)
            except TimeoutError:  # concurrent.futures.TimeoutError là alias từ Python 3.11
                if time.monotonic() > deadline:
                    token.cancel("timeout")
                    return ToolResult.failure("Thao tác quá thời gian chờ.", "timeout")

    def cancel_all(self, reason: str = "Dừng") -> int:
        n = 0
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is None:
                continue
            item.ctx.token.cancel(reason)
            if not item.future.done():
                item.future.set_result(ToolResult.failure("Đã hủy do dừng khẩn cấp.", "cancelled"))
            self._emit(item.call, "cancelled", reason)
            n += 1
        self.force_release_control()
        if n:
            log.warning("Đã hủy %d thao tác trong hàng đợi (%s)", n, reason)
        return n

    @property
    def busy(self) -> bool:
        return self._busy.is_set() or not self._queue.empty()

    # ----- nội bộ -----
    def _worker(self) -> None:
        if self._com_init:
            try:
                import pythoncom
                pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
            except Exception:
                log.debug("Không khởi tạo được COM trong executor")
        while self._running:
            item = self._queue.get()
            if item is None:
                break
            call, ctx, future = item.call, item.ctx, item.future
            if ctx.token.cancelled:
                future.set_result(self._finish(call, ToolResult.failure("Đã hủy trước khi thực hiện.", "cancelled"), cache=False))
                continue
            if self.safety.control_paused and not self.registry.get(call.name).allowed_when_paused:
                future.set_result(self._finish(call, ToolResult.failure("Quyền điều khiển đang tạm dừng.", "control_paused"), cache=False))
                continue
            spec = self.registry.get(call.name)
            # Quyền điều khiển có thể đã đổi chủ trong lúc thao tác nằm trong hàng đợi.
            if spec.needs_control and self.control_owner not in (self.owner_key(call), None):
                future.set_result(self._finish(call, ToolResult.failure("Quyền điều khiển đang bận.", "busy"), cache=False))
                continue
            self._busy.set()
            self._emit(call, "running", spec.title)
            started = time.monotonic()
            # cửa sổ công cụ này mở ra sẽ được xếp CẠNH NEXA (nexa/desktop/side_by_side.py), không che NEXA
            sbs = getattr(self.services, "side_by_side", None)
            snap = None
            try:
                snap = sbs.before(call.name) if sbs is not None else None
            except Exception:
                log.debug("side_by_side.before lỗi", exc_info=True)
            try:
                result = spec.handler(call.args, ctx)
                if not isinstance(result, ToolResult):
                    result = ToolResult.failure("Công cụ trả về dữ liệu không hợp lệ.", "bad_result")
            except Exception as exc:  # lỗi công cụ không làm sập executor
                log.exception("Công cụ %s lỗi", call.name)
                result = ToolResult.failure(f"Lỗi khi thực hiện: {exc}", "exception")
            finally:
                self._busy.clear()
            # Ghi vết thời gian từng thao tác để tìm chỗ chậm/lỗi (không ghi tham số: có thể chứa nội dung riêng).
            log.info("Công cụ %s: %s trong %d ms", call.name, "OK" if result.ok else f"LỖI {result.error_code}",
                     int((time.monotonic() - started) * 1000))
            if snap is not None and not ctx.token.cancelled:
                try:
                    sbs.after(snap, call.name, result.ok)
                except Exception:
                    log.debug("side_by_side.after lỗi", exc_info=True)
            if ctx.token.cancelled and result.ok:
                result.message += " (tác vụ đã bị hủy sau bước này)"
            future.set_result(self._finish(call, result, cache=True))

    def _cached(self, call: ToolCall) -> ToolResult | None:
        with self._cache_lock:
            return self._cache.get(call.idempotency_key)

    def _finish(self, call: ToolCall, result: ToolResult, cache: bool) -> ToolResult:
        if cache:
            with self._cache_lock:
                self._cache[call.idempotency_key] = result
                while len(self._cache) > 500:
                    self._cache.popitem(last=False)
        status = "done" if result.ok else ("cancelled" if result.error_code == "cancelled" else "failed")
        self._emit(call, status, result.message, result.data)
        return result

    def _reject(self, call: ToolCall, result: ToolResult) -> ToolResult:
        self._emit(call, "rejected", result.message)
        return result

    def _emit(self, call: ToolCall, status: str, message: str, data: dict | None = None) -> None:
        ev = TaskEvent(task_id=call.task_id, step_id=call.step_id, tool=call.name, status=status,
                       message=message, source=call.source, data=dict(data or {}))
        for fn in list(self._listeners):
            try:
                fn(ev)
            except Exception:
                log.exception("Listener executor lỗi")
