"""Kiểm thử điều khiển YouTube: pause/resume xác định, gắn mục tiêu, bridge IPC và native host framing."""
from __future__ import annotations

import io
import json
import threading
import time
import uuid

import pytest

from nexa.desktop.media import MediaController, MediaTarget, Playback


class FakeBackend:
    name = "bridge"

    def __init__(self, targets):
        self.states = {t.key: Playback.PLAYING for t in targets}
        self.targets = list(targets)
        self.calls = []
        self.refuse_play = False

    def list_targets(self):
        from dataclasses import replace
        return [replace(t, playing=None if self.states.get(t.key) is None else self.states[t.key] == Playback.PLAYING)
                for t in self.targets if t.key in self.states]

    def state(self, t):
        self.calls.append(("state", t.key))
        return self.states.get(t.key, Playback.GONE), ""

    def pause(self, t):
        self.calls.append(("pause", t.key))
        if t.key in self.states:
            self.states[t.key] = Playback.PAUSED
        return self.state(t)

    def play(self, t):
        self.calls.append(("play", t.key))
        if self.refuse_play:
            return Playback.PAUSED, "NotAllowedError"
        if t.key in self.states:
            self.states[t.key] = Playback.PLAYING
        return self.state(t)


YT = MediaTarget("bridge", "Chrome:5", "abc123", "Video YouTube", "Chrome")
OTHER = MediaTarget("bridge", "Chrome:9", "zzz999", "Video khác", "Chrome")


def controller():
    b = FakeBackend([YT, OTHER])
    mc = MediaController({"bridge": b})
    mc.bind(YT)
    return mc, b


def test_pause_then_resume_same_target():
    mc, b = controller()
    r = mc.pause()
    assert r.ok and r.verified and b.states[YT.key] == Playback.PAUSED
    assert mc.can_resume()
    r = mc.resume()
    assert r.ok and b.states[YT.key] == Playback.PLAYING
    assert not mc.can_resume()
    assert b.states[OTHER.key] == Playback.PLAYING
    assert all(k == YT.key for _, k in b.calls)  # không bao giờ đụng video khác


def test_pause_when_already_paused_does_not_play():
    mc, b = controller()
    b.states[YT.key] = Playback.PAUSED
    b.states[OTHER.key] = Playback.PAUSED               # không còn video nào khác đang phát
    r = mc.pause()
    assert r.ok and r.data.get("no_op")
    assert ("play", YT.key) not in b.calls and ("pause", YT.key) not in b.calls


def test_resume_when_already_playing_does_not_pause():
    mc, b = controller()
    mc.pause()
    b.states[YT.key] = Playback.PLAYING  # người dùng tự bấm phát
    b.calls.clear()
    r = mc.resume()
    assert r.ok and r.data.get("no_op")
    assert ("pause", YT.key) not in b.calls and ("play", YT.key) not in b.calls


def test_resume_when_bound_video_is_playing_is_noop():
    mc, b = controller()
    r = mc.resume()
    assert r.ok and r.data.get("no_op")
    assert ("play", YT.key) not in b.calls


def test_pause_without_binding_picks_playing_video():
    """Không cần bấm 'Gắn tab': tạm dừng tự tìm video đang phát."""
    b = FakeBackend([YT, OTHER])
    b.states[OTHER.key] = Playback.PAUSED
    mc = MediaController({"bridge": b})
    r = mc.pause()
    assert r.ok and b.states[YT.key] == Playback.PAUSED
    assert mc.bound.identity == YT.identity and mc.can_resume()
    assert ("pause", OTHER.key) not in b.calls


def test_resume_without_binding_picks_paused_video():
    b = FakeBackend([YT, OTHER])
    b.states[YT.key] = Playback.PAUSED
    mc = MediaController({"bridge": b})
    r = mc.resume()
    assert r.ok and b.states[YT.key] == Playback.PLAYING
    assert ("play", OTHER.key) not in b.calls


def test_nothing_playing_reports_clearly():
    b = FakeBackend([YT])
    b.states[YT.key] = Playback.PAUSED
    mc = MediaController({"bridge": b})
    assert mc.pause().error_code == "no_target"          # không có gì đang phát
    empty = MediaController({"bridge": FakeBackend([])})
    assert empty.pause().error_code == "no_target"
    assert empty.resume().error_code == "no_paused_target"


def test_video_opened_by_nexa_is_preferred():
    b = FakeBackend([YT, OTHER])
    mc = MediaController({"bridge": b})
    mc.expect(OTHER.video_id, OTHER.title)
    assert mc.pause().ok
    assert b.states[OTHER.key] == Playback.PAUSED and b.states[YT.key] == Playback.PLAYING


def test_bound_but_paused_switches_to_the_playing_one():
    """Anh tự dừng video cũ và mở video khác: nắm tay phải dừng video đang phát, không báo 'đã dừng sẵn'."""
    mc, b = controller()
    b.states[YT.key] = Playback.PAUSED
    r = mc.pause()
    assert r.ok and not r.data.get("no_op") and b.states[OTHER.key] == Playback.PAUSED


def test_gsmtc_auto_pick_ignores_non_browser_apps():
    spotify = MediaTarget("gsmtc", "Spotify.exe", "", "Bài hát", "Spotify.exe", playing=True)
    edge = MediaTarget("gsmtc", "MSEdge", "", "Video YouTube", "MSEdge", playing=True)

    class G(FakeBackend):
        name = "gsmtc"

        def list_targets(self):
            return [spotify, edge]
    g = G([spotify, edge])
    mc = MediaController({"gsmtc": g})
    assert mc.pause().ok
    assert g.states["Spotify.exe"] == Playback.PLAYING and g.states["MSEdge"] == Playback.PAUSED


def test_target_gone_unbinds():
    mc, b = controller()
    del b.states[YT.key]
    del b.states[OTHER.key]
    r = mc.pause()
    assert not r.ok and r.error_code == "no_target"
    assert mc.bound is None


def test_target_gone_moves_to_other_playing_video():
    mc, b = controller()
    del b.states[YT.key]                                  # tab cũ đã đóng
    assert mc.pause().ok and b.states[OTHER.key] == Playback.PAUSED


def test_video_change_on_tab_invalidates_resume():
    mc, b = controller()
    mc.pause()
    mc.on_bridge_event({"type": "tab_update", "key": YT.key, "video_id": "khac", "paused": True})
    assert mc.bound is None and not mc.can_resume()
    del b.states[YT.key]                                  # video cũ không còn trong danh sách
    r = mc.resume()
    assert not r.ok


def test_tab_closed_invalidates():
    mc, b = controller()
    mc.on_bridge_event({"type": "tab_closed", "key": YT.key})
    assert mc.bound is None


def test_rebinding_other_target_clears_resume():
    mc, b = controller()
    mc.pause()
    mc.bind(OTHER)
    r = mc.resume()
    assert r.ok and r.data.get("no_op")                  # OTHER đang phát sẵn
    assert b.states[YT.key] == Playback.PAUSED           # không tự phát video cũ


def test_browser_refuses_play_reports_honestly():
    mc, b = controller()
    mc.pause()
    b.refuse_play = True
    r = mc.resume()
    assert not r.ok and r.error_code == "play_refused"


def test_gsmtc_other_app_session_is_not_controlled():
    """Phiên media khác (Spotify) không được điều khiển khi mục tiêu đã gắn là YouTube trên Edge."""
    from nexa.desktop.media import GsmtcBackend

    class S:
        def __init__(self, app, title, status):
            self.app, self.title, self.status = app, title, status
            self.paused = False

        def get_playback_info(self):
            return type("I", (), {"playback_status": self.status})()

    class G(GsmtcBackend):
        def __init__(self, sessions):
            self.sessions = sessions
            self.available = True

        def _find(self, target):
            for s in self.sessions:
                if s.app == target.key and s.title == target.title:
                    return s
            return None

    spotify = S("Spotify.exe", "Bài hát", 4)
    g = G([spotify])
    target = MediaTarget("gsmtc", "MSEdge", "", "Video YouTube", "MSEdge")
    assert g.state(target)[0] == Playback.GONE
    mc = MediaController({"gsmtc": g})
    mc.bind(target)
    r = mc.pause()
    assert not r.ok
    assert spotify.status == 4


# ------------------------------------------------------------------ BridgeBackend mapping
def test_bridge_backend_maps_results():
    from nexa.desktop.media import BridgeBackend

    class Srv:
        def __init__(self):
            self.resp = {}

        def tabs(self):
            return []

        def command(self, key, vid, action):
            return self.resp

    s = Srv()
    b = BridgeBackend(s)
    s.resp = {"ok": True, "state": {"videoId": "abc123", "paused": True}}
    assert b.pause(YT)[0] == Playback.PAUSED
    s.resp = {"ok": False, "error": "video_changed"}
    assert b.play(YT)[0] == Playback.GONE
    s.resp = {"ok": False, "error": "NotAllowedError", "state": {"paused": True}}
    assert b.play(YT) == (Playback.PAUSED, "NotAllowedError")
    s.resp = {"ok": True, "state": {"videoId": "other", "paused": False}}
    assert b.state(YT)[0] == Playback.GONE


# ------------------------------------------------------------------ IPC thật qua named pipe
@pytest.fixture
def bridge(monkeypatch, tmp_path):
    from nexa.desktop import bridge_server as bs
    name = rf"\\.\pipe\nexa-test-{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(bs, "pipe_name", lambda: name)
    monkeypatch.setattr(bs, "key_path", lambda: tmp_path / "bridge.key")
    events = []
    srv = bs.BridgeServer(on_event=events.append)
    assert srv.start()
    yield srv, name, bs.load_or_create_key(tmp_path / "bridge.key"), events
    srv.stop()


def test_bridge_roundtrip_over_named_pipe(bridge):
    from multiprocessing.connection import Client
    srv, name, key, events = bridge
    conn = Client(name, family="AF_PIPE", authkey=key)

    def fake_extension():
        conn.send_bytes(json.dumps({"type": "hello", "browser": "Edge", "version": "1.0.0"}).encode())
        while True:
            msg = json.loads(conn.recv_bytes().decode())
            if msg["type"] == "list":
                conn.send_bytes(json.dumps({"type": "tabs", "reqId": msg["reqId"], "tabs": [
                    {"tabId": 7, "videoId": "abc123", "title": "Bài giảng", "paused": False}]}).encode())
            elif msg["type"] == "command":
                ok = msg["videoId"] == "abc123"
                conn.send_bytes(json.dumps({"type": "result", "reqId": msg["reqId"], "ok": ok,
                                            "error": "" if ok else "video_changed",
                                            "state": {"videoId": "abc123", "paused": msg["action"] == "pause"}}).encode())
                if msg["action"] == "play":
                    return

    t = threading.Thread(target=fake_extension, daemon=True)
    t.start()
    for _ in range(50):
        if srv.tabs():
            break
        time.sleep(0.05)
    tabs = srv.tabs()
    assert tabs and tabs[0].key == "Edge:7" and tabs[0].video_id == "abc123"
    r = srv.command("Edge:7", "abc123", "pause")
    assert r["ok"] and r["state"]["paused"] is True
    r = srv.command("Edge:7", "abc123", "play")
    assert r["ok"] and r["state"]["paused"] is False
    t.join(2)
    conn.close()


def test_bridge_rejects_wrong_key(bridge):
    from multiprocessing import AuthenticationError
    from multiprocessing.connection import Client
    srv, name, key, events = bridge
    with pytest.raises((AuthenticationError, EOFError, OSError)):
        Client(name, family="AF_PIPE", authkey=b"x" * 32)
    assert not srv.connected


def test_native_host_framing_roundtrip():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("native_host", Path(__file__).resolve().parents[1] / "browser_bridge" / "native_host.py")
    nh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nh)
    frame = nh.encode_message({"type": "hello", "browser": "Chrome", "text": "Tiếng Việt"})
    assert nh.read_message(io.BytesIO(frame)) == {"type": "hello", "browser": "Chrome", "text": "Tiếng Việt"}
    assert nh.main(["native_host.py", "chrome-extension://khac/"]) == 1  # origin lạ bị từ chối
