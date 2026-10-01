"""Chuột bằng tay: di chuyển con trỏ, click, kéo thả, click phải và cuộn bằng webcam.

Chỉ chạy khi anh BẬT chế độ chuột ("bật chuột bằng tay", nút trong bảng Cử chỉ). Khi đang ở chế độ chuột, sáu cử chỉ
lệnh bị tạm ngưng để không lẫn (ví dụ chỉ ngón trỏ sang phải sẽ không chuyển cửa sổ).

  Di chuyển tay (xòe hoặc chỉ ngón trỏ)       → con trỏ đi theo (kiểu touchpad: tương đối, có gia tốc)
  Chụm ngón cái + ngón trỏ rồi nhả nhanh     → click trái (chụm hai lần nhanh = click đúp)
  Chụm ngón cái + ngón trỏ, giữ và di chuyển → kéo thả
  Chụm ngón cái + ngón giữa                  → click phải
  ✌ Hai ngón (trỏ + giữa) rồi đưa lên/xuống  → cuộn
  ✊ Nắm tay                                   → "nhấc tay khỏi touchpad": con trỏ đứng yên để anh đặt lại tay

Chống lỗi:
- Con trỏ bám theo TÂM LÒNG BÀN TAY, không bám đầu ngón trỏ: lúc chụm tay, đầu ngón di chuyển nhưng lòng bàn tay
  gần như đứng yên, nên con trỏ không bị giật đúng lúc click.
- Nhận ra cú chụm luôn trễ vài khung hình. Vì vậy khi bắt đầu chụm, con trỏ được đưa về vị trí ~rewind_ms trước đó
  rồi mới nhấn. Sau đó con trỏ bị "khóa" cho tới khi tay đi quá drag_start (tính theo kích thước bàn tay) —
  click không bị trượt, còn kéo thả vẫn chạy.
- Chụm = khoảng cách đầu ngón cái tới đầu ngón trỏ/giữa (chia cho kích thước tay), có trễ bật/tắt (hysteresis).
  Đầu ngón đó phải cách xa tâm lòng bàn tay, nên nắm tay không bị hiểu nhầm là chụm.
- Anh cầm chuột thật di chuyển → chuột bằng tay nhường yield_ms, không giành con trỏ.
- Không bao giờ tự đưa con trỏ vào góc màn hình chính (điểm fail-safe của PyAutoGUI). Nếu CHÍNH anh đưa chuột thật
  vào góc, lỗi fail-safe được báo lên để NEXA dừng khẩn cấp như mọi thao tác khác.
- Mất tay, tắt chế độ, dừng khẩn cấp → nhả mọi nút đang giữ.
"""
from __future__ import annotations

import threading
from collections import Counter, deque
from dataclasses import dataclass
from typing import Any, Callable, Protocol, Sequence

import numpy as np

from nexa.vision.gesture_features import PALM_POINTS, Pose, _pts, classify, hand_scale
from nexa.vision.gesture_state_machine import OneEuro

Rect = tuple[int, int, int, int]


class MouseOutput(Protocol):
    def position(self) -> tuple[int, int]: ...
    def move_to(self, x: int, y: int) -> None: ...
    def button(self, button: str, down: bool) -> None: ...
    def scroll(self, notches: int) -> None: ...


@dataclass
class MouseParams:
    mapping: str = "relative"         # relative (kiểu touchpad) | absolute (vùng giữa khung hình = toàn màn hình)
    gain: float = 900.0               # pixel cho mỗi "kích thước bàn tay" khi tay đi ở tốc độ tham chiếu
    accel: float = 0.7                # 0 = không gia tốc; lớn hơn = tay chậm chính xác hơn, tay nhanh đi xa hơn
    ref_speed: float = 1.5            # tốc độ tham chiếu (kích thước tay / giây)
    min_factor: float = 0.25
    max_factor: float = 3.0
    deadband: float = 0.004           # bỏ rung nhỏ hơn mức này (kích thước tay / khung)
    min_cutoff: float = 1.0           # One Euro: nhỏ hơn = mượt hơn khi tay chậm
    beta: float = 0.4                 # One Euro: lớn hơn = ít trễ hơn khi tay nhanh
    absolute_margin: float = 0.18     # absolute: bỏ viền khung hình (tỷ lệ) — tay không cần với ra mép
    pinch_on: float = 0.32            # chụm khi khoảng cách đầu ngón / kích thước tay < pinch_on
    pinch_off: float = 0.48           # nhả khi > pinch_off
    pinch_frames: int = 2             # số khung liên tiếp để nhận chụm
    pinch_margin: float = 0.06        # chụm cả trỏ lẫn giữa: ngón gần hơn phải gần hơn hẳn chừng này, không thì bỏ qua
    tip_reach: float = 0.7            # đầu ngón chụm phải cách tâm lòng bàn tay ít nhất chừng này (không phải nắm tay)
    drag_start: float = 0.35          # kích thước tay: đi quá mức này khi đang chụm → kéo thả
    rewind_ms: int = 90
    rewind_max_px: int = 40           # chỉ tua lại độ trôi nhỏ do động tác chụm, không kéo lùi khi tay đang đi nhanh
    scroll_step: float = 0.18         # kích thước tay mỗi nấc cuộn
    invert_scroll: bool = False
    pose_frames: int = 3              # bỏ phiếu tư thế (nắm tay / hai ngón / di chuyển)
    lost_hand_ms: int = 300
    yield_px: int = 24                # chuột thật lệch quá mức này so với vị trí NEXA đặt → nhường
    yield_ms: int = 1000
    corner_margin: int = 3            # tránh các góc fail-safe của màn hình chính
    invert_x: bool = False

    @classmethod
    def from_config(cls, g: dict[str, Any]) -> "MouseParams":
        m = dict(g.get("mouse") or {})
        d = cls()
        kwargs = {k: type(getattr(d, k))(m[k]) for k in d.__dataclass_fields__ if k in m and k != "invert_x"}
        return cls(**kwargs, invert_x=bool((g.get("calibration") or {}).get("invert_x", False)))


@dataclass
class MouseFrame:
    """Đặc trưng một khung hình cho chuột bằng tay."""
    anchor: tuple[float, float]       # tâm lòng bàn tay (x đã nhân tỷ lệ khung, đơn vị = chiều cao khung)
    raw: tuple[float, float]          # tâm lòng bàn tay chuẩn hóa [0,1] (cho absolute)
    scale: float
    pose: Pose
    pinch_index: float                # khoảng cách đầu ngón cái – trỏ / kích thước tay
    pinch_middle: float
    reach_index: float                # khoảng cách đầu ngón trỏ – tâm lòng bàn tay / kích thước tay
    reach_middle: float


def mouse_frame(landmarks, aspect: float = 4 / 3, pose: Pose | None = None) -> MouseFrame:
    """pose: tư thế đã phân loại ở engine (khỏi phân loại lại mỗi khung)."""
    p = _pts(landmarks, aspect)
    scale = hand_scale(p)
    center = p[list(PALM_POINTS)].mean(axis=0)
    raw = np.asarray(landmarks, dtype=np.float64)[list(PALM_POINTS), :2].mean(axis=0)
    if pose is None:
        pose = classify(landmarks, aspect=aspect).pose
    return MouseFrame(anchor=(float(center[0]), float(center[1])), raw=(float(raw[0]), float(raw[1])), scale=scale,
                      pose=pose,
                      pinch_index=float(np.linalg.norm(p[4] - p[8]) / scale),
                      pinch_middle=float(np.linalg.norm(p[4] - p[12]) / scale),
                      reach_index=float(np.linalg.norm(p[8] - center) / scale),
                      reach_middle=float(np.linalg.norm(p[12] - center) / scale))


def clamp_to_monitors(x: float, y: float, monitors: Sequence[Rect], primary: Rect | None = None,
                      corner_margin: int = 3) -> tuple[int, int]:
    """Đưa điểm về trong màn hình gần nhất (hai màn hình khác chiều cao có vùng chết) và né góc fail-safe."""
    if not monitors:
        return int(round(x)), int(round(y))
    best, best_d = None, None
    for r in monitors:
        cx = min(max(x, r[0]), r[2] - 1)
        cy = min(max(y, r[1]), r[3] - 1)
        d = (cx - x) ** 2 + (cy - y) ** 2
        if best_d is None or d < best_d:
            best, best_d = (cx, cy, r), d
    cx, cy, r = best
    px, py = int(round(cx)), int(round(cy))
    if primary is not None and corner_margin > 0:
        near_x = px <= primary[0] + corner_margin - 1 or px >= primary[2] - corner_margin
        near_y = py <= primary[1] + corner_margin - 1 or py >= primary[3] - corner_margin
        if near_x and near_y and primary[0] <= px < primary[2] and primary[1] <= py < primary[3]:
            px = min(max(px, primary[0] + corner_margin), primary[2] - 1 - corner_margin)
    return px, py


class AirMouse:
    def __init__(self, params: MouseParams, output: MouseOutput,
                 monitors: Callable[[], Sequence[Rect]], primary: Callable[[], Rect | None] = lambda: None,
                 can_control: Callable[[], bool] = lambda: True) -> None:
        self.p = params
        self.out = output
        self.monitors = monitors
        self.primary = primary
        self.can_control = can_control
        self.enabled = False
        self.last_action = ""
        self._lock = threading.RLock()      # luồng camera gọi update(); luồng giao diện/giọng nói bật/tắt, nhả nút
        self._reset_tracking()
        self._held: set[str] = set()
        self._yield_until = 0.0

    # ----- vòng đời -----
    def update_params(self, params: MouseParams) -> None:
        with self._lock:
            self.release()
            self.p = params
            self._reset_tracking()

    def set_enabled(self, on: bool, reason: str = "") -> None:
        with self._lock:
            if not on:
                self.release(reason or "tắt chuột bằng tay")
            self.enabled = on
            self._reset_tracking()

    def release(self, reason: str = "") -> None:
        """Nhả mọi nút chuột đang giữ (mất tay, tắt chế độ, dừng khẩn cấp)."""
        with self._lock:
            self._release(reason)

    def _release(self, reason: str) -> None:
        for button in list(self._held):
            try:
                self.out.button(button, False)
            except Exception:
                pass
            self._held.discard(button)
        self._pinch = None
        self._dragging = False
        if reason:
            self.last_action = f"nhả chuột ({reason})"

    def _reset_tracking(self) -> None:
        self._fx = OneEuro(self.p.min_cutoff, self.p.beta)
        self._fy = OneEuro(self.p.min_cutoff, self.p.beta)
        self._prev: tuple[float, float] | None = None
        self._prev_t: float | None = None
        self._scale = 0.1
        self._cursor: tuple[float, float] | None = None   # vị trí NEXA đặt (số thực, giữ phần lẻ)
        self._history: deque[tuple[float, int, int]] = deque(maxlen=30)
        self._poses: deque[str] = deque(maxlen=max(1, self.p.pose_frames))
        self._mode = "move"
        self._pinch: str | None = None                    # "left" | "right" đang chụm
        self._pinch_count = {"left": 0, "right": 0}
        self._pinch_anchor: tuple[float, float] | None = None
        self._dragging = False
        self._scroll_acc = 0.0
        self._last_seen: float | None = None

    # ----- đầu vào -----
    def lost(self, t: float) -> None:
        with self._lock:
            if self._last_seen is not None and (t - self._last_seen) * 1000.0 >= self.p.lost_hand_ms:
                if self._held:
                    self._release("mất tay")
                self._reset_tracking()

    def update(self, frame: MouseFrame, t: float) -> list[str]:
        """Xử lý một khung hình có tay. Trả về các hành động đã làm (để log/hiển thị)."""
        with self._lock:
            return self._update(frame, t)

    def _update(self, frame: MouseFrame, t: float) -> list[str]:
        if not self.enabled:
            return []
        if not self.can_control():
            if self._held:
                self._release("điều khiển đang khóa")
            self._reset_tracking()
            return []
        self._last_seen = t
        actions: list[str] = []
        sx, sy = self._fx(frame.anchor[0], t), self._fy(frame.anchor[1], t)
        self._scale = frame.scale if self._prev is None else 0.8 * self._scale + 0.2 * max(1e-4, frame.scale)
        if self._cursor is None:
            px, py = self.out.position()
            self._cursor = (float(px), float(py))

        # Chuột thật đang được dùng → nhường.
        real = self.out.position()
        if t < self._yield_until:
            self._cursor = (float(real[0]), float(real[1]))
            self._prev, self._prev_t = (sx, sy), t
            return actions
        if not self._held and max(abs(real[0] - self._cursor[0]), abs(real[1] - self._cursor[1])) > self.p.yield_px:
            self._yield_until = t + self.p.yield_ms / 1000.0
            self._cursor = (float(real[0]), float(real[1]))
            self._prev, self._prev_t = (sx, sy), t
            self.last_action = "nhường chuột thật"
            return ["yield"]

        mode = self._vote_mode(frame)
        actions += self._update_pinch(frame, t, (sx, sy))

        if mode == "scroll" and self._pinch is None:
            if self._prev is not None:
                self._scroll_acc += (self._prev[1] - sy) / self._scale     # tay đi lên = dương
                steps = int(self._scroll_acc / self.p.scroll_step)
                if steps:
                    self._scroll_acc -= steps * self.p.scroll_step
                    notches = -steps if self.p.invert_scroll else steps
                    self.out.scroll(notches)
                    self.last_action = f"cuộn {'lên' if notches > 0 else 'xuống'} {abs(notches)}"
                    actions.append(f"scroll:{notches}")
        else:
            self._scroll_acc = 0.0
            locked = self._pinch is not None and not self._dragging
            if mode == "move" and not locked and self._prev is not None:
                self._move(sx, sy, t, frame)
        self._prev, self._prev_t = (sx, sy), t
        return actions

    # ----- nội bộ -----
    def _vote_mode(self, frame: MouseFrame) -> str:
        if self._pinch is not None:
            self._poses.clear()
            return "move"                     # đang chụm: luôn là di chuyển/kéo
        kind = {Pose.FIST: "clutch", Pose.TWO_FINGERS: "scroll"}.get(frame.pose, "move")
        self._poses.append(kind)
        if kind != "move":
            # Dừng con trỏ (nắm tay / hai ngón) có hiệu lực NGAY: dừng nhầm một khung không hại gì, còn trễ vài khung
            # thì con trỏ đã chạy theo tay mất rồi. Chạy lại mới cần bỏ phiếu.
            self._mode = kind
            return kind
        top, n = Counter(self._poses).most_common(1)[0]
        if n / len(self._poses) >= 0.67:
            self._mode = top
        return self._mode

    def _pinch_kind(self, frame: MouseFrame) -> str | None:
        p = self.p
        left = frame.pinch_index < p.pinch_on and frame.reach_index >= p.tip_reach
        right = frame.pinch_middle < p.pinch_on and frame.reach_middle >= p.tip_reach
        if left and right:
            if abs(frame.pinch_index - frame.pinch_middle) < p.pinch_margin:
                return None                    # ngón cái nằm giữa hai ngón: không rõ click trái hay phải
            return "left" if frame.pinch_index < frame.pinch_middle else "right"
        return "left" if left else ("right" if right else None)

    def _update_pinch(self, frame: MouseFrame, t: float, anchor: tuple[float, float]) -> list[str]:
        p = self.p
        out: list[str] = []
        if self._pinch is not None:
            dist = frame.pinch_index if self._pinch == "left" else frame.pinch_middle
            if dist > p.pinch_off:
                if self._pinch == "left":
                    self.out.button("left", False)
                    self._held.discard("left")
                    out.append("drag_end" if self._dragging else "click")
                    self.last_action = "thả kéo" if self._dragging else "click"
                self._pinch = None
                self._dragging = False
                self._pinch_count = {"left": 0, "right": 0}
            elif self._pinch == "left" and not self._dragging and self._pinch_anchor is not None:
                moved = ((anchor[0] - self._pinch_anchor[0]) ** 2 + (anchor[1] - self._pinch_anchor[1]) ** 2) ** 0.5
                if moved / self._scale > p.drag_start:
                    self._dragging = True
                    self.last_action = "đang kéo"
                    out.append("drag_start")
            return out
        kind = self._pinch_kind(frame)
        for k in ("left", "right"):
            self._pinch_count[k] = self._pinch_count[k] + 1 if kind == k else 0
        if kind is None or self._pinch_count[kind] < max(1, p.pinch_frames):
            return out
        self._rewind(t)
        self._pinch = kind
        self._pinch_anchor = anchor
        if kind == "left":
            self.out.button("left", True)
            self._held.add("left")
            out.append("press")
        else:
            self.out.button("right", True)
            self.out.button("right", False)
            self.last_action = "click phải"
            out.append("right_click")
        return out

    def _rewind(self, t: float) -> None:
        """Đưa con trỏ về vị trí rewind_ms trước: bù độ trễ nhận ra cú chụm."""
        target = None
        for ht, hx, hy in reversed(self._history):
            if (t - ht) * 1000.0 >= self.p.rewind_ms:
                target = (hx, hy)
                break
        if target is None and self._history:
            target = self._history[0][1:]
        cur = self.out.position()
        if target is not None and max(abs(target[0] - cur[0]), abs(target[1] - cur[1])) <= self.p.rewind_max_px:
            self.out.move_to(*target)
            self._cursor = (float(target[0]), float(target[1]))

    def _move(self, sx: float, sy: float, t: float, frame: MouseFrame) -> None:
        p = self.p
        mons = list(self.monitors() or [])
        if p.mapping == "absolute" and mons:
            left = min(r[0] for r in mons)
            top = min(r[1] for r in mons)
            right = max(r[2] for r in mons)
            bottom = max(r[3] for r in mons)
            m = p.absolute_margin
            ux = min(1.0, max(0.0, (frame.raw[0] - m) / max(1e-6, 1 - 2 * m)))   # chuẩn hóa, đã lật gương
            uy = min(1.0, max(0.0, (frame.raw[1] - m) / max(1e-6, 1 - 2 * m)))
            if p.invert_x:
                ux = 1.0 - ux
            tx, ty = left + ux * (right - left - 1), top + uy * (bottom - top - 1)
        else:
            dx, dy = (sx - self._prev[0]) / self._scale, (sy - self._prev[1]) / self._scale
            if p.invert_x:
                dx = -dx
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < p.deadband:
                return
            dt = max(1e-3, t - (self._prev_t or t))
            speed = dist / dt
            factor = 1.0 if p.accel <= 0 else (speed / p.ref_speed) ** p.accel
            factor = min(p.max_factor, max(p.min_factor, factor))
            tx = self._cursor[0] + dx * p.gain * factor
            ty = self._cursor[1] + dy * p.gain * factor
        x, y = clamp_to_monitors(tx, ty, mons, self.primary(), p.corner_margin)
        # Giữ phần lẻ khi không bị chặn ở mép: tay đi rất chậm vẫn cộng dồn được.
        self._cursor = (tx if x == int(round(tx)) else float(x), ty if y == int(round(ty)) else float(y))
        self.out.move_to(x, y)
        self._history.append((t, x, y))

    def status(self) -> dict[str, Any]:
        return {"mouse_enabled": self.enabled, "mouse_mode": self._mode if self.enabled else "",
                "mouse_pinch": self._pinch or "", "mouse_dragging": self._dragging,
                "mouse_last": self.last_action}


class InputMouseOutput:
    """Nối AirMouse với InputController (SendInput / SetCursorPos) của NEXA."""

    def __init__(self, input_controller: Any) -> None:
        self.ic = input_controller

    def position(self) -> tuple[int, int]:
        return self.ic.cursor()

    def move_to(self, x: int, y: int) -> None:
        self.ic.air_move(x, y)

    def button(self, button: str, down: bool) -> None:
        self.ic.air_button(button, down)

    def scroll(self, notches: int) -> None:
        self.ic.air_scroll(notches)
