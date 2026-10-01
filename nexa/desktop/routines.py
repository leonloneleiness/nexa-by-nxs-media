"""Kịch bản làm việc: một câu lệnh ("bắt đầu làm việc") mở nhiều ứng dụng/trang web lên đúng màn hình.

Kịch bản nằm trong cấu hình `routines` (config/settings.yaml, mặc định ở nexa/utils/config.py). Mỗi bước là:
- một ỨNG DỤNG (`app` = tên như khi nói "mở …", `aumid` = mã ứng dụng Store/MSIX, `process` = tên tiến trình để
  nhận cửa sổ), hoặc
- một TRANG WEB (`url`, `title` = chữ có trong tiêu đề tab) — mở trong CỬA SỔ trình duyệt riêng để đặt được chỗ, hoặc
- một HÀNH ĐỘNG (`action: check_zalo`) chạy sau khi các cửa sổ đã vào chỗ.
`monitor` 1/2 theo vai trò màn hình trong Cài đặt > Màn hình. `zone` mặc định "keep": chỉ đưa cửa sổ sang đúng màn
hình, giữ nguyên kích thước/trạng thái phóng to (đã đúng màn hình thì để nguyên); các vùng khác trong ZONES để xếp.

Ứng dụng đã mở sẵn thì dùng lại cửa sổ đang có (không mở bản thứ hai); đang ẩn xuống khay thì gọi lên. Mọi ứng
dụng được mở cùng lúc, cửa sổ nào hiện ra trước được đặt trước. Cuối cùng đưa lần lượt lên trước theo thứ tự bước.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from nexa.desktop import win32api as w
from nexa.desktop.side_by_side import move_visible
from nexa.utils.logging import get_logger
from nexa.utils.text import fold

log = get_logger("desktop.routines")

Rect = tuple[int, int, int, int]
ZONES = ("keep", "full", "left", "right", "top", "bottom", "left_third", "center_third", "right_third",
         "left_two_thirds", "right_two_thirds")
ACTIONS = ("check_zalo",)
MIN_W, MIN_H = 240, 160
WAIT_S = 25.0               # tổng thời gian chờ các cửa sổ hiện ra (ứng dụng khởi động nguội, trang web tải)


@dataclass
class Step:
    label: str
    monitor: int = 1
    zone: str = "keep"
    app: str = ""
    aumid: str = ""
    process: str = ""
    url: str = ""
    title: str = ""
    action: str = ""

    @property
    def is_window(self) -> bool:
        return not self.action


@dataclass
class Routine:
    key: str
    name: str
    phrases: list[str] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)


def load_routines(config: Any) -> dict[str, Routine]:
    out: dict[str, Routine] = {}
    for key, raw in (config.get("routines") or {}).items():
        if not isinstance(raw, dict):
            continue
        steps = []
        for s in raw.get("steps") or []:
            if not isinstance(s, dict):
                continue
            action = str(s.get("action") or "").strip()
            if action and action not in ACTIONS:
                log.warning("Kịch bản %s: bỏ qua hành động lạ %s", key, action)
                continue
            if not action and not (s.get("app") or s.get("url") or s.get("aumid")):
                continue
            zone = str(s.get("zone") or "keep")
            steps.append(Step(label=str(s.get("label") or s.get("app") or s.get("url") or action),
                              monitor=2 if int(s.get("monitor") or 1) == 2 else 1,
                              zone=zone if zone in ZONES else "keep",
                              app=str(s.get("app") or ""), aumid=str(s.get("aumid") or ""),
                              process=str(s.get("process") or "").lower(), url=str(s.get("url") or ""),
                              title=str(s.get("title") or ""), action=action))
        if steps:
            out[str(key)] = Routine(str(key), str(raw.get("name") or key),
                                    [fold(p) for p in raw.get("phrases") or [] if p], steps)
    return out


_SUFFIX = r"(?: (?:thoi|nao|nhe|di|thoi nao|nha|em|di em|nhe em))*"


def match_routine(folded: str, routines: dict[str, Routine]) -> str | None:
    """Khóa kịch bản nếu cả câu (đã bỏ dấu) là một câu gọi của nó, hoặc "chạy/bật kịch bản <tên>"."""
    u = folded.strip()
    for key, r in routines.items():
        for p in r.phrases:
            if re.fullmatch(re.escape(p) + _SUFFIX, u):
                return key
    m = re.fullmatch(r"(?:chay|bat|mo|thuc hien|kich hoat) (?:kich ban|che do|bo) (.+?)" + _SUFFIX, u)
    if m:
        want = m.group(1)
        for key, r in routines.items():
            if want in (fold(r.name), fold(key.replace("_", " "))):
                return key
    return None


def zone_rect(work: Rect, zone: str) -> Rect:
    left, top, right, bottom = work
    wd, ht = right - left, bottom - top
    third = wd // 3
    return {
        "full": work,
        "left": (left, top, left + wd // 2, bottom),
        "right": (left + wd // 2, top, right, bottom),
        "top": (left, top, right, top + ht // 2),
        "bottom": (left, top + ht // 2, right, bottom),
        "left_third": (left, top, left + third, bottom),
        "center_third": (left + third, top, right - third, bottom),
        "right_third": (right - third, top, right, bottom),
        "left_two_thirds": (left, top, right - third, bottom),
        "right_two_thirds": (left + third, top, right, bottom),
    }.get(zone, work)


class RoutineRunner:
    """Chạy phần CỬA SỔ của một kịch bản. Khởi chạy ứng dụng qua `launch(step)` (trả thông báo lỗi hoặc None)."""

    def __init__(self, api: Any, monitors: Any, launch: Callable[[Step], str | None], browser_process: str,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                 wait_s: float = WAIT_S) -> None:
        self.api = api
        self.monitors = monitors
        self.launch = launch
        self.browser_process = (browser_process or "").lower()
        self.sleep = sleep
        self.clock = clock
        self.wait_s = wait_s

    # ----- nhận cửa sổ -----
    def _process(self, h: int) -> str:
        name, _, _ = self.api.process_identity(self.api.get_pid(h))
        return (name or "").lower()

    def _usable(self, h: int, need_visible: bool = True) -> bool:
        api = self.api
        try:
            if not api.is_window(h) or api.get_pid(h) == api.own_pid() or not api.get_title(h).strip():
                return False
            if api.get_ex_style(h) & w.WS_EX_TOOLWINDOW or api.get_root_owner(h) not in (h, 0):
                return False
            if api.is_iconic(h):
                return True
            if need_visible and (not api.is_visible(h) or api.is_cloaked(h)):
                return False
            r = api.get_rect(h)
            return r[2] - r[0] >= MIN_W and r[3] - r[1] >= MIN_H
        except OSError:
            return False

    def _title_ok(self, step: Step, h: int) -> bool:
        return not step.title or fold(step.title) in fold(self.api.get_title(h))

    def find(self, step: Step, taken: set[int], among: list[int] | None = None) -> int:
        """Cửa sổ đang mở (hiện hoặc thu nhỏ) khớp bước; theo thứ tự Z (trên cùng trước)."""
        for h in among if among is not None else self.api.enum_windows():
            if h in taken or not self._usable(h):
                continue
            proc = self._process(h)
            if step.url:
                if proc == self.browser_process and step.title and self._title_ok(step, h):
                    return h
            elif proc == step.process and self._title_ok(step, h):
                return h
        return 0

    # ----- đặt chỗ -----
    def _wait(self, cond: Callable[[], bool], limit: float) -> None:
        end = self.clock() + limit
        while not cond() and self.clock() < end:
            self.sleep(0.05)

    def place(self, h: int, mon: Any, zone: str) -> bool:
        if zone == "keep":
            return self.move_to_monitor(h, mon)
        api = self.api
        if api.is_iconic(h) or api.is_zoomed(h):
            api.show_async(h, w.SW_RESTORE)
            self._wait(lambda: not api.is_iconic(h) and not api.is_zoomed(h), 1.0)
        rect = zone_rect(mon.work, zone)
        if not move_visible(api, h, rect):
            return False
        # Sang màn hình khác DPI: Windows/ứng dụng tự co giãn theo WM_DPICHANGED → đặt lại lần hai cho đúng khung.
        self.sleep(0.15)
        if api.get_rect(h) != rect:
            move_visible(api, h, rect)
        if zone == "full":
            api.show_async(h, w.SW_SHOWMAXIMIZED)
            self._wait(lambda: api.is_zoomed(h), 1.0)
        self.sleep(0.05)
        on = self.monitors.monitor_of_window(h, self.monitors.refresh())
        return on is not None and on.hmonitor == mon.hmonitor

    def move_to_monitor(self, h: int, mon: Any) -> bool:
        """Chỉ đưa cửa sổ sang đúng màn hình: giữ kích thước, giữ trạng thái phóng to; đã đúng màn hình thì để nguyên."""
        api = self.api
        if api.is_iconic(h):
            api.show_async(h, w.SW_RESTORE)
            self._wait(lambda: not api.is_iconic(h), 1.0)
        monitors = self.monitors.refresh()
        on = self.monitors.monitor_of_window(h, monitors)
        if on is not None and on.hmonitor == mon.hmonitor:
            return True
        zoomed = api.is_zoomed(h)
        if zoomed:
            api.show_async(h, w.SW_RESTORE)
            self._wait(lambda: not api.is_zoomed(h), 1.0)
        vis = api.get_rect(h)
        src = (self.monitors.monitor_of_window(h, monitors) or on or mon).work
        tw, th = mon.work[2] - mon.work[0], mon.work[3] - mon.work[1]
        cw, ch = min(vis[2] - vis[0], tw), min(vis[3] - vis[1], th)
        # Giữ vị trí tương đối so với góc trên-trái vùng làm việc, kẹp để nằm gọn trong màn hình đích.
        x = mon.work[0] + min(max(0, vis[0] - src[0]), tw - cw)
        y = mon.work[1] + min(max(0, vis[1] - src[1]), th - ch)
        rect = (x, y, x + cw, y + ch)
        if not move_visible(api, h, rect):
            return False
        self.sleep(0.15)
        if api.get_rect(h) != rect:
            move_visible(api, h, rect)
        if zoomed:
            api.show_async(h, w.SW_SHOWMAXIMIZED)
            self._wait(lambda: api.is_zoomed(h), 1.0)
        self.sleep(0.05)
        on = self.monitors.monitor_of_window(h, self.monitors.refresh())
        return on is not None and on.hmonitor == mon.hmonitor

    # ----- chạy -----
    def run(self, routine: Routine, focus: Callable[[int], Any], cancelled: Callable[[], bool] = lambda: False
            ) -> dict[str, Any]:
        """Trả {"placed": [label], "failed": [(label, lý do)], "note": str, "cancelled": bool}."""
        roles = self.monitors.roles()
        mons = {1: roles.source, 2: roles.target}
        note = ""
        if mons[1] is None or mons[2] is None:
            only = self.monitors.primary(roles.monitors)
            mons = {1: only, 2: only}
            note = "Em chỉ thấy một màn hình nên mở tất cả trên màn hình này."
        out: dict[str, Any] = {"placed": [], "failed": [], "note": note, "cancelled": False}
        steps = [s for s in routine.steps if s.is_window]
        if mons[1] is None:
            out["failed"] = [(s.label, "không thấy màn hình nào") for s in steps]
            return out

        before = set(self.api.enum_windows())
        taken: set[int] = set()
        found: dict[int, int] = {}              # chỉ số bước -> hwnd
        for i, s in enumerate(steps):
            h = self.find(s, taken)
            if h:
                found[i] = h
                taken.add(h)
        for i, s in enumerate(steps):
            if i in found:
                continue
            err = self.launch(s)
            if err:
                out["failed"].append((s.label, err))
        failed_labels = {lb for lb, _ in out["failed"]}
        waiting = {i for i in range(len(steps)) if i not in found and steps[i].label not in failed_labels}

        placed: dict[int, int] = {}

        def place_ready() -> None:
            for i in sorted(found):
                if i in placed:
                    continue
                s = steps[i]
                if self.place(found[i], mons[s.monitor], s.zone):
                    placed[i] = found[i]
                    out["placed"].append(s.label)
                else:
                    placed[i] = 0
                    out["failed"].append((s.label, "Windows không cho di chuyển cửa sổ"))

        place_ready()
        deadline = self.clock() + self.wait_s
        while waiting and not cancelled():
            fresh = [h for h in self.api.enum_windows() if h not in before]
            for i in sorted(waiting):
                s = steps[i]
                # Trang web: chỉ nhận cửa sổ trình duyệt MỚI (không kéo cửa sổ anh đang dùng); ứng dụng: mọi cửa sổ
                # của tiến trình (ứng dụng một-phiên như Zalo/Claude chỉ hiện lại cửa sổ cũ).
                h = self.find(s, taken, fresh if s.url else None)
                if h:
                    found[i] = h
                    taken.add(h)
                    waiting.discard(i)
            place_ready()
            if not waiting or self.clock() >= deadline:
                break
            self.sleep(0.25)
        if cancelled():
            out["cancelled"] = True
            return out
        # Trang web chưa kịp đổi tiêu đề (đang tải): nhận khi chỉ còn đúng một cửa sổ trình duyệt mới chưa ai nhận.
        web_left = [i for i in waiting if steps[i].url]
        spare = [h for h in self.api.enum_windows() if h not in before and h not in taken and self._usable(h)
                 and self._process(h) == self.browser_process]
        if len(web_left) == 1 and len(spare) == 1:
            found[web_left[0]] = spare[0]
            taken.add(spare[0])
            waiting.discard(web_left[0])
            place_ready()
        for i in sorted(waiting):
            out["failed"].append((steps[i].label, "chưa thấy cửa sổ hiện ra"))
        # Đưa lên trước theo thứ tự bước: bước sau nằm trên.
        for i in sorted(placed):
            if placed[i] and not cancelled():
                try:
                    focus(placed[i])
                except Exception:
                    log.debug("Không đưa được cửa sổ lên trước", exc_info=True)
        order = {s.label: i for i, s in enumerate(steps)}
        out["placed"].sort(key=lambda lb: order.get(lb, 0))
        return out


def summarize(routine: Routine, result: dict[str, Any], extra: list[str]) -> tuple[str, str]:
    """(câu hiện trên màn hình, câu đọc ngắn)."""
    total = sum(1 for s in routine.steps if s.is_window)
    ok = len(result["placed"])
    head = f"Xong kịch bản «{routine.name}»: {ok}/{total} ứng dụng đã mở đúng màn hình."
    if result.get("cancelled"):
        head = f"Đã dừng kịch bản «{routine.name}» giữa chừng ({ok}/{total} ứng dụng đã mở)."
    parts = [head]
    if result.get("note"):
        parts.append(result["note"])
    if result["failed"]:
        parts.append("Chưa được: " + "; ".join(f"{lb} ({why})" for lb, why in result["failed"]) + ".")
    parts.extend(extra)
    spoken = [f"Đã mở xong {ok} trên {total} ứng dụng." if ok == total else
              f"Mở được {ok} trên {total} ứng dụng, còn " + ", ".join(lb for lb, _ in result["failed"]) + " chưa được."]
    spoken.extend(extra)
    return " ".join(parts), " ".join(spoken)


# ------------------------------------------------------------------ công cụ run_routine
def find_routine(name: str, routines: dict[str, Routine]) -> Routine | None:
    want = fold(name).replace("_", " ")
    for key, r in routines.items():
        if want in (fold(key.replace("_", " ")), fold(r.name)):
            return r
    key = match_routine(want, routines)
    return routines.get(key) if key else None


def _browser_args(browser: str, url: str) -> list[str]:
    return [browser, "-new-window" if "firefox" in browser.lower() else "--new-window", url]


def make_launcher(apps: Any) -> Callable[[Step], str | None]:
    import os
    import subprocess

    def launch(step: Step) -> str | None:
        try:
            if step.url:
                browser = apps.browser_exe()
                if browser:
                    subprocess.Popen(_browser_args(browser, step.url), shell=False, close_fds=True)
                else:
                    os.startfile(step.url)  # noqa: S606
                return None
            if step.aumid:
                # Ứng dụng Store/MSIX (Claude Desktop…) không có lối tắt .lnk: mở qua shell:AppsFolder.
                subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + step.aumid], shell=False, close_fds=True)
                return None
        except OSError as exc:
            return f"không mở được: {exc.strerror or exc}"
        app, candidates = apps.resolve(step.app)
        if app is None:
            return "nhiều ứng dụng trùng tên" if candidates else "chưa tìm thấy ứng dụng trên máy"
        if not step.process and app.process_names:
            step.process = sorted(app.process_names)[0].lower()
        err = apps.start(app)
        return err.message if err is not None else None

    return launch


def _first_sentence(text: str) -> str:
    t = re.split(r"(?<=[.!?])\s+", (text or "").strip())[0]
    return t


def h_run_routine(args: dict, ctx: Any) -> Any:
    from pathlib import Path

    from nexa.core.events import ToolResult
    sv = ctx.services
    routines = load_routines(sv.config)
    routine = find_routine(args.get("name") or "", routines)
    if routine is None:
        names = ", ".join(r.name for r in routines.values()) or "chưa có"
        return ToolResult.failure(f"Em chưa có kịch bản '{args.get('name')}'. Các kịch bản hiện có: {names}.",
                                  "not_found")
    browser = sv.apps.browser_exe() or ""
    runner = RoutineRunner(sv.wm.api, sv.monitors, make_launcher(sv.apps),
                           Path(browser).name.lower() if browser else "msedge.exe")
    cancelled = lambda: bool(ctx.token.cancelled)  # noqa: E731
    result = runner.run(routine, sv.wm.focus, cancelled)
    extra: list[str] = []
    spoken_extra: list[str] = []
    for s in routine.steps:
        if cancelled():
            break
        if s.action == "check_zalo":
            from nexa.desktop.zalo import check_unread
            z = check_unread()
            extra.append(z.message)
            spoken_extra.append(_first_sentence(z.message))
    shown = summarize(routine, result, extra)[0]
    spoken = summarize(routine, result, spoken_extra)[1]
    data = {"spoken": spoken, "placed": result["placed"], "failed": [lb for lb, _ in result["failed"]]}
    if result["cancelled"]:
        return ToolResult.failure(shown, "cancelled", **data)
    if not result["placed"]:
        return ToolResult.failure(shown, "routine_failed", **data)
    return ToolResult.success(shown, verified=not result["failed"], **data)


def register_routine_tools(reg: Any, config: Any) -> None:
    from nexa.ai.tool_registry import S_STR, ToolSpec, obj
    reg.register(ToolSpec(
        "run_routine", "Kịch bản làm việc",
        "Chạy một kịch bản làm việc đã cấu hình: mở nhiều ứng dụng/trang web cùng lúc, đưa từng cửa sổ lên đúng màn "
        "hình, rồi làm các việc kèm theo (ví dụ kiểm tra tin nhắn Zalo). Dùng khi anh nói 'bắt đầu làm "
        "việc', 'vào việc' hoặc gọi tên một kịch bản. Kịch bản có sẵn: "
        + (", ".join(f"{r.name} ({k})" for k, r in load_routines(config).items()) or "chưa có") + ".",
        obj({"name": S_STR("Tên hoặc khóa kịch bản", 80, minLength=1)}, ["name"]),
        h_run_routine))
