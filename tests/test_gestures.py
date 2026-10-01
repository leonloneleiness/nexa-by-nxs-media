"""Kiểm thử bộ cử chỉ giữ-tư-thế: phân loại tư thế và máy trạng thái với dữ liệu tổng hợp (không camera)."""
from __future__ import annotations

import numpy as np
import pytest

from hand_synth import make_hand
from nexa.core.events import GestureEvent as E
from nexa.utils.config import GESTURE_DEFAULTS
from nexa.vision.gesture_features import Pose, classify
from nexa.vision.gesture_state_machine import GestureParams, GestureStateMachine, Observation

FPS = 30.0
SCALE = 0.12  # kích thước bàn tay (đơn vị chiều cao khung)


# ------------------------------------------------------------------ tư thế
@pytest.mark.parametrize("pose,angle,expect", [
    ("open", 0, Pose.OPEN_PALM), ("open", -40, Pose.OPEN_PALM), ("open", 35, Pose.OPEN_PALM),
    ("fist", 0, Pose.FIST), ("fist", -40, Pose.FIST), ("fist", 90, Pose.FIST),
    ("two", 0, Pose.TWO_FINGERS), ("two", -40, Pose.TWO_FINGERS), ("two", 35, Pose.TWO_FINGERS),
    ("thumb", 90, Pose.THUMB_UP), ("thumb", 70, Pose.THUMB_UP), ("thumb", 110, Pose.THUMB_UP),
    ("thumb", -90, Pose.THUMB_DOWN), ("thumb", -70, Pose.THUMB_DOWN),
    ("point", 90, Pose.POINT_RIGHT), ("point", 70, Pose.POINT_RIGHT), ("point", 110, Pose.POINT_RIGHT),
    ("point", -90, Pose.POINT_LEFT), ("point", 0, Pose.POINT_UP),
])
@pytest.mark.parametrize("size", [0.06, 0.2])
def test_pose_classification_rotation_and_scale(pose, angle, expect, size):
    rng = np.random.default_rng(1)
    f = classify(make_hand(pose, angle_deg=angle, size=size, jitter=0.002 * size / 0.12, rng=rng))
    assert f.pose == expect
    assert f.confidence >= 0.6


@pytest.mark.parametrize("pose,angle", [("thumb", 0), ("thumb", 30), ("thumb", 180), ("point", 45), ("point", 180)])
def test_diagonal_or_sideways_direction_is_unknown(pose, angle):
    """Ngón cái nằm ngang / ngón trỏ chỉ chéo hay chỉ xuống không được đoán thành lệnh."""
    assert classify(make_hand(pose, angle_deg=angle)).pose == Pose.UNKNOWN


def test_fist_and_thumb_up_are_not_confused():
    fist = classify(make_hand("fist", angle_deg=90))
    thumb = classify(make_hand("thumb", angle_deg=90))
    assert (fist.pose, thumb.pose) == (Pose.FIST, Pose.THUMB_UP)


def test_gun_shape_still_points_right():
    """Chỉ tay kiểu 'khẩu súng' (ngón cái giơ lên) vẫn là chỉ sang phải, không phải like."""
    f = classify(make_hand("point", angle_deg=90, thumb="side"))
    assert f.pose == Pose.POINT_RIGHT


def test_config_mapping_matches_state_machine():
    assert set(GESTURE_DEFAULTS["mapping"].values()) == {e.value for e in E}
    assert "swipe" not in GESTURE_DEFAULTS


# ------------------------------------------------------------------ trình mô phỏng
class Sim:
    def __init__(self, **params):
        self.snapshots = 0
        self.sm = GestureStateMachine(GestureParams(**params), on_candidate_start=self._snap)
        self.t = 100.0
        self.x, self.y = 0.6, 0.5
        self.events = []

    def _snap(self):
        self.snapshots += 1
        return {"snapshot": self.snapshots}

    def frame(self, pose: Pose | None, dx=0.0, dy=0.0, jitter=0.0, rng=None):
        self.t += 1 / FPS
        if pose is None:
            out = self.sm.update(Observation(self.t, False))
        else:
            self.x += dx
            self.y += dy
            jx = jy = 0.0
            if jitter and rng is not None:
                jx, jy = rng.normal(0, jitter, 2)
            out = self.sm.update(Observation(self.t, True, pose, 0.9, (self.x + jx, self.y + jy), SCALE))
        self.events.extend(out)
        return out

    def hold(self, pose, seconds, **kw):
        for _ in range(int(seconds * FPS)):
            self.frame(pose, **kw)

    def move(self, pose, total_dx, total_dy, seconds):
        n = max(1, int(seconds * FPS))
        for _ in range(n):
            self.frame(pose, total_dx / n, total_dy / n)

    def kinds(self):
        return [e.event for e in self.events]


def hands(n: float) -> float:
    return n * SCALE


# ------------------------------------------------------------------ lệnh cửa sổ
@pytest.mark.parametrize("pose,event", [
    (Pose.POINT_RIGHT, E.MOVE_WINDOW_TO_MONITOR_2),
    (Pose.THUMB_DOWN, E.MINIMIZE_ACTIVE_WINDOW),
    (Pose.THUMB_UP, E.RESTORE_LAST_MINIMIZED_WINDOW),
])
def test_window_pose_held_fires_once_with_snapshot(pose, event):
    s = Sim()
    s.hold(pose, 3.0)
    assert s.kinds() == [event]
    assert s.events[0].snapshot == {"snapshot": 1}


def test_short_flash_of_pose_does_nothing():
    s = Sim()
    s.hold(Pose.OPEN_PALM, 0.3)
    s.hold(Pose.THUMB_DOWN, 0.4)                     # < action_hold_ms
    s.hold(Pose.OPEN_PALM, 1.0)
    assert s.kinds() == []


def test_moving_hand_never_fires():
    """Đưa tay vào khung / vẫy tay qua lại với bất kỳ tư thế nào: không lệnh."""
    s = Sim()
    for pose in (Pose.POINT_RIGHT, Pose.THUMB_UP, Pose.THUMB_DOWN, Pose.FIST, Pose.TWO_FINGERS):
        for _ in range(3):
            s.move(pose, hands(2), 0, 0.3)
            s.move(pose, -hands(2), 0, 0.3)
    assert s.kinds() == []


def test_open_palm_moving_down_does_not_minimize():
    """Lỗi cũ: hạ bàn tay mở xuống bị hiểu là vuốt xuống → thu nhỏ."""
    s = Sim()
    s.hold(Pose.OPEN_PALM, 0.3)
    s.move(Pose.OPEN_PALM, 0, hands(3), 0.35)
    s.move(Pose.OPEN_PALM, hands(3), 0, 0.35)
    s.hold(Pose.OPEN_PALM, 1.5)
    assert s.kinds() == []


def test_unmapped_poses_do_nothing():
    s = Sim()
    s.hold(Pose.POINT_LEFT, 2.0)
    s.hold(Pose.POINT_UP, 2.0)
    s.hold(Pose.OPEN_PALM, 2.0)
    s.hold(Pose.UNKNOWN, 2.0)
    assert s.kinds() == []


def test_minimize_then_restore_in_sequence():
    s = Sim()
    s.hold(Pose.THUMB_DOWN, 1.0)
    s.hold(Pose.UNKNOWN, 0.3)
    s.hold(Pose.THUMB_UP, 1.0)
    assert s.kinds() == [E.MINIMIZE_ACTIVE_WINDOW, E.RESTORE_LAST_MINIMIZED_WINDOW]


def test_cooldown_delays_but_does_not_drop_second_command():
    s = Sim(cooldown_ms=1500)
    s.hold(Pose.THUMB_DOWN, 0.75)                    # phát ở ~0.65 s
    s.hold(Pose.THUMB_UP, 0.8)                       # vẫn trong cooldown
    assert s.kinds() == [E.MINIMIZE_ACTIVE_WINDOW]
    s.hold(Pose.THUMB_UP, 1.0)                       # hết cooldown khi vẫn giữ
    assert s.kinds() == [E.MINIMIZE_ACTIVE_WINDOW, E.RESTORE_LAST_MINIMIZED_WINDOW]


def test_repeat_requires_changing_pose():
    s = Sim()
    s.hold(Pose.POINT_RIGHT, 1.0)
    s.move(Pose.POINT_RIGHT, hands(1.5), 0, 0.3)     # dịch tay nhưng vẫn chỉ phải
    s.hold(Pose.POINT_RIGHT, 1.5)
    assert s.kinds() == [E.MOVE_WINDOW_TO_MONITOR_2]
    s.hold(Pose.UNKNOWN, 0.3)
    s.hold(Pose.POINT_RIGHT, 1.0)
    assert s.kinds() == [E.MOVE_WINDOW_TO_MONITOR_2] * 2


def test_noisy_still_hand_still_fires_once():
    rng = np.random.default_rng(3)
    s = Sim()
    s.hold(Pose.POINT_RIGHT, 3.0, jitter=0.004, rng=rng)
    assert s.kinds() == [E.MOVE_WINDOW_TO_MONITOR_2]


def test_flickering_classification_is_voted_out():
    """1/3 khung bị phân loại nhầm thành like: vẫn chỉ ra 'chỉ phải'."""
    s = Sim()
    for i in range(int(2 * FPS)):
        s.frame(Pose.THUMB_UP if i % 3 == 0 else Pose.POINT_RIGHT)
    assert s.kinds() == [E.MOVE_WINDOW_TO_MONITOR_2]


def test_lost_hand_mid_hold_cancels():
    s = Sim()
    s.hold(Pose.THUMB_DOWN, 0.4)
    s.hold(None, 0.5)
    s.hold(Pose.THUMB_DOWN, 0.4)
    assert s.kinds() == []


def test_invert_x_flips_point_direction():
    s = Sim(invert_x=True)
    s.hold(Pose.POINT_RIGHT, 1.5)
    s.hold(Pose.UNKNOWN, 0.3)
    s.hold(Pose.POINT_LEFT, 1.5)
    assert s.kinds() == [E.MOVE_WINDOW_TO_MONITOR_2]


def test_invert_y_flips_thumb_direction():
    s = Sim(invert_y=True)
    s.hold(Pose.THUMB_UP, 1.0)
    assert s.kinds() == [E.MINIMIZE_ACTIVE_WINDOW]


# ------------------------------------------------------------------ hai ngón cuộn
def test_two_fingers_hold_scrolls_repeatedly_until_released():
    s = Sim()
    s.hold(Pose.TWO_FINGERS, 2.0)
    n = len(s.events)
    assert set(s.kinds()) == {E.SCROLL_UP}
    assert 6 <= n <= 9                               # (2.0 - 0.65) / 0.18 ≈ 7.5
    assert all(e.amount == 2 for e in s.events)
    s.hold(Pose.OPEN_PALM, 1.0)
    assert len(s.events) == n


def test_two_fingers_short_flash_does_not_scroll():
    s = Sim()
    s.hold(Pose.TWO_FINGERS, 0.5)
    s.hold(Pose.UNKNOWN, 1.0)
    assert s.kinds() == []


def test_scroll_stops_when_hand_lost():
    s = Sim()
    s.hold(Pose.TWO_FINGERS, 1.0)
    n = len(s.events)
    s.hold(None, 0.5)
    assert len(s.events) == n


# ------------------------------------------------------------------ nắm tay / mở tay
def test_fist_hold_pauses_exactly_once():
    s = Sim()
    s.hold(Pose.FIST, 3.0)
    assert s.kinds() == [E.YOUTUBE_PAUSE]


def test_open_after_fist_resumes_once():
    s = Sim()
    s.hold(Pose.FIST, 0.8)
    s.hold(Pose.OPEN_PALM, 3.0)
    assert s.kinds() == [E.YOUTUBE_PAUSE, E.YOUTUBE_RESUME]


def test_open_palm_without_prior_fist_never_resumes():
    s = Sim()
    s.hold(Pose.OPEN_PALM, 3.0)
    assert s.kinds() == []


def test_repeated_fist_open_cycles_alternate_without_flapping():
    s = Sim()
    for _ in range(2):
        s.hold(Pose.FIST, 1.5)
        s.hold(Pose.OPEN_PALM, 1.5)
    assert s.kinds() == [E.YOUTUBE_PAUSE, E.YOUTUBE_RESUME, E.YOUTUBE_PAUSE, E.YOUTUBE_RESUME]


def test_moving_fist_does_not_pause():
    s = Sim()
    s.hold(Pose.FIST, 0.1)
    for _ in range(4):
        s.move(Pose.FIST, hands(1.5), 0, 0.2)
        s.move(Pose.FIST, -hands(1.5), 0, 0.2)
    assert E.YOUTUBE_PAUSE not in s.kinds()


def test_fist_then_thumb_up_restores_not_resumes():
    s = Sim()
    s.hold(Pose.FIST, 0.8)
    s.hold(Pose.THUMB_UP, 1.0)
    assert s.kinds() == [E.YOUTUBE_PAUSE, E.RESTORE_LAST_MINIMIZED_WINDOW]


def test_lost_hand_between_fist_and_open_cancels_resume():
    s = Sim()
    s.hold(Pose.FIST, 0.8)
    s.hold(None, 0.5)
    s.hold(Pose.OPEN_PALM, 1.5)
    assert s.kinds() == [E.YOUTUBE_PAUSE]


def test_reset_clears_everything():
    s = Sim()
    s.hold(Pose.FIST, 0.8)
    s.hold(Pose.OPEN_PALM, 0.1)
    s.sm.reset("dừng khẩn cấp")
    s.hold(Pose.OPEN_PALM, 1.5)
    assert s.kinds() == [E.YOUTUBE_PAUSE]


# ------------------------------------------------------------------ hiệu chuẩn
def test_calibration_right_measures_without_emitting():
    s = Sim()
    got = []

    def cb(dx, dy):                                  # giống engine: đảo trục ngay khi đo xong
        got.append((dx, dy))
        s.sm.update_params(GestureParams(invert_x=dx < 0))
    s.sm.calibration_callback = cb
    s.hold(Pose.POINT_LEFT, 3.0)                     # camera đã lật: chỉ phải nhưng ảnh thấy trái; giữ tiếp
    assert got == [(-1.0, 0.0)]
    assert s.kinds() == []                           # vừa đảo trục cũng không tự chuyển cửa sổ
    s.hold(Pose.UNKNOWN, 0.3)
    s.hold(Pose.POINT_LEFT, 1.0)                     # lần chỉ sau: đã được hiểu là chỉ phải
    assert s.kinds() == [E.MOVE_WINDOW_TO_MONITOR_2]


def test_calibration_ignores_pose_of_other_step():
    s = Sim()
    got = []

    def cb(dx, dy):
        if dx == 0:
            return False
        got.append((dx, dy))
        return True
    s.sm.calibration_callback = cb
    s.hold(Pose.THUMB_UP, 1.0)                       # sai bước: bỏ qua, vẫn chờ
    s.hold(Pose.UNKNOWN, 0.3)
    s.hold(Pose.POINT_RIGHT, 1.0)
    assert got == [(1.0, 0.0)]
    assert s.kinds() == []
