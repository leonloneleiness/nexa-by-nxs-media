"""Âm lượng hệ thống, thông tin CPU/RAM, thời gian và nguồn điện."""
from __future__ import annotations

import datetime as _dt
import subprocess
import threading

from nexa.core.events import ToolResult
from nexa.utils.logging import get_logger

log = get_logger("system")

WEEKDAYS_VI = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]


class VolumeControl:
    """Âm lượng loa mặc định qua Core Audio (pycaw). Mỗi luồng gọi phải khởi tạo COM."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def _endpoint(self):
        from pycaw.pycaw import AudioUtilities
        device = AudioUtilities.GetSpeakers()
        if device is None:
            raise RuntimeError("Không tìm thấy thiết bị phát âm thanh mặc định")
        return device.EndpointVolume, getattr(device, "FriendlyName", "loa")

    def get(self) -> tuple[int, bool]:
        with self._lock:
            ep, _ = self._endpoint()
            return int(round(ep.GetMasterVolumeLevelScalar() * 100)), bool(ep.GetMute())

    def set(self, percent: int) -> ToolResult:
        percent = max(0, min(100, int(percent)))
        with self._lock:
            ep, name = self._endpoint()
            ep.SetMasterVolumeLevelScalar(percent / 100.0, None)
            if percent > 0 and ep.GetMute():
                ep.SetMute(0, None)
            actual = int(round(ep.GetMasterVolumeLevelScalar() * 100))
        if abs(actual - percent) <= 1:
            return ToolResult.success(f"Đã đặt âm lượng {actual}%.", verified=True, volume=actual, device=name)
        return ToolResult.failure(f"Âm lượng hiện là {actual}%, chưa đúng {percent}%.", "not_verified", volume=actual)

    def change(self, delta: int) -> ToolResult:
        current, _ = self.get()
        return self.set(current + int(delta))

    def mute(self, on: bool) -> ToolResult:
        with self._lock:
            ep, _ = self._endpoint()
            ep.SetMute(1 if on else 0, None)
            actual = bool(ep.GetMute())
        if actual == on:
            return ToolResult.success("Đã tắt tiếng." if on else "Đã bật tiếng.", verified=True, muted=actual)
        return ToolResult.failure("Không đổi được trạng thái tắt tiếng.", "not_verified")


def now_text(part: str = "both", now: _dt.datetime | None = None) -> str:
    """Trả lời đúng phần được hỏi (câu ngắn → đọc nhanh). Viết "22 giờ 24" để giọng đọc không đọc "22:24" lạ."""
    now = now or _dt.datetime.now()
    clock = f"{now.hour} giờ {now.minute:02d}" if now.minute else f"{now.hour} giờ đúng"
    date = f"{WEEKDAYS_VI[now.weekday()]}, ngày {now.day} tháng {now.month}"
    if part == "time":
        return f"Bây giờ là {clock}."
    if part == "date":
        return f"Hôm nay là {date} năm {now.year}."
    return f"Bây giờ là {clock}, {date}."


def system_info() -> ToolResult:
    import psutil
    cpu = psutil.cpu_percent(interval=0.5)
    vm = psutil.virtual_memory()
    freq = psutil.cpu_freq()
    data = {
        "cpu_percent": cpu, "cpu_cores_logical": psutil.cpu_count(), "cpu_cores_physical": psutil.cpu_count(logical=False),
        "cpu_mhz": round(freq.current) if freq else None,
        "ram_total_gb": round(vm.total / 2**30, 1), "ram_used_gb": round(vm.used / 2**30, 1), "ram_percent": vm.percent,
    }
    try:
        battery = psutil.sensors_battery()
        if battery is not None:
            data["battery_percent"] = battery.percent
            data["plugged"] = battery.power_plugged
    except Exception:
        pass
    msg = f"CPU đang dùng {cpu:.0f}%, RAM {data['ram_used_gb']}/{data['ram_total_gb']} GB ({vm.percent:.0f}%)."
    if "battery_percent" in data:
        msg += f" Pin {data['battery_percent']:.0f}%."
    return ToolResult.success(msg, verified=True, **data)


def power_action(action: str) -> ToolResult:
    """Khóa máy / ngủ / tắt máy / khởi động lại. Tắt và khởi động lại có hẹn 60 giây để có thể hủy."""
    import ctypes
    if action == "lock":
        ok = bool(ctypes.windll.user32.LockWorkStation())
        return ToolResult.success("Đã khóa máy.", verified=ok) if ok else ToolResult.failure("Không khóa được máy.", "failed")
    if action == "shutdown":
        subprocess.run(["shutdown.exe", "/s", "/t", "60"], check=False, shell=False)
        return ToolResult.success("Máy sẽ tắt sau 60 giây. Anh nói 'hủy tắt máy' hoặc chạy shutdown /a để hủy.", verified=False)
    if action == "restart":
        subprocess.run(["shutdown.exe", "/r", "/t", "60"], check=False, shell=False)
        return ToolResult.success("Máy sẽ khởi động lại sau 60 giây.", verified=False)
    if action == "cancel_shutdown":
        r = subprocess.run(["shutdown.exe", "/a"], check=False, shell=False, capture_output=True)
        return ToolResult.success("Đã hủy lịch tắt máy.", verified=r.returncode == 0)
    if action == "sleep":
        ok = bool(ctypes.windll.powrprof.SetSuspendState(False, False, False))
        return ToolResult.success("Máy đã vào chế độ ngủ.", verified=ok)
    return ToolResult.failure("Hành động nguồn không hợp lệ.", "bad_action")


class MediaDucker:
    """Tạm vặn nhỏ âm thanh các ỨNG DỤNG KHÁC (video, nhạc…) trong lúc NEXA nghe lệnh, rồi trả lại đúng mức cũ.

    Nhạc/video phát qua loa lọt vào mic làm Whisper nghe thành câu vô nghĩa và làm VAD tưởng anh đang nói.
    Chỉ đổi âm lượng từng phiên (mixer của Windows), không đụng âm lượng loa tổng, không đụng tiếng của NEXA.
    Khi trả lại: chỉ khôi phục phiên nào vẫn đang ở mức NEXA đã đặt (nếu anh tự chỉnh trong lúc đó thì giữ nguyên).
    Chạy trên một luồng COM riêng nên gọi duck()/restore() không bao giờ chặn luồng âm thanh.
    """

    ACTIVE = 1

    def __init__(self, level: float = 0.2, exclude_pids: tuple[int, ...] = ()) -> None:
        import os
        import queue
        self.level = max(0.0, min(1.0, float(level)))
        self.exclude = {os.getpid(), 0, *exclude_pids}
        self._saved: dict[str, tuple[float, float]] = {}    # instance id -> (âm lượng gốc, âm lượng đã đặt)
        # Bộ quản lý phiên của loa mặc định: dựng lại tốn ~50 ms (pycaw đọc cả thuộc tính thiết bị) nên chỉ lấy lại
        # mỗi lượt nghe mới (anh có thể vừa đổi loa/tai nghe); các lần quét lại trong lượt dùng lại (~1 ms).
        self._mgr = None
        self._refresh_mgr = True
        self._q: "queue.Queue[str | None]" = queue.Queue()
        self._thread = threading.Thread(target=self._worker, name="nexa-ducker", daemon=True)
        self._thread.start()

    @property
    def ducked(self) -> bool:
        return bool(self._saved)

    def duck(self) -> None:
        self._q.put("duck")

    def restore(self) -> None:
        self._q.put("restore")

    def stop(self) -> None:
        """Khôi phục đồng bộ (gọi khi tắt NEXA) rồi dừng luồng."""
        self._q.put("restore")
        self._q.put(None)
        self._thread.join(timeout=2)

    RESCAN_S = 0.4

    def _worker(self) -> None:
        import queue
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass
        held = False
        while True:
            # Đang giữ vặn nhỏ: quét lại định kỳ để bắt cả ứng dụng BẮT ĐẦU phát sau lúc NEXA bắt đầu nghe
            # (video vừa mở còn đang tải/quảng cáo — trước đây lọt qua và phát to suốt lượt nghe).
            try:
                cmd = self._q.get(timeout=self.RESCAN_S) if held else self._q.get()
            except queue.Empty:
                cmd = "rescan"
            if cmd is None:
                return
            if cmd == "duck":
                held = True
                self._refresh_mgr = True
            elif cmd == "restore":
                held = False
            try:
                self._do_duck() if cmd in ("duck", "rescan") else self._do_restore()
            except Exception:
                log.exception("Lỗi %s âm lượng ứng dụng", cmd)

    def _sessions(self):
        from pycaw.pycaw import AudioUtilities, IAudioSessionControl2
        from pycaw.utils import AudioSession
        if self._refresh_mgr or self._mgr is None:
            self._mgr = AudioUtilities.GetAudioSessionManager()
            self._refresh_mgr = False
        if self._mgr is None:
            return
        enum = self._mgr.GetSessionEnumerator()
        for i in range(enum.GetCount()):
            ctl = enum.GetSession(i)
            if ctl is None:
                continue
            s = AudioSession(ctl.QueryInterface(IAudioSessionControl2))
            if s.ProcessId in self.exclude:
                continue
            key = s.InstanceIdentifier or f"pid:{s.ProcessId}"
            yield key, s

    def _do_duck(self) -> None:
        names = []
        for key, s in self._sessions():
            if key in self._saved or s.State != self.ACTIVE:
                continue
            vol = s.SimpleAudioVolume
            cur = float(vol.GetMasterVolume())
            target = round(cur * self.level, 3)
            if cur <= 0.01:
                continue
            vol.SetMasterVolume(target, None)
            self._saved[key] = (cur, target)
            names.append(s.Process.name() if s.Process else str(s.ProcessId))
        if names:
            log.info("Vặn nhỏ âm thanh khi nghe lệnh: %s", ", ".join(names))

    def _do_restore(self) -> None:
        if not self._saved:
            return
        for key, s in self._sessions():
            saved = self._saved.pop(key, None)
            if saved is None:
                continue
            orig, set_to = saved
            vol = s.SimpleAudioVolume
            if abs(float(vol.GetMasterVolume()) - set_to) < 0.02:
                vol.SetMasterVolume(orig, None)
        self._saved.clear()                                 # phiên đã đóng: bỏ qua
