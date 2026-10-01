"""Máy trạng thái cử chỉ khi bảng Sinh code đang mở (chế độ CODE — độc quyền như VIEWER_3D).

  NẮM TAY giữ yên fist_hold_ms ─────────────▶ save (1 lần; phải mở/bỏ tay ra rồi nắm lại mới lưu tiếp)
  Búng tay (ngón cái chạm ngón giữa ≥ snap_ready_ms rồi bật ra trong snap_window_ms) ──▶ run (1 lần)
  HAI NGÓN (trỏ + giữa) ổn định acquire_ms ──▶ SCROLL_READY (ghi điểm neo)
        └─ đưa tay lên/xuống quá deadzone ──▶ SCROLLING: như cần điều khiển — tay càng xa điểm neo cuộn càng nhanh,
           tay lên = cuộn lên, tay xuống = cuộn xuống, đưa tay về điểm neo = dừng.

Chống nhầm:
- Nắm tay đang di chuyển (nhanh hơn still_speed) không đếm; sau khi lưu có save_cooldown_ms.
- Mất tay quá lost_hand_ms hoặc tư thế không rõ kéo dài → về IDLE (dừng cuộn ngay, không trượt quán tính).
- Khóa (dừng khẩn cấp): không phát sự kiện nào.
"""
from __future__ import annotations

import math
from collections import Counter, deque
from dataclasses import dataclass
from enum import Enum
from typing import Any

from nexa.vision.gesture_features import Pose
from nexa.vision.gesture_state_machine import Observation, OneEuro


class CState(str, Enum):
    IDLE = "IDLE"
    FIST_HOLD = "FIST_HOLD"
    SCROLL_READY = "SCROLL_READY"
    SCROLLING = "SCROLLING"
    LOCKED = "LOCKED"


LABELS = {
    CState.IDLE: "✊ nắm tay: lưu · 🫰 búng tay: chạy / tắt · ✌ hai ngón: cuộn",
    CState.FIST_HOLD: "✊ Giữ yên nắm tay để lưu…",
    CState.SCROLL_READY: "✌ Đưa tay lên / xuống để cuộn",
    CState.SCROLLING: "✌ Đang cuộn",
    CState.LOCKED: "Cử chỉ đang khóa (dừng khẩn cấp)",
}


@dataclass
class CodeGestureParams:
    fist_hold_ms: int = 700
    still_speed: float = 0.9              # kích thước tay / giây
    save_cooldown_ms: int = 1500
    acquire_ms: int = 200
    acquire_speed: float = 1.6
    scroll_deadzone: float = 0.3          # kích thước tay: lệch khỏi điểm neo ít hơn = không cuộn
    scroll_gain: float = 1600.0           # px/giây cho mỗi kích thước tay vượt deadzone
    scroll_max: float = 3000.0            # px/giây
    invert_scroll: bool = False
    lost_hand_ms: int = 250
    unknown_reset_ms: int = 400
    vote_frames: int = 5
    vote_ratio: float = 0.6
    min_confidence: float = 0.55
    euro_min_cutoff: float = 1.2
    euro_beta: float = 3.0
    snap_enabled: bool = True
    snap_ready_ms: int = 90
    snap_window_ms: int = 400
    snap_cooldown_ms: int = 1200

    @classmethod
    def from_config(cls, cfg: Any) -> "CodeGestureParams":
        g = (cfg.get("code.gesture") if cfg is not None else None) or {}
        d = cls()
        kw = {}
        for k in d.__dataclass_fields__:
            if k in g and g[k] is not None:
                try:
                    kw[k] = type(getattr(d, k))(g[k])
                except (TypeError, ValueError):
                    pass
        if cfg is not None and cfg.get("audio.snap.camera") is not None and "snap_enabled" not in g:
            kw["snap_enabled"] = bool(cfg.get("audio.snap.camera")) and cfg.get("audio.snap.enabled") is not False
        return cls(**kw)


@dataclass
class CodeGestureEvent:
    kind: str                            # save | run | scroll | hud
    t: float
    dy: float = 0.0                      # scroll: px (dương = cuộn xuống)
    state: str = ""
    label: str = ""
    progress: float = 0.0


class CodeGestureStateMachine:
    def __init__(self, params: CodeGestureParams | None = None) -> None:
        self.p = params or CodeGestureParams()
        self.locked = False
        self.save_count = 0
        self.run_count = 0
        self._save_cooldown_until = 0.0
        self._snap_cooldown_until = 0.0
        self.reset("khởi tạo")

    def reset(self, reason: str = "") -> None:
        self.state = CState.LOCKED if self.locked else CState.IDLE
        self._votes: deque[Pose] = deque(maxlen=max(1, self.p.vote_frames))
        self._stable = Pose.UNKNOWN
        self._fx = OneEuro(self.p.euro_min_cutoff, self.p.euro_beta)
        self._fy = OneEuro(self.p.euro_min_cutoff, self.p.euro_beta)
        self._pos: tuple[float, float] | None = None
        self._scale = 0.1
        self._prev_t: float | None = None
        self._dt = 1 / 30
        self._speed = 0.0
        self._last_seen: float | None = None
        self._timer: float | None = None
        self._anchor_y: float | None = None
        self._fist_consumed = False
        self._unknown_since: float | None = None
        self._hud_key: tuple | None = None
        self._snap_since: float | None = None
        self._snap_last: float | None = None
        self._flash_label = ""
        self._flash_until = 0.0
        self.reset_reason = reason

    def update_params(self, params: CodeGestureParams) -> None:
        self.p = params
        self._votes = deque(self._votes, maxlen=max(1, params.vote_frames))

    def lock(self, locked: bool) -> list[CodeGestureEvent]:
        self.locked = locked
        self.reset("khóa" if locked else "mở khóa")
        return [self._hud(0.0, force=True)]

    # ----- đầu vào -----
    def update(self, obs: Observation) -> list[CodeGestureEvent]:
        p = self.p
        out: list[CodeGestureEvent] = []
        if self.locked:
            return out
        t = obs.t
        if not obs.present:
            if self._last_seen is not None and (t - self._last_seen) * 1000 >= p.lost_hand_ms:
                was = self.state
                self.reset("mất tay")
                if was != CState.IDLE:
                    out.append(self._hud(t, force=True))
            return out
        self._last_seen = t
        first = self._track(obs)
        if self._check_snap(obs):
            self.run_count += 1
            self._idle()
            self._flash(t, "🫰 Búng tay — chạy thử / tắt")
            out.append(CodeGestureEvent("run", t))
            out.append(self._hud(t, force=True))
            return out
        if first:
            return out
        pose = self._stable
        if pose == Pose.UNKNOWN:
            self._unknown_since = self._unknown_since if self._unknown_since is not None else t
            if (t - self._unknown_since) * 1000 >= p.unknown_reset_ms and self.state != CState.IDLE:
                self._idle()
                out.append(self._hud(t, force=True))
            return out
        self._unknown_since = None
        if pose != Pose.FIST:
            self._fist_consumed = False
        if pose == Pose.FIST:
            self._handle_fist(t, out)
        elif pose == Pose.TWO_FINGERS:
            self._handle_scroll(t, out)
        elif self.state != CState.IDLE:
            self._idle()
            out.append(self._hud(t, force=True))
        else:
            self._timer = None
        hud = self._hud(t) if self.state != CState.SCROLLING else None     # đang cuộn: nhãn kèm hướng ở _handle_scroll
        if hud is not None:
            out.append(hud)
        return out

    def _idle(self) -> None:
        self.state = CState.IDLE
        self._timer = None
        self._anchor_y = None

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
        self._dt = dt
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

    def _flash(self, t: float, label: str) -> None:
        """Nhãn xác nhận (đã lưu / chạy thử) giữ trên HUD một lúc thay vì biến mất ở khung kế tiếp."""
        self._flash_label, self._flash_until = label, t + 1.5

    def _hud(self, t: float, force: bool = False, label: str | None = None) -> CodeGestureEvent | None:
        if label is None and self.state == CState.IDLE and t < self._flash_until:
            label = self._flash_label
        prog = self._progress(t)
        key = (self.state, round(prog, 1), label)
        if not force and key == self._hud_key:
            return None
        self._hud_key = key
        return CodeGestureEvent("hud", t, state=self.state.value, label=label if label is not None else LABELS[self.state],
                                progress=round(prog, 2))

    def _progress(self, t: float) -> float:
        if self.state == CState.FIST_HOLD and self._timer is not None:
            return min(1.0, (t - self._timer) * 1000 / max(1, self.p.fist_hold_ms))
        return 0.0

    # ----- xử lý theo tư thế -----
    def _handle_fist(self, t: float, out: list[CodeGestureEvent]) -> None:
        p = self.p
        if self.state in (CState.SCROLL_READY, CState.SCROLLING):
            self._idle()
        if self._fist_consumed or t < self._save_cooldown_until:
            return
        if self._speed > p.still_speed:
            self._timer = None                          # nắm tay đang di chuyển: không đếm
            self.state = CState.IDLE
            return
        if self.state != CState.FIST_HOLD or self._timer is None:
            self.state = CState.FIST_HOLD
            self._timer = t
            return
        if (t - self._timer) * 1000 < p.fist_hold_ms:
            return
        self._fist_consumed = True
        self._save_cooldown_until = t + p.save_cooldown_ms / 1000
        self.save_count += 1
        self._idle()
        self._flash(t, "✊ Nắm tay — lưu code")
        out.append(CodeGestureEvent("save", t))
        out.append(self._hud(t, force=True))

    def _handle_scroll(self, t: float, out: list[CodeGestureEvent]) -> None:
        p = self.p
        pos = self._pos
        assert pos is not None
        if self.state not in (CState.SCROLL_READY, CState.SCROLLING):
            if self.state != CState.IDLE:
                self._idle()
            if self._speed > p.acquire_speed or self._timer is None:
                self._timer = t                         # đang đưa tay vào khung: chưa ghi neo
                return
            if (t - self._timer) * 1000 >= p.acquire_ms:
                self.state = CState.SCROLL_READY
                self._anchor_y = pos[1]
                self._timer = None
                out.append(self._hud(t, force=True))
            return
        off = (pos[1] - (self._anchor_y if self._anchor_y is not None else pos[1])) / self._scale
        if p.invert_scroll:
            off = -off
        excess = abs(off) - p.scroll_deadzone
        if excess <= 0:
            if self.state == CState.SCROLLING:
                self.state = CState.SCROLL_READY
                out.append(self._hud(t, force=True))
            return
        if self.state != CState.SCROLLING:
            self.state = CState.SCROLLING
        speed = min(p.scroll_max, excess * p.scroll_gain)
        dy = math.copysign(speed * min(0.1, self._dt), off)     # y ảnh tăng khi tay đi xuống → cuộn xuống
        out.append(CodeGestureEvent("scroll", t, dy=dy))
        hud = self._hud(t, label="✌ Đang cuộn " + ("↓" if dy > 0 else "↑"))
        if hud is not None:
            out.append(hud)

    def status(self) -> dict:
        return {"state": self.state.value, "label": LABELS[self.state], "stable_pose": self._stable.value,
                "speed": round(self._speed, 2), "saves": self.save_count, "runs": self.run_count, "locked": self.locked}
