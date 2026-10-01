"""Công cụ sinh code trong tool registry chung (giọng nói, bàn phím, Gemini function calling đều gọi qua Executor).

Không công cụ nào đụng chuột/bàn phím hay clipboard. generate/refine chỉ khởi động việc nền và trả NGAY; bản code hiện
trên bảng Sinh code để anh xem trước — sao chép/lưu chỉ khi anh bấm nút. Chạy thử = chạy code thật trên máy nên rủi ro
MEDIUM: Gemini tự đề xuất thì phải hỏi anh xác nhận.
"""
from __future__ import annotations

from typing import Any

from nexa.core.events import Risk, ToolResult
from nexa.core.safety import Assessment
from nexa.utils.text import truncate

LANGS = ["auto", "python", "javascript", "typescript", "java", "csharp", "cpp", "c", "go", "rust", "php", "kotlin",
         "sql", "powershell", "bash", "batch", "ruby", "perl", "lua", "r", "julia", "dart", "swift", "scala", "haskell",
         "elixir", "zig", "fsharp", "html", "css", "yaml", "json", "dockerfile"]


def _svc(ctx: Any):
    svc = getattr(ctx.services, "code", None)
    if svc is None or not svc.enabled:
        return None
    return svc


def _unavailable() -> ToolResult:
    return ToolResult.failure("Tính năng sinh code đang tắt (code.enabled).", "unavailable")


def h_generate(args: dict, ctx: Any) -> ToolResult:
    svc = _svc(ctx)
    if svc is None:
        return _unavailable()
    prompt = args["prompt"].strip()
    lang = args.get("language", "auto")
    ok, msg = svc.generate(prompt, "" if lang == "auto" else lang, source=ctx.source.value)
    if not ok:
        return ToolResult.failure(msg, "busy" if "bận" in msg else "failed")
    return ToolResult.success(f"Em đang viết code cho “{truncate(prompt, 60)}”. Khi xong code sẽ hiện trên bảng Sinh "
                              "code để anh xem trước; em không tự sao chép.", verified=True, in_progress=True)


def h_refine(args: dict, ctx: Any) -> ToolResult:
    svc = _svc(ctx)
    if svc is None:
        return _unavailable()
    ok, msg = svc.refine(args.get("instruction", ""), use_run_output=bool(args.get("fix_run_errors", False)))
    if not ok:
        return ToolResult.failure(msg, "failed")
    return ToolResult.success("Em đang chỉnh sửa bản code hiện tại, xong sẽ hiện bản mới trên bảng.", verified=True,
                              in_progress=True)


def h_status(args: dict, ctx: Any) -> ToolResult:
    svc = _svc(ctx)
    if svc is None:
        return _unavailable()
    job = svc.job()
    cur = svc.current
    if job["state"] == "running":
        return ToolResult.success(f"{job['message']} ({job['progress'] * 100:.0f}%).", verified=True, **job)
    if cur is None:
        return ToolResult.success("Hiện chưa có bản code nào.", verified=True, state=job["state"])
    return ToolResult.success(f"Bản code gần nhất: «{cur.title}» ({len(cur.files)} tệp, kiểm tra: {cur.check_status}).",
                              verified=True, state=job["state"], title=cur.title,
                              files=[f.path for f in cur.files], check=cur.check_status)


def h_cancel(args: dict, ctx: Any) -> ToolResult:
    svc = _svc(ctx)
    if svc is None:
        return _unavailable()
    if svc.cancel("Người dùng hủy"):
        return ToolResult.success("Em đã hủy việc viết code.", verified=True)
    return ToolResult.success("Không có việc code nào đang chạy.", verified=True)


def h_open(args: dict, ctx: Any) -> ToolResult:
    svc = _svc(ctx)
    if svc is None:
        return _unavailable()
    svc.open_panel()
    return ToolResult.success("Em đã mở bảng Sinh code.", verified=True)


def h_close(args: dict, ctx: Any) -> ToolResult:
    svc = _svc(ctx)
    if svc is None:
        return _unavailable()
    if not svc.close_panel():
        return ToolResult.success("Bảng Sinh code đang không mở ạ.", verified=True)
    return ToolResult.success("Em đã đóng bảng Sinh code.", verified=True)


def h_run(args: dict, ctx: Any) -> ToolResult:
    svc = _svc(ctx)
    if svc is None:
        return _unavailable()
    if svc.current is None:                     # chưa có bản code do NEXA viết → chạy tệp đang mở trong VS Code
        return _run_active_file(svc)
    ok, msg = svc.run_tests()
    if not ok:
        return ToolResult.failure(msg, "failed")
    return ToolResult.success(f"Em đang chạy thử trong thư mục tạm: {msg}", verified=True, in_progress=True)


def _run_path(svc: Any, path: Any, warn: str = "") -> ToolResult:
    ok, msg = svc.run_file(path)
    if not ok:
        return ToolResult.failure(warn + msg, "failed")
    return ToolResult.success(warn + msg, verified=True, in_progress=True, path=str(path))


def _run_active_file(svc: Any) -> ToolResult:
    from nexa.desktop.office import vscode_active_file
    path, dirty, why = vscode_active_file()
    if path is None:
        return ToolResult.failure(why + " Anh có thể nói “chạy thử file <tên tệp>”.", "not_found")
    warn = f"Lưu ý: {path.name} trong VS Code chưa được lưu, em chạy bản đã lưu trên đĩa. " if dirty else ""
    return _run_path(svc, path, warn)


def h_run_file(args: dict, ctx: Any) -> ToolResult:
    """Chạy thử một tệp có sẵn trên máy: theo tên (tìm giống 'mở file'), hoặc tệp đang mở trong VS Code."""
    svc = _svc(ctx)
    if svc is None:
        return _unavailable()
    name = (args.get("name") or "").strip()
    if not name:
        return _run_active_file(svc)
    return ctx.services.files.open_by_name(name, "file", args.get("folder"), cancelled=lambda: ctx.token.cancelled,
                                           app="run")


def register_code_tools(reg: Any, config: Any) -> None:
    from nexa.ai.tool_registry import S_BOOL, S_STR, ToolSpec, obj
    enabled = lambda: bool(config.get("code.enabled", True))  # noqa: E731

    def spec(name, title, desc, params, handler, **kw):
        kw.setdefault("needs_control", False)
        reg.register(ToolSpec(name, title, desc, params, handler, ai_enabled=enabled, **kw))

    spec("generate_code", "Sinh code",
         "Viết code/script/hàm/lớp/API/truy vấn SQL/regex/kiểm thử cho công việc lập trình của anh. Chạy NỀN và trả ngay; "
         "NEXA tự kiểm tra cú pháp, nhờ Gemini sửa lỗi, rồi hiện code (tô màu, số dòng) trên bảng Sinh code để anh xem "
         "trước — không tự sao chép hay chạy. Truyền NGUYÊN yêu cầu của anh vào prompt (giữ tên hàm, kiểu dữ liệu, ràng "
         "buộc, ví dụ). Dùng công cụ này thay vì đọc code thành tiếng.",
         obj({"prompt": S_STR("Yêu cầu đầy đủ của anh (tiếng Việt hoặc Anh)", 4000, minLength=4),
              "language": {"type": "string", "enum": LANGS, "default": "auto",
                           "description": "Ngôn ngữ nếu anh nói rõ; không rõ thì auto"}}, ["prompt"]),
         h_generate)
    spec("refine_code", "Chỉnh sửa code",
         "Chỉnh sửa bản code đang hiện trên bảng Sinh code theo yêu cầu mới (thêm tính năng, đổi ngôn ngữ, tối ưu, sửa "
         "lỗi). fix_run_errors=true: sửa theo kết quả chạy thử bị lỗi.",
         obj({"instruction": S_STR("Yêu cầu chỉnh sửa", 2000),
              "fix_run_errors": S_BOOL("Sửa theo lỗi của lần chạy thử gần nhất", default=False)}), h_refine)
    spec("get_code_status", "Tiến độ sinh code", "Xem tiến độ viết code hoặc tóm tắt bản code gần nhất.", obj({}),
         h_status, allowed_when_paused=True)
    spec("cancel_code_job", "Hủy sinh code", "Hủy việc viết/chỉnh sửa/chạy thử code đang chạy.", obj({}), h_cancel,
         allowed_when_paused=True)
    spec("open_code_panel", "Mở bảng Sinh code", "Mở bảng Sinh code (xem lại bản code, lịch sử).", obj({}), h_open,
         allowed_when_paused=True)
    spec("close_code_panel", "Đóng bảng Sinh code", "Đóng bảng Sinh code (việc đang chạy vẫn tiếp tục chạy nền).",
         obj({}), h_close, allowed_when_paused=True)
    spec("run_code_tests", "Chạy thử code",
         "Chạy thử bản code hiện tại trên bảng Sinh code (kiểm thử hoặc tệp chính; mọi ngôn ngữ có trình biên dịch/thông "
         "dịch trên máy: Python, JS/TS, C/C++, C#, Java, Go, Rust, PHP, PowerShell, SQL…) trong thư mục tạm có giới hạn "
         "thời gian. Chưa có bản code nào thì chạy tệp đang mở trong VS Code. Đây là chạy code thật trên máy — chỉ dùng "
         "khi anh yêu cầu.", obj({}), h_run,
         risk=lambda a, c: Assessment(Risk.MEDIUM, "Chạy code trên máy (thư mục tạm, có giới hạn thời gian)."))
    spec("run_file", "Chạy thử tệp",
         "Chạy thử MỘT TỆP CÓ SẴN trên máy (mọi ngôn ngữ: .py .js .ts .c .cpp .cs .java .go .rs .php .ps1 .bat .sh .sql "
         ".rb .pl .lua…) — kết quả hiện ngay trong bảng Sinh code của NEXA (đầu ra trực tiếp, ô nhập dữ liệu, trang HTML xem tại chỗ). name: tên tệp "
         "như anh nói (kể cả nghe sai kiểu 'men chấm bay'); bỏ trống name = tệp đang mở trong VS Code. Chỉ dùng khi anh "
         "yêu cầu chạy.",
         obj({"name": S_STR("Tên tệp (tùy chọn; trống = tệp đang mở trong VS Code)"),
              "folder": S_STR("Chỉ tìm trong thư mục này (tùy chọn)")}), h_run_file,
         risk=lambda a, c: Assessment(Risk.MEDIUM, "Chạy một chương trình trên máy."))
