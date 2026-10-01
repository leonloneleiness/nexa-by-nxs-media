"""Quản lý cửa sổ: xác định cửa sổ đích, chuyển màn hình, thu nhỏ/khôi phục, đóng, focus.

Mọi lệnh Win32 liên quan hình học/trạng thái cửa sổ nằm ở đây (và monitors.py) — các module
cử chỉ/AI chỉ gọi các phương thức cấp cao của WindowManager.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from nexa.core.events import ToolResult
from nexa.desktop import win32api as w
from nexa.desktop.monitors import (MonitorInfo, MonitorManager, clamp_rect_to, map_rect_between_work_areas,
                                   rect_h, rect_w, screen_to_workspace, workspace_to_screen)
from nexa.desktop.window_history import MinimizedEntry, WindowHistory, WindowIdentity
from nexa.utils.logging import get_logger
from nexa.utils.text import fold, truncate

log = get_logger("windows")


@dataclass
class WindowSnapshot:
    identity: WindowIdentity
    title: str
    rect: tuple[int, int, int, int]
    monitor_device: str
    taken_at: float

    def describe(self) -> str:
        return f"{self.identity.process_name} — {truncate(self.title, 50)}"


class WindowManager:
    def __init__(self, api: Any, monitors: MonitorManager, history: WindowHistory,
                 own_pids: set[int] | None = None, sleep: Callable[[float], None] = time.sleep) -> None:
        self.api = api
        self.monitors = monitors
        self.history = history
        self.own_pids = set(own_pids or {api.own_pid()})
        self.sleep = sleep
        self.last_external: WindowIdentity | None = None   # cửa sổ ngoài NEXA được dùng gần nhất

    # ----- định danh & kiểm tra -----
    def identity(self, hwnd: int) -> WindowIdentity | None:
        if not hwnd or not self.api.is_window(hwnd):
            return None
        pid = self.api.get_pid(hwnd)
        name, created, _exe = self.api.process_identity(pid)
        return WindowIdentity(hwnd=hwnd, pid=pid, process_name=name, create_time=created,
                              class_name=self.api.get_class(hwnd))

    def same_window(self, ident: WindowIdentity) -> bool:
        current = self.identity(ident.hwnd)
        return current is not None and current == ident

    def validate_target(self, hwnd: int) -> tuple[bool, str]:
        api = self.api
        if not hwnd or not api.is_window(hwnd):
            return False, "Không có cửa sổ ứng dụng nào đang được chọn."
        root = api.get_root(hwnd) or hwnd
        if root != hwnd:
            return False, "Cửa sổ đang chọn là cửa sổ con, không phải cửa sổ ứng dụng."
        if api.get_pid(hwnd) in self.own_pids:
            return False, "Cửa sổ đang chọn là của NEXA; anh bấm vào ứng dụng cần điều khiển trước."
        cls = api.get_class(hwnd)
        if cls in w.SHELL_CLASSES:
            return False, "Desktop/thanh tác vụ không phải cửa sổ ứng dụng."
        if not api.is_visible(hwnd) or api.is_cloaked(hwnd):
            return False, "Cửa sổ không hiển thị."
        ex = api.get_ex_style(hwnd)
        if ex & w.WS_EX_TOOLWINDOW:
            return False, "Đây là cửa sổ công cụ/overlay, em bỏ qua."
        return True, ""

    def foreground_target(self) -> tuple[int | None, str]:
        hwnd = self.api.get_foreground()
        ok, reason = self.validate_target(hwnd)
        return (hwnd if ok else None), reason

    def snapshot_foreground(self) -> WindowSnapshot | None:
        hwnd, _ = self.foreground_target()
        if hwnd is None:
            return None
        ident = self.identity(hwnd)
        if ident is None:
            return None
        monitors = self.monitors.refresh()
        mon = self.monitors.monitor_of_window(hwnd, monitors)
        return WindowSnapshot(identity=ident, title=self.api.get_title(hwnd), rect=self.api.get_rect(hwnd),
                              monitor_device=mon.device_name if mon else "", taken_at=time.monotonic())

    def verify_snapshot(self, snap: WindowSnapshot | None) -> tuple[bool, str]:
        if snap is None:
            return False, "Không có cửa sổ ứng dụng hợp lệ lúc bắt đầu cử chỉ."
        fg = self.api.get_foreground()
        if fg != snap.identity.hwnd:
            return False, "Cửa sổ đang làm việc đã thay đổi giữa chừng nên em hủy thao tác."
        if not self.same_window(snap.identity):
            return False, "Cửa sổ ban đầu không còn nữa nên em hủy thao tác."
        return True, ""

    def remember_external_foreground(self) -> None:
        hwnd = self.api.get_foreground()
        ok, _ = self.validate_target(hwnd)
        if ok:
            ident = self.identity(hwnd)
            if ident:
                self.last_external = ident

    def resolve_work_window(self) -> tuple[int | None, str]:
        """Cửa sổ ứng dụng để thao tác: foreground nếu hợp lệ, nếu không thì cửa sổ ngoài gần nhất."""
        hwnd, reason = self.foreground_target()
        if hwnd:
            return hwnd, ""
        if self.last_external and self.same_window(self.last_external):
            return self.last_external.hwnd, ""
        return None, reason

    def info(self, hwnd: int) -> dict[str, Any]:
        ident = self.identity(hwnd)
        return {"hwnd": hwnd, "title": self.api.get_title(hwnd), "process": ident.process_name if ident else "",
                "rect": list(self.api.get_rect(hwnd)), "minimized": self.api.is_iconic(hwnd),
                "maximized": self.api.is_zoomed(hwnd)}

    # ----- chuyển màn hình -----
    def move_to_target_monitor(self, hwnd: int) -> ToolResult:
        ok, reason = self.validate_target(hwnd)
        if not ok:
            return ToolResult.failure(reason, "invalid_window")
        roles = self.monitors.roles()
        if roles.problem:
            return ToolResult.failure(roles.problem, "monitor_unavailable")
        src_cfg, dst = roles.source, roles.target
        monitors = roles.monitors
        current = self.monitors.monitor_of_window(hwnd, monitors)
        if current is None:
            return ToolResult.failure("Không xác định được cửa sổ đang ở màn hình nào.", "unknown_monitor")
        title = truncate(self.api.get_title(hwnd), 60)
        if current.hmonitor == dst.hmonitor:
            return ToolResult.success("Cửa sổ đã ở màn hình 2 rồi.", verified=True, no_op=True, title=title,
                                      source=current.device_name, target=dst.device_name)
        if self.api.is_iconic(hwnd):
            return ToolResult.failure("Cửa sổ đang thu nhỏ nên em không chuyển.", "minimized")
        src = current
        primary = self.monitors.primary(monitors)
        try:
            placement = self.api.get_placement(hwnd)
        except OSError:
            return ToolResult.failure("Windows không cho đọc trạng thái cửa sổ này.", "access_denied")
        was_max = self.api.is_zoomed(hwnd) or placement.maximized

        if was_max:
            moved = self._move_maximized(hwnd, placement, src, dst, primary)
        else:
            moved = self._move_normal(hwnd, src, dst)
        if not moved:
            return ToolResult.failure(
                "Windows không cho phép NEXA di chuyển cửa sổ này (có thể ứng dụng chạy quyền quản trị hoặc là cửa sổ đặc biệt).",
                "move_denied")
        # Kiểm chứng
        self.sleep(0.15)
        after = self.monitors.monitor_of_window(hwnd, self.monitors.refresh())
        if after is None or after.device_name != dst.device_name:
            return ToolResult.failure("Em đã gửi lệnh nhưng cửa sổ chưa sang màn hình 2 (ứng dụng có thể chặn).",
                                      "not_verified")
        if was_max and not self.api.is_zoomed(hwnd):
            self.api.show_async(hwnd, w.SW_SHOWMAXIMIZED)
            self.sleep(0.1)
        return ToolResult.success("Đã chuyển sang màn hình 2.", verified=True, title=title,
                                  source=src.device_name, target=dst.device_name,
                                  source_rect=list(src.rect), target_rect=list(dst.rect),
                                  maximized=self.api.is_zoomed(hwnd), rect=list(self.api.get_rect(hwnd)),
                                  configured_source=src_cfg.device_name if src_cfg else "")

    def _move_maximized(self, hwnd: int, placement: w.Placement, src: MonitorInfo, dst: MonitorInfo,
                        primary: MonitorInfo) -> bool:
        normal_screen = workspace_to_screen(placement.normal_rect, primary)
        target_normal = map_rect_between_work_areas(normal_screen, src.work, dst.work, scale=1.0)
        new_pl = w.Placement(show_cmd=w.SW_SHOWMAXIMIZED, flags=placement.flags,
                             normal_rect=screen_to_workspace(target_normal, primary))
        if self.api.set_placement(hwnd, new_pl):
            self.sleep(0.12)
            mon = self.monitors.monitor_of_window(hwnd, self.monitors.refresh())
            if mon is not None and mon.device_name == dst.device_name:
                return True
        # Phương án dự phòng: khôi phục -> dời -> phóng to lại.
        log.info("SetWindowPlacement không chuyển được cửa sổ phóng to, dùng phương án dự phòng")
        self.api.show_async(hwnd, w.SW_RESTORE)
        self.sleep(0.15)
        if not self.api.set_pos(hwnd, target_normal[0], target_normal[1], rect_w(target_normal),
                                rect_h(target_normal)):
            return False
        self.sleep(0.1)
        self.api.show_async(hwnd, w.SW_SHOWMAXIMIZED)
        return True

    def _move_normal(self, hwnd: int, src: MonitorInfo, dst: MonitorInfo) -> bool:
        cur = self.api.get_window_rect(hwnd)
        target = map_rect_between_work_areas(cur, src.work, dst.work, scale=1.0)
        # Bước 1: dời vị trí, giữ kích thước để Windows/ứng dụng tự xử lý WM_DPICHANGED.
        if not self.api.set_pos(hwnd, target[0], target[1], no_size=True):
            return False
        self.sleep(0.12)
        # Bước 2: đọc kích thước thật sau khi đổi DPI rồi giới hạn trong work area đích.
        after = self.api.get_window_rect(hwnd)
        rel = map_rect_between_work_areas((cur[0], cur[1], cur[0] + rect_w(after), cur[1] + rect_h(after)),
                                          src.work, dst.work, scale=1.0)
        fit = clamp_rect_to(dst.work, rel)
        if fit != after:
            self.api.set_pos(hwnd, fit[0], fit[1], rect_w(fit), rect_h(fit))
        return True

    # ----- thu nhỏ / khôi phục -----
    def minimize(self, hwnd: int) -> ToolResult:
        ok, reason = self.validate_target(hwnd)
        if not ok:
            return ToolResult.failure(reason, "invalid_window")
        if self.api.is_iconic(hwnd):
            return ToolResult.success("Cửa sổ đã được thu nhỏ sẵn.", verified=True, no_op=True)
        if not (self.api.get_style(hwnd) & w.WS_MINIMIZEBOX):
            return ToolResult.failure("Cửa sổ này không có nút thu nhỏ nên em không thu nhỏ.", "no_minimize_box")
        ident = self.identity(hwnd)
        title = self.api.get_title(hwnd)
        try:
            placement = self.api.get_placement(hwnd)
        except OSError:
            return ToolResult.failure("Windows không cho đọc trạng thái cửa sổ này.", "access_denied")
        was_max = self.api.is_zoomed(hwnd) or placement.maximized
        rect = self.api.get_rect(hwnd)
        mon = self.monitors.monitor_of_window(hwnd, self.monitors.refresh())
        # Giống thao tác bấm nút "−": gửi WM_SYSCOMMAND/SC_MINIMIZE.
        self.api.post_message(hwnd, w.WM_SYSCOMMAND, w.SC_MINIMIZE, 0)
        if not self._wait(lambda: self.api.is_iconic(hwnd), 1.0):
            self.api.show_async(hwnd, w.SW_MINIMIZE)
            self._wait(lambda: self.api.is_iconic(hwnd), 0.6)
        if not self.api.is_window(hwnd):
            return ToolResult.failure("Cửa sổ đã đóng thay vì thu nhỏ.", "closed")
        if not self.api.is_visible(hwnd):
            return ToolResult.failure("Ứng dụng tự ẩn xuống khay hệ thống thay vì thu nhỏ; em không ghi vào lịch sử.",
                                      "hidden_to_tray")
        if not self.api.is_iconic(hwnd):
            return ToolResult.failure("Ứng dụng không chấp nhận lệnh thu nhỏ.", "not_verified")
        entry = MinimizedEntry(identity=ident, title=title, placement=placement, was_maximized=was_max,
                               rect=rect, monitor=MonitorManager.identity(mon) if mon else {},
                               session_id=self.history.session_id)
        self.history.push(entry)
        return ToolResult.success(f"Đã thu nhỏ {truncate(title, 50) or ident.process_name}.", verified=True,
                                  title=title, rect=list(rect), history_size=len(self.history))

    def restore_last(self) -> ToolResult:
        def validator(entry: MinimizedEntry) -> tuple[bool, str]:
            hwnd = entry.identity.hwnd
            if not self.api.is_window(hwnd):
                return False, "cửa sổ đã đóng"
            if self.identity(hwnd) != entry.identity:
                return False, "HWND đã được dùng cho cửa sổ khác"
            if not self.api.is_iconic(hwnd):
                return False, "anh đã tự khôi phục"
            return True, ""

        entry, skipped = self.history.pop_valid(validator)
        for e, why in skipped:
            log.info("Bỏ qua mục lịch sử %s: %s", e.title, why)
        if entry is None:
            return ToolResult.failure("Chưa có cửa sổ để khôi phục.", "history_empty",
                                      skipped=[e.title for e, _ in skipped])
        hwnd = entry.identity.hwnd
        monitors = self.monitors.refresh()
        primary = self.monitors.primary(monitors)
        normal_ws = entry.placement.normal_rect
        moved_note = ""
        if primary is not None:
            old_mon = MonitorManager.resolve(entry.monitor, monitors) if entry.monitor else None
            if old_mon is None:
                # Màn hình cũ đã ngắt: đưa về work area của màn hình còn hoạt động (màn hình chính).
                normal_screen = workspace_to_screen(normal_ws, primary)
                fitted = clamp_rect_to(primary.work, normal_screen)
                normal_ws = screen_to_workspace(fitted, primary)
                moved_note = " (màn hình cũ đã ngắt nên em đưa về màn hình chính)"
        show_cmd = w.SW_SHOWMAXIMIZED if entry.was_maximized else w.SW_RESTORE
        flags = entry.placement.flags | (w.WPF_RESTORETOMAXIMIZED if entry.was_maximized else 0)
        if not self.api.set_placement(hwnd, w.Placement(show_cmd=show_cmd, flags=flags, normal_rect=normal_ws)):
            self.api.show_async(hwnd, w.SW_RESTORE)
        if not self._wait(lambda: not self.api.is_iconic(hwnd), 1.0):
            self.history.push_back(entry)
            return ToolResult.failure("Ứng dụng chưa chịu khôi phục, em giữ lại trong lịch sử.", "not_verified")
        focused = self.api.set_foreground(hwnd)
        if entry.was_maximized and not self.api.is_zoomed(hwnd):
            self.api.show_async(hwnd, w.SW_SHOWMAXIMIZED)
        note = "" if focused else " Windows có thể chỉ nháy biểu tượng trên thanh tác vụ thay vì đưa lên trước."
        return ToolResult.success(f"Đã khôi phục {truncate(entry.title, 50) or entry.identity.process_name}.{moved_note}{note}",
                                  verified=True, title=entry.title, rect=list(self.api.get_rect(hwnd)),
                                  maximized=self.api.is_zoomed(hwnd), skipped=[e.title for e, _ in skipped])

    # ----- thao tác khác -----
    def maximize(self, hwnd: int) -> ToolResult:
        ok, reason = self.validate_target(hwnd)
        if not ok:
            return ToolResult.failure(reason, "invalid_window")
        self.api.show_async(hwnd, w.SW_SHOWMAXIMIZED)
        if self._wait(lambda: self.api.is_zoomed(hwnd), 1.0):
            return ToolResult.success("Đã phóng to cửa sổ.", verified=True)
        return ToolResult.failure("Cửa sổ không chấp nhận phóng to.", "not_verified")

    def restore_window(self, hwnd: int) -> ToolResult:
        if not self.api.is_window(hwnd):
            return ToolResult.failure("Cửa sổ không còn tồn tại.", "invalid_window")
        self.api.show_async(hwnd, w.SW_RESTORE)
        if self._wait(lambda: not self.api.is_iconic(hwnd) and not self.api.is_zoomed(hwnd), 1.0):
            return ToolResult.success("Đã đưa cửa sổ về kích thước thường.", verified=True)
        return ToolResult.failure("Cửa sổ không đổi trạng thái.", "not_verified")

    def focus(self, hwnd: int) -> ToolResult:
        if not self.api.is_window(hwnd):
            return ToolResult.failure("Cửa sổ không còn tồn tại.", "invalid_window")
        if self.api.is_iconic(hwnd):
            self.api.show_async(hwnd, w.SW_RESTORE)
            self._wait(lambda: not self.api.is_iconic(hwnd), 1.0)
        self.api.set_foreground(hwnd)
        if self._wait(lambda: self.api.get_foreground() == hwnd, 1.0):
            ident = self.identity(hwnd)
            if ident:
                self.last_external = ident
            return ToolResult.success(f"Đã chuyển tới {truncate(self.api.get_title(hwnd), 50)}.", verified=True)
        return ToolResult.failure("Windows không cho đưa cửa sổ lên trước lúc này (giới hạn foreground). "
                                  "Anh bấm vào cửa sổ đó giúp em.", "foreground_denied")

    # ----- theo hướng nhìn (nexa/core/attention.py) -----
    def top_window_on_monitor(self, device_name: str) -> int | None:
        """Cửa sổ ứng dụng trên cùng (theo thứ tự z) đang hiện trên màn hình device_name; không tính cửa sổ NEXA."""
        monitors = self.monitors.refresh()
        for hwnd in self.api.enum_windows():
            ok, _ = self.validate_target(hwnd)
            if not ok or self.api.is_iconic(hwnd) or not self.api.get_title(hwnd):
                continue
            mon = self.monitors.monitor_of_window(hwnd, monitors)
            if mon is not None and mon.device_name == device_name:
                return hwnd
        return None

    def follow_attention(self, device_name: str) -> ToolResult:
        """Đưa cửa sổ trên cùng của màn hình anh đang nhìn lên foreground (nếu foreground đang ở màn hình khác)."""
        fg, _ = self.foreground_target()
        monitors = self.monitors.refresh()
        if fg is not None:
            mon = self.monitors.monitor_of_window(fg, monitors)
            if mon is not None and mon.device_name == device_name:
                return ToolResult.success("Cửa sổ đang dùng đã ở màn hình anh nhìn.", verified=True, no_op=True, hwnd=fg)
        hwnd = self.top_window_on_monitor(device_name)
        if hwnd is None:
            return ToolResult.failure("Màn hình anh đang nhìn không có cửa sổ ứng dụng nào.", "no_window")
        force = getattr(self.api, "force_foreground", None)
        if force is not None and not self.api.is_iconic(hwnd):
            force(hwnd)
            if self._wait(lambda: self.api.get_foreground() == hwnd, 0.3):
                ident = self.identity(hwnd)
                if ident:
                    self.last_external = ident
                return ToolResult.success(f"Đã chuyển tới {truncate(self.api.get_title(hwnd), 50)}.", verified=True,
                                          hwnd=hwnd, rect=list(self.api.get_rect(hwnd)))
        res = self.focus(hwnd)
        res.data.setdefault("hwnd", hwnd)
        res.data.setdefault("rect", list(self.api.get_rect(hwnd)))
        return res

    def close(self, hwnd: int) -> ToolResult:
        ok, reason = self.validate_target(hwnd)
        if not ok:
            return ToolResult.failure(reason, "invalid_window")
        title = self.api.get_title(hwnd)
        self.api.post_message(hwnd, w.WM_CLOSE, 0, 0)
        if self._wait(lambda: not self.api.is_window(hwnd), 1.5):
            return ToolResult.success(f"Đã đóng {truncate(title, 50)}.", verified=True)
        return ToolResult(ok=True, verified=False, message=(
            "Em đã gửi lệnh đóng thông thường. Ứng dụng vẫn mở — có thể đang hỏi lưu; em không tự bỏ qua hộp thoại đó."),
            data={"title": title})

    def list_windows(self, limit: int = 40) -> list[dict[str, Any]]:
        out = []
        for hwnd in self.api.enum_windows():
            ok, _ = self.validate_target(hwnd)
            if not ok:
                continue
            title = self.api.get_title(hwnd)
            if not title:
                continue
            ident = self.identity(hwnd)
            out.append({"hwnd": hwnd, "title": truncate(title, 80), "process": ident.process_name if ident else "",
                        "minimized": self.api.is_iconic(hwnd)})
            if len(out) >= limit:
                break
        return out

    def find_windows(self, query: str) -> list[dict[str, Any]]:
        q = fold(query)
        if not q:
            return []
        matches = []
        for item in self.list_windows(limit=100):
            hay = fold(item["title"]) + " " + fold(item["process"].rsplit(".", 1)[0])
            if q in hay:
                matches.append(item)
        return matches

    def wait_for_new_window(self, before: set[int], process_names: set[str], timeout: float = 8.0) -> int | None:
        names = {n.lower() for n in process_names}
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for hwnd in self.api.enum_windows():
                if hwnd in before:
                    continue
                ok, _ = self.validate_target(hwnd)
                if not ok or not self.api.get_title(hwnd):
                    continue
                ident = self.identity(hwnd)
                if ident and (not names or ident.process_name.lower() in names):
                    return hwnd
            self.sleep(0.2)
        return None

    def _wait(self, cond: Callable[[], bool], timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while True:
            try:
                if cond():
                    return True
            except Exception:
                return False
            if time.monotonic() >= deadline:
                return False
            self.sleep(0.05)
