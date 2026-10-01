"""Máy trạng thái cử chỉ cho chế độ VIEWER_3D (độc lập với GestureStateMachine sáu lệnh hệ thống).

  IDLE ── bàn tay MỞ ổn định acquire_ms ──────────▶ ROTATE_READY (ghi điểm neo, bỏ qua chuyển động đưa tay vào)
                                                    └─ đi quá deadzone ─▶ ROTATING (yaw/pitch theo tay, One Euro)
  IDLE ── NẮM TAY giữ yên fist_hold_ms ──(chưa tách)▶ EXPLODE_ARMED ── MỞ tay, giữ yên open_hold_ms ─▶ EXPLODE (1 lần)
                                     └─(đang tách)──▶ COLLAPSE (1 lần)
  Hai ngón (tùy chọn) đưa lên/xuống ──▶ ZOOM.
  Búng tay: ngón cái chạm ngón giữa ≥ snap_ready_ms rồi bật ra trong snap_window_ms ──▶ motion_toggle (1 lần).

Chống nhầm:
- Bàn tay mở xuất hiện trực tiếp chỉ dẫn tới xoay, không bao giờ tách (tách chỉ đi từ EXPLODE_ARMED).
- Nắm tay ngắn hơn fist_hold_ms, hoặc nắm tay khi đang di chuyển → không gì cả. Mở tay nhưng tay đi nhanh hơn
  explode_max_speed → hủy chuẩn bị tách. Đang xoay muốn tách phải nắm tay giữ yên lại từ đầu.
- Trong lúc animation tách/lắp: khóa mọi cử chỉ; sau đó cooldown_ms mới cho tách/lắp tiếp.
- Mất tay quá lost_hand_ms hoặc tư thế không rõ kéo dài → reset; xuất hiện lại thì lấy điểm neo mới (không nhảy).
- Mất tay → dừng ngay (không trượt quán tính). Quán tính nhẹ chỉ làm mượt khi tay dừng đột ngột.
- Khóa (dừng khẩn cấp): không phát sự kiện nào.
Tốc độ: sự kiện xoay phát theo từng khung camera (~30 Hz); QML nội suy tới tốc độ khung hình màn hình.
"""
from __future__ import annotations

import math
from collections import Counter, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from nexa.vision.gesture_features import Pose
from nexa.vision.gesture_state_machine import Observation, OneEuro


class VState(str, Enum):
    IDLE = "IDLE"
    ROTATE_READY = "ROTATE_READY"
    ROTATING = "ROTATING"
    FIST_HOLD = "FIST_HOLD"
    EXPLODE_ARMED = "EXPLODE_ARMED"
    OPEN_HOLD = "OPEN_HOLD"
    ANIMATING = "ANIMATING"
    ZOOMING = "ZOOMING"
    LOCKED = "LOCKED"


LABELS = {
    VState.IDLE: "Đưa bàn tay mở vào camera để xoay · nắm tay giữ yên để tách",
    VState.ROTATE_READY: "Sẵn sàng xoay",
    VState.ROTATING: "Đang xoay mô hình",
    VState.FIST_HOLD: "Giữ yên nắm tay…",
    VState.EXPLODE_ARMED: "Đang chuẩn bị tách… mở bàn tay và giữ yên",
    VState.OPEN_HOLD: "Giữ yên bàn tay mở…",
    VState.ANIMATING: "",
    VState.ZOOMING: "Đang thu phóng",
    VState.LOCKED: "Tương tác đang khóa (dừng khẩn cấp)",
}


@dataclass
class ViewerGestureParams:
    rotate_sensitivity: float = 110.0     # độ xoay cho mỗi "kích thước bàn tay" tay di chuyển
    rotate_deadzone: float = 0.25         # kích thước tay: phải đi quá mức này mới bắt đầu xoay
    acquire_ms: int = 200
    acquire_speed: float = 1.6            # tay/giây: nhanh hơn = đang đưa tay vào khung, chưa ghi neo
    fist_hold_ms: int = 500
    open_hold_ms: int = 350
    arm_timeout_ms: int = 3000
    cooldown_ms: int = 700
    animation_ms: int = 900
    still_speed: float = 0.9
    explode_max_speed: float = 1.8
    inertia: float = 0.35                 # 0 = không quán tính; 0.9 = rất trơn
    pitch_limit_deg: float = 85.0
    zoom_two_fingers: bool = True
    zoom_sensitivity: float = 1.2
    lost_hand_ms: int = 250
    unknown_reset_ms: int = 400
    vote_frames: int = 5
    vote_ratio: float = 0.6
    min_confidence: float = 0.55
    euro_min_cutoff: float = 1.2
    euro_beta: float = 3.0
    invert_x: bool = False
    invert_y: bool = False
    snap_enabled: bool = True
    snap_ready_ms: int = 90
    snap_window_ms: int = 400
    snap_cooldown_ms: int = 900

    @classmethod
    def from_config(cls, cfg: Any) -> "ViewerGestureParams":
        g = (cfg.get("three_d.gesture") if cfg is not None else None) or {}
        d = cls()
        kw = {}
        for k in d.__dataclass_fields__:
            if k in g and g[k] is not None:
                try:
                    kw[k] = type(getattr(d, k))(g[k])
                except (TypeError, ValueError):
                    pass
        if cfg is not None and hasattr(cfg, "gesture"):
            kw.setdefault("invert_x", bool(cfg.gesture("calibration.invert_x", False)))
            kw.setdefault("invert_y", bool(cfg.gesture("calibration.invert_y", False)))
        if cfg is not None and cfg.get("audio.snap.camera") is not None and "snap_enabled" not in g:
            kw["snap_enabled"] = bool(cfg.get("audio.snap.camera")) and cfg.get("audio.snap.enabled") is not False
        return cls(**kw)


@dataclass
class ViewerEvent:
    kind: str                            # rotate | zoom | explode | collapse | motion_toggle | hud
    t: float
    dyaw: float = 0.0
    dpitch: float = 0.0
    factor: float = 1.0
    state: str = ""
    label: str = ""
    progress: float = 0.0
    extra: dict = field(default_factory=dict)


class ViewerGestureStateMachine:
    def __init__(self, params: ViewerGestureParams | None = None) -> None:
        self.p = params or ViewerGestureParams()
        self.locked = False
        self._cooldown_until = 0.0
        self._fist_consumed = False
        self.explode_count = 0
        self.collapse_count = 0
        self.snap_count = 0
        self._snap_cooldown_until = 0.0
        self.reset("khởi tạo")

    # ----- trạng thái -----
    def reset(self, reason: str = "") -> None:
        self.state = VState.LOCKED if self.locked else VState.IDLE
        self._votes: deque[Pose] = deque(maxlen=max(1, self.p.vote_frames))
        self._stable = Pose.UNKNOWN
        self._fx = OneEuro(self.p.euro_min_cutoff, self.p.euro_beta)
        self._fy = OneEuro(self.p.euro_min_cutoff, self.p.euro_beta)
        self._pos: tuple[float, float] | None = None
        self._scale = 0.1
        self._prev_t: float | None = None
        self._speed = 0.0
        self._last_seen: float | None = None
        self._timer: float | None = None          # mốc bắt đầu giữ tư thế của trạng thái hiện tại
        self._anchor: tuple[float, float] | None = None
        self._last: tuple[float, float] | None = None
        self._vel = (0.0, 0.0)
        self._arm_until = 0.0
        self._anim_until = 0.0
        self._unknown_since: float | None = None
        self._hud_key: tuple | None = None
        self._snap_since: float | None = None
        self._snap_last: float | None = None
        self.reset_reason = reason

    def update_params(self, params: ViewerGestureParams) -> None:
        self.p = params
        self._votes = deque(self._votes, maxlen=max(1, params.vote_frames))

    def lock(self, locked: bool) -> list[ViewerEvent]:
        self.locked = locked
        self.reset("khóa" if locked else "mở khóa")
        return [self._hud(0.0, force=True)]

    @property
    def stable_pose(self) -> Pose:
        return self._stable

    # ----- đầu vào -----
    def update(self, obs: Observation, exploded: bool) -> list[ViewerEvent]:
        p = self.p
        out: list[ViewerEvent] = []
        if self.locked:
            return out
        t = obs.t
        if self.state == VState.ANIMATING:
            if t < self._anim_until:
                self._track(obs)
                return out
            self._go(VState.IDLE)
            self._timer = None
        if not obs.present:
            if self._last_seen is not None and (t - self._last_seen) * 1000 >= p.lost_hand_ms:
                was = self.state
                self.reset("mất tay")
                if was != VState.IDLE:
                    out.append(self._hud(t, force=True, label="Mất tay — đưa tay vào lại"))
            return out
        self._last_seen = t
        first = self._track(obs)
        if self._check_snap(obs):
            self.snap_count += 1
            self._go(VState.IDLE)
            self._timer = None
            self._anchor = self._last = None
            out.append(ViewerEvent("motion_toggle", t))
            out.append(self._hud(t, force=True, label="Búng tay — bật/tắt chuyển động"))
            return out
        if first:
            return out
        pose = self._stable
        if pose == Pose.UNKNOWN:
            self._unknown_since = self._unknown_since if self._unknown_since is not None else t
            if (t - self._unknown_since) * 1000 >= p.unknown_reset_ms and self.state not in (VState.IDLE, VState.EXPLODE_ARMED):
                self._go(VState.IDLE)
                self._timer = None
                out.append(self._hud(t, force=True))
            if self.state == VState.EXPLODE_ARMED and t > self._arm_until:
                self._go(VState.IDLE)
                out.append(self._hud(t, force=True, label="Hết thời gian chờ tách"))
            return out
        self._unknown_since = None
        if pose != Pose.FIST:
            self._fist_consumed = False

        s = self.state
        if s in (VState.IDLE, VState.FIST_HOLD) and pose == Pose.FIST:
            self._handle_fist(t, exploded, out)
        elif s == VState.EXPLODE_ARMED:
            self._handle_armed(t, pose, out)
        elif s == VState.OPEN_HOLD:
            self._handle_open_hold(t, pose, out)
        elif pose == Pose.OPEN_PALM:
            self._handle_open(t, out)
        elif pose == Pose.TWO_FINGERS and p.zoom_two_fingers:
            self._handle_zoom(t, out)
        else:
            if s != VState.IDLE:
                self._go(VState.IDLE)
                self._timer = None
                out.append(self._hud(t, force=True))
            self._timer = None
        hud = self._hud(t)
        if hud is not None:
            out.append(hud)
        return out

    def _track(self, obs: Observation) -> bool:
        """Bỏ phiếu tư thế + lọc tâm bàn tay. True nếu là khung đầu (chưa có vận tốc)."""
        p = self.p
        pose = obs.pose if obs.confidence >= p.min_confidence else Pose.UNKNOWN
        self._votes.append(pose)
        top, n = Counter(self._votes).most_common(1)[0]
        if n / len(self._votes) >= p.vote_ratio:
            self._stable = top
        elif Counter(self._votes).get(self._stable, 0) / len(self._votes) < 0.3:
            self._stable = Pose.UNKNOWN
        cx, cy = obs.center
        if self._pos is None:
            self._pos = (self._fx(cx, obs.t), self._fy(cy, obs.t))
            self._scale = max(1e-4, obs.scale)
            self._prev_t = obs.t
            return True
        px, py = self._pos
        sx, sy = self._fx(cx, obs.t), self._fy(cy, obs.t)
        self._scale = 0.8 * self._scale + 0.2 * max(1e-4, obs.scale)
        dt = max(1e-3, obs.t - (self._prev_t or obs.t))
        inst = math.hypot(sx - px, sy - py) / self._scale / dt
        self._speed = 0.5 * self._speed + 0.5 * inst
        self._pos = (sx, sy)
        self._prev_t = obs.t
        return False

    def _check_snap(self, obs: Observation) -> bool:
        """Dáng chuẩn bị búng giữ đủ lâu, rồi trong cửa sổ ngắn thấy dáng vừa búng xong → True (một lần)."""
        p = self.p
        t = obs.t
        if not p.snap_enabled:
            return False
        if obs.snap_ready:
            if self._snap_since is None or (self._snap_last is not None and t - self._snap_last > 0.15):
                self._snap_since = t
            self._snap_last = t
            return False
        if self._snap_since is None or self._snap_last is None:
            return False
        held = (self._snap_last - self._snap_since) * 1000
        gap = (t - self._snap_last) * 1000
        if gap > p.snap_window_ms:
            self._snap_since = self._snap_last = None
            return False
        if not obs.snap_released or held < p.snap_ready_ms or t < self._snap_cooldown_until:
            return False
        self._snap_since = self._snap_last = None
        self._snap_cooldown_until = t + p.snap_cooldown_ms / 1000
        return True

    def _go(self, state: VState) -> None:
        self.state = state

    def _hud(self, t: float, force: bool = False, label: str | None = None, progress: float | None = None) -> ViewerEvent | None:
        prog = progress if progress is not None else self._progress(t)
        key = (self.state, round(prog, 1), label)
        if not force and key == self._hud_key:
            return None
        self._hud_key = key
        return ViewerEvent("hud", t, state=self.state.value, label=label if label is not None else LABELS[self.state],
                           progress=round(prog, 2))

    def _progress(self, t: float) -> float:
        p = self.p
        if self._timer is None:
            return 0.0
        if self.state == VState.FIST_HOLD:
            return min(1.0, (t - self._timer) * 1000 / max(1, p.fist_hold_ms))
        if self.state == VState.OPEN_HOLD:
            return min(1.0, (t - self._timer) * 1000 / max(1, p.open_hold_ms))
        if self.state == VState.IDLE:
            return min(1.0, (t - self._timer) * 1000 / max(1, p.acquire_ms))
        return 0.0

    # ----- xử lý theo tư thế -----
    def _handle_fist(self, t: float, exploded: bool, out: list[ViewerEvent]) -> None:
        p = self.p
        if self._fist_consumed or t < self._cooldown_until:
            return
        if self._speed > p.still_speed:
            self._timer = None                          # nắm tay đang di chuyển: không đếm
            if self.state == VState.FIST_HOLD:
                self._go(VState.IDLE)
            return
        if self.state != VState.FIST_HOLD:
            self._go(VState.FIST_HOLD)
            self._timer = t
            return
        if self._timer is None:
            self._timer = t
            return
        if (t - self._timer) * 1000 < p.fist_hold_ms:
            return
        self._fist_consumed = True
        if exploded:
            self._trigger(t, "collapse", out)
        else:
            self._go(VState.EXPLODE_ARMED)
            self._arm_until = t + p.arm_timeout_ms / 1000
            self._timer = None
            out.append(self._hud(t, force=True))

    def _handle_armed(self, t: float, pose: Pose, out: list[ViewerEvent]) -> None:
        p = self.p
        if t > self._arm_until:
            self._go(VState.IDLE)
            out.append(self._hud(t, force=True, label="Hết thời gian chờ tách"))
            return
        if pose == Pose.FIST:
            self._arm_until = t + p.arm_timeout_ms / 1000     # còn nắm: tiếp tục chờ
            return
        if pose == Pose.OPEN_PALM:
            if self._speed > p.explode_max_speed:
                self._go(VState.IDLE)
                out.append(self._hud(t, force=True, label="Tay di chuyển nhanh — không tách"))
                return
            self._go(VState.OPEN_HOLD)
            self._timer = t if self._speed <= p.still_speed else None
            return
        # tư thế khác (hai ngón…) → hủy chuẩn bị
        self._go(VState.IDLE)
        out.append(self._hud(t, force=True))

    def _handle_open_hold(self, t: float, pose: Pose, out: list[ViewerEvent]) -> None:
        p = self.p
        if pose != Pose.OPEN_PALM:
            if pose == Pose.FIST and t <= self._arm_until:
                self._go(VState.EXPLODE_ARMED)          # quay lại nắm: vẫn đang chuẩn bị
                self._arm_until = t + p.arm_timeout_ms / 1000
                return
            self._go(VState.IDLE)
            out.append(self._hud(t, force=True))
            return
        if self._speed > p.explode_max_speed:
            self._go(VState.IDLE)
            out.append(self._hud(t, force=True, label="Tay di chuyển nhanh — không tách"))
            return
        if self._speed > p.still_speed:
            self._timer = None                          # chưa đứng yên: chờ
            return
        if self._timer is None:
            self._timer = t
            return
        if (t - self._timer) * 1000 >= p.open_hold_ms:
            self._trigger(t, "explode", out)

    def _trigger(self, t: float, kind: str, out: list[ViewerEvent]) -> None:
        p = self.p
        self._go(VState.ANIMATING)
        self._anim_until = t + p.animation_ms / 1000
        self._cooldown_until = self._anim_until + p.cooldown_ms / 1000
        self._timer = None
        self._anchor = self._last = None
        self._vel = (0.0, 0.0)
        if kind == "explode":
            self.explode_count += 1
        else:
            self.collapse_count += 1
        out.append(ViewerEvent(kind, t))
        out.append(self._hud(t, force=True, label="Assembly đã tách" if kind == "explode" else "Đã lắp lại"))

    def _handle_open(self, t: float, out: list[ViewerEvent]) -> None:
        p = self.p
        pos = self._pos
        assert pos is not None
        if self.state not in (VState.ROTATE_READY, VState.ROTATING):
            if self.state != VState.IDLE:
                self._go(VState.IDLE)
            # thu nhận: bàn tay mở ổn định và không lao nhanh (đang đưa tay vào khung)
            if self._speed > p.acquire_speed or self._timer is None:
                self._timer = t
                return
            if (t - self._timer) * 1000 >= p.acquire_ms:
                self._go(VState.ROTATE_READY)
                self._anchor = pos
                self._last = pos
                self._vel = (0.0, 0.0)
                self._timer = None
                out.append(self._hud(t, force=True))
            return
        if self.state == VState.ROTATE_READY:
            ax, ay = self._anchor or pos
            if math.hypot(pos[0] - ax, pos[1] - ay) / self._scale > p.rotate_deadzone:
                self._go(VState.ROTATING)
                self._last = pos                        # bắt đầu từ đây: không nhảy
                out.append(self._hud(t, force=True))
            return
        lx, ly = self._last or pos
        dx, dy = (pos[0] - lx) / self._scale, (pos[1] - ly) / self._scale
        self._last = pos
        if p.invert_x:
            dx = -dx
        if p.invert_y:
            dy = -dy
        a = min(0.9, max(0.0, p.inertia))
        vx = (1 - a) * dx + a * self._vel[0]
        vy = (1 - a) * dy + a * self._vel[1]
        self._vel = (vx, vy)
        if abs(vx) + abs(vy) > 1e-5:
            # tay sang phải → mô hình quay sang phải (yaw +); tay lên (y ảnh giảm) → mô hình ngửa lên (pitch +)
            out.append(ViewerEvent("rotate", t, dyaw=vx * p.rotate_sensitivity, dpitch=-vy * p.rotate_sensitivity))

    def _handle_zoom(self, t: float, out: list[ViewerEvent]) -> None:
        p = self.p
        pos = self._pos
        assert pos is not None
        if self.state != VState.ZOOMING:
            if self._speed > p.acquire_speed or self._timer is None or self.state != VState.IDLE:
                self._go(VState.IDLE)
                self._timer = t
                return
            if (t - self._timer) * 1000 >= p.acquire_ms:
                self._go(VState.ZOOMING)
                self._last = pos
                self._timer = None
                out.append(self._hud(t, force=True))
            return
        dy = (pos[1] - (self._last or pos)[1]) / self._scale
        self._last = pos
        if abs(dy) > 1e-4:
            out.append(ViewerEvent("zoom", t, factor=math.exp(-dy * p.zoom_sensitivity)))  # tay lên (dy < 0) → phóng to (> 1)

    def status(self) -> dict:
        return {"state": self.state.value, "label": LABELS[self.state], "stable_pose": self._stable.value,
                "speed": round(self._speed, 2), "explodes": self.explode_count, "collapses": self.collapse_count, "snaps": self.snap_count,
                "locked": self.locked}
