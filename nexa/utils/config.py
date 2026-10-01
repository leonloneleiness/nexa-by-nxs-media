"""Nạp, gộp và lưu cấu hình NEXA.

- Cấu hình mặc định nằm trong mã (DEFAULTS) và được mô tả trong config/settings.example.yaml.
- Người dùng chỉnh trong config/settings.yaml (tự tạo lần chạy đầu, không đưa vào Git).
- Ngưỡng cử chỉ nằm trong config/gestures.yaml.
- Bí mật (GEMINI_API_KEY) chỉ đọc từ biến môi trường hoặc tệp .env cục bộ; không bao giờ
  được ghi vào settings.yaml.
"""
from __future__ import annotations

import copy
import os
import sys
import threading
from pathlib import Path
from typing import Any

import yaml


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _resource_root() -> Path:
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else _project_root()


PROJECT_ROOT = _project_root()
RESOURCE_ROOT = _resource_root()
CONFIG_DIR = PROJECT_ROOT / "config"
MODELS_DIR = PROJECT_ROOT / "models"
LOG_DIR = PROJECT_ROOT / "logs"
ASSETS_DIR = RESOURCE_ROOT / "assets"
QML_DIR = RESOURCE_ROOT / "nexa" / "ui" / "qml"
ENV_FILE = PROJECT_ROOT / ".env"
LOCAL_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "NEXA"

HOME = Path.home()

_KNOWN_FOLDERS = {
    "Desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "Documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
    "Downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "Pictures": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
}


def known_folder(name: str) -> Path:
    """Đường dẫn thật của thư mục người dùng (kể cả khi bị OneDrive chuyển hướng)."""
    if sys.platform == "win32" and name in _KNOWN_FOLDERS:
        try:
            import ctypes
            import uuid
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                            ("Data4", ctypes.c_ubyte * 8)]

            u = uuid.UUID(_KNOWN_FOLDERS[name])
            guid = GUID(u.fields[0], u.fields[1], u.fields[2], (ctypes.c_ubyte * 8).from_buffer_copy(u.bytes[8:]))
            out = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) == 0:
                value = out.value
                ctypes.windll.ole32.CoTaskMemFree(out)
                if value:
                    return Path(value)
        except Exception:
            pass
    return HOME / name

DEFAULTS: dict[str, Any] = {
    "audio": {
        "input_device": None,        # tên thiết bị; None = mặc định Windows
        "output_device": None,
        "preferred_hostapi": "MME",  # MME ổn định nhất cho hầu hết mic; có thể đổi WASAPI
        "clap": {
            "mode": "single",         # single | double
            "sensitivity": 0.55,      # 0..1, càng cao càng nhạy
            "min_level_dbfs": -42.0,  # xung phải to hơn mức tuyệt đối này
            "double_min_gap_ms": 120,
            "double_max_gap_ms": 700,
            "debounce_ms": 110,
            "cooldown_ms": 1500,
            "calibration_seconds": 2.0,
        },
        "snap": {                     # búng tay: bật/tắt chuyển động khi viewer 3D đang mở
            "enabled": True,
            "camera": True,           # nhận cử chỉ búng tay (ngón cái + ngón giữa) qua camera
            "sensitivity": 0.6,
            "min_level_dbfs": -50.0,
            "cooldown_ms": 900,
            "calibration_seconds": 2.0,
        },
        "vad": {
            "start_margin_db": 10.0,
            "end_margin_db": 6.0,
            "min_speech_ms": 250,
            "end_silence_ms": 600,       # ngắn hơn = trả lời nhanh hơn (dễ cắt câu nếu ngập ngừng)
            "max_utterance_s": 12.0,
            "listen_timeout_s": 8.0,
            "pre_roll_ms": 300,
        },
        "echo_tail_ms": 300,         # chặn mic thêm sau khi NEXA nói xong (chống tự nghe tiếng vang)
        "duck_media": True,          # vặn nhỏ nhạc/video của ứng dụng khác trong lúc NEXA nghe lệnh
        "duck_level": 0.2,           # còn 20% âm lượng gốc
    },
    "session": {
        "idle_timeout_s": 60,
        "conversation_idle_timeout_s": 300,
        "greeting": "Chào anh Sơn, em là Nexa. Em sẵn sàng.",
    },
    "power": {
        # Ngủ canh gác: máy không tự ngủ (màn hình vẫn tắt theo hẹn giờ), "cho máy ngủ" chỉ tắt màn hình,
        # vỗ tay thì bật màn hình và chào. Ngủ thật (Modern Standby) đóng băng NEXA nên không nghe được.
        "clap_wake_guard": True,
        "keep_display_awake": False,  # giữ cả màn hình; nút nguồn/ngủ và gập nắp không làm gì
        "screen_off": True,          # "cho máy ngủ" tắt màn hình; tự tắt nếu phát hiện việc đó làm máy ngủ thật
        "away_after_s": 300,         # vỗ tay sau ngần này giây không thao tác thì chào đầy đủ và mở cửa sổ NEXA
        "wake_greeting": "",         # rỗng = "Chào buổi sáng/chiều/tối anh Sơn, em là Nexa. Em sẵn sàng."
        # Trong lúc canh gác: nút nguồn/nút ngủ = "Tắt màn hình" (vẫn nghe vỗ tay); trả lại cài đặt gốc khi tắt/thoát.
        "button_turns_off_display": True,
        "lid_keep_awake": False,     # gập nắp = không làm gì (máy vẫn chạy trong túi → mặc định tắt)
        # Tự mở khóa Windows khi vỗ tay (cần cài dịch vụ SYSTEM "NexaUnlock"). Mặc định TẮT — tính năng
        # nhạy cảm: ai đứng trước máy khóa vỗ tay cũng vào được. Mã mở khóa KHÔNG lưu ở đây, chỉ ở
        # %ProgramData%\NEXA\unlock.bin do dịch vụ mã hóa DPAPI phạm vi máy. Xem nexa/desktop/unlock.py.
        "auto_unlock": False,
        # Cách chắc chắn hơn (khuyên dùng): khi NEXA canh gác, KHÔNG đòi mật khẩu lúc thức dậy (dịch vụ
        # NexaUnlock đặt console-lock=0), trả lại khi tắt NEXA. Bật màn hình là vào thẳng desktop, khỏi gõ mã.
        "no_lock": False,
    },
    "stt": {
        "model": "auto",              # auto = large-v3-turbo trên GPU NVIDIA nếu có, không thì small trên CPU
        "device": "auto",             # auto | cuda | cpu
        "compute_type": "auto",       # auto = float16 trên GPU, int8 trên CPU
        "beam_size": 3,               # đo trên máy: 1 → 3 chỉ chậm thêm ~0,1 s/câu nhưng đúng hơn; 5 không hơn 3
        "hotwords": [],               # tên riêng anh hay nói, thêm vào gợi ý cho Whisper
        # Dưới ngưỡng này (avg_logprob) mà câu không khớp lệnh cơ bản nào thì hỏi lại thay vì gửi Gemini đoán.
        "min_confidence_logprob": -0.9,
        "cpu_threads": 0,
        "language": "vi",
        # Gợi ý cho Whisper: none | static (danh sách cố định) | context (thêm tên ứng dụng/dịch vụ đang mở trên máy).
        # Là biến thí nghiệm của docs/research_asr.md; dùng hằng ngày để "context".
        "bias_mode": "context",
        "context_max_terms": 12,
    },
    "research": {
        # Thu dữ liệu nghiên cứu nhận dạng (docs/research_asr.md). TẮT mặc định: bật lên thì mỗi câu nói được lưu
        # thành WAV + dòng JSONL (chữ nhận dạng, độ tin cậy, gợi ý đã dùng) trong %LOCALAPPDATA%\NEXA\asr_corpus.
        "record_corpus": False,
        "corpus_dir": "",             # rỗng = %LOCALAPPDATA%\NEXA\asr_corpus
        "max_items": 5000,            # đủ số câu thì ngừng ghi
        "speaker_id": "S01",          # mã người nói (ẩn danh) ghi kèm mỗi câu
    },
    "tts": {
        "backend": "auto",            # auto | edge | winrt | sapi | none
        "edge_voice": "en-US-AndrewMultilingualNeural",   # nam đa ngữ; thuần Việt: vi-VN-NamMinhNeural / vi-VN-HoaiMyNeural
        "edge_pitch_hz": 0,           # chỉnh cao độ giọng Edge (Hz)
        "winrt_voice": "",            # rỗng = giọng vi-VN đầu tiên tìm được
        "winrt_pitch": None,          # 0..2; None = tự hạ (0.6) khi chọn giọng nam
        "effect": "jarvis",           # jarvis | robot | none
        "effect_strength": 0.5,       # 0..1
        "rate": 5,                    # -50..50 (%)
        "volume": 1.0,
    },
    "ai": {
        "provider": "gemini",
        "model": "",                  # rỗng = lấy GEMINI_MODEL từ môi trường
        "max_history_turns": 12,
        "max_output_tokens": 1024,
        "temperature": 0.6,
        "max_calls_per_session": 300,
        "max_retries": 2,
        # Model chính (GEMINI_MODEL) lỗi 503/504/quá hạn thì đổi ngay sang model dự phòng còn chạy.
        # Đo 2026-09-23 khi Google quá tải: 3.5-flash-lite/3.5-flash 504, 3.1-flash-lite 503, 3.6-flash vẫn trả lời.
        "fallback_models": ["gemini-3.6-flash", "gemini-3.1-flash-lite"],
        "attempt_timeout_s": 7,       # chờ tối đa model chưa chắc chạy được khi còn dự phòng (model vừa
                                      # trả lời được thì chờ đủ lâu: 3.6-flash lúc quá tải cần ~12 s)
        "request_budget_s": 20,       # tối đa cho MỘT lần hỏi Gemini, kể cả thử lại (trước đây có thể tới ~100 s)
        "thinking_level": "minimal",  # minimal | low | medium | high | "" (mặc định của model); thấp = nhanh hơn
    },
    "gestures": {
        "enabled_on_start": False,
        "camera_index": 0,
        "camera_width": 640,
        "camera_height": 480,
        "camera_fps": 30,
        "num_hands": 1,               # 1 = nhanh hơn, ít nhầm tay; 2 nếu cần chọn tay trái/phải khi cả hai trong khung
        "control_hand": "any",        # any | right | left
        "show_landmarks": True,
    },
    "attention": {
        # Nhận biết anh có ngồi ở máy (webcam, chạy cục bộ, cần camera cử chỉ đang bật). Không lưu ảnh khuôn mặt.
        "presence_enabled": False,
        "away_after_s": 45,           # vắng liên tục bao lâu (không thấy mặt, không phím/chuột) thì coi là rời máy
        "warning_s": 10,              # báo đếm ngược trước khi khóa; cử động/nhìn lại camera là hủy
        "lock_on_away": True,         # rời máy → khóa Windows (mở lại bằng PIN/Windows Hello như thường)
        "pause_media_on_away": True,  # rời máy → tạm dừng video đang phát; quay lại → phát tiếp (chỉ khi NEXA đã dừng)
        "resume_media_on_back": True,
        # Người thứ hai nhìn màn hình từ phía sau → thu nhỏ cửa sổ nhạy cảm (không tự mở lại; "khôi phục cửa sổ" để mở)
        "privacy_guard": True,
        "sensitive_processes": ["Zalo.exe", "Telegram.exe", "KeePass.exe", "KeePassXC.exe", "1Password.exe",
                                "Bitwarden.exe"],
        "sensitive_titles": ["ngân hàng", "internet banking", "ibanking", "vietcombank", "techcombank", "vpbank",
                             "mb bank", "bidv", "vietinbank", "agribank", "tpbank", "acb", "momo", "zalopay",
                             "paypal", "password", "mật khẩu", ".env"],
        # Chọn màn hình theo hướng quay đầu: off | commands (lệnh giọng nói/cử chỉ tác động lên màn hình anh đang
        # nhìn) | auto (focus tự theo hướng nhìn khi anh không gõ phím/di chuột)
        "head_target": "commands",
        "head_move_cursor": True,     # đưa con trỏ sang màn hình đang nhìn (cuộn chuột đi theo con trỏ)
        "head_auto_dwell_s": 0.8,
        "head_calibration": {},       # {khóa màn hình: [yaw, pitch]} — hiệu chuẩn bằng "hiệu chỉnh hướng nhìn"
        "face_every_n_frames": 3,     # chạy nhận diện mặt mỗi N khung camera (~10 Hz ở 30 fps)
    },
    "monitors": {
        "source": None,               # {device_name, device_id, friendly_name}
        "target": None,
    },
    "media": {
        "backend": "auto",            # auto | bridge | gsmtc
    },
    "youtube": {
        "auto_skip_ads": False,       # true = tự bấm "Bỏ qua" mỗi khi YouTube hiện quảng cáo
    },
    "files": {
        "allowed_roots": ["{Desktop}", "{Documents}", "{Downloads}", "{Pictures}"],
        "screenshot_dir": "{Pictures}/NEXA",
        "search_limit": 50,
    },
    "apps": {
        "custom": [],                 # [{name, path, aliases: []}]
        "browser_path": "",           # rỗng = trình duyệt mặc định của Windows
        "search_engine": "https://www.google.com/search?q={query}",
    },
    "ui": {
        "effects": "full",            # full | reduced | minimal
        "overlay": True,
        "sounds": True,
        "compact_on_start": False,
        "show_fps": False,
        "side_by_side": True,          # cửa sổ NEXA mở ra được xếp cạnh NEXA, không che NEXA
        "side_by_side_ratio": 0.4,     # phần bề ngang màn hình dành cho NEXA khi xếp cạnh
        "theme": "arc_reactor",
        "stats_ring": True,            # vòng CPU / RAM / GPU / độ trễ AI quanh quả cầu
        # HUD góc màn hình (click-through): phụ đề câu NEXA đang nói + thẻ kết quả trượt ra rồi tự ẩn
        "hud": {
            "enabled": True,
            "screen": "primary",       # primary | cursor | tên thiết bị (\\.\DISPLAY2)
            "corner": "bottom_right",  # bottom_right | bottom_left | top_right | top_left
            "subtitles": True,
            "cards": True,
            "card_seconds": 5,
        },
    },
    "safety": {
        # standard: hỏi xác nhận hành động rủi ro; full: người dùng trao toàn quyền — không hỏi xác nhận
        # (vẫn giữ: dừng khẩn cấp, xóa chỉ vào Thùng rác, tắt máy hẹn 60 giây, xem trước ảnh trước khi gửi Gemini).
        "autonomy": "standard",
    },
    "hotkeys": {
        "emergency_stop": "ctrl+alt+escape",
        "wake": "ctrl+alt+n",
    },
    # Sinh code (docs/code.md): Gemini viết → kiểm tra cú pháp → hiện để anh xem trước; chỉ sao chép/chạy khi anh bấm.
    "code": {
        "enabled": True,
        "models": ["gemini-3.8-flash", "gemini-3.5-flash"],   # chuỗi model riêng (thêm model chính của ai.model ở cuối)
        "thinking": "medium",
        "timeout_s": 180,
        "max_tokens": 32000,
        "temperature": 0.2,
        "repair_rounds": 2,          # số lượt nhờ Gemini sửa khi trình kiểm tra còn báo lỗi
        "with_tests": True,          # kèm kiểm thử tự động nhỏ
        "comment_language": "vi",    # vi | en — ngôn ngữ chú thích trong code
        "run_timeout_s": 30,         # chạy thử: dừng sau N giây
        "run_file_in": "nexa",       # nexa = kết quả hiện trong bảng Sinh code | console = cửa sổ console riêng
        "html_preview": True,        # trang HTML xem ngay trong NEXA (QtWebEngine); false = mở trình duyệt
        "python_path": "",           # trống = Python của NEXA (bản đóng gói: py -3 / python trên PATH)
        "save_dir": "",              # trống = Documents/NEXA Code
        "history_limit": 30,
        # cử chỉ khi bảng Sinh code mở (camera đang bật): nắm tay giữ yên = lưu, búng tay = chạy thử, hai ngón = cuộn
        "gesture": {
            "auto_camera": False,        # tự bật camera khi mở bảng (mặc định không — quyền riêng tư)
            "fist_hold_ms": 700,
            "scroll_deadzone": 0.3,      # kích thước bàn tay: lệch khỏi điểm neo ít hơn = đứng yên
            "scroll_gain": 1600,         # px/giây cho mỗi kích thước bàn tay vượt deadzone
            "scroll_max": 3000,
            "invert_scroll": False,
        },
    },
    # Mô hình 3D (docs/three_d.md). API key dịch vụ cloud chỉ đặt trong .env (TRIPO_API_KEY / MESHY_API_KEY).
    "three_d": {
        "enabled": True,
        "default_mode": "auto",           # auto (CAD tham số cho nhóm hỗ trợ, cloud cho vật thể khác) | parametric | cloud
        "provider": "auto",               # auto (Tripo/Meshy nếu có key, không thì Hugging Face Space) | tripo | meshy
                                          # | hf_space | none — biến môi trường NEXA_3D_PROVIDER được ưu tiên
        "cache_dir": "",                  # rỗng = %LOCALAPPDATA%\NEXA\3d_cache
        "cache_size_mb": 4096,
        "keep_generated_assets": True,
        "max_asset_mb": 200,
        "max_triangles": 2000000,
        "max_texture_size": 4096,
        "candidate_count": 2,             # số ứng viên cloud ở chế độ chất lượng cao (1–3)
        "refinement_rounds": 1,           # số vòng làm lại tối đa (0–2)
        "quality_threshold": 90,
        "generation_timeout_s": 900,
        "max_cost_per_job": 0,            # credit; 0 = không giới hạn (chỉ áp dụng khi provider báo chi phí)
        "ai_review": True,                # Gemini chấm ảnh render 6 góc (chỉ là một phần điểm)
        "use_gemini_planner": True,
        "reference_images": "auto",       # auto (chỉ chất lượng cao) | on | off — ảnh tham chiếu nhiều góc bằng Gemini
        "reference_image_model": "gemini-3.1-flash-image",
        "cloud_segmentation": True,
        "tripo_model_version": "v3.1-20260211",
        "tripo_api": "v3",                # v3 (openapi.tripo3d.ai/v3, mặc định) | v2 (api.tripo3d.ai/v2/openapi)
        "tripo_texture_quality": "detailed",      # standard | detailed (HD, +10 credit) | extreme (8K, +20)
        "tripo_texture_quality_high": "extreme",  # khi nói "chất lượng cao"
        "tripo_geometry_quality": "detailed",     # standard | detailed (Ultra, +20 credit)
        "tripo_auto_size": True,          # Tripo trả kích thước thật (mét) → không phải đoán cỡ
        "tripo_face_limit": 0,            # 0 = Tripo tự chọn (adaptive)
        "tripo_segment_model": "v2.0-20260430",   # tách bộ phận ngữ nghĩa (Beta) | v1.0-20250506
        "cloud_segment_free_objects": False,      # tách bộ phận cả vật thể tự do (+40 credit/mô hình)
        "meshy_ai_model": "latest",
        # mức 2: Gemini thiết kế vật thể tự do bằng CAD DSL (tác vụ dài, không theo ngân sách 20 s của hội thoại)
        "dsl_models": ["gemini-3.8-flash", "gemini-3.5-flash"],   # thử lần lượt; cuối chuỗi luôn có GEMINI_MODEL
        "dsl_thinking": "medium",         # minimal | low | medium | high | "" (mặc định model)
        "dsl_timeout_s": 180,
        "dsl_max_tokens": 24000,
        "dsl_repair_rounds": 2,           # số lần gửi lỗi biên dịch cho Gemini sửa
        "dsl_refine_rounds": 2,           # số vòng Gemini xem ảnh render rồi sửa mô hình (0–4)
        "dsl_fallback_below": 55,         # điểm mức 2 thấp hơn → thử thêm mức 3 (cloud/HF), giữ bản tốt hơn; 0 = tắt
        # mức 3 miễn phí: Hugging Face Spaces (ảnh FLUX/Gemini → TRELLIS/Hunyuan3D). HF_TOKEN trong .env tăng hạn mức GPU.
        "hf_enabled": True,
        "hf_prefer_with_token": True,     # có HF_TOKEN → vật thể tự do dùng mức 3 (HF) trước, mức 2 dự phòng
        "hf_image_space": "black-forest-labs/FLUX.1-schnell",
        "hf_3d_spaces": ["trellis-community/TRELLIS", "tencent/Hunyuan3D-2", "tencent/Hunyuan3D-2.1"],
        "hf_timeout_s": 840,              # tổng cho một ứng viên HF (< generation_timeout_s)
        "hf_image_timeout_s": 180,        # bước tạo ảnh (FLUX) tối đa
        "hf_space_timeout_s": 360,        # mỗi Space image-to-3D tối đa — quá thì thử Space kế tiếp
        "hf_expected_s": 120,
        "open_viewer_when_ready": True,
        "viewer_auto_camera": False,      # tự bật camera cử chỉ khi mở viewer (mặc định không — quyền riêng tư)
        "viewer_triangle_budget": 1500000,
        "gesture": {
            "rotate_sensitivity": 110.0,  # độ xoay mỗi "kích thước bàn tay" tay di chuyển
            "rotate_deadzone": 0.25,      # kích thước tay
            "acquire_ms": 200,
            "fist_hold_ms": 500,
            "open_hold_ms": 350,
            "cooldown_ms": 700,
            "animation_ms": 900,
            "arm_timeout_ms": 3000,
            "explode_max_speed": 1.8,     # kích thước tay / giây
            "inertia": 0.35,              # 0..0.9
            "pitch_limit_deg": 85,
            "zoom_two_fingers": True,
        },
    },
    # Kịch bản làm việc (nexa/desktop/routines.py): nói một câu trong `phrases` để mở + xếp cả bộ cửa sổ.
    # monitor 1/2 theo vai trò trong Cài đặt > Màn hình. zone (tùy chọn): mặc định "keep" = chỉ đưa sang đúng màn hình,
    # giữ nguyên kích thước; muốn xếp thì dùng full/left/right/top/bottom/left_third/center_third/right_third/
    # left_two_thirds/right_two_thirds.
    "routines": {
        "bat_dau_lam_viec": {
            "name": "Bắt đầu làm việc",
            "phrases": ["bắt đầu làm việc", "vào việc", "bắt đầu ngày làm việc", "chế độ làm việc"],
            "steps": [
                {"label": "Claude", "app": "Claude", "aumid": "Claude_pzs8sxrjxfjjc!Claude", "process": "claude.exe",
                 "monitor": 1},
                {"label": "Zalo", "app": "Zalo", "process": "zalo.exe", "title": "Zalo", "monitor": 1},
                {"label": "YouTube", "url": "https://www.youtube.com", "title": "YouTube", "monitor": 2},
                {"label": "ChatGPT", "url": "https://chatgpt.com", "title": "ChatGPT", "monitor": 2},
                {"label": "VS Code", "app": "Visual Studio Code", "process": "code.exe", "monitor": 1},
                {"label": "Tin nhắn Zalo", "action": "check_zalo"},
            ],
        },
    },
}

# (khóa, kiểu, nhỏ nhất, lớn nhất) — validate_three_d kẹp giá trị ngoài khoảng về mặc định/giới hạn.
THREE_D_LIMITS: list[tuple[str, type, float, float]] = [
    ("cache_size_mb", float, 100, 200000), ("max_asset_mb", float, 1, 2000), ("max_triangles", int, 10000, 10000000),
    ("max_texture_size", int, 256, 16384), ("candidate_count", int, 1, 3), ("refinement_rounds", int, 0, 2),
    ("quality_threshold", float, 50, 100), ("generation_timeout_s", float, 30, 7200), ("max_cost_per_job", float, 0, 100000),
    ("viewer_triangle_budget", int, 50000, 10000000),
    ("dsl_timeout_s", float, 30, 900), ("dsl_max_tokens", int, 4096, 65536), ("dsl_repair_rounds", int, 0, 4),
    ("dsl_refine_rounds", int, 0, 4), ("dsl_fallback_below", float, 0, 100), ("hf_timeout_s", float, 60, 3600), ("hf_expected_s", float, 10, 1800),
    ("hf_image_timeout_s", float, 20, 900), ("hf_space_timeout_s", float, 30, 3600),
    ("gesture.rotate_sensitivity", float, 10, 720), ("gesture.rotate_deadzone", float, 0.0, 2.0),
    ("gesture.acquire_ms", int, 100, 600), ("gesture.fist_hold_ms", int, 200, 2000), ("gesture.open_hold_ms", int, 150, 1500),
    ("gesture.cooldown_ms", int, 0, 5000), ("gesture.animation_ms", int, 100, 5000), ("gesture.arm_timeout_ms", int, 500, 10000),
    ("gesture.explode_max_speed", float, 0.3, 10), ("gesture.inertia", float, 0.0, 0.9), ("gesture.pitch_limit_deg", float, 10, 89),
]
THREE_D_ENUMS = {"default_mode": ("auto", "parametric", "cloud"),
                 "provider": ("auto", "tripo", "meshy", "hf_space", "none"),
                 "dsl_thinking": ("minimal", "low", "medium", "high", ""),
                 "tripo_api": ("v3", "v2"), "tripo_texture_quality": ("standard", "detailed", "extreme"),
                 "tripo_texture_quality_high": ("standard", "detailed", "extreme"),
                 "tripo_geometry_quality": ("standard", "detailed"),
                 "reference_images": ("auto", "on", "off", True, False)}


def validate_three_d(config: "Config") -> list[str]:
    """Kẹp cấu hình three_d về khoảng hợp lệ (ghi thẳng vào config). Trả danh sách cảnh báo tiếng Việt."""
    warnings: list[str] = []
    defaults = DEFAULTS["three_d"]
    for key, typ, lo, hi in THREE_D_LIMITS:
        dotted = f"three_d.{key}"
        cur = config.get(dotted)
        node = defaults
        for part in key.split("."):
            node = node[part]
        try:
            val = typ(cur)
        except (TypeError, ValueError):
            config.set(dotted, node)
            warnings.append(f"{dotted} không hợp lệ ({cur!r}) — dùng mặc định {node}.")
            continue
        if not (lo <= val <= hi):
            clamped = typ(min(hi, max(lo, val)))
            config.set(dotted, clamped)
            warnings.append(f"{dotted}={cur} ngoài khoảng [{lo:g}, {hi:g}] — đặt {clamped}.")
        elif val != cur:
            config.set(dotted, val)
    for key, allowed in THREE_D_ENUMS.items():
        cur = config.get(f"three_d.{key}")
        if cur not in allowed:
            config.set(f"three_d.{key}", defaults[key])
            warnings.append(f"three_d.{key}={cur!r} không hợp lệ — dùng '{defaults[key]}'.")
    return warnings

GESTURE_DEFAULTS: dict[str, Any] = {
    # Chỉ để mô tả (UI/tài liệu). Bảng thật nằm trong nexa/vision/gesture_state_machine.py.
    "mapping": {
        "point_right_hold": "MOVE_WINDOW_TO_MONITOR_2",
        "thumb_down_hold": "MINIMIZE_ACTIVE_WINDOW",
        "thumb_up_hold": "RESTORE_LAST_MINIMIZED_WINDOW",
        "fist_hold": "YOUTUBE_PAUSE",
        "open_palm_hold_after_fist": "YOUTUBE_RESUME",
        "two_fingers_hold": "SCROLL_UP",
    },
    "pose": {
        "min_confidence": 0.6,
        "vote_frames": 6,
        "vote_ratio": 0.65,
    },
    "hold": {
        "hold_ms": 500,               # nắm tay / mở tay
        "action_hold_ms": 650,        # chỉ tay, like/dislike, hai ngón
        "still_speed": 0.9,           # đơn vị: kích thước bàn tay / giây
        "deadzone": 0.5,              # xê dịch tối đa (kích thước tay) vẫn coi là giữ yên
        "resume_window_ms": 4000,
        "release_ms": 250,
    },
    "scroll": {
        "repeat_ms": 180,             # giữ hai ngón: cứ mỗi repeat_ms cuộn một lần
        "notch_size": 2,              # số nấc mỗi lần
        "invert_scroll": False,
    },
    "timing": {
        "cooldown_ms": 900,
        "lost_hand_ms": 250,
        "smoothing": 0.5,
    },
    "calibration": {
        "invert_x": False,
        "invert_y": False,
    },
    # Chuột bằng tay (nexa/vision/air_mouse.py) — chỉ chạy khi anh bật "chuột bằng tay". Các khóa khác xem MouseParams.
    "mouse": {
        "mapping": "relative",        # relative = kiểu touchpad (nắm tay để nhấc tay) | absolute = khung hình ↔ màn hình
        "gain": 900.0,                # tốc độ con trỏ: pixel mỗi "kích thước bàn tay"
        "accel": 0.7,                 # gia tốc: 0 = tắt; lớn hơn = tay chậm chính xác hơn, tay nhanh đi xa hơn
        "pinch_on": 0.32,             # chụm khi đầu ngón cái – trỏ gần hơn mức này (× kích thước tay)
        "pinch_off": 0.48,            # nhả khi xa hơn mức này
        "drag_start": 0.35,           # đang chụm mà tay đi quá mức này → kéo thả (nhỏ hơn → click dễ thành kéo)
        "scroll_step": 0.18,          # hai ngón: tay đi chừng này (× kích thước tay) = 1 nấc cuộn
        "invert_scroll": False,
        "yield_ms": 1000,             # cầm chuột thật thì chuột bằng tay nhường chừng này
    },
}

# Khóa của bộ cử chỉ vuốt cũ (trước v1.1) — bỏ khi nạp để file cấu hình không giữ rác.
_LEGACY_GESTURE_KEYS = ("swipe",)

PLACEHOLDER_MARKERS = ("YOUR_", "PLACEHOLDER", "CHANGE_ME", "<", "XXXX")
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"


def expand_path(value: str) -> Path:
    """Mở rộng {Desktop}/{Documents}/{Downloads}/{Pictures}, %BIẾN% và ~ thành đường dẫn thật."""
    text = str(value or "")
    for name in _KNOWN_FOLDERS:
        token = "{" + name + "}"
        if token in text:
            text = text.replace(token, str(known_folder(name)))
    return Path(os.path.expandvars(os.path.expanduser(text)))


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def is_placeholder_secret(value: str | None) -> bool:
    if value is None:
        return True
    v = value.strip()
    if not v:
        return True
    upper = v.upper()
    return any(marker in upper for marker in PLACEHOLDER_MARKERS)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Tệp cấu hình {path.name} không hợp lệ")
    return data


def load_env_file(path: Path = ENV_FILE) -> None:
    """Nạp .env mà không ghi đè biến môi trường đã có."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover
        return
    if path.exists():
        load_dotenv(path, override=False, encoding="utf-8")


class Config:
    """Cấu hình dùng chung, an toàn luồng khi đọc/ghi."""

    def __init__(self, settings_path: Path | None = None, gestures_path: Path | None = None,
                 load_env: bool = True):
        self._lock = threading.RLock()
        self.settings_path = settings_path or (CONFIG_DIR / "settings.yaml")
        self.gestures_path = gestures_path or (CONFIG_DIR / "gestures.yaml")
        if load_env:
            load_env_file()
        self.data: dict[str, Any] = deep_merge(DEFAULTS, _load_yaml(self.settings_path))
        self.gestures: dict[str, Any] = deep_merge(GESTURE_DEFAULTS, _load_yaml(self.gestures_path))
        for key in _LEGACY_GESTURE_KEYS:
            self.gestures.pop(key, None)
        self.gestures["mapping"] = dict(GESTURE_DEFAULTS["mapping"])
        for key in ("step_distance", "max_notches_per_second"):
            self.gestures["scroll"].pop(key, None)
        self.gestures["timing"].pop("rearm_ms", None)
        self.load_error: str | None = None
        self.config_warnings: list[str] = validate_three_d(self)

    # ----- truy cập -----
    def get(self, dotted: str, default: Any = None) -> Any:
        with self._lock:
            node: Any = self.data
            for part in dotted.split("."):
                if not isinstance(node, dict) or part not in node:
                    return default
                node = node[part]
            return copy.deepcopy(node)

    def set(self, dotted: str, value: Any) -> None:
        with self._lock:
            parts = dotted.split(".")
            node = self.data
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value

    def gesture(self, dotted: str, default: Any = None) -> Any:
        with self._lock:
            node: Any = self.gestures
            for part in dotted.split("."):
                if not isinstance(node, dict) or part not in node:
                    return default
                node = node[part]
            return copy.deepcopy(node)

    def set_gesture(self, dotted: str, value: Any) -> None:
        with self._lock:
            parts = dotted.split(".")
            node = self.gestures
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value

    def update(self, patch: dict) -> None:
        with self._lock:
            self.data = deep_merge(self.data, patch)
        if "three_d" in (patch or {}):
            self.config_warnings = validate_three_d(self)

    def update_gestures(self, patch: dict) -> None:
        with self._lock:
            self.gestures = deep_merge(self.gestures, patch)

    def snapshot(self) -> dict:
        with self._lock:
            return copy.deepcopy(self.data)

    # ----- lưu -----
    def save(self) -> None:
        with self._lock:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.settings_path.with_suffix(".yaml.tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                fh.write("# Cấu hình cục bộ của NEXA (tự sinh). Không chứa API key.\n")
                yaml.safe_dump(self.data, fh, allow_unicode=True, sort_keys=False)
            tmp.replace(self.settings_path)

    def save_gestures(self) -> None:
        with self._lock:
            self.gestures_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.gestures_path.with_suffix(".yaml.tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                fh.write("# Ánh xạ và ngưỡng cử chỉ của NEXA. Xem docs/gestures.md.\n")
                yaml.safe_dump(self.gestures, fh, allow_unicode=True, sort_keys=False)
            tmp.replace(self.gestures_path)

    # ----- AI / bí mật -----
    @property
    def ai_provider(self) -> str:
        return (os.environ.get("NEXA_AI_PROVIDER") or self.get("ai.provider") or "gemini").strip().lower()

    @property
    def gemini_model(self) -> str:
        return (self.get("ai.model") or os.environ.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL).strip()

    @property
    def gemini_timeout_s(self) -> float:
        try:
            return max(5.0, float(os.environ.get("GEMINI_REQUEST_TIMEOUT_SECONDS", "15")))
        except ValueError:
            return 15.0

    @property
    def max_tool_steps(self) -> int:
        try:
            return max(1, min(20, int(os.environ.get("NEXA_MAX_TOOL_STEPS", "8"))))
        except ValueError:
            return 8

    @property
    def cloud_screen_vision(self) -> bool:
        return os.environ.get("NEXA_CLOUD_SCREEN_VISION", "false").strip().lower() in ("1", "true", "yes", "on")

    def set_cloud_screen_vision(self, enabled: bool) -> None:
        os.environ["NEXA_CLOUD_SCREEN_VISION"] = "true" if enabled else "false"
        _upsert_env_line("NEXA_CLOUD_SCREEN_VISION", "true" if enabled else "false")

    def gemini_api_key(self) -> str:
        """Trả về key hợp lệ hoặc chuỗi rỗng nếu thiếu/placeholder. Không bao giờ log giá trị."""
        key = os.environ.get("GEMINI_API_KEY", "")
        if is_placeholder_secret(key):
            return ""
        return key.strip()

    def gemini_key_status(self) -> str:
        raw = os.environ.get("GEMINI_API_KEY")
        if raw is None or not raw.strip():
            return "missing"
        if is_placeholder_secret(raw):
            return "placeholder"
        return "set"

    def store_api_key(self, key: str, persist: bool) -> None:
        """Đặt key cho phiên hiện tại; nếu persist=True thì ghi vào .env cục bộ."""
        key = (key or "").strip()
        os.environ["GEMINI_API_KEY"] = key
        from nexa.utils.logging import register_secret
        register_secret(key)
        if persist:
            _upsert_env_line("GEMINI_API_KEY", key)

    def set_gemini_model(self, model: str) -> None:
        self.set("ai.model", model.strip())


def _upsert_env_line(name: str, value: str, path: Path = ENV_FILE) -> None:
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{name}="):
            lines[i] = f"{name}={value}"
            replaced = True
    if not replaced:
        lines.append(f"{name}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_user_settings(config_dir: Path = CONFIG_DIR) -> Path:
    """Tạo config/settings.yaml từ bản mẫu nếu chưa có."""
    target = config_dir / "settings.yaml"
    if not target.exists():
        example = config_dir / "settings.example.yaml"
        config_dir.mkdir(parents=True, exist_ok=True)
        if example.exists():
            target.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    return target
