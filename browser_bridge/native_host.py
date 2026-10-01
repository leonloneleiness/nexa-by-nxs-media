"""Native Messaging host của NEXA Bridge.

Trình duyệt khởi chạy tệp này (qua native_host.bat) khi extension gọi connectNative.
- Kiểm tra origin do trình duyệt truyền vào (đối số đầu tiên) đúng ID extension NEXA Bridge.
- Chuyển tiếp JSON giữa stdin/stdout (khung: 4 byte độ dài theo byte order của máy + UTF-8 JSON)
  và named pipe cục bộ của NEXA (xác thực HMAC bằng khóa trong %LOCALAPPDATA%\\NEXA\\bridge.key).
- Không mở cổng mạng, không thực thi lệnh nào — chỉ chuyển tiếp.
"""
from __future__ import annotations

import json
import os
import struct
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nexa.desktop.bridge_server import load_or_create_key, pipe_name  # noqa: E402

EXTENSION_ID = "ghkmpnijfoceebnoolnbhedljpelgnhp"
ALLOWED_ORIGINS = {f"chrome-extension://{EXTENSION_ID}/"}
MAX_FROM_BROWSER = 64 * 1024 * 1024
MAX_TO_BROWSER = 1024 * 1024

_stdout_lock = threading.Lock()


def encode_message(obj: dict) -> bytes:
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    return struct.pack("=I", len(data)) + data


def read_message(stream) -> dict | None:
    header = stream.read(4)
    if len(header) < 4:
        return None
    (length,) = struct.unpack("=I", header)
    if length > MAX_FROM_BROWSER:
        raise ValueError("message too large")
    data = stream.read(length)
    if len(data) < length:
        return None
    obj = json.loads(data.decode("utf-8"))
    return obj if isinstance(obj, dict) else {}


def write_message(obj: dict) -> None:
    frame = encode_message(obj)
    if len(frame) - 4 > MAX_TO_BROWSER:
        return
    with _stdout_lock:
        sys.stdout.buffer.write(frame)
        sys.stdout.buffer.flush()


def log(msg: str) -> None:
    # stderr được trình duyệt ghi vào log của nó; stdout chỉ dành cho giao thức.
    sys.stderr.write(f"[nexa-bridge] {msg}\n")
    sys.stderr.flush()


class Relay:
    def __init__(self) -> None:
        self.conn = None
        self.lock = threading.Lock()
        self.hello: dict | None = None
        self.running = True

    def send_to_nexa(self, msg: dict) -> None:
        with self.lock:
            conn = self.conn
        if conn is None:
            return
        try:
            conn.send_bytes(json.dumps(msg, ensure_ascii=False).encode("utf-8"))
        except OSError:
            self._drop()

    def _drop(self) -> None:
        with self.lock:
            conn, self.conn = self.conn, None
        if conn is not None:
            try:
                conn.close()
            except OSError:
                pass
            write_message({"type": "nexa_status", "connected": False})

    def pipe_loop(self) -> None:
        from multiprocessing.connection import Client
        address = pipe_name()
        while self.running:
            try:
                conn = Client(address, family="AF_PIPE", authkey=load_or_create_key())
            except (OSError, EOFError, Exception):
                time.sleep(3)
                continue
            with self.lock:
                self.conn = conn
            write_message({"type": "nexa_status", "connected": True})
            if self.hello:
                self.send_to_nexa(self.hello)
            try:
                while self.running:
                    raw = conn.recv_bytes(MAX_TO_BROWSER)
                    msg = json.loads(raw.decode("utf-8"))
                    if isinstance(msg, dict):
                        write_message(msg)
            except (EOFError, OSError, ValueError):
                pass
            self._drop()
            time.sleep(1)


def main(argv: list[str]) -> int:
    origin = argv[1] if len(argv) > 1 else ""
    if origin not in ALLOWED_ORIGINS:
        log(f"Từ chối origin không hợp lệ: {origin!r}")
        return 1
    if os.name == "nt":
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    relay = Relay()
    threading.Thread(target=relay.pipe_loop, daemon=True).start()
    while True:
        try:
            msg = read_message(sys.stdin.buffer)
        except (ValueError, json.JSONDecodeError):
            log("Gói tin hỏng, thoát")
            break
        if msg is None:
            break  # trình duyệt đóng kết nối
        if msg.get("type") == "hello":
            relay.hello = msg
        relay.send_to_nexa(msg)
    relay.running = False
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
