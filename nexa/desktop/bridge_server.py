"""Máy chủ IPC cục bộ cho NEXA Browser Bridge.

Luồng: extension (Chrome/Edge) ⇄ Native Messaging host (browser_bridge/native_host.py, do trình
duyệt khởi chạy) ⇄ named pipe \\\\.\\pipe\\nexa-bridge-<user> ⇄ BridgeServer trong NEXA.

Bảo mật:
- Không mở cổng TCP. Named pipe dùng xác thực challenge-response HMAC (multiprocessing.connection)
  với khóa ngẫu nhiên 32 byte lưu trong %LOCALAPPDATA%\\NEXA\\bridge.key (chỉ tài khoản người dùng đọc được).
- Chỉ trao đổi JSON qua send_bytes/recv_bytes — không dùng pickle.
- Native host tự kiểm tra origin extension; manifest Native Messaging chỉ cho phép đúng ID extension.
"""
from __future__ import annotations

import getpass
import json
import os
import re
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from nexa.utils.logging import get_logger

log = get_logger("bridge")

MAX_MESSAGE = 1024 * 1024


def pipe_name() -> str:
    user = re.sub(r"[^A-Za-z0-9_.-]", "_", getpass.getuser() or "user")
    return rf"\\.\pipe\nexa-bridge-{user}"


def key_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "NEXA"
    return base / "bridge.key"


def load_or_create_key(path: Path | None = None) -> bytes:
    path = path or key_path()
    if path.exists():
        data = path.read_text(encoding="ascii").strip()
        if re.fullmatch(r"[0-9a-f]{64}", data):
            return bytes.fromhex(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    path.write_text(key.hex(), encoding="ascii")
    return key


@dataclass
class TabInfo:
    browser: str
    tab_id: int
    video_id: str
    title: str
    paused: bool | None
    url: str
    updated: float = field(default_factory=time.time)

    @property
    def key(self) -> str:
        return f"{self.browser}:{self.tab_id}"

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "browser": self.browser, "tab_id": self.tab_id, "video_id": self.video_id,
                "title": self.title, "paused": self.paused, "url": self.url}


class _Peer:
    def __init__(self, conn, peer_id: str) -> None:
        self.conn = conn
        self.id = peer_id
        self.browser = "Trình duyệt"
        self.lock = threading.Lock()
        self.alive = True

    def send(self, msg: dict) -> None:
        data = json.dumps(msg, ensure_ascii=False).encode("utf-8")
        with self.lock:
            self.conn.send_bytes(data)


class BridgeServer:
    def __init__(self, on_event: Callable[[dict], None] | None = None) -> None:
        self.on_event = on_event
        self._address = pipe_name()
        self._key: bytes | None = None
        self._listener = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._peers: dict[str, _Peer] = {}
        self._tabs: dict[str, TabInfo] = {}
        self._pending: dict[str, tuple[threading.Event, dict]] = {}
        self._lock = threading.RLock()
        self.error = ""

    # ----- vòng đời -----
    def start(self) -> bool:
        from multiprocessing.connection import Listener
        try:
            self._key = load_or_create_key()
            self._listener = Listener(self._address, family="AF_PIPE", authkey=self._key)
        except Exception as exc:
            self.error = f"Không mở được kênh bridge: {exc}"
            log.warning(self.error)
            return False
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, name="nexa-bridge", daemon=True)
        self._thread.start()
        log.info("Bridge server đang chờ tại %s", self._address)
        return True

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        with self._lock:
            peers = list(self._peers.values())
        for p in peers:
            try:
                p.conn.close()
            except Exception:
                pass
        # Mở một kết nối giả để giải phóng accept() đang chặn.
        try:
            from multiprocessing.connection import Client
            Client(self._address, family="AF_PIPE", authkey=self._key).close()
        except Exception:
            pass
        try:
            self._listener.close()
        except Exception:
            pass

    @property
    def connected(self) -> bool:
        with self._lock:
            return any(p.alive for p in self._peers.values())

    def browsers(self) -> list[str]:
        with self._lock:
            return [p.browser for p in self._peers.values() if p.alive]

    # ----- nhận kết nối -----
    def _accept_loop(self) -> None:
        from multiprocessing import AuthenticationError
        while self._running:
            try:
                conn = self._listener.accept()
            except AuthenticationError:
                log.warning("Từ chối kết nối bridge không xác thực")
                continue
            except OSError:
                if self._running:
                    log.exception("Lỗi accept bridge")
                    time.sleep(0.5)
                continue
            if not self._running:
                conn.close()
                break
            peer = _Peer(conn, uuid.uuid4().hex[:8])
            with self._lock:
                self._peers[peer.id] = peer
            threading.Thread(target=self._reader, args=(peer,), name=f"nexa-bridge-{peer.id}", daemon=True).start()

    def _reader(self, peer: _Peer) -> None:
        try:
            while self._running:
                raw = peer.conn.recv_bytes(MAX_MESSAGE)
                try:
                    msg = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    log.warning("Bỏ qua gói bridge không phải JSON")
                    continue
                if isinstance(msg, dict):
                    self._handle(peer, msg)
        except (EOFError, OSError):
            pass
        finally:
            peer.alive = False
            with self._lock:
                self._peers.pop(peer.id, None)
                gone = [k for k, t in self._tabs.items() if t.browser == peer.browser]
                if not any(p.browser == peer.browser for p in self._peers.values()):
                    for k in gone:
                        self._tabs.pop(k, None)
            log.info("Bridge %s ngắt kết nối", peer.browser)
            self._emit({"type": "disconnected", "browser": peer.browser, "keys": gone})

    def _handle(self, peer: _Peer, msg: dict) -> None:
        mtype = msg.get("type")
        if mtype == "hello":
            peer.browser = str(msg.get("browser") or "Trình duyệt")[:40]
            log.info("Bridge kết nối: %s (extension %s)", peer.browser, msg.get("version"))
            self._emit({"type": "connected", "browser": peer.browser})
            try:
                peer.send({"type": "list", "reqId": uuid.uuid4().hex})
            except OSError:
                pass
        elif mtype == "tabs":
            with self._lock:
                for k in [k for k, t in self._tabs.items() if t.browser == peer.browser]:
                    self._tabs.pop(k, None)
                for tab in msg.get("tabs") or []:
                    info = self._tab_from(peer.browser, tab)
                    if info:
                        self._tabs[info.key] = info
            self._emit({"type": "tabs"})
            self._complete(msg)
        elif mtype == "tab_update":
            info = self._tab_from(peer.browser, msg.get("tab") or {})
            if info:
                with self._lock:
                    old = self._tabs.get(info.key)
                    self._tabs[info.key] = info
                self._emit({"type": "tab_update", "key": info.key, "video_id": info.video_id,
                            "previous_video_id": old.video_id if old else None, "paused": info.paused})
        elif mtype == "tab_closed":
            key = f"{peer.browser}:{msg.get('tabId')}"
            with self._lock:
                self._tabs.pop(key, None)
            self._emit({"type": "tab_closed", "key": key})
        elif mtype == "bind":
            info = self._tab_from(peer.browser, msg.get("tab") or {})
            if info:
                with self._lock:
                    self._tabs[info.key] = info
                self._emit({"type": "bind", "key": info.key, "video_id": info.video_id, "title": info.title})
        elif mtype == "result":
            self._complete(msg)

    @staticmethod
    def _tab_from(browser: str, tab: dict) -> TabInfo | None:
        try:
            tab_id = int(tab.get("tabId"))
        except (TypeError, ValueError):
            return None
        return TabInfo(browser=browser, tab_id=tab_id, video_id=str(tab.get("videoId") or "")[:32],
                       title=str(tab.get("title") or "")[:200], paused=tab.get("paused"),
                       url=str(tab.get("url") or "")[:300])

    def _complete(self, msg: dict) -> None:
        req = msg.get("reqId")
        if not req:
            return
        with self._lock:
            entry = self._pending.get(req)
        if entry:
            event, box = entry
            box.update(msg)
            event.set()

    def _emit(self, ev: dict) -> None:
        if self.on_event:
            try:
                self.on_event(ev)
            except Exception:
                log.exception("Listener bridge lỗi")

    # ----- API cho MediaController -----
    def tabs(self) -> list[TabInfo]:
        with self._lock:
            return list(self._tabs.values())

    def tab(self, key: str) -> TabInfo | None:
        with self._lock:
            return self._tabs.get(key)

    def request(self, browser: str, msg: dict, timeout: float = 3.0) -> dict:
        with self._lock:
            peer = next((p for p in self._peers.values() if p.browser == browser and p.alive), None)
        if peer is None:
            return {"ok": False, "error": "not_connected"}
        req = uuid.uuid4().hex
        msg = dict(msg, reqId=req)
        event, box = threading.Event(), {}
        with self._lock:
            self._pending[req] = (event, box)
        try:
            peer.send(msg)
            if not event.wait(timeout):
                return {"ok": False, "error": "timeout"}
            return box
        except OSError as exc:
            return {"ok": False, "error": f"io:{exc}"}
        finally:
            with self._lock:
                self._pending.pop(req, None)

    def command(self, key: str, video_id: str, action: str, timeout: float = 3.0) -> dict:
        info = self.tab(key)
        if info is None:
            return {"ok": False, "error": "tab_gone"}
        return self.request(info.browser, {"type": "command", "tabId": info.tab_id, "videoId": video_id,
                                           "action": action}, timeout)

    def refresh(self) -> None:
        for browser in self.browsers():
            self.request(browser, {"type": "list"}, timeout=2.0)
