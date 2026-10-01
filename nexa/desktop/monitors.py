"""Nhận diện màn hình, work area, DPI và vai trò nguồn/đích.

- Luôn liệt kê lại màn hình trước mỗi hành động (không giữ HMONITOR cũ sau khi cắm/rút).
- Định danh màn hình được lưu bằng đường dẫn thiết bị ổn định (monitorDevicePath từ
  QueryDisplayConfig) kèm tên GDI (\\\\.\\DISPLAYn) và tên EDID để xác minh lại.
- Thứ tự liệt kê KHÔNG được coi là số trong Windows Display Settings; người dùng chọn
  nguồn "1" và đích "2" qua nút "Nhận diện màn hình".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from nexa.desktop.win32api import RawMonitor, Rect
from nexa.utils.logging import get_logger

log = get_logger("monitors")

MonitorInfo = RawMonitor


def rect_w(r: Rect) -> int:
    return r[2] - r[0]


def rect_h(r: Rect) -> int:
    return r[3] - r[1]


def rect_center(r: Rect) -> tuple[float, float]:
    return ((r[0] + r[2]) / 2.0, (r[1] + r[3]) / 2.0)


def intersection_area(a: Rect, b: Rect) -> int:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0, w) * max(0, h)


def monitor_for_rect(monitors: Iterable[MonitorInfo], rect: Rect) -> MonitorInfo | None:
    best, best_area = None, 0
    for m in monitors:
        area = intersection_area(m.rect, rect)
        if area > best_area:
            best, best_area = m, area
    return best


def workspace_offset(primary: MonitorInfo) -> tuple[int, int]:
    """Gốc tọa độ workspace = góc trên-trái work area của màn hình chính."""
    return primary.work[0], primary.work[1]


def screen_to_workspace(rect: Rect, primary: MonitorInfo) -> Rect:
    ox, oy = workspace_offset(primary)
    return (rect[0] - ox, rect[1] - oy, rect[2] - ox, rect[3] - oy)


def workspace_to_screen(rect: Rect, primary: MonitorInfo) -> Rect:
    ox, oy = workspace_offset(primary)
    return (rect[0] + ox, rect[1] + oy, rect[2] + ox, rect[3] + oy)


def map_rect_between_work_areas(win: Rect, src_work: Rect, dst_work: Rect,
                                scale: float = 1.0) -> Rect:
    """Giữ vị trí tương đối của cửa sổ, co kích thước theo DPI (scale) và giới hạn trong work area đích."""
    w = max(80, int(round(rect_w(win) * scale)))
    h = max(60, int(round(rect_h(win) * scale)))
    dw, dh = rect_w(dst_work), rect_h(dst_work)
    w, h = min(w, dw), min(h, dh)
    sw, sh = rect_w(src_work), rect_h(src_work)
    free_sx = max(1, sw - rect_w(win))
    free_sy = max(1, sh - rect_h(win))
    rel_x = min(1.0, max(0.0, (win[0] - src_work[0]) / free_sx))
    rel_y = min(1.0, max(0.0, (win[1] - src_work[1]) / free_sy))
    x = dst_work[0] + int(round(rel_x * max(0, dw - w)))
    y = dst_work[1] + int(round(rel_y * max(0, dh - h)))
    return clamp_rect_to(dst_work, (x, y, x + w, y + h))


def clamp_rect_to(area: Rect, r: Rect) -> Rect:
    w = min(rect_w(r), rect_w(area))
    h = min(rect_h(r), rect_h(area))
    x = min(max(r[0], area[0]), area[2] - w)
    y = min(max(r[1], area[1]), area[3] - h)
    return (x, y, x + w, y + h)


@dataclass
class RoleResolution:
    source: MonitorInfo | None
    target: MonitorInfo | None
    monitors: list[MonitorInfo]
    problem: str = ""          # thông báo tiếng Việt nếu không thể dùng hai màn hình
    configured: bool = False


class MonitorManager:
    def __init__(self, api: Any, config: Any = None) -> None:
        self.api = api
        self.config = config

    def refresh(self) -> list[MonitorInfo]:
        try:
            return list(self.api.enum_monitors())
        except Exception:
            log.exception("Không liệt kê được màn hình")
            return []

    @staticmethod
    def identity(m: MonitorInfo) -> dict[str, str]:
        return {"device_id": m.device_id, "device_name": m.device_name, "friendly_name": m.friendly_name}

    @staticmethod
    def resolve(identity: dict | None, monitors: list[MonitorInfo]) -> MonitorInfo | None:
        if not identity:
            return None
        dev_id = identity.get("device_id") or ""
        if dev_id:
            for m in monitors:
                if m.device_id and m.device_id == dev_id:
                    return m
        name = identity.get("device_name") or ""
        friendly = identity.get("friendly_name") or ""
        for m in monitors:
            if m.device_name == name and (not friendly or m.friendly_name == friendly):
                return m
        return None

    @staticmethod
    def primary(monitors: list[MonitorInfo]) -> MonitorInfo | None:
        for m in monitors:
            if m.primary:
                return m
        return monitors[0] if monitors else None

    def roles(self) -> RoleResolution:
        monitors = self.refresh()
        src_id = self.config.get("monitors.source") if self.config else None
        dst_id = self.config.get("monitors.target") if self.config else None
        configured = bool(src_id and dst_id)
        if len(monitors) < 2:
            return RoleResolution(None, None, monitors,
                                  "Em chỉ thấy một màn hình (có thể đang Duplicate hoặc màn hình 2 đã ngắt).",
                                  configured)
        if configured:
            src = self.resolve(src_id, monitors)
            dst = self.resolve(dst_id, monitors)
            if dst is None:
                return RoleResolution(src, None, monitors,
                                      "Màn hình đích đã chọn không còn kết nối. Anh chọn lại trong Cài đặt > Màn hình.",
                                      configured)
            if src is None:
                src = next((m for m in monitors if m.hmonitor != dst.hmonitor), None)
            if src is not None and src.hmonitor == dst.hmonitor:
                return RoleResolution(src, dst, monitors, "Màn hình nguồn và đích đang trùng nhau.", configured)
            return RoleResolution(src, dst, monitors, "", configured)
        # Chưa cấu hình: nguồn = màn hình chính, đích = màn hình còn lại gần nhất bên phải.
        src = self.primary(monitors)
        others = [m for m in monitors if m.hmonitor != src.hmonitor]
        others.sort(key=lambda m: (0 if m.rect[0] >= src.rect[2] else 1, abs(m.rect[0] - src.rect[2])))
        return RoleResolution(src, others[0], monitors, "", False)

    def monitor_of_window(self, hwnd: int, monitors: list[MonitorInfo]) -> MonitorInfo | None:
        try:
            hmon = self.api.monitor_from_window(hwnd)
        except Exception:
            hmon = 0
        for m in monitors:
            if m.hmonitor == hmon:
                return m
        try:
            return monitor_for_rect(monitors, self.api.get_rect(hwnd))
        except Exception:
            return None

    def set_roles(self, source_device_name: str, target_device_name: str) -> tuple[bool, str]:
        monitors = self.refresh()
        src = next((m for m in monitors if m.device_name == source_device_name), None)
        dst = next((m for m in monitors if m.device_name == target_device_name), None)
        if src is None or dst is None:
            return False, "Không tìm thấy màn hình đã chọn."
        if src.hmonitor == dst.hmonitor:
            return False, "Màn hình nguồn và đích phải khác nhau."
        self.config.set("monitors.source", self.identity(src))
        self.config.set("monitors.target", self.identity(dst))
        self.config.save()
        return True, f"Đã chọn nguồn: {src.friendly_name} ({src.device_name}), đích: {dst.friendly_name} ({dst.device_name})."

    def describe(self) -> list[dict[str, Any]]:
        monitors = self.refresh()
        roles = self.roles()
        out = []
        for m in monitors:
            role = ""
            if roles.source is not None and m.hmonitor == roles.source.hmonitor:
                role = "source"
            if roles.target is not None and m.hmonitor == roles.target.hmonitor:
                role = "target"
            out.append({
                "device_name": m.device_name, "friendly_name": m.friendly_name, "device_id": m.device_id,
                "x": m.rect[0], "y": m.rect[1], "width": rect_w(m.rect), "height": rect_h(m.rect),
                "work": list(m.work), "dpi": m.dpi, "scale": round(m.dpi / 96.0 * 100), "primary": m.primary,
                "role": role,
            })
        return out
