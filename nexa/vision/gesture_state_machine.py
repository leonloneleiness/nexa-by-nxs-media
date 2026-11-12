"""Máy trạng thái cử chỉ: MỌI lệnh là một tư thế tĩnh riêng biệt, giữ yên một khoảng ngắn.

Vì sao không dùng vuốt: khi tay chuyển động nhanh, webcam bị nhòe nên MediaPipe mất tư thế; động tác đưa tay
lên/hạ tay xuống bị hiểu thành vuốt; và bàn tay mở vừa là "vuốt" vừa là "phát tiếp" nên dễ lộn lệnh.
Bảng cử chỉ (xem docs/gestures.md):

  ✊ Nắm tay (ngón cái áp vào)      giữ hold_ms          → YOUTUBE_PAUSE
  🖐 Xòe cả bàn tay ngay sau đó    giữ hold_ms          → YOUTUBE_RESUME (chỉ khi vừa nắm tay tạm dừng)
  👉 Ngón trỏ chỉ sang phải         giữ action_hold_ms   → MOVE_WINDOW_TO_MONITOR_2
  👎 Ngón cái chỉ xuống             giữ action_hold_ms   → MINIMIZE_ACTIVE_WINDOW
  👍 Ngón cái chỉ lên               giữ action_hold_ms   → RESTORE_LAST_MINIMIZED_WINDOW
  ✌ Hai ngón (trỏ + giữa)          giữ action_hold_ms   → SCROLL_UP, lặp lại mỗi scroll_repeat_ms tới khi đổi tư thế

Nguyên tắc chống nhầm:
- Tư thế ổn định = bỏ phiếu trên vote_frames khung; tư thế chưa rõ/chéo không bao giờ phát lệnh.
- Chỉ đếm giờ khi tay ĐỨNG YÊN (tốc độ < still_speed và không trôi quá deadzone): đưa tay vào/ra khung hình
  không kích hoạt gì.
- Mỗi lần giữ chỉ phát MỘT lệnh (trừ cuộn); muốn lặp phải đổi tư thế rồi làm lại.
- Lệnh cửa sổ có cooldown_ms dùng chung, và chụp snapshot cửa sổ foreground ngay lúc bắt đầu giữ.
- Hướng theo khung hình đã lật gương (như preview). calibration.invert_x/invert_y đảo trái↔phải / lên↔xuống
  nếu camera đã tự lật sẵn; chỉ đảo tại một chỗ duy nhất ở đây.
- Mất tay / reset: xóa mọi ứng viên, không phát sự kiện.
"""
from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any, Callable

from nexa.core.events import GestureEvent
from nexa.vision.gesture_features import Pose


class OneEuro:
    """Bộ lọc One Euro (Casiez 2012): làm mượt mạnh khi tay chậm, ít trễ khi tay di chuyển nhanh."""

    def __init__(self, min_cutoff: float = 1.5, beta: float = 4.0, d_cutoff: float = 1.0) -> None:
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self._x: float | None = None
        self._dx = 0.0
        self._t: float | None = None

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2 * 3.141592653589793 * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x: float, t: float) -> float:
        if self._x is None or self._t is None:
            self._x, self._t = x, t
            return x
        dt = max(1e-3, t - self._t)
        dx = (x - self._x) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        self._dx = a_d * dx + (1 - a_d) * self._dx
        a = self._alpha(self.min_cutoff + self.beta * abs(self._dx), dt)
        self._x = a * x + (1 - a) * self._x
        self._t = t
        return self._x


@dataclass
class Observation:
    t: float                          # giây (monotonic)
    present: bool
    pose: Pose = Pose.UNKNOWN
    confidence: float = 0.0
    center: tuple[float, float] = (0.0, 0.0)
    scale: float = 0.1
    snap_ready: bool = False
    snap_released: bool = False
    pointer: tuple[float, float] | None = None


@dataclass
class GestureSignal:
    event: GestureEvent
    t: float
    amount: int = 0
    snapshot: Any = None
    detail: dict[str, Any] = field(default_factory=dict)


# Tư thế (sau khi áp hiệu chuẩn) → sự kiện một lần. FIST/OPEN_PALM/TWO_FINGERS xử lý riêng.
WINDOW_ACTIONS: dict[Pose, GestureEvent] = {
    Pose.POINT_RIGHT: GestureEvent.MOVE_WINDOW_TO_MONITOR_2,
    Pose.THUMB_DOWN: GestureEvent.MINIMIZE_ACTIVE_WINDOW,
    Pose.THUMB_UP: GestureEvent.RESTORE_LAST_MINIMIZED_WINDOW,
}
_FLIP_X = {Pose.POINT_RIGHT: Pose.POINT_LEFT, Pose.POINT_LEFT: Pose.POINT_RIGHT}
_FLIP_Y = {Pose.THUMB_UP: Pose.THUMB_DOWN, Pose.THUMB_DOWN: Pose.THUMB_UP}


@dataclass
class GestureParams:
    min_confidence: float = 0.6
    vote_frames: int = 6
    vote_ratio: float = 0.65
    hold_ms: int = 500                # nắm tay / mở tay
    action_hold_ms: int = 650         # chỉ tay, like/dislike, hai ngón (lệnh cửa sổ cần chắc hơn)
    still_speed: float = 0.9          # kích thước bàn tay / giây
    deadzone: float = 0.5             # xê dịch tối đa (kích thước tay) khi "giữ yên"
    resume_window_ms: int = 4000
    release_ms: int = 250
    scroll_repeat_ms: int = 180
    scroll_notch: int = 2
    invert_scroll: bool = False
    cooldown_ms: int = 900
    lost_hand_ms: int = 250
    smoothing: float = 0.5
    filter: str = "one_euro"          # one_euro | ema
    euro_min_cutoff: float = 1.5
    euro_beta: float = 4.0
    invert_x: bool = False
    invert_y: bool = False

    @classmethod
    def from_config(cls, g: dict[str, Any]) -> "GestureParams":
        pose, hold = g.get("pose", {}), g.get("hold", {})
        scroll, timing, cal = g.get("scroll", {}), g.get("timing", {}), g.get("calibration", {})
        d = cls()
        return cls(
            min_confidence=pose.get("min_confidence", d.min_confidence), vote_frames=pose.get("vote_frames", d.vote_frames),
            vote_ratio=pose.get("vote_ratio", d.vote_ratio), hold_ms=hold.get("hold_ms", d.hold_ms),
            action_hold_ms=hold.get("action_hold_ms", d.action_hold_ms),
            still_speed=hold.get("still_speed", d.still_speed), deadzone=hold.get("deadzone", d.deadzone),
            resume_window_ms=hold.get("resume_window_ms", d.resume_window_ms),
            release_ms=hold.get("release_ms", d.release_ms),
            scroll_repeat_ms=scroll.get("repeat_ms", d.scroll_repeat_ms),
            scroll_notch=scroll.get("notch_size", d.scroll_notch), invert_scroll=scroll.get("invert_scroll", d.invert_scroll),
            cooldown_ms=timing.get("cooldown_ms", d.cooldown_ms),
            lost_hand_ms=timing.get("lost_hand_ms", d.lost_hand_ms), smoothing=timing.get("smoothing", d.smoothing),
            filter=timing.get("filter", d.filter), euro_min_cutoff=timing.get("euro_min_cutoff", d.euro_min_cutoff),
            euro_beta=timing.get("euro_beta", d.euro_beta),
            invert_x=cal.get("invert_x", d.invert_x), invert_y=cal.get("invert_y", d.invert_y))


class GestureStateMachine:
    def __init__(self, params: GestureParams | None = None,
                 on_candidate_start: Callable[[], Any] | None = None) -> None:
        self.p = params or GestureParams()
        self.on_candidate_start = on_candidate_start
        # Hiệu chuẩn: nhận (dx, dy) THÔ (chưa áp invert) khi người dùng giữ chỉ tay ngang hoặc like/dislike.
        self.calibration_callback: Callable[[float, float], None] | None = None
        self.reset()
        self.last_event: str = ""
        self.last_event_t = 0.0

    # ----- trạng thái -----
    def reset(self, reason: str = "") -> None:
        self._votes: deque[Pose] = deque(maxlen=max(1, self.p.vote_frames))
        self._stable_raw: Pose = Pose.UNKNOWN
        self._smooth: tuple[float, float] | None = None
        self._fx = OneEuro(self.p.euro_min_cutoff, self.p.euro_beta)
        self._fy = OneEuro(self.p.euro_min_cutoff, self.p.euro_beta)
        self._scale = 0.1
        self._prev_t: float | None = None
        self._speed = 0.0
        self._hold_pose: Pose = Pose.UNKNOWN
        self._hold_raw: Pose = Pose.UNKNOWN   # so theo tư thế THÔ: đổi hiệu chuẩn không tạo lần giữ mới
        self._hold_start: float | None = None
        self._hold_anchor: tuple[float, float] | None = None
        self._hold_fired = False
        self._hold_snapshot: Any = None
        self._next_scroll_t = 0.0
        self._fist_paused = False           # nắm tay hiện tại đã phát PAUSE
        self._pause_armed = False           # có thể resume
        self._fist_released_t: float | None = None
        self._not_fist_since: float | None = None
        self._last_seen: float | None = None
        self._cooldown_until = getattr(self, "_cooldown_until", 0.0)
        self.reset_reason = reason

    def update_params(self, params: GestureParams) -> None:
        self.p = params
        self._votes = deque(self._votes, maxlen=max(1, params.vote_frames))

    @property
    def stable_pose(self) -> Pose:
        """Tư thế ổn định SAU khi áp hiệu chuẩn hướng."""
        pose = self._stable_raw
        if self.p.invert_x:
            pose = _FLIP_X.get(pose, pose)
        if self.p.invert_y:
            pose = _FLIP_Y.get(pose, pose)
        return pose

    def _hold_needed_ms(self, pose: Pose) -> int:
        return self.p.hold_ms if pose in (Pose.FIST, Pose.OPEN_PALM) else self.p.action_hold_ms

    def status(self, now: float) -> dict[str, Any]:
        cd_total = self.p.cooldown_ms / 1000.0
        remaining = max(0.0, self._cooldown_until - now)
        hold = 0.0
        if self._hold_start is not None and not self._hold_fired:
            hold = min(1.0, (now - self._hold_start) * 1000.0 / max(1, self._hold_needed_ms(self._hold_pose)))
        return {
            "stable_pose": self.stable_pose.value, "speed": round(self._speed, 2),
            "motion": "đứng yên" if self._speed <= self.p.still_speed else "đang di chuyển",
            "cooldown": round(remaining / cd_total, 2) if cd_total > 0 else 0.0,
            "need_rearm": self._hold_fired and self._hold_pose in WINDOW_ACTIONS,
            "pause_armed": self._pause_armed, "hold": round(hold, 2), "last_event": self.last_event,
        }

    # ----- đầu vào -----
    def update(self, obs: Observation) -> list[GestureSignal]:
        p = self.p
        if not obs.present:
            if self._last_seen is not None and (obs.t - self._last_seen) * 1000.0 >= p.lost_hand_ms:
                self.reset("mất tay")
            return []
        self._last_seen = obs.t

        # 1) Bỏ phiếu tư thế (lọc rung / hysteresis).
        pose = obs.pose if obs.confidence >= p.min_confidence else Pose.UNKNOWN
        self._votes.append(pose)
        counts = Counter(self._votes)
        top, n = counts.most_common(1)[0]
        if n / len(self._votes) >= p.vote_ratio:
            self._stable_raw = top
        elif self._stable_raw != Pose.UNKNOWN and counts.get(self._stable_raw, 0) / len(self._votes) < 0.3:
            self._stable_raw = Pose.UNKNOWN

        # 2) Động học: tâm làm mượt + tốc độ theo kích thước tay.
        cx, cy = obs.center
        if self._smooth is None:
            self._smooth = (self._fx(cx, obs.t), self._fy(cy, obs.t))
            self._scale = obs.scale
            self._prev_t = obs.t
            return []
        px, py = self._smooth
        if p.filter == "one_euro":
            sx, sy = self._fx(cx, obs.t), self._fy(cy, obs.t)
        else:
            a = min(0.95, max(0.0, p.smoothing))
            sx, sy = a * px + (1 - a) * cx, a * py + (1 - a) * cy
        self._scale = 0.8 * self._scale + 0.2 * max(1e-4, obs.scale)
        dt = max(1e-3, obs.t - (self._prev_t or obs.t))
        inst_speed = ((sx - px) ** 2 + (sy - py) ** 2) ** 0.5 / self._scale / dt
        self._speed = 0.5 * self._speed + 0.5 * inst_speed
        self._smooth = (sx, sy)
        self._prev_t = obs.t

        return self._update_hold(obs)

    # ----- tư thế tĩnh -----
    def _cancel_hold(self) -> None:
        self._hold_start = None
        self._hold_anchor = None
        self._hold_fired = False
        self._hold_snapshot = None

    def _update_hold(self, obs: Observation) -> list[GestureSignal]:
        p = self.p
        out: list[GestureSignal] = []
        stable = self.stable_pose
        # Theo dõi nhả nắm tay (cho chuỗi nắm tay → mở tay = phát tiếp).
        if stable == Pose.FIST:
            self._not_fist_since = None
        elif self._fist_paused:
            if self._not_fist_since is None:
                self._not_fist_since = obs.t
            elif (obs.t - self._not_fist_since) * 1000.0 >= p.release_ms:
                self._fist_paused = False
                self._pause_armed = True
                self._fist_released_t = obs.t

        if self._stable_raw != self._hold_raw:
            self._hold_raw = self._stable_raw
            self._cancel_hold()
        self._hold_pose = stable
        if stable in (Pose.UNKNOWN, Pose.POINT_UP):
            return out
        if self.calibration_callback is None and stable == Pose.POINT_LEFT:
            return out
        if self._speed > p.still_speed:
            if not self._hold_fired:
                self._cancel_hold()
            return out
        if self._hold_start is None:
            self._hold_start = obs.t
            self._hold_anchor = self._smooth
            if stable in WINDOW_ACTIONS or stable == Pose.TWO_FINGERS:
                self._hold_snapshot = self.on_candidate_start() if self.on_candidate_start else None
            return out
        ax, ay = self._hold_anchor
        drift = ((self._smooth[0] - ax) ** 2 + (self._smooth[1] - ay) ** 2) ** 0.5 / self._scale
        if drift > p.deadzone and not self._hold_fired:
            self._hold_start = obs.t
            self._hold_anchor = self._smooth
            return out
        if (obs.t - self._hold_start) * 1000.0 < self._hold_needed_ms(stable):
            return out

        if self.calibration_callback is not None:
            return self._calibrate(obs)

        if stable == Pose.TWO_FINGERS:
            # Cuộn lặp lại trong khi còn giữ hai ngón.
            if obs.t >= self._next_scroll_t:
                self._hold_fired = True
                self._next_scroll_t = obs.t + p.scroll_repeat_ms / 1000.0
                out.append(self._emit(GestureEvent.SCROLL_UP, obs.t, amount=max(1, int(p.scroll_notch)),
                                      snapshot=self._hold_snapshot, cooldown=False))
            return out
        if self._hold_fired:
            return out
        if stable == Pose.FIST:
            self._hold_fired = True
            if not self._fist_paused:
                self._fist_paused = True
                self._pause_armed = False
                out.append(self._emit(GestureEvent.YOUTUBE_PAUSE, obs.t, cooldown=False))
        elif stable == Pose.OPEN_PALM:
            self._hold_fired = True
            recent = self._fist_released_t is not None and \
                (obs.t - self._fist_released_t) * 1000.0 <= p.resume_window_ms
            if self._pause_armed and recent:
                self._pause_armed = False
                out.append(self._emit(GestureEvent.YOUTUBE_RESUME, obs.t, cooldown=False))
        elif stable in WINDOW_ACTIONS:
            if obs.t < self._cooldown_until:
                return out                     # vẫn giữ: sẽ phát khi hết cooldown
            self._hold_fired = True
            out.append(self._emit(WINDOW_ACTIONS[stable], obs.t, snapshot=self._hold_snapshot))
        return out

    def _calibrate(self, obs: Observation) -> list[GestureSignal]:
        """Đo hướng THÔ: chỉ tay ngang → dx = ±1, like/dislike → dy = ∓1. Không phát sự kiện."""
        raw = self._stable_raw
        self._hold_fired = True
        vec = {Pose.POINT_RIGHT: (1.0, 0.0), Pose.POINT_LEFT: (-1.0, 0.0),
               Pose.THUMB_UP: (0.0, -1.0), Pose.THUMB_DOWN: (0.0, 1.0)}.get(raw)
        if vec is not None:
            cb, self.calibration_callback = self.calibration_callback, None
            if cb(*vec) is False:          # sai loại tư thế cho bước này: tiếp tục chờ
                self.calibration_callback = cb
        return []

    def _emit(self, ev: GestureEvent, t: float, amount: int = 0, snapshot: Any = None,
              cooldown: bool = True) -> GestureSignal:
        if cooldown:
            self._cooldown_until = t + self.p.cooldown_ms / 1000.0
        self.last_event = ev.value
        self.last_event_t = t
        return GestureSignal(ev, t, amount, snapshot)
