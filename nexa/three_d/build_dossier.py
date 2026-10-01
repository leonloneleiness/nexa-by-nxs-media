"""Build preparation for existing/new projects. Visual parts are NOT a purchasing BOM.

User sourcing notes persist outside the evictable asset cache. No supplier, fit,
load rating or physical assembly is marked verified by this module.
"""
from __future__ import annotations

import hashlib
import html
import json
import math
import os
import tempfile
import threading
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from nexa.three_d.build_profiles import PURCHASE_ASSEMBLIES, SOURCES, requirements

_LOCK = threading.RLock()
ASSEMBLY_ID = "@assembly"
NOTICE = ("Hồ sơ chuẩn bị chế tạo — chưa xác minh lắp ráp thực tế. Kích thước hình học không thay thế "
          "bản vẽ có dung sai. Số chi tiết đồ họa không phải số lượng cần mua.")
BUY_PARTS = {"motor", "battery", "camera", "lidar", "bearing", "bolt", "nut", "washer", "servo", "sensor",
             "connector", "cable", "wheel", "propeller", "controller", "fan"}
MAKE_PARTS = {"frame", "shell", "bracket", "plate", "cover", "chassis", "housing"}
MODES = {"unknown": "Chưa phân loại", "buy": "Mua sẵn", "make": "Tự gia công", "reference": "Tham chiếu nội bộ"}


def fingerprint(project):
    raw = json.dumps({"spec": project.spec, "parts": [p.to_dict() for p in project.parts],
                      "materials": [m.to_dict() for m in project.materials], "bounds": project.bounds.to_dict(),
                      "fit_scale": project.metadata.get("fit_scale", 1),
                      "generator": project.generator_version, "units": project.units}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _record_path(project_id, root=None):
    if root is None:
        from nexa.utils.config import LOCAL_DATA_DIR
        root = LOCAL_DATA_DIR / "build_records"
    # IDs never become filesystem paths.
    return Path(root) / (hashlib.sha256(project_id.encode()).hexdigest() + ".json")


def load_records(project, root=None):
    path = _record_path(project.id, root)
    if not path.exists():
        return {}, False
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("project_id") != project.id or not isinstance(data.get("parts"), dict):
        raise ValueError("Hồ sơ linh kiện không hợp lệ; không tự ghi đè.")
    return data["parts"], data.get("fingerprint") != fingerprint(project)


def save_record(project, part_id, record, root=None):
    if part_id != ASSEMBLY_ID and project.part(part_id) is None:
        raise ValueError("Bộ phận không tồn tại.")
    mode = record.get("mode", "unknown")
    if mode not in MODES:
        raise ValueError("Loại cung ứng không hợp lệ.")
    clean = {k: str(record.get(k) or "").strip() for k in ("manufacturer", "model_number", "url", "notes")}
    if any(len(v) > 4000 for v in clean.values()):
        raise ValueError("Nội dung quá dài (tối đa 4000 ký tự mỗi trường).")
    if clean["url"]:
        u = urlsplit(clean["url"])
        if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password:
            raise ValueError("Nguồn linh kiện phải là địa chỉ HTTP/HTTPS hợp lệ.")
    qty = record.get("quantity")
    if qty in (None, "", 0):
        qty = None
    elif isinstance(qty, bool) or not isinstance(qty, int) or not 1 <= qty <= 100000:
        raise ValueError("Số lượng phải là số nguyên 1–100000, hoặc 0 nếu chưa biết.")
    clean.update(mode=mode, quantity=qty, verification="user_entered_unverified",
                 fingerprint=fingerprint(project))
    with _LOCK:
        records, _ = load_records(project, root)
        records[part_id] = clean
        path = _record_path(project.id, root)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as out:
                json.dump({"project_id": project.id, "fingerprint": fingerprint(project), "parts": records}, out,
                          ensure_ascii=False, indent=2)
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)


def build_dossier(project, records=None):
    records = records or {}
    fp = fingerprint(project)
    whole = project.category in PURCHASE_ASSEMBLIES
    rows = []
    material_names = {m.id: m.name for m in project.materials}

    def row(pid, name, category, parent, dimensions, bounds, material, suggestion):
        rec = records.get(pid, {})
        stale = bool(rec) and rec.get("fingerprint") != fp
        missing = []
        mode = rec.get("mode", "unknown")
        if mode == "unknown":
            missing.append("Chọn mua sẵn / tự gia công / tham chiếu")
        if mode == "buy":
            if not rec.get("model_number"):
                missing.append("Mã linh kiện cụ thể")
            if not rec.get("url"):
                missing.append("Nguồn mua hoặc datasheet")
            missing.append("Đối chiếu kích thước ghép và thông số vận hành")
        if mode == "make":
            missing.append("Bản vẽ có dung sai, vật liệu thực và quy trình gia công")
        if mode in ("make", "buy") and not rec.get("quantity"):
            missing.append("Số lượng vật lý (không suy ra từ số mesh)")
        if stale:
            missing.append("Mô hình đã thay đổi: cần đối chiếu lại ghi chú cũ")
        return {"id": pid, "name": name, "category": category, "parent": parent,
                "dimensions": dimensions, "bounds": bounds, "material_visual": material,
                "suggestion": suggestion, "mode": mode, "mode_label": MODES.get(mode, MODES["unknown"]),
                "record": rec, "stale": stale, "missing": missing, "verified": False}

    rows.append(row(ASSEMBLY_ID, project.name + " — toàn bộ sản phẩm", project.category, "", {},
                    project.bounds.to_dict(), "", "Ưu tiên tìm mua nguyên cụm; chi tiết bên trong chỉ minh họa."
                    if whole else "Xác định cấu hình sản phẩm và yêu cầu sử dụng trước khi chọn linh kiện."))
    for p in project.parts:
        suggestion = ("Chi tiết trong cụm mua sẵn; không tự cộng vào danh sách mua." if whole else
                      "Có thể mua sẵn; cần chọn mã cụ thể." if p.category in BUY_PARTS else
                      "Có thể cần gia công; phải có bản vẽ và dung sai." if p.category in MAKE_PARTS else
                      "Cần xác định đây là linh kiện, cụm hay chi tiết minh họa.")
        rows.append(row(p.id, p.name_vi, p.category, p.parent_id or "", p.dimensions, p.bounds.to_dict(),
                        material_names.get(p.material, p.material), suggestion))
    blockers = ["Chưa có bộ bản vẽ chế tạo và dung sai đã duyệt.",
                "Chưa kiểm chứng các giao diện lắp ghép và danh sách linh kiện thực.",
                "Chưa có hướng dẫn lắp ráp vật lý, thử tải và biên bản chạy thử."]
    if project.units != "mm":
        blockers.append("Đơn vị mô hình chưa phải mm; phải xác minh quy đổi.")
    if project.generation_mode != "parametric" or not project.has_assembly:
        blockers.append("Mô hình AI/không có cấu trúc: cần thiết kế kỹ thuật lại trước khi chế tạo.")
    scale = project.metadata.get("fit_scale", 1)
    if not isinstance(scale, (int, float)) or not math.isfinite(scale) or abs(scale - 1) > 1e-6:
        blockers.append("Mô hình đã co giãn: mã và kích thước linh kiện tiêu chuẩn có thể không còn khớp.")
    return {"schema_version": 1, "project_id": project.id, "name": project.name, "category": project.category,
            "fingerprint": fp, "units": project.units, "ready_to_build": False, "notice": NOTICE,
            "rows": rows, "requirements": requirements(project.category), "blockers": blockers,
            "references": SOURCES.get(project.category, []),
            "assembly": {"status": "missing", "note": "Thứ tự tách hình chỉ phục vụ xem cấu tạo; không phải hướng dẫn lắp thật."}}


def export_dossier(dossier, destination):
    """A portable, escaped HTML report + machine-readable JSON, no external assets/scripts."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    folder = destination / ("ho_so_" + uuid.uuid4().hex[:12])
    folder.mkdir()
    esc = lambda x: html.escape(str(x), quote=True)
    li = lambda items: "<ul>" + "".join("<li>" + esc(x) + "</li>" for x in items) + "</ul>"
    rows = []
    for r in dossier["rows"]:
        rec = r["record"]
        rows.append("<tr>" + "".join("<td>" + esc(x) + "</td>" for x in (
            r["id"], r["name"], r["mode_label"], rec.get("quantity") or "Chưa xác định",
            rec.get("manufacturer", ""), rec.get("model_number", ""), rec.get("url", ""),
            json.dumps(r["dimensions"], ensure_ascii=False), r["suggestion"], "; ".join(r["missing"]),
            rec.get("notes", ""))) + "</tr>")
    content = ("<!doctype html><html lang='vi'><meta charset='utf-8'><title>Hồ sơ chuẩn bị chế tạo</title>"
               "<style>body{font:16px system-ui;margin:32px;color:#142332}table{border-collapse:collapse;width:100%}"
               "td,th{border:1px solid #ccd5df;padding:8px;text-align:left;overflow-wrap:anywhere}"
               "th{background:#edf2f7}h1{font-size:26px}</style><h1>" + esc(dossier["name"]) + "</h1><p>" +
               esc(dossier["notice"]) + "</p><h2>Thông số cần hoàn thiện</h2>" + li(dossier["requirements"]) +
               "<h2>Chưa đủ điều kiện chế tạo</h2>" + li(dossier["blockers"]) +
               "<h2>Bảng đối chiếu linh kiện — chưa phải BOM đã duyệt</h2><p>Đơn vị mô hình: " + esc(dossier["units"]) +
               ". Vật liệu hiển thị và kích thước mesh chưa xác nhận vật liệu chế tạo/dung sai.</p><table><tr>" +
               "".join("<th>" + x + "</th>" for x in ["ID", "Bộ phận", "Cách cung ứng", "SL thực", "Hãng", "Mã",
                                                     "Nguồn", "Thông số mô hình", "Gợi ý", "Còn thiếu", "Ghi chú"]) +
               "</tr>" + "".join(rows) + "</table><h2>Lắp ráp</h2><p>" + esc(dossier["assembly"]["note"]) +
               "</p><h2>Tài liệu tham khảo</h2>" + li([s["title"] + ": " + s["url"] for s in dossier["references"]]) + "</html>")
    try:
        (folder / "dossier.json").write_text(json.dumps(dossier, ensure_ascii=False, indent=2), encoding="utf-8")
        report = folder / "ho_so.html"
        report.write_text(content, encoding="utf-8")
        return report
    except Exception:
        for p in folder.iterdir():
            p.unlink()
        folder.rmdir()
        raise
