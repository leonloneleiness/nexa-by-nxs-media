"""Chẩn đoán môi trường NEXA: Python, thư viện, mic, camera, màn hình, media, giọng nói, bridge, Gemini.

  python scripts/diagnose.py             # kiểm tra đầy đủ (mở mic 3 giây và camera ~1 giây, không lưu dữ liệu)
  python scripts/diagnose.py --quick     # bỏ qua mic/camera
  python scripts/diagnose.py --gemini    # thêm yêu cầu văn bản ngắn tới Gemini (dùng key trong .env)

Không in API key, không lưu âm thanh/hình ảnh.
"""
from __future__ import annotations

import argparse
import importlib
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import warnings  # noqa: E402

warnings.filterwarnings("ignore", message="Revert to STA COM threading mode")
from nexa.desktop.win32api import set_dpi_awareness  # noqa: E402

DPI_MODE = set_dpi_awareness()  # như main.py: đặt trước khi nạp thư viện khác
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

OK, BAD, WARN = "✓", "✗", "!"
problems: list[str] = []


def line(mark: str, text: str) -> None:
    print(f"  {mark} {text}")
    if mark == BAD:
        problems.append(text)


def section(title: str) -> None:
    print(f"\n== {title} ==")


def check_python() -> None:
    section("Hệ thống")
    line(OK if sys.platform == "win32" else BAD, f"Hệ điều hành: {platform.platform()}")
    bits = 64 if sys.maxsize > 2**32 else 32
    line(OK if sys.version_info[:2] == (3, 11) and bits == 64 else WARN,
         f"Python {sys.version.split()[0]} {bits}-bit (khuyến nghị 3.11 64-bit)")
    line(OK if ".venv" in sys.prefix else WARN, f"Môi trường: {sys.prefix}")


def check_packages() -> None:
    section("Thư viện")
    mods = [("PySide6", "PySide6"), ("numpy", "numpy"), ("scipy", "scipy"), ("sounddevice", "sounddevice"),
            ("faster_whisper", "faster-whisper"), ("mediapipe", "mediapipe"), ("cv2", "opencv"),
            ("google.genai", "google-genai"), ("edge_tts", "edge-tts"), ("miniaudio", "miniaudio"),
            ("pywinauto", "pywinauto"), ("pyautogui", "pyautogui"), ("pycaw", "pycaw"), ("mss", "mss"),
            ("send2trash", "Send2Trash"), ("winrt.windows.media.control", "winrt Media.Control"),
            ("winrt.windows.media.speechsynthesis", "winrt SpeechSynthesis")]
    for mod, label in mods:
        try:
            m = importlib.import_module(mod)
            ver = getattr(m, "__version__", "")
            line(OK, f"{label} {ver}")
        except Exception as exc:
            line(BAD, f"{label}: {exc}")


def check_models() -> None:
    section("Model")
    from nexa.utils.config import MODELS_DIR, Config
    hand = MODELS_DIR / "hand_landmarker.task"
    line(OK if hand.exists() else BAD, f"MediaPipe hand_landmarker.task: {'có' if hand.exists() else 'chưa có — chạy scripts/download_models.py --hands'}")
    from nexa.audio.stt import AUTO_CPU_MODEL, AUTO_GPU_MODEL
    name = Config().get("stt.model") or "small"
    # "auto" = large-v3-turbo (GPU) hoặc small (CPU); large-v3-turbo nằm ở repo mobiuslabsgmbh, không phải Systran.
    for model in ([AUTO_GPU_MODEL, AUTO_CPU_MODEL] if name == "auto" else [name]):
        cached = list((MODELS_DIR / "whisper").glob(f"models--*--faster-whisper-{model}"))
        line(OK if cached else WARN, f"faster-whisper '{model}'{' (auto)' if name == 'auto' else ''}: "
                                     f"{'đã cache' if cached else 'chưa tải — sẽ tải ở lần chạy đầu'}")


def check_mic() -> None:
    section("Mic (thử 3 giây — hãy vỗ tay một lần)")
    import numpy as np
    import sounddevice as sd
    from nexa.audio.clap_detector import ClapConfig, ClapDetector
    from nexa.audio.pipeline import AudioPipeline, resample, to_mono
    from nexa.utils.config import Config
    cfg = Config()
    try:
        devices = AudioPipeline.list_input_devices(cfg.get("audio.preferred_hostapi") or "MME")
        line(OK, f"{len(devices)} mic: " + "; ".join(d["name"] for d in devices[:6]))
        pipe = AudioPipeline(cfg)
        dev = AudioPipeline.find_device(cfg.get("audio.input_device"), "input", cfg.get("audio.preferred_hostapi") or "MME")
        sr, ch = pipe._choose_format(dev)
        line(OK, f"Định dạng dùng được: {sr} Hz, {ch} kênh")
        rec = sd.rec(int(sr * 3.5), samplerate=sr, channels=ch, dtype="float32", device=dev)
        sd.wait()
        x = resample(to_mono(rec), sr)
        det = ClapDetector(ClapConfig.from_dict(cfg.get("audio.clap")))
        det.cfg.calibration_seconds = 0.5
        events = det.process(x, 0.0)
        st = det.stats()
        level = 20 * np.log10(np.sqrt(np.mean(x * x)) + 1e-12)
        line(OK, f"Mức trung bình {level:.1f} dBFS · nền ồn {st['floor_db']} dBFS · ngưỡng vỗ tay {st['threshold_db']} dBFS")
        line(OK if events else WARN, f"Phát hiện {len(events)} tiếng vỗ tay" + ("" if events else " (nếu anh đã vỗ, tăng độ nhạy trong Cài đặt)"))
    except Exception as exc:
        line(BAD, f"Mic lỗi: {exc}")


def check_camera() -> None:
    section("Camera (mở ~1 giây, không lưu hình)")
    try:
        import cv2
        from nexa.utils.config import Config
        idx = int(Config().get("gestures.camera_index") or 0)
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if not cap.isOpened():
            line(BAD, f"Không mở được camera {idx} (bị ứng dụng khác dùng hoặc quyền camera bị tắt trong Windows Privacy)")
            return
        t, n = time.monotonic(), 0
        while time.monotonic() - t < 1.0:
            ok, _ = cap.read()
            n += int(ok)
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        line(OK if n else BAD, f"Camera {idx}: {w}×{h}, đọc được {n} khung/giây")
    except Exception as exc:
        line(BAD, f"Camera lỗi: {exc}")


def check_monitors() -> None:
    section("Màn hình")
    from nexa.desktop.monitors import MonitorManager
    from nexa.desktop.win32api import Win32Api
    line(OK if DPI_MODE == "per-monitor-v2" else WARN, f"DPI awareness: {DPI_MODE}")
    from nexa.utils.config import Config
    mm = MonitorManager(Win32Api(), Config())
    mons = mm.describe()
    for m in mons:
        line(OK, f"{m['device_name']} · {m['friendly_name']} · {m['width']}×{m['height']} tại ({m['x']},{m['y']}) · "
                 f"{m['scale']}% · {'chính' if m['primary'] else 'phụ'} · vai trò: {m['role'] or '—'}")
    if len(mons) < 2:
        line(WARN, "Chỉ có 1 màn hình (hoặc đang Duplicate): cử chỉ chuyển màn hình sẽ được bỏ qua.")
    roles = mm.roles()
    if roles.problem and len(mons) >= 2:
        line(WARN, roles.problem)


def check_media_and_bridge() -> None:
    section("YouTube / media")
    try:
        from nexa.desktop.media import GsmtcBackend
        g = GsmtcBackend()
        targets = g.list_targets()
        line(OK, f"Windows Media Controls: {len(targets)} phiên" + (": " + "; ".join(f"{t.app} — {t.title[:40]}" for t in targets[:4]) if targets else ""))
    except Exception as exc:
        line(WARN, f"GSMTC: {exc}")
    import winreg
    from nexa.desktop.bridge_server import key_path, pipe_name
    for hive_path, label in ((r"Software\Google\Chrome\NativeMessagingHosts\com.nxsmedia.nexa_bridge", "Chrome"),
                             (r"Software\Microsoft\Edge\NativeMessagingHosts\com.nxsmedia.nexa_bridge", "Edge")):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, hive_path) as k:
                manifest = winreg.QueryValue(k, None)
            line(OK if Path(manifest).exists() else WARN, f"Native host đã đăng ký cho {label}: {manifest}")
        except OSError:
            line(WARN, f"Chưa đăng ký native host cho {label} (chạy browser_bridge\\install_bridge.ps1 nếu dùng YouTube bridge)")
    line(OK, f"Kênh bridge: {pipe_name()} · khóa: {'có' if key_path().exists() else 'sẽ tạo khi NEXA chạy'}")


def check_tts() -> None:
    section("Giọng nói")
    try:
        from winrt.windows.media.speechsynthesis import SpeechSynthesizer
        vi = [v.display_name for v in SpeechSynthesizer.all_voices if (v.language or "").lower().startswith("vi")]
        line(OK if vi else WARN, "Giọng Windows (offline) tiếng Việt: " + (", ".join(vi) if vi else "không có — cài gói giọng nói tiếng Việt trong Settings > Time & language > Speech"))
    except Exception as exc:
        line(WARN, f"WinRT TTS: {exc}")
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        sp = win32com.client.Dispatch("SAPI.SpVoice")
        vi = [v.GetDescription() for v in sp.GetVoices() if "42a" in (v.GetAttribute("Language") or "").lower()]
        line(OK if vi else WARN, "SAPI5 tiếng Việt: " + (", ".join(vi) if vi else "không có (bình thường trên nhiều máy)"))
    except Exception as exc:
        line(WARN, f"SAPI: {exc}")
    line(OK, "edge-tts (online) sẽ được thử khi chạy; cần Internet.")


def check_gemini(online: bool) -> None:
    section("Gemini")
    from nexa.ai.gemini_provider import GeminiProvider
    from nexa.utils.config import Config
    cfg = Config()
    status = cfg.gemini_key_status()
    line(OK if status == "set" else WARN, {"set": "GEMINI_API_KEY: đã đặt (không hiển thị)",
                                            "placeholder": "GEMINI_API_KEY: vẫn là giá trị mẫu → chế độ lệnh cơ bản",
                                            "missing": "GEMINI_API_KEY: chưa có → chế độ lệnh cơ bản"}[status])
    line(OK, f"Model: {cfg.gemini_model} · timeout {cfg.gemini_timeout_s:.0f}s · tối đa {cfg.max_tool_steps} bước · "
             f"đọc màn hình: {'bật' if cfg.cloud_screen_vision else 'tắt'}")
    if online and status == "set":
        ok, msg = GeminiProvider(cfg).test_connection()
        line(OK if ok else BAD, msg)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="bỏ qua mic và camera")
    ap.add_argument("--gemini", action="store_true", help="gửi một yêu cầu kiểm tra tới Gemini")
    args = ap.parse_args()
    print("NEXA — by NXS MEDIA · chẩn đoán")
    check_python()
    check_packages()
    check_models()
    check_monitors()
    check_tts()
    check_media_and_bridge()
    check_gemini(args.gemini)
    if not args.quick:
        check_mic()
        check_camera()
    print("\nKết quả:", "không có lỗi nghiêm trọng." if not problems else f"{len(problems)} lỗi cần xử lý:")
    for p in problems:
        print("  -", p)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
