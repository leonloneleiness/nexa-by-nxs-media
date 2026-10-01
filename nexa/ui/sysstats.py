"""Thông số máy cho vòng HUD quanh quả cầu: CPU, RAM, GPU (NVIDIA qua NVML), độ trễ AI.

NVML nạp bằng ctypes từ nvml.dll của driver (không cần gói pynvml, không chạy nvidia-smi).
Máy không có GPU NVIDIA → gpu = None, giao diện hiện "—". Mọi hàm đều nhanh (< 1 ms) nên gọi được
từ luồng GUI theo QTimer.
"""
from __future__ import annotations

import ctypes
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from nexa.utils.logging import get_logger

log = get_logger("sysstats")


class _Util(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


class _Mem(ctypes.Structure):
    _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong), ("used", ctypes.c_ulonglong)]


class Nvml:
    """GPU NVIDIA đầu tiên; ok=False nếu không có driver / không có GPU."""

    def __init__(self) -> None:
        self.ok = False
        self._lib = None
        self._dev = ctypes.c_void_p()
        if sys.platform != "win32":
            return
        try:
            lib = ctypes.WinDLL("nvml.dll")
            if lib.nvmlInit_v2() != 0:
                return
            if lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(self._dev)) != 0:
                lib.nvmlShutdown()
                return
            self._lib, self.ok = lib, True
        except (OSError, AttributeError):
            log.debug("Không nạp được NVML", exc_info=True)

    def sample(self) -> tuple[float, float] | None:
        """(% dùng GPU, % VRAM) hoặc None."""
        if not self.ok:
            return None
        u, m = _Util(), _Mem()
        if self._lib.nvmlDeviceGetUtilizationRates(self._dev, ctypes.byref(u)) != 0:
            return None
        vram = 0.0
        if self._lib.nvmlDeviceGetMemoryInfo(self._dev, ctypes.byref(m)) == 0 and m.total:
            vram = 100.0 * m.used / m.total
        return float(u.gpu), vram

    def close(self) -> None:
        if self.ok:
            self.ok = False
            try:
                self._lib.nvmlShutdown()
            except Exception:
                pass


class SysStats:
    def __init__(self, nvml: Nvml | None = None) -> None:
        import psutil
        self._psutil = psutil
        psutil.cpu_percent(interval=None)          # lần đầu luôn trả 0: "mồi" để lần sau có số thật
        self._nvml = nvml if nvml is not None else Nvml()
        self._device_pool = None
        self._device_future = None
        self._device_values = {}
        self._device_at = 0.0

    def device_sample(self) -> dict:
        """Return cached optional probes; disk/WLAN never block QML animation."""
        if self._device_future is not None and self._device_future.done():
            try:
                self._device_values = self._device_future.result()
            except Exception:
                log.debug("Không đọc được thông số thiết bị", exc_info=True)
            self._device_future = None
        if self._device_future is None and time.monotonic() - self._device_at >= 5:
            from nexa.ui.device_telemetry import sample_device
            if self._device_pool is None:
                self._device_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nexa-device-stats")
            self._device_at = time.monotonic()
            self._device_future = self._device_pool.submit(sample_device, self._psutil)
        return dict(self._device_values)

    def sample(self, ai_ms: float = 0.0) -> dict[str, Any]:
        g = self._nvml.sample()
        return {
            "cpu": float(self._psutil.cpu_percent(interval=None)),
            "ram": float(self._psutil.virtual_memory().percent),
            "gpu": None if g is None else g[0],
            "vram": None if g is None else g[1],
            "ai_ms": float(ai_ms or 0.0),
        }

    def close(self) -> None:
        self._nvml.close()
        if self._device_pool is not None:
            self._device_pool.shutdown(wait=False, cancel_futures=True)
