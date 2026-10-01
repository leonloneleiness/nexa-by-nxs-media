"""Read-only device information; invoked off the GUI thread, with no cloud requests."""
from __future__ import annotations

import ctypes as C
import os
import sys
from importlib import metadata


def wifi_status() -> dict:
    """Native WLAN API: distinguish an unavailable reading from disconnected Wi-Fi."""
    unknown = {"available": False, "connected": False, "signal": None, "ssid": ""}
    if sys.platform != "win32":
        return unknown
    from ctypes import wintypes as W

    class Interface(C.Structure):
        _fields_ = [("guid", C.c_ubyte * 16), ("description", W.WCHAR * 256), ("state", W.DWORD)]

    class SSID(C.Structure):
        _fields_ = [("length", W.DWORD), ("data", C.c_ubyte * 32)]

    class Association(C.Structure):
        _fields_ = [("ssid", SSID), ("bss_type", W.DWORD), ("bssid", C.c_ubyte * 6),
                    ("phy_type", W.DWORD), ("phy_index", W.DWORD), ("signal", W.DWORD),
                    ("rx_rate", W.DWORD), ("tx_rate", W.DWORD)]

    class Connection(C.Structure):
        _fields_ = [("state", W.DWORD), ("mode", W.DWORD), ("profile", W.WCHAR * 256),
                    ("association", Association)]

    handle, listing = W.HANDLE(), C.c_void_p()
    try:
        api = C.WinDLL("wlanapi.dll")
        api.WlanOpenHandle.argtypes = [W.DWORD, C.c_void_p, C.POINTER(W.DWORD), C.POINTER(W.HANDLE)]
        api.WlanEnumInterfaces.argtypes = [W.HANDLE, C.c_void_p, C.POINTER(C.c_void_p)]
        api.WlanQueryInterface.argtypes = [W.HANDLE, C.c_void_p, W.DWORD, C.c_void_p,
                                          C.POINTER(W.DWORD), C.POINTER(C.c_void_p), C.POINTER(W.DWORD)]
        api.WlanFreeMemory.argtypes = [C.c_void_p]
        api.WlanCloseHandle.argtypes = [W.HANDLE, C.c_void_p]
        version = W.DWORD()
        if api.WlanOpenHandle(2, None, C.byref(version), C.byref(handle)) != 0:
            return unknown
        if api.WlanEnumInterfaces(handle, None, C.byref(listing)) != 0 or not listing.value:
            return unknown
        count = W.DWORD.from_address(listing.value).value
        for i in range(count):
            interface = Interface.from_address(listing.value + 8 + i * C.sizeof(Interface))
            if interface.state != 1:  # wlan_interface_state_connected
                continue
            data, size, opcode_type = C.c_void_p(), W.DWORD(), W.DWORD()
            try:
                # wlan_intf_opcode_current_connection = 7
                result = api.WlanQueryInterface(handle, C.byref(interface), 7, None,
                                                C.byref(size), C.byref(data), C.byref(opcode_type))
                if result or not data.value or size.value < C.sizeof(Connection):
                    return {**unknown, "connected": True}
                association = Connection.from_address(data.value).association
                ssid = bytes(association.ssid.data[:min(32, association.ssid.length)]).decode("utf-8", "replace")
                return {"available": True, "connected": True, "signal": min(100, association.signal), "ssid": ssid}
            finally:
                if data.value:
                    api.WlanFreeMemory(data)
        return {**unknown, "available": True}
    except (OSError, AttributeError, ValueError):
        return unknown
    finally:
        if listing.value:
            api.WlanFreeMemory(listing)
        if handle.value:
            api.WlanCloseHandle(handle, None)


def sample_device(psutil) -> dict:
    """Slow/optional probes fail independently; missing batteries never become 0%."""
    result = {"disk": None, "disk_free_gb": None, "disk_total_gb": None,
              "disk_path": os.path.abspath(os.sep), "battery": None, "charging": None,
              "wifi": {"available": False, "connected": False, "signal": None, "ssid": ""}}
    try:
        disk = psutil.disk_usage(result["disk_path"])
        result.update(disk=disk.percent, disk_free_gb=round(disk.free / 2**30, 1),
                      disk_total_gb=round(disk.total / 2**30, 1))
    except (OSError, AttributeError):
        pass
    try:
        battery = psutil.sensors_battery()
        if battery is not None:
            result.update(battery=battery.percent, charging=battery.power_plugged)
    except (OSError, AttributeError, NotImplementedError):
        pass
    result["wifi"] = wifi_status()
    return result


def library_inventory() -> list[dict]:
    """Installed versions, not a claim that every package is currently running."""
    packages = [
        ("PySide6", "Qt Quick / giao diện & 3D"), ("google-genai", "Gemini SDK / trí tuệ AI"),
        ("faster-whisper", "Nhận dạng giọng nói cục bộ"), ("ctranslate2", "Suy luận CPU / GPU"),
        ("edge-tts", "Tổng hợp giọng nói"), ("mediapipe", "Nhận diện bàn tay & cử chỉ"),
        ("opencv-contrib-python", "Xử lý hình ảnh & camera"), ("numpy", "Tính toán số"),
        ("scipy", "Xử lý tín hiệu"), ("sounddevice", "Thu / phát âm thanh"),
        ("miniaudio", "Giải mã âm thanh"), ("pywin32", "Tích hợp Windows"),
        ("pywinauto", "Tự động hóa ứng dụng"), ("pyautogui", "Chuột & bàn phím"),
        ("pycaw", "Điều khiển âm lượng"), ("psutil", "Thông số hệ thống"),
        ("mss", "Chụp màn hình"), ("Pillow", "Xử lý ảnh"),
        ("manifold3d", "Hình học 3D / CSG"), ("fast-simplification", "Tối ưu lưới 3D"),
        ("gradio_client", "Kết nối Hugging Face Spaces"), ("Pygments", "Tô màu mã nguồn"),
        ("pyflakes", "Kiểm tra Python"), ("PyYAML", "Cấu hình YAML"),
        ("python-dotenv", "Cấu hình môi trường"), ("Send2Trash", "Thùng rác an toàn"),
        ("comtypes", "Windows COM"), ("winrt-runtime", "Windows Runtime"),
        ("nvidia-cublas-cu12", "Tăng tốc CUDA / cuBLAS"),
        ("winrt-Windows.Foundation", "Windows Foundation"),
        ("winrt-Windows.Foundation.Collections", "Windows Collections"),
        ("winrt-Windows.Media.Control", "Điều khiển phát nhạc Windows"),
        ("winrt-Windows.Media.SpeechSynthesis", "Giọng nói Windows cục bộ"),
        ("winrt-Windows.Storage.Streams", "Luồng dữ liệu Windows"),
    ]
    rows = []
    for name, purpose in packages:
        try:
            version = metadata.version(name)
        except metadata.PackageNotFoundError:
            version = ""
        rows.append({"name": name, "purpose": purpose, "version": version, "installed": bool(version)})
    return rows
