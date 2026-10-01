"""Đọc Zalo PC: AI ĐANG CÓ TIN NHẮN CHƯA ĐỌC — chỉ tên cuộc trò chuyện + số tin, KHÔNG đọc nội dung tin nhắn.

Zalo PC là ứng dụng Electron; UI Automation thấy danh sách trò chuyện trong Group id="conversationListId" › Table
dưới dạng các ô chữ rời (tên, giờ, trích tin, số chưa đọc…). Cách nhận (đo trên máy anh Sơn, 2026-09-23):
- Tên cuộc trò chuyện = ô chữ có cỡ chữ (chiều cao) LỚN NHẤT trong danh sách, ở cột chữ.
- Số chưa đọc = ô chỉ gồm chữ số (hoặc "5+", "99+") nằm ở cột ảnh đại diện, bên TRÁI cột chữ; thuộc về cuộc trò
  chuyện có tên nằm ngay phía trên nó.
Ô trích tin nhắn không bao giờ được đọc ra hay ghi log.
Cửa sổ Zalo thu nhỏ vẫn đọc được. Lần đầu Electron cần ~1–2 s để dựng cây trợ năng, nên có thử lại.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

from nexa.core.events import ToolResult
from nexa.utils.logging import get_logger

log = get_logger("zalo")

BADGE_RE = re.compile(r"^\d{1,3}\+?$")


@dataclass
class TextBox:
    text: str
    left: int
    top: int
    height: int


@dataclass
class Unread:
    name: str
    count: str


def parse_unread(boxes: list[TextBox]) -> list[Unread]:
    """Từ các ô chữ của danh sách trò chuyện → [(tên, số chưa đọc)] theo thứ tự hiển thị. Hàm thuần (dễ kiểm thử).

    Tên = ô có ĐÚNG cỡ chữ lớn nhất (trích tin nhắn nhỏ hơn chỉ 1 px nên không dùng dung sai), gom các mảnh trên cùng
    một dòng. Số chưa đọc = ô toàn chữ số ở bên trái cột tên, thuộc dòng tên gần nhất phía trên.
    """
    boxes = [b for b in boxes if b.text.strip()]
    words = [b for b in boxes if not BADGE_RE.match(b.text.strip())]
    if not words:
        return []
    name_h = max(b.height for b in words)
    name_boxes = sorted((b for b in words if b.height == name_h), key=lambda b: (b.top, b.left))
    rows: list[list[TextBox]] = []
    for b in name_boxes:
        if rows and abs(rows[-1][0].top - b.top) <= 4:
            rows[-1].append(b)
        else:
            rows.append([b])
    if not rows:
        return []
    text_col = min(b.left for b in name_boxes)
    badges = [b for b in boxes if BADGE_RE.match(b.text.strip()) and b.left < text_col - 5]
    found: dict[int, Unread] = {}
    for badge in badges:
        above = [i for i, row in enumerate(rows) if row[0].top <= badge.top + 2]
        if not above:
            continue
        i = above[-1]
        name = " ".join(x.text.strip() for x in sorted(rows[i], key=lambda x: x.left))
        found[i] = Unread(name, badge.text.strip())
    return [found[i] for i in sorted(found)]


def unread_sentence(names: list[str], limit: int = 6) -> str:
    """"Có tin nhắn mới từ A, B và C." — không dùng dấu ':' vì phần đọc to cắt bỏ mọi thứ sau ':'."""
    shown = names[:limit]
    rest = len(names) - len(shown)
    if rest > 0:
        people = ", ".join(shown) + f" và {rest} cuộc trò chuyện khác"
    elif len(shown) > 1:
        people = ", ".join(shown[:-1]) + " và " + shown[-1]
    else:
        people = shown[0]
    return f"Có tin nhắn mới từ {people}."


def _main_windows() -> list[int]:
    import psutil
    import win32gui
    import win32process
    found: list[tuple[int, bool]] = []

    def cb(h, _):
        try:
            _, pid = win32process.GetWindowThreadProcessId(h)
            if win32gui.GetWindowText(h) == "Zalo" and psutil.Process(pid).name().lower() == "zalo.exe":
                found.append((h, bool(win32gui.IsWindowVisible(h))))
        except Exception:
            pass
    win32gui.EnumWindows(cb, None)
    found.sort(key=lambda x: not x[1])          # cửa sổ hiện (kể cả thu nhỏ) trước
    return [h for h, _ in found]


def _read_boxes(hwnd: int) -> list[TextBox] | None:
    from pywinauto import Desktop
    win = Desktop(backend="uia").window(handle=hwnd)
    group = None
    for el in win.descendants(control_type="Group"):
        if el.element_info.automation_id == "conversationListId":
            group = el
            break
    if group is None:
        return None
    boxes = []
    for el in group.descendants(control_type="Text"):
        try:
            r = el.rectangle()
            boxes.append(TextBox(el.element_info.name or "", r.left, r.top, r.height()))
        except Exception:
            continue
    return boxes


def check_unread(retries: int = 3, wait_s: float = 1.2) -> ToolResult:
    windows = _main_windows()
    if not windows:
        return ToolResult.failure("Zalo chưa mở trên máy nên em không kiểm tra được tin nhắn.", "not_running")
    boxes = None
    for attempt in range(retries):
        for hwnd in windows:
            try:
                boxes = _read_boxes(hwnd)
            except Exception:
                log.exception("Không đọc được cửa sổ Zalo")
                boxes = None
            if boxes:
                break
        if boxes:
            break
        time.sleep(wait_s)                      # Electron đang dựng cây trợ năng
    if not boxes:
        return ToolResult.failure("Em chưa đọc được danh sách trò chuyện của Zalo. Anh mở cửa sổ Zalo lên một lần "
                                  "rồi hỏi lại em nhé.", "unreadable")
    unread = parse_unread(boxes)
    log.info("Zalo: %d cuộc trò chuyện có tin chưa đọc", len(unread))   # không ghi tên/nội dung vào log
    if not unread:
        return ToolResult.success("Zalo không có tin nhắn mới nào chưa đọc.", verified=True, unread=[])
    msg = unread_sentence([u.name for u in unread])
    return ToolResult.success(msg, verified=True, unread=[{"name": u.name, "count": u.count} for u in unread])
