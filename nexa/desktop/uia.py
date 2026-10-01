"""Windows UI Automation qua pywinauto (backend "uia").

Ưu tiên xác định control bằng tên/kiểu/AutomationId và gọi Invoke/Toggle/Select pattern thay vì
nhấp theo tọa độ. Chỉ khi control không hỗ trợ pattern nào mới nhấp vào tâm hình chữ nhật hiện
tại của control, sau khi kiểm tra control hiển thị, bật và nằm trong cửa sổ đích.
"""
from __future__ import annotations

import re
from typing import Any

from nexa.core.events import ToolResult
from nexa.utils.logging import get_logger
from nexa.utils.text import fold, truncate

log = get_logger("uia")

INTERACTIVE_TYPES = {"Button", "MenuItem", "Hyperlink", "CheckBox", "RadioButton", "TabItem", "ListItem",
                     "TreeItem", "ComboBox", "Edit", "SplitButton", "Document"}


def _window(hwnd: int):
    from pywinauto import Desktop
    return Desktop(backend="uia").window(handle=hwnd)


def _reading_order(el) -> tuple[int, int]:
    r = el.rectangle()
    return (r.top // 12, r.left)   # gom theo dòng (~12 px) rồi trái → phải


def _ctype_id(name: str) -> int | None:
    _, UIA = uia_core()
    return getattr(UIA, f"UIA_{name}ControlTypeId", None)


def _cached_descendants(hwnd: int, props: list[int], control_types: list[str] | None = None):
    """MỘT lần gọi UIA lấy mọi phần tử (lọc theo kiểu) kèm thuộc tính đã cache — thay cho duyệt từng phần tử."""
    iuia, UIA = uia_core()
    cr = iuia.CreateCacheRequest()
    for pid in props:
        cr.AddProperty(pid)
    cond = iuia.CreateTrueCondition()
    ids = [i for i in (_ctype_id(t) for t in control_types or []) if i is not None]
    if ids:
        cond = iuia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, ids[0])
        for i in ids[1:]:
            cond = iuia.CreateOrCondition(cond, iuia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, i))
    arr = iuia.ElementFromHandle(hwnd).FindAllBuildCache(UIA.TreeScope_Descendants, cond, cr)
    return [arr.GetElement(k) for k in range(arr.Length)]


def list_controls(hwnd: int, limit: int = 60, control_type: str | None = None,
                  contains: str | None = None) -> ToolResult:
    q = fold(contains or "")
    try:
        _, UIA = uia_core()
        types_ = [control_type] if control_type else sorted(INTERACTIVE_TYPES)
        names = {_ctype_id(t): t for t in types_}
        wr = _window(hwnd).rectangle()
        found = []
        for e in _cached_descendants(hwnd, [UIA.UIA_NamePropertyId, UIA.UIA_ControlTypePropertyId,
                                            UIA.UIA_AutomationIdPropertyId, UIA.UIA_BoundingRectanglePropertyId,
                                            UIA.UIA_IsOffscreenPropertyId, UIA.UIA_IsEnabledPropertyId], types_):
            try:
                name = (e.CachedName or "").strip()
                if not name or (q and q not in fold(name)):
                    continue
                r = e.CachedBoundingRectangle
                offscreen = r.right < wr.left or r.left > wr.right or r.bottom < wr.top or r.top > wr.bottom
                if r.right - r.left <= 1 or r.bottom - r.top <= 1 or offscreen or e.CachedIsOffscreen:
                    continue   # ngoài vùng hiển thị (ví dụ phần trang chưa cuộn tới)
                found.append({"name": truncate(name, 80), "type": names.get(e.CachedControlType, ""),
                              "automation_id": e.CachedAutomationId or "", "enabled": bool(e.CachedIsEnabled),
                              "rect": [r.left, r.top, r.right, r.bottom]})
                if len(found) >= limit * 3:
                    break
            except Exception:
                continue
        found.sort(key=lambda it: (it["rect"][1] // 12, it["rect"][0]))   # gom theo dòng (~12 px) rồi trái → phải
        items = found[:limit]
    except Exception as exc:
        return ToolResult.failure(f"Không đọc được cấu trúc giao diện: {exc}", "uia_error")
    return ToolResult.success(f"Có {len(items)} control tương tác đang hiển thị.", verified=True, controls=items)


def find_control(hwnd: int, name: str, control_type: str | None = None, automation_id: str | None = None):
    _, UIA = uia_core()
    q = fold(name)
    exact, partial = [], []
    for e in _cached_descendants(hwnd, [UIA.UIA_NamePropertyId, UIA.UIA_AutomationIdPropertyId],
                                 [control_type] if control_type else None):
        try:
            if automation_id and e.CachedAutomationId != automation_id:
                continue
            nm = fold(e.CachedName or "")
            if not nm:
                continue
            if nm == q:
                exact.append(e)
            elif q and q in nm:
                partial.append(e)
        except Exception:
            continue
    return [wrap(e) for e in (exact or partial)]


def invoke_control(hwnd: int, name: str, control_type: str | None = None,
                   automation_id: str | None = None, window_rect: tuple[int, int, int, int] | None = None,
                   index: int | None = None) -> ToolResult:
    try:
        matches = find_control(hwnd, name, control_type, automation_id)
    except Exception as exc:
        return ToolResult.failure(f"Không truy cập được UI Automation: {exc}", "uia_error")
    if not matches:
        return ToolResult.failure(f"Không tìm thấy control '{name}' trong cửa sổ.", "not_found")
    visible = [m for m in matches if _safe(m.is_visible)]
    if index and len(visible) >= index:
        visible.sort(key=_reading_order)
        visible = [visible[index - 1]]
    if len(visible) != 1:
        names = [f"{m.element_info.name} ({m.element_info.control_type})" for m in visible[:5]]
        if not visible:
            return ToolResult.failure(f"Control '{name}' đang bị ẩn.", "hidden")
        return ToolResult.failure("Có nhiều control khớp, anh chỉ rõ giúp em: " + "; ".join(names), "ambiguous",
                                  candidates=names)
    el = visible[0]
    if not _safe(el.is_enabled):
        return ToolResult.failure(f"Control '{name}' đang bị vô hiệu hóa.", "disabled")
    label = f"{el.element_info.name} ({el.element_info.control_type})"
    for method in ("invoke", "toggle", "select"):
        fn = getattr(el, method, None)
        if fn is None:
            continue
        try:
            fn()
            return ToolResult.success(f"Đã kích hoạt {label}.", verified=False, control=label, method=method)
        except Exception:
            continue
    # Dự phòng: nhấp vào tâm control hiện tại nếu nằm trọn trong cửa sổ đích.
    try:
        r = el.rectangle()
        rect = (r.left, r.top, r.right, r.bottom)
        if window_rect and not (rect[0] >= window_rect[0] - 2 and rect[1] >= window_rect[1] - 2
                                and rect[2] <= window_rect[2] + 2 and rect[3] <= window_rect[3] + 2):
            return ToolResult.failure("Control nằm ngoài cửa sổ đích, em không nhấp đoán.", "outside_window")
        el.click_input()
        return ToolResult.success(f"Đã nhấp {label}.", verified=False, control=label, method="click",
                                  x=(rect[0] + rect[2]) // 2, y=(rect[1] + rect[3]) // 2)
    except Exception as exc:
        return ToolResult.failure(f"Không thao tác được {label}: {exc}", "uia_error")


def control_label_for_risk(hwnd: int, name: str, control_type: str | None) -> str:
    try:
        matches = find_control(hwnd, name, control_type)
        if matches:
            return fold(matches[0].element_info.name or name)
    except Exception:
        pass
    return fold(name)


def _safe(fn: Any) -> bool:
    try:
        return bool(fn())
    except Exception:
        return False


# ------------------------------------------------------------------ tab trình duyệt
BROWSER_PROCESSES = {"msedge.exe", "chrome.exe", "firefox.exe", "browser.exe", "brave.exe", "opera.exe",
                     "vivaldi.exe"}
_TAB_SUFFIX = re.compile(r"\s+-\s+(mức sử dụng bộ nhớ|memory usage)\b.*$", re.IGNORECASE)
_CLOSE_WORDS = ("dong", "close")


def tab_title(el) -> str:
    """Tên tab bỏ phần Edge tự thêm (" - Mức sử dụng bộ nhớ - 281 MB")."""
    return _TAB_SUFFIX.sub("", (el.element_info.name or "").strip())


# ----- truy vấn UIA trực tiếp (nhanh) -----
# pywinauto `descendants()` quét CẢ trang web (YouTube: hàng nghìn phần tử) rồi bọc từng phần tử bằng Python và
# hỏi thuộc tính qua nhiều lần gọi COM → vài giây mỗi lần. Ở đây: chỉ đi qua khung trình duyệt (không vào trang
# web) để tìm thanh tab / trang web, nhớ lại theo cửa sổ, và lấy thuộc tính theo lô (CacheRequest).
_STRIP_CACHE: dict[int, Any] = {}
_BFS_LIMIT = 600


def uia_core():
    from pywinauto.uia_defines import IUIA
    i = IUIA()
    return i.iuia, i.UIA_dll


def wrap(elem):
    """Bọc IUIAutomationElement thành wrapper pywinauto (select/invoke/children… như trước)."""
    from pywinauto.controls.uiawrapper import UIAWrapper
    from pywinauto.uia_element_info import UIAElementInfo
    return UIAWrapper(UIAElementInfo(elem))


def chrome_find(hwnd: int, control_type_id: int):
    """Phần tử ĐẦU TIÊN có kiểu `control_type_id` trong khung trình duyệt, KHÔNG đi vào bên trong trang web
    (Document). Tìm Document thì trả về chính trang đang xem."""
    iuia, UIA = uia_core()
    cr = iuia.CreateCacheRequest()
    cr.AddProperty(UIA.UIA_ControlTypePropertyId)
    true = iuia.CreateTrueCondition()
    queue = [iuia.ElementFromHandle(hwnd)]
    seen = 0
    while queue and seen < _BFS_LIMIT:
        node = queue.pop(0)
        try:
            kids = node.FindAllBuildCache(UIA.TreeScope_Children, true, cr)
        except Exception:
            continue
        for k in range(kids.Length):
            el = kids.GetElement(k)
            seen += 1
            ctype = el.CachedControlType
            if ctype == control_type_id:
                return el
            if ctype != UIA.UIA_DocumentControlTypeId:
                queue.append(el)
    return None


def _alive(elem) -> bool:
    try:
        elem.CurrentControlType
        r = elem.CurrentBoundingRectangle
        return (r.right - r.left) > 0
    except Exception:
        return False


def _tab_strip(hwnd: int):
    _, UIA = uia_core()
    el = _STRIP_CACHE.get(hwnd)
    if el is not None and _alive(el):
        return el
    el = chrome_find(hwnd, UIA.UIA_TabControlTypeId)
    if el is not None:
        _STRIP_CACHE[hwnd] = el
        if len(_STRIP_CACHE) > 32:
            _STRIP_CACHE.pop(next(iter(_STRIP_CACHE)))
    return el


def tab_count(hwnd: int) -> int:
    try:
        iuia, UIA = uia_core()
        strip = _tab_strip(hwnd)
        if strip is None:
            return len(browser_tabs(hwnd))
        cond = iuia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, UIA.UIA_TabItemControlTypeId)
        return strip.FindAll(UIA.TreeScope_Descendants, cond).Length
    except Exception:
        return len(browser_tabs(hwnd))


def browser_tabs(hwnd: int) -> list:
    try:
        iuia, UIA = uia_core()
        strip = _tab_strip(hwnd)
        if strip is not None:
            cond = iuia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, UIA.UIA_TabItemControlTypeId)
            arr = strip.FindAll(UIA.TreeScope_Descendants, cond)
            return [wrap(arr.GetElement(k)) for k in range(arr.Length)]
    except Exception:
        log.debug("Đọc tab nhanh lỗi, dùng cách cũ", exc_info=True)
        _STRIP_CACHE.pop(hwnd, None)
    try:
        return list(_window(hwnd).descendants(control_type="TabItem"))
    except Exception:
        log.exception("Không đọc được tab của cửa sổ %s", hwnd)
        return []


def page_document(hwnd: int):
    """Trang web đang xem của cửa sổ trình duyệt (IUIAutomationElement) hoặc None."""
    try:
        _, UIA = uia_core()
        return chrome_find(hwnd, UIA.UIA_DocumentControlTypeId)
    except Exception:
        log.debug("Không tìm được trang web", exc_info=True)
        return None


def _close_button(tab):
    for child in tab.children():
        info = child.element_info
        if info.control_type == "Button" and any(w in fold(info.name or "") for w in _CLOSE_WORDS):
            return child
    return None


def close_tab(hwnd: int, tab, hotkey=None, sleep=None) -> bool:
    """Đóng MỘT tab: chọn tab (UIA, không dùng chuột) rồi bấm nút "Đóng tab" của nó; không có nút thì Ctrl+W.

    Trả về True nếu tab đã biến mất khỏi thanh tab.
    """
    import time as _time
    sleep = sleep or _time.sleep
    title = tab_title(tab)
    before = tab_count(hwnd)
    try:
        tab.select()
    except Exception:
        try:
            tab.invoke()
        except Exception:
            pass
    sleep(0.15)
    current = next((t for t in browser_tabs(hwnd) if tab_title(t) == title), None)
    btn = _close_button(current) if current is not None else None
    try:
        if btn is not None:
            btn.invoke()
        elif hotkey is not None:
            hotkey(["ctrl", "w"], hwnd)
        else:
            return False
    except Exception:
        log.exception("Không bấm được nút đóng tab")
        if hotkey is None:
            return False
        hotkey(["ctrl", "w"], hwnd)
    for _ in range(20):
        sleep(0.05)
        if tab_count(hwnd) < before:
            return True
    return False


# ------------------------------------------------------------------ trang web trong trình duyệt
def address_bar(hwnd: int) -> str:
    """Địa chỉ trên thanh địa chỉ của cửa sổ trình duyệt (Edge/Chrome), "" nếu không đọc được."""
    try:
        _, UIA = uia_core()
        el = chrome_find(hwnd, UIA.UIA_EditControlTypeId)   # ô Edit đầu tiên của khung trình duyệt = omnibox
        if el is not None and el.CurrentClassName == "OmniboxViewViews":
            return el.GetCurrentPropertyValue(UIA.UIA_ValueValuePropertyId) or ""
    except Exception:
        pass
    try:
        for el in _window(hwnd).descendants(control_type="Edit"):
            if el.element_info.class_name == "OmniboxViewViews":
                return el.iface_value.CurrentValue or ""
    except Exception:
        pass
    return ""


def page_title(hwnd: int) -> str:
    """Tiêu đề trang đang xem (tên của Document chính)."""
    try:
        doc = page_document(hwnd)
        return (doc.CurrentName or "").strip() if doc is not None else ""
    except Exception:
        return ""


def focused_page_editor(hwnd: int, page_contains: str):
    """Ô soạn thảo ĐANG CÓ CON TRỎ, nếu nó nằm trong trang web của cửa sổ `hwnd` có tiêu đề chứa `page_contains`.

    Trả về (element_info, nội dung hiện có) hoặc None. Không bao giờ trả về thanh địa chỉ hay control ngoài trang —
    để NEXA chỉ gõ khi chắc chắn con trỏ đang ở ô chat của đúng trang đó.
    """
    try:
        import win32process
        from pywinauto.uia_defines import IUIA
        from pywinauto.uia_element_info import UIAElementInfo
        info = UIAElementInfo(IUIA().iuia.GetFocusedElement())
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if info.process_id != pid or info.class_name == "OmniboxViewViews":
            return None
        if info.control_type not in ("Edit", "Group", "Custom", "Text", "Pane", "Document"):
            return None
        node, in_page = info, False
        for _ in range(40):
            node = node.parent
            if node is None:
                break
            if node.control_type == "Document":
                in_page = fold(page_contains) in fold(node.name or "")
                break
        if not in_page:
            return None
        value = ""
        try:
            value = info.element.GetCurrentPropertyValue(30045) or ""    # UIA_ValueValuePropertyId
        except Exception:
            pass
        return info, str(value)
    except Exception:
        log.exception("Không đọc được ô đang có con trỏ")
        return None
