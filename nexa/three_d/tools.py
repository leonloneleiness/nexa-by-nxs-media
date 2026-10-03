"""Công cụ 3D trong tool registry chung (giọng nói, bàn phím, Gemini function calling đều gọi qua Executor).

Mọi công cụ needs_control=False (không đụng chuột/bàn phím máy thật). Tạo mô hình chỉ khởi động job nền và trả
job_id NGAY — không bao giờ chặn executor tuần tự. Dùng dịch vụ cloud (tốn credit) = rủi ro MEDIUM: khi Gemini tự đề
xuất thì hỏi anh xác nhận. Khi bộ phận mơ hồ, công cụ trả error_code "ambiguous" kèm câu hỏi và "resume" để câu trả lời
tiếp theo của anh ("trước trái") được ghép lại thành lệnh đầy đủ.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from nexa.core.events import Risk, ToolResult
from nexa.core.safety import Assessment
from nexa.utils.text import truncate


def _svc(ctx: Any):
    svc = getattr(ctx.services, "three_d", None)
    if svc is None or not svc.enabled:
        return None
    return svc


def _unavailable() -> ToolResult:
    return ToolResult.failure("Tính năng mô hình 3D đang tắt (three_d.enabled).", "unavailable")


def _result(ok: bool, msg: str, r: Any = None, resume_template: str = "", **data: Any) -> ToolResult:
    if ok:
        return ToolResult.success(msg, verified=True, **data)
    extra: dict[str, Any] = {}
    code = "failed"
    if r is not None and r.status == "ambiguous":
        code = "ambiguous"
        extra["options"] = r.options
        if resume_template:
            extra["resume"] = resume_template
    elif r is not None and r.status == "not_found":
        code = "not_found"
    elif "Chưa mở mô hình" in msg:
        code = "no_model"
    return ToolResult.failure(msg, code, **extra, **data)


# ------------------------------------------------------------------ handlers
def h_generate(args: dict, ctx: Any) -> ToolResult:
    svc = _svc(ctx)
    if svc is None:
        return _unavailable()
    prompt = args["prompt"].strip()
    questions = svc.precheck(prompt)
    if questions:
        suffix = " bằng CAD tham số" if args.get("mode") == "parametric" else " bằng cloud" if args.get("mode") == "cloud" else ""
        suffix += " chất lượng cao" if args.get("quality") == "high" else ""
        return ToolResult.failure(questions[0], "needs_input", questions=questions,
                                  resume=prompt.rstrip(" .") + suffix + ", {}")
    job = svc.submit(prompt, mode=args.get("mode", "auto"), quality=args.get("quality", "standard"),
                     source=ctx.source.value, open_when_ready=bool(args.get("open_when_ready", True)))
    return ToolResult.success(f"Em bắt đầu tạo mô hình “{truncate(prompt, 60)}”. Em sẽ báo và mở trình xem 3D khi xong "
                              f"(mã {job.id}).", verified=True, job_id=job.id, state=job.state.value, in_progress=True)


def h_status(args: dict, ctx: Any) -> ToolResult:
    svc = _svc(ctx)
    if svc is None:
        return _unavailable()
    job = svc.jobs.get(args["job_id"]) if args.get("job_id") else svc.jobs.latest()
    if job is None:
        return ToolResult.success("Hiện chưa có yêu cầu tạo mô hình nào.", verified=True, jobs=0)
    snap = job.snapshot()
    if job.terminal:
        msg = f"Yêu cầu {job.id}: {snap['label'].lower()}. {job.message}"
    else:
        msg = f"Đang {snap['label'].lower()} ({snap['progress'] * 100:.0f}%)."
    return ToolResult.success(msg, verified=True, **{k: snap[k] for k in ("id", "state", "progress", "project_id",
                                                                           "quality_score", "error")})


def h_cancel(args: dict, ctx: Any) -> ToolResult:
    svc = _svc(ctx)
    if svc is None:
        return _unavailable()
    if args.get("job_id"):
        ok = svc.jobs.cancel(args["job_id"], "Người dùng hủy")
        return ToolResult.success("Đã hủy yêu cầu tạo mô hình.", verified=True) if ok else \
            ToolResult.failure("Yêu cầu này đã kết thúc hoặc không tồn tại.", "not_found")
    n = svc.cancel_jobs("Người dùng hủy")
    return ToolResult.success(f"Đã hủy {n} yêu cầu tạo mô hình." if n else "Không có mô hình nào đang tạo.", verified=True,
                              cancelled=n)


def h_open(args: dict, ctx: Any) -> ToolResult:
    svc = _svc(ctx)
    if svc is None:
        return _unavailable()
    pid = args.get("project_id") or ""
    if not pid:
        name = (args.get("name") or "").strip()
        if name:
            from nexa.utils.text import fold
            hits = [p for p in svc.store.list_projects(60) if fold(name) in fold(p.get("name", "")) or
                    fold(name) in fold(p.get("prompt", ""))]
            if not hits:
                return ToolResult.failure(f"Em không thấy mô hình nào tên '{name}'.", "not_found")
            pid = hits[0]["id"]
        else:
            latest_job = svc.jobs.latest()
            pid = (latest_job.project_id if latest_job and latest_job.project_id else None) or svc.store.latest(ready_only=False) or ""
    if not pid:
        return ToolResult.failure("Chưa có mô hình nào. Anh nói 'tạo …' để em tạo mô hình mới.", "not_found")
    try:
        ok, msg = svc.viewer.open(pid)
    except Exception as exc:
        return ToolResult.failure(f"Không mở được mô hình: {exc}", "open_failed")
    return _result(ok, msg, project_id=pid)


def h_close(args: dict, ctx: Any) -> ToolResult:
    svc = _svc(ctx)
    if svc is None:
        return _unavailable()
    was_open = svc.viewer.is_open
    ok, msg = svc.viewer.close()
    svc._notify("3d_workspace", {"open": False})     # đóng cả khung Mô hình 3D (kể cả khi chỉ đang xem tiến độ tạo)
    if not was_open:
        msg = "Đã đóng cửa sổ mô hình 3D."
    return _result(ok, msg)


def _part_tool(method: str, template: str):
    def handler(args: dict, ctx: Any) -> ToolResult:
        svc = _svc(ctx)
        if svc is None:
            return _unavailable()
        part = args.get("part") or "bộ phận này"
        ok, msg, r = getattr(svc.viewer, method)(part)
        return _result(ok, msg, r, template.replace("{part}", part) if r is not None and r.status == "ambiguous" else "",
                       parts=r.part_ids if r is not None else [])
    return handler


def _simple(method: str):
    def handler(args: dict, ctx: Any) -> ToolResult:
        svc = _svc(ctx)
        if svc is None:
            return _unavailable()
        ok, msg = getattr(svc.viewer, method)()
        return _result(ok, msg)
    return handler


def h_motion(args: dict, ctx: Any) -> ToolResult:
    svc = _svc(ctx)
    if svc is None:
        return _unavailable()
    on = args.get("on", True)
    ok, msg = svc.set_animation(on if isinstance(on, bool) else str(on).lower() not in ("false", "0", "off"))
    return _result(ok, msg)


def h_rotate_view(args: dict, ctx: Any) -> ToolResult:
    svc = _svc(ctx)
    if svc is None:
        return _unavailable()
    deg = float(args.get("degrees", 45.0))
    d = args.get("direction", "right")
    dyaw = {"left": -deg, "right": deg}.get(d, 0.0)
    dpitch = {"up": deg, "down": -deg}.get(d, 0.0)
    ok, msg = svc.viewer.rotate_view(dyaw, dpitch)
    return _result(ok, msg)


def h_zoom(args: dict, ctx: Any) -> ToolResult:
    svc = _svc(ctx)
    if svc is None:
        return _unavailable()
    f = float(args.get("factor", 1.4))
    ok, msg = svc.viewer.zoom_view(f if args.get("direction", "in") == "in" else 1.0 / f)
    return _result(ok, msg)


def h_rotate_part(args: dict, ctx: Any) -> ToolResult:
    svc = _svc(ctx)
    if svc is None:
        return _unavailable()
    part = args.get("part") or "bộ phận này"
    ok, msg, r = svc.viewer.rotate_part(part, float(args.get("degrees", 90.0)), args.get("axis", "y"))
    return _result(ok, msg, r, f"quay {part} {{}} {args.get('degrees', 90):g} độ" if r is not None and r.status == "ambiguous" else "")


def h_render_mode(args: dict, ctx: Any) -> ToolResult:
    svc = _svc(ctx)
    if svc is None:
        return _unavailable()
    ok, msg = svc.viewer.set_render_mode(args["mode"])
    return _result(ok, msg)


def h_list(args: dict, ctx: Any) -> ToolResult:
    svc = _svc(ctx)
    if svc is None:
        return _unavailable()
    items = svc.store.list_projects(int(args.get("count", 8)))
    if not items:
        return ToolResult.success("Chưa có mô hình nào trong kho.", verified=True, models=[])
    names = "; ".join(f"{i['name']} ({i.get('quality_score', 0):.0f}/100{'' if i.get('status') == 'ready' else ', chưa đạt'})"
                      for i in items[:5])
    return ToolResult.success(f"Có {len(items)} mô hình gần đây: {names}.", verified=True,
                              models=[{k: i.get(k) for k in ("id", "name", "status", "quality_score", "category")} for i in items])


def h_export(args: dict, ctx: Any) -> ToolResult:
    svc = _svc(ctx)
    if svc is None:
        return _unavailable()
    from nexa.three_d.asset_store import export_project
    from nexa.utils.config import known_folder
    pid = args.get("project_id") or (svc.viewer.project.id if svc.viewer.project else svc.store.latest(ready_only=False))
    if not pid:
        return ToolResult.failure("Chưa có mô hình để xuất.", "not_found")
    dest = known_folder("Documents") / "NEXA 3D"
    try:
        path = export_project(svc.store, pid, args.get("format", "glb"), dest)
    except Exception as exc:
        return ToolResult.failure(f"Không xuất được: {exc}", "export_failed")
    note = " Lưu ý: tệp chỉ để hình dung/in thử — chưa kiểm chứng để chế tạo." if args.get("format") in ("stl", "3mf") else ""
    return ToolResult.success(f"Đã xuất {path.name} vào thư mục Tài liệu/NEXA 3D.{note}", verified=Path(path).exists(),
                              path=str(path))


def risk_generate(args: dict, ctx: Any) -> Assessment:
    mode = args.get("mode", "auto")
    svc = getattr(getattr(ctx, "services", None), "three_d", None)
    status: dict = {}
    if svc is not None:
        try:
            status = svc.provider_status()
        except Exception:
            status = {}
    where = (f"{status.get('name', 'dịch vụ 3D cloud')} (gửi mô tả lên dịch vụ ngoài"
             + (", miễn phí)" if status.get("free") else ", tốn credit)"))
    if mode == "cloud":
        return Assessment(Risk.MEDIUM, f"Dùng {where}.")
    if mode == "auto" and svc is not None:
        try:
            from nexa.three_d.planner import detect_category
            if detect_category(args.get("prompt", "")) == "generic" and status.get("ok"):
                return Assessment(Risk.MEDIUM, f"Vật thể ngoài nhóm hỗ trợ sẽ được tạo bằng {where}.")
        except Exception:
            pass
    return Assessment(Risk.LOW, "")


# ------------------------------------------------------------------ đăng ký
def register_3d_tools(reg: Any, config: Any) -> None:
    from nexa.ai.tool_registry import S_BOOL, S_INT, S_STR, ToolSpec, obj
    P = S_STR("Tên/mô tả bộ phận như anh nói, ví dụ 'cánh quạt trước trái', 'rotor chính', 'khớp gối chân phải'; "
              "'bộ phận này' = bộ phận đang chọn", 120, minLength=1)
    enabled = lambda: bool(config.get("three_d.enabled", True))  # noqa: E731
    add = reg.register

    def spec(name, title, desc, params, handler, **kw):
        kw.setdefault("needs_control", False)
        add(ToolSpec(name, title, desc, params, handler, ai_enabled=enabled, **kw))

    spec("generate_3d_model", "Tạo mô hình 3D",
         "Tạo mô hình 3D từ mô tả (UAV/drone, xe tự hành, robot hình người, robot chó, trực thăng, thuyền, bu-lông/đai ốc/vòng "
         "đệm/bánh răng/mặt bích/giá đỡ, ổ bi, động cơ bước NEMA, hộp số, xi lanh, van bi, co/tê/mặt bích ống DN, bộ truyền "
         "đai/xích, khớp nối, vít me bi, ray trượt, lò xo, cánh tay robot 6 trục, robot hút bụi, AGV/robot giao hàng, máy bay cánh "
         "bằng/UAV cánh cố định/VTOL, ô tô điện, xe máy/tay ga/xe đạp điện, máy xúc, xe nâng, xe cẩu, tàu hỏa/tàu điện, CubeSat, "
         "tên lửa nhiều tầng, tuabin gió, hệ điện mặt trời, máy phát điện, máy bơm, bồn chứa, cầu, giàn thép, tháp thép dựng bằng CAD "
         "tham số chính xác theo tiêu chuẩn; mọi vật thể khác — đồ vật, con vật, nhân vật… — "
         "bằng AI 3D: Hugging Face Space miễn phí (TRELLIS/Hunyuan3D) hoặc Tripo/Meshy nếu có key, dự phòng Gemini CAD). Chạy "
         "NỀN và trả job_id ngay; KHÔNG chờ xong. Truyền nguyên câu yêu cầu của anh vào prompt (giữ mọi con số). Không bịa "
         "kích thước.",
         obj({"prompt": S_STR("Mô tả đầy đủ bằng tiếng Việt, giữ nguyên số đo", 1000, minLength=3),
              "mode": {"type": "string", "enum": ["auto", "parametric", "cloud"], "default": "auto",
                       "description": "auto: NEXA tự chọn; cloud: dịch vụ AI 3D (Hugging Face miễn phí, Tripo/Meshy tốn "
                                      "credit) — dùng khi anh nói rõ tên dịch vụ"},
              "quality": {"type": "string", "enum": ["standard", "high"], "default": "standard"},
              "open_when_ready": S_BOOL("Mở trình xem khi xong", default=True)}, ["prompt"]),
         h_generate, risk=risk_generate)
    spec("get_3d_job_status", "Tiến độ tạo mô hình", "Xem trạng thái/tiến độ yêu cầu tạo mô hình 3D (mặc định gần nhất).",
         obj({"job_id": S_STR("Mã job (tùy chọn)", 40)}), h_status, allowed_when_paused=True)
    spec("cancel_3d_job", "Hủy tạo mô hình", "Hủy yêu cầu tạo mô hình 3D đang chạy (mặc định: mọi yêu cầu đang chạy).",
         obj({"job_id": S_STR("Mã job (tùy chọn)", 40)}), h_cancel, allowed_when_paused=True)
    spec("open_3d_model", "Mở mô hình 3D", "Mở mô hình trong trình xem 3D: mặc định mô hình vừa tạo; hoặc theo tên/mã.",
         obj({"project_id": S_STR("Mã dự án (tùy chọn)", 64), "name": S_STR("Tên mô hình (tùy chọn)", 80)}), h_open)
    spec("close_3d_viewer", "Đóng trình xem 3D", "Đóng mô hình 3D đang mở (trình xem và khung Mô hình 3D), trả cử chỉ tay về chế độ thường. Dùng khi anh nói 'đóng/tắt mô hình (tên)'.", obj({}), h_close,
         allowed_when_paused=True)
    spec("focus_3d_part", "Xem chi tiết bộ phận", "Căn giữa, phóng to và làm nổi bật một bộ phận (hoặc cả cụm) của mô hình "
         "đang mở, hiện tên/kích thước/chức năng. Nếu nhiều bộ phận trùng tên, công cụ trả câu hỏi lại.",
         obj({"part": P}, ["part"]), _part_tool("focus", "xem {part} {}"))
    spec("isolate_3d_part", "Tách riêng bộ phận", "Chỉ hiển thị bộ phận/cụm được chọn (ẩn phần còn lại).",
         obj({"part": P}, ["part"]), _part_tool("isolate_parts", "tách riêng {part} {}"))
    spec("hide_3d_part", "Ẩn bộ phận", "Ẩn bộ phận/nhóm bộ phận (ví dụ 'lớp vỏ' ẩn mọi phần vỏ).",
         obj({"part": P}, ["part"]), _part_tool("hide", "ẩn {part} {}"))
    spec("show_all_3d_parts", "Hiện toàn bộ", "Hiện lại mọi bộ phận, bỏ cô lập/tâm điểm.", obj({}), _simple("show_all"))
    spec("show_3d_part_info", "Thông tin bộ phận", "Đọc tên, kích thước, vật liệu, chức năng của một bộ phận.",
         obj({"part": P}, ["part"]), _part_tool("show_info", "thông tin {part} {}"), allowed_when_paused=True)
    spec("explode_3d_assembly", "Tách các bộ phận", "Exploded view theo trình tự tháo lắp của mô hình đang mở.", obj({}),
         _simple("explode"))
    spec("collapse_3d_assembly", "Lắp mô hình lại", "Đưa mọi bộ phận về vị trí lắp.", obj({}), _simple("collapse"))
    spec("reset_3d_view", "Đặt lại góc nhìn", "Về góc nhìn mặc định, khung toàn bộ mô hình.", obj({}), _simple("reset_view"))
    spec("set_3d_motion", "Bật/tắt chuyển động", "Cho mô hình đang mở chuyển động cơ bản (cánh quạt quay, bánh xe lăn, "
         "bánh răng ăn khớp, khớp robot, xi lanh…) hoặc dừng lại. Mô hình tĩnh thì xoay trưng bày.",
         obj({"on": {"type": "boolean", "default": True}}), h_motion)
    spec("rotate_3d_view", "Xoay mô hình", "Xoay góc nhìn mô hình sang trái/phải/lên/xuống một số độ.",
         obj({"direction": {"type": "string", "enum": ["left", "right", "up", "down"], "default": "right"},
              "degrees": {"type": "number", "minimum": 1, "maximum": 180, "default": 45}}), h_rotate_view)
    spec("zoom_3d_view", "Thu phóng mô hình", "Phóng to (in) hoặc thu nhỏ (out) khung nhìn 3D.",
         obj({"direction": {"type": "string", "enum": ["in", "out"], "default": "in"},
              "factor": {"type": "number", "minimum": 1.05, "maximum": 4, "default": 1.4}}), h_zoom)
    spec("rotate_3d_part", "Quay bộ phận", "Quay riêng một bộ phận quanh tâm của nó (ví dụ 'quay bộ phận này 90 độ').",
         obj({"part": P, "degrees": {"type": "number", "minimum": -360, "maximum": 360, "default": 90},
              "axis": {"type": "string", "enum": ["x", "y", "z"], "default": "y"}}), h_rotate_part)
    spec("reset_3d_part", "Đưa bộ phận về vị trí lắp", "Bỏ phép quay riêng và đưa bộ phận về vị trí lắp (kể cả khi đang tách).",
         obj({"part": P}), _part_tool("reset_part", "đưa {part} {} về vị trí lắp"))
    spec("set_3d_render_mode", "Chế độ hiển thị 3D", "Đổi chế độ hiển thị: thường, X-quang (xuyên thấu) hoặc khung dây.",
         obj({"mode": {"type": "string", "enum": ["normal", "xray", "wireframe"]}}, ["mode"]), h_render_mode)
    spec("list_3d_models", "Danh sách mô hình", "Liệt kê các mô hình 3D đã tạo gần đây.",
         obj({"count": S_INT("Số mô hình", 1, 30, default=8)}), h_list, allowed_when_paused=True)
    spec("export_3d_model", "Xuất mô hình 3D", "Xuất mô hình (mặc định đang mở) ra Tài liệu/NEXA 3D dạng GLB/STL/OBJ/3MF. "
         "Không ghi đè tệp có sẵn. Không tạo G-code.",
         obj({"format": {"type": "string", "enum": ["glb", "stl", "obj", "3mf"], "default": "glb"},
              "project_id": S_STR("Mã dự án (tùy chọn)", 64)}), h_export)
