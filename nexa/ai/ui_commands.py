"""Allowlisted user-facing UI operations, shared by voice, keyboard and AI."""
from __future__ import annotations

from dataclasses import dataclass, field

from nexa.core.events import Risk, ToolResult


def string(**kw):
    return {"type": "string", "maxLength": 2000, **kw}


def enum(*values, **kw):
    return string(enum=list(values), **kw)


def boolean():
    return {"type": "boolean"}


def numeric(lo=-10000, hi=10000, **kw):
    return {"type": "number", "minimum": lo, "maximum": hi, **kw}


@dataclass(frozen=True)
class UiCommand:
    name: str
    vi: str
    en: str
    target: str
    method: str
    params: dict = field(default_factory=dict)
    risk: Risk = Risk.LOW
    background: bool = False


# Parameter insertion order is the positional order of the existing Qt slot.
COMMANDS = (
    UiCommand("navigate_nexa", "mở bảng NEXA", "open nexa panel", "navigation", "open",
              {"panel": enum("settings", "gestures", "history", "3d", "edu", "code", "build", "media")}),
    UiCommand("close_nexa_panel", "đóng bảng NEXA", "close nexa panel", "navigation", "close",
              {"panel": enum("settings", "gestures", "history", "3d", "edu", "code", "build", "media")}),
    UiCommand("set_compact_mode", "chế độ thu gọn", "set compact mode", "navigation", "compact", {"enabled": boolean()}),
    UiCommand("edu_select_lesson", "chọn bài học", "select lesson", "edu", "selectLesson",
              {"lesson_id": enum("bridge_load", "pendulum", "circuit", "ph_scale", "solar", "solar_system")}),
    UiCommand("edu_set_parameter", "đặt tham số bài học", "set lesson parameter", "edu", "setParameter",
              {"key": string(minLength=1), "value": numeric()}),
    UiCommand("edu_run", "chạy mô phỏng bài học", "run lesson simulation", "edu", "runSimulation"),
    UiCommand("edu_next_step", "bước tiếp theo bài học", "next lesson step", "edu", "nextStep"),
    UiCommand("edu_reset", "đặt lại bài học", "reset lesson", "edu", "resetLesson"),
    UiCommand("edu_export", "xuất báo cáo bài học", "export lesson report", "edu", "exportReport"),
    UiCommand("code_copy_all", "sao chép toàn bộ code", "copy all code", "code", "copyAll"),
    UiCommand("code_copy_file", "sao chép tệp code", "copy code file", "code", "copyFile",
              {"index": {"type":"integer", "minimum":0, "maximum":1000}}),
    UiCommand("code_save", "lưu bản code", "save generated code", "code", "save"),
    UiCommand("code_copy_output", "sao chép kết quả chạy", "copy run output", "code", "copyRunOutput"),
    UiCommand("code_stop_run", "dừng chương trình đang chạy", "stop running program", "code", "stopRun"),
    UiCommand("code_rerun", "chạy lại chương trình", "rerun program", "code", "rerun", risk=Risk.MEDIUM, background=True),
    UiCommand("code_console", "chạy code trong console", "run code in console", "code", "runInConsole", risk=Risk.MEDIUM, background=True),
    UiCommand("code_input", "nhập dữ liệu chương trình", "send program input", "code", "sendInput", {"text":string()}, risk=Risk.MEDIUM),
    UiCommand("code_fix_errors", "sửa lỗi chạy code", "fix code run errors", "code", "fixRunErrors", background=True),
    UiCommand("code_open_history", "mở bản code đã lưu", "open code history", "code", "openHistory", {"rid":string(minLength=1)}),
    UiCommand("code_delete_history", "xóa bản code đã lưu", "delete code history", "code", "deleteHistory", {"rid":string(minLength=1)}, risk=Risk.HIGH),
    UiCommand("code_set_view", "chọn trang bảng code", "set code panel view", "navigation", "code_view", {"view":enum("code", "run", "web")}),
    UiCommand("refresh_3d_library", "làm mới thư viện mô hình", "refresh model library", "3d", "refreshModels"),
    UiCommand("select_3d_part", "chọn bộ phận theo mã", "select part by id", "3d", "selectPart", {"pid":string(minLength=1)}),
    UiCommand("apply_3d_part_action", "thao tác bộ phận theo mã", "apply part action", "3d", "partAction",
              {"action":enum("focus", "hide", "show", "toggle", "isolate"),
               "ids":{"type":"array", "items":string(minLength=1), "minItems":1, "maxItems":100}}),
    UiCommand("generate_3d_references", "tạo mô hình từ ảnh", "generate model from images", "3d", "generateFromReferences",
              {"prompt":string(default=""), "quality":enum("standard", "high", default="standard"),
               "references":{"type":"object", "properties":{k:string() for k in ("front", "back", "left", "right", "top", "bottom")}},
               "method":enum("auto", "cad", default="auto")}, risk=Risk.HIGH, background=True),
    UiCommand("save_build_record", "lưu ghi chú linh kiện", "save build record", "3d", "saveBuildRecord",
              {"project_id":string(minLength=1), "part_id":string(minLength=1),
               "record":{"type":"object", "properties":{"mode":enum("unknown", "make", "buy", "reference", default="unknown"),
                         "quantity":{"type":"integer", "minimum":0, "maximum":100000, "default":0},
                         **{k:string(default="") for k in ("manufacturer", "model_number", "url", "notes")}}}}),
    UiCommand("refresh_build_dossier", "làm mới hồ sơ lắp ráp", "refresh build dossier", "3d", "refreshBuildDossier"),
    UiCommand("export_build_dossier", "xuất hồ sơ lắp ráp", "export build dossier", "3d", "exportBuildDossier", {"project_id":string(default="")}, background=True),
    UiCommand("open_build_folder", "mở thư mục hồ sơ lắp ráp", "open build folder", "3d", "openBuildDossierFolder"),
    UiCommand("export_product_media", "xuất ảnh video sản phẩm", "export product media", "3d", "exportProductMedia",
              {"kind":enum("png", "mp4", default="png"), "size":{"type":"integer", "minimum":256,"maximum":1024,"default":768},
               "background":enum("light", "transparent", "dark", default="light"),
               "seconds":{"type":"integer", "minimum":3,"maximum":10,"default":6},
               "yaw":numeric(-360,360,default=35), "pitch":numeric(-80,80,default=20)}, background=True),
    UiCommand("cancel_product_media", "hủy xuất ảnh video", "cancel product media", "3d", "cancelProductMedia"),
    UiCommand("open_media_folder", "mở thư mục ảnh video", "open product media folder", "3d", "openProductMediaFolder"),
    UiCommand("set_camera_preview", "bật tắt xem trước camera", "set camera preview", "main", "setPreviewEnabled", {"on":boolean()}),
    UiCommand("toggle_3d_camera", "bật tắt camera 3D", "toggle 3d camera", "3d", "toggleCamera", background=True),
    UiCommand("set_hand_landmarks", "bật tắt điểm bàn tay", "set hand landmarks", "main", "setShowLandmarks", {"on":boolean()}),
    UiCommand("test_voice", "thử giọng đọc", "test voice", "main", "testTts", background=True),
    UiCommand("test_ai_connection", "kiểm tra kết nối AI", "test ai connection", "main", "testGemini", background=True),
    UiCommand("test_hud", "thử phụ đề HUD", "test hud", "main", "testHud"),
    UiCommand("identify_monitors", "đánh số màn hình", "identify monitors", "main", "identifyMonitors"),
    UiCommand("set_monitor_roles", "đặt vai trò màn hình", "set monitor roles", "main", "setMonitorRoles", {"src":string(), "dst":string()}),
    UiCommand("list_monitors", "danh sách màn hình", "list monitors", "main", "monitors"),
    UiCommand("list_microphones", "danh sách micro", "list microphones", "main", "inputDevices"),
    UiCommand("list_speakers", "danh sách loa", "list speakers", "main", "outputDevices"),
    UiCommand("list_cameras", "danh sách camera", "list cameras", "main", "cameras"),
    UiCommand("list_speech_models", "danh sách model giọng nói", "list speech models", "main", "sttModels"),
    UiCommand("list_voice_backends", "danh sách bộ đọc", "list voice backends", "main", "ttsBackends"),
    UiCommand("list_windows_voices", "danh sách giọng Windows", "list windows voices", "main", "winrtVoices"),
    UiCommand("list_online_voices", "danh sách giọng trực tuyến", "list online voices", "main", "edgeVoices"),
    UiCommand("list_voice_effects", "danh sách hiệu ứng giọng", "list voice effects", "main", "voiceEffects"),
    UiCommand("list_media_targets", "danh sách nguồn media", "list media targets", "main", "mediaTargets"),
    UiCommand("bind_media_target", "chọn nguồn media", "bind media target", "main", "bindMedia", {"target_id":string(minLength=1)}),
    UiCommand("refresh_media_targets", "làm mới nguồn media", "refresh media targets", "main", "refreshMedia", background=True),
    UiCommand("set_clap_test", "bật tắt thử vỗ tay", "set clap test", "main", "setClapTest", {"on":boolean()}),
    UiCommand("calibrate_clap", "hiệu chuẩn vỗ tay", "calibrate clap", "main", "recalibrateClap", background=True),
    UiCommand("clap_statistics", "thống kê vỗ tay", "clap statistics", "main", "clapStats"),
    UiCommand("calibrate_gesture", "hiệu chuẩn cử chỉ", "calibrate gesture", "main", "calibrateGesture", {"step":enum("right", "up")}, background=True),
    UiCommand("refresh_attention", "làm mới trạng thái hiện diện", "refresh attention", "main", "refreshAttention"),
    UiCommand("set_cloud_vision", "bật tắt đọc màn hình AI", "set cloud vision", "main", "setCloudVision", {"on":boolean()}, risk=Risk.HIGH),
    UiCommand("set_ai_model", "chọn model AI", "set ai model", "main", "setGeminiModel", {"model":string(minLength=1)}),
    UiCommand("unlock_service_status", "trạng thái dịch vụ mở khóa", "unlock service status", "main", "unlockServiceStatus"),
    UiCommand("install_unlock_service", "cài dịch vụ mở khóa", "install unlock service", "main", "installUnlockService", risk=Risk.HIGH, background=True),
    UiCommand("uninstall_unlock_service", "gỡ dịch vụ mở khóa", "uninstall unlock service", "main", "uninstallUnlockService", risk=Risk.HIGH, background=True),
    UiCommand("clear_unlock_password", "xóa mã mở khóa đã lưu", "clear unlock password", "main", "clearUnlockPassword", risk=Risk.HIGH),
    UiCommand("show_log_path", "đường dẫn nhật ký", "show log path", "main", "logPath"),
    UiCommand("read_nexa_settings", "xem cấu hình NEXA", "read nexa settings", "main", "settingsJson"),
    UiCommand("read_gesture_settings", "xem cấu hình cử chỉ", "read gesture settings", "main", "gesturesJson"),
    UiCommand("set_nexa_setting", "đặt cấu hình NEXA", "set nexa setting", "settings", "set",
              {"key":string(minLength=1), "value":string(), "scope":enum("settings", "gestures", default="settings")}, risk=Risk.HIGH),
    UiCommand("resume_nexa_control", "tiếp tục điều khiển", "resume nexa control", "main", "resumeControl", risk=Risk.HIGH),
    UiCommand("quit_nexa", "thoát NEXA", "quit nexa", "main", "quit", risk=Risk.HIGH),
)


def register_ui_tools(reg, config):
    from nexa.ai.tool_registry import ToolSpec, obj

    def handler(command):
        def run(args, ctx):
            dispatch = ctx.services.hooks.get("ui_command")
            if dispatch is None:
                return ToolResult.failure("Giao diện chưa sẵn sàng / UI unavailable.", "unavailable")
            return dispatch(command.name, args, ctx.token)
        return run

    for cmd in COMMANDS:
        required = [key for key, schema in cmd.params.items() if "default" not in schema]
        reg.register(ToolSpec(cmd.name, cmd.vi, f"{cmd.vi} / {cmd.en}.", obj(cmd.params, required),
                              handler(cmd), risk=cmd.risk, needs_control=False,
                              always_confirm=cmd.risk == Risk.HIGH,
                              allowed_when_paused=cmd.name == "resume_nexa_control",
                              expose_to_ai=cmd.name != "resume_nexa_control"))

    def catalog(args, ctx):
        entries = [{"vi": s.title, "en": n.replace("_", " "), "parameters": s.ai_schema()}
                   for n in reg.names() if (s := reg.get(n))]
        return ToolResult.success("\n".join(f"• {e['vi']} / {e['en']}" for e in entries), commands=entries)
    reg.register(ToolSpec("list_commands", "Danh sách lệnh", "List bilingual commands and their public parameters.",
                          obj({}), catalog, needs_control=False, allowed_when_paused=True))
