"""Nhận biết anh có đang ngồi ở máy không — máy trạng thái thuần (không camera, không Win32) để test được.

Đầu vào mỗi lần (~10 Hz, từ luồng camera): có thấy mặt chủ máy không, số mặt người khác đủ lớn (đứng gần/nhìn
màn hình), và bao lâu rồi không có phím/chuột. Có phím/chuột gần đây luôn tính là anh đang ngồi (mặt có thể bị che,
cúi xuống đọc giấy...).

    PRESENT ──vắng (away_after_s − warning_s)──► WARNING ──vắng đủ away_after_s──► AWAY
       ▲                                           │                                │
       └───────── thấy mặt / có phím chuột ────────┘ (cancel)    thấy mặt ≥ return_s │ (back)
       └────────────────────────────────────────────────────────────────────────────┘

Sự kiện: warning (còn N giây), cancel, away, back, onlooker (người thứ hai nhìn màn hình ≥ onlooker_s khi anh
đang ngồi), onlooker_gone.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PRESENT, WARNING, AWAY = "present", "warning", "away"


@dataclass
class PresenceParams:
    away_after_s: float = 45.0      # vắng liên tục bao lâu thì coi là rời máy
    warning_s: float = 10.0         # báo trước bao nhiêu giây (toast đếm ngược, cử động bất kỳ là hủy)
    return_s: float = 1.0           # thấy mặt liên tục bao lâu thì coi là đã quay lại
    recent_input_s: float = 10.0    # có phím/chuột trong khoảng này = đang ngồi
    onlooker_s: float = 1.5         # người thứ hai xuất hiện liên tục bao lâu thì cảnh báo
    onlooker_gone_s: float = 2.0
    onlooker_min_ratio: float = 0.45  # mặt người sau phải lớn ≥ tỷ lệ này so với mặt anh (xa quá thì bỏ qua)
    min_face_size: float = 0.035    # mặt nhỏ hơn (khoảng cách mắt / rộng khung) coi như người ở xa, không tính

    @classmethod
    def from_config(cls, cfg: dict[str, Any] | None) -> "PresenceParams":
        p = cls()
        for k, v in (cfg or {}).items():
            if hasattr(p, k) and isinstance(v, (int, float)) and not isinstance(v, bool):
                setattr(p, k, float(v))
        p.warning_s = max(0.0, min(p.warning_s, p.away_after_s - 1.0))
        return p


@dataclass
class PresenceEvent:
    kind: str                       # warning | cancel | away | back | onlooker | onlooker_gone
    seconds: float = 0.0            # warning: còn bao nhiêu giây; back: đã vắng bao lâu


def split_faces(sizes: list[float], params: PresenceParams) -> tuple[bool, int]:
    """sizes: kích thước các mặt, lớn nhất trước. → (thấy chủ máy, số người khác đáng kể)."""
    faces = sorted((s for s in sizes if s >= params.min_face_size), reverse=True)
    if not faces:
        return False, 0
    owner = faces[0]
    return True, sum(1 for s in faces[1:] if s >= owner * params.onlooker_min_ratio)


class PresenceMonitor:
    def __init__(self, params: PresenceParams | None = None) -> None:
        self.params = params or PresenceParams()
        self.state = PRESENT
        self._last_seen: float | None = None     # lần cuối thấy mặt hoặc có phím/chuột
        self._seen_since: float | None = None    # thấy mặt liên tục từ lúc nào (để xác nhận quay lại)
        self._away_since: float | None = None
        self._onlooker_since: float | None = None
        self._onlooker_clear_since: float | None = None
        self.onlooker_active = False
        self.faces = 0

    def reset(self, t: float) -> None:
        """Bật camera lại / vừa mở khóa: coi như anh đang ngồi."""
        self.state = PRESENT
        self._last_seen = t
        self._seen_since = None
        self._away_since = None
        self._onlooker_since = self._onlooker_clear_since = None
        self.onlooker_active = False

    def update(self, t: float, owner_seen: bool, onlookers: int = 0,
               input_idle_s: float | None = None) -> list[PresenceEvent]:
        p = self.params
        ev: list[PresenceEvent] = []
        if self._last_seen is None:
            self._last_seen = t
        self.faces = (1 if owner_seen else 0) + onlookers
        typing = input_idle_s is not None and input_idle_s < p.recent_input_s
        # Đang AWAY mà phím/chuột vừa bấm (thường là lúc anh mở khóa) — chỉ tính phím rất mới để không lẫn với
        # lần bấm cuối trước khi rời đi.
        fresh_input = input_idle_s is not None and input_idle_s < 1.5
        if owner_seen:
            self._seen_since = t if self._seen_since is None else self._seen_since
        else:
            self._seen_since = None

        if self.state == AWAY:
            if fresh_input or (self._seen_since is not None and t - self._seen_since >= p.return_s):
                away_for = t - (self._away_since or t)
                self.reset(t)
                ev.append(PresenceEvent("back", away_for))
            return ev

        if owner_seen or typing:
            self._last_seen = t
            if self.state == WARNING:
                self.state = PRESENT
                ev.append(PresenceEvent("cancel"))
        absent = t - self._last_seen
        if self.state == PRESENT and absent >= p.away_after_s - p.warning_s and p.warning_s > 0:
            self.state = WARNING
            ev.append(PresenceEvent("warning", max(0.0, p.away_after_s - absent)))
        if absent >= p.away_after_s:
            self.state = AWAY
            self._away_since = self._last_seen
            if self.onlooker_active:
                self.onlooker_active = False
                ev.append(PresenceEvent("onlooker_gone"))
            self._onlooker_since = self._onlooker_clear_since = None
            ev.append(PresenceEvent("away", absent))
            return ev

        # Người thứ hai phía sau: chỉ có ý nghĩa khi anh đang ngồi (thấy mặt anh)
        if owner_seen and onlookers > 0:
            self._onlooker_clear_since = None
            self._onlooker_since = t if self._onlooker_since is None else self._onlooker_since
            if not self.onlooker_active and t - self._onlooker_since >= p.onlooker_s:
                self.onlooker_active = True
                ev.append(PresenceEvent("onlooker", t - self._onlooker_since))
        else:
            self._onlooker_since = None
            if self.onlooker_active:
                self._onlooker_clear_since = t if self._onlooker_clear_since is None else self._onlooker_clear_since
                if t - self._onlooker_clear_since >= p.onlooker_gone_s:
                    self.onlooker_active = False
                    self._onlooker_clear_since = None
                    ev.append(PresenceEvent("onlooker_gone"))
        return ev

    def absent_for(self, t: float) -> float:
        return 0.0 if self._last_seen is None else max(0.0, t - self._last_seen)

    def status(self, t: float) -> dict[str, Any]:
        return {"presence": self.state, "absent_s": round(self.absent_for(t), 1), "faces": self.faces,
                "onlooker": self.onlooker_active}
