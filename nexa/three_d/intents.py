"""Mẫu câu tiếng Việt cho mô hình 3D, chạy cục bộ trong IntentRouter (không cần Gemini).

- Tạo mô hình: "tạo/dựng/thiết kế (mô hình 3D) <vật thể>" khi vật thể thuộc nhóm hỗ trợ hoặc câu có chữ "mô hình 3D".
  Không bắt nhầm "tạo thư mục", "tạo file word".
- Lệnh viewer chỉ khớp khi viewer ĐANG MỞ; lệnh nhắm bộ phận chỉ khớp khi tên đó có trong mô hình (nên "xem thông tin
  hệ thống", "phóng to cửa sổ" vẫn là lệnh cũ).
Trả về (kind, calls, reply, resume) để IntentRouter bọc thành Route.
"""
from __future__ import annotations

import re
from typing import Callable

from nexa.three_d.planner import detect_category

Out = tuple[str, list[tuple[str, dict]], str, str | None]

PROVIDER_3D = r"(?:hugging ?face|\bhf\b|trellis|hunyuan|tripo|meshy)"
GEN_VERB = (r"^(?:hay |giup (?:anh|toi|minh) |(?:dung |bang |qua )?" + PROVIDER_3D +
            r" (?:de |giup (?:anh|toi|minh) )?)?(?:tao|dung|thiet ke|ve|lam|mo phong|sinh|gen|generate|create|model)\b")
GEN_OBJECT_3D = r"\b(mo hinh|model|ban mo phong)( 3d| ba chieu)?\b|\b3d\b|" + PROVIDER_3D
STATUS = re.compile(r"^(?:tien do|trang thai)( tao)? mo hinh|^mo hinh( 3d)?( (tao|lam))? (xong|den dau|toi dau)( chua)?|"
                    r"^(?:da )?tao (xong )?mo hinh (chua|xong chua)")
CANCEL = re.compile(r"^(?:huy|dung|ngung|thoi)( viec)? (tao|dung) mo hinh")
OPEN_MODEL = re.compile(r"^(?:mo|xem|hien)( lai)? (?:mo hinh|model)( 3d)?( (vua tao|moi tao|cuoi|gan nhat|vua roi|do|nay))?$")
LIST_MODELS = re.compile(r"^(?:danh sach|liet ke|co nhung|xem cac) mo hinh")
# "Đóng mô hình UAV cho tôi", "tắt trình xem 3D", "thoát mô hình đi": luôn khả dụng (đóng cả khung tạo mô hình khi chưa
# mở viewer). Tên mô hình tùy ý nhưng không chứa từ nối nhiều bước hay lệnh viewer ("tắt chuyển động mô hình").
_CLOSE_LEAD = r"^(?:(?:hay|em|nexa|oi|lam on|giup (?:anh|toi|minh))\s+)*(?:dong|tat|thoat|close)(?: khoi| lai| het)?(?: cai)?"
_CLOSE_TAIL = r"(?: (?:cho|giup|ho) (?:toi|anh|minh|em))?(?: (?:di|nhe|lai|luon|nay|do|ngay|dum|giup))*$"
_CLOSE_NAME = (r"(?: (?!(?:.* )?(?:va|roi|sau do|chuyen dong|hoat dong|animation|quay|xoay|tach|lap|snap)(?: |$))"
               r"[a-z0-9][a-z0-9 .\-]{0,40}?)?")
CLOSE_MODEL = re.compile(
    _CLOSE_LEAD + r"(?: (?:trinh xem|viewer|che do xem|cua so|khung|man hinh|bang|giao dien)(?: xem)?)?"
    r" (?:mo hinh|model)(?: 3d| ba chieu)?" + _CLOSE_NAME + _CLOSE_TAIL + "|"
    + _CLOSE_LEAD + r" (?:trinh xem|viewer|che do xem|cua so|khung|man hinh|giao dien)(?: xem)? (?:3d|ba chieu)" + _CLOSE_TAIL
    + "|" + _CLOSE_LEAD + r" (?:trinh xem|viewer|che do xem)" + _CLOSE_TAIL)


def route_3d(orig: str, fold_text: str, viewer_active: bool,
             part_known: Callable[[str], bool] | None = None) -> Out | None:
    u = fold_text
    if not u:
        return None
    # ----- tiến độ / hủy / mở / liệt kê (luôn khả dụng) -----
    if STATUS.search(u):
        return "basic", [("get_3d_job_status", {})], "", None
    if CANCEL.search(u):
        return "basic", [("cancel_3d_job", {})], "", None
    if OPEN_MODEL.match(u):
        return "basic", [("open_3d_model", {})], "", None
    if LIST_MODELS.search(u):
        return "basic", [("list_3d_models", {})], "", None
    if CLOSE_MODEL.match(u):
        return "basic", [("close_3d_viewer", {})], "", None
    # ----- tạo mô hình -----
    # "dừng …" (có dấu) là lệnh dừng, không phải "dựng …"; câu hỏi/tính toán về thiết bị không phải yêu cầu dựng mô hình
    stop_word = bool(re.match(r"\s*dừng\b", (orig or "").lower()))
    if re.match(GEN_VERB, u) and not stop_word:
        cat = detect_category(orig)
        mentions_3d = bool(re.search(GEN_OBJECT_3D, u))
        blocked = re.search(r"\b(thu muc|folder|file|tep|tai lieu|van ban|bang tinh|slide|thuyet trinh|word|excel|"
                            r"powerpoint|ghi chu|nhac nho|lich|email|thu|playlist)\b", u)
        if not mentions_3d and re.search(r"\b(so do|bieu do|do thi|bai tap|bai giai|cong thuc|giai thich|tinh toan|"
                                         r"nhu the nao|la gi|tai sao|vi sao|bao nhieu tien|gia bao nhieu|mua|dat hang|"
                                         r"sua chua|bao duong|thay the|lap dat)\b", u):
            blocked = True
        if (cat != "generic" or mentions_3d) and not blocked:
            quality = "high" if re.search(r"chat luong cao|chi tiet cao|high quality|dep nhat|sieu chi tiet", u) else "standard"
            mode = "cloud" if re.search(r"\b(bang|dung|qua) (cloud|dich vu)\b|" + PROVIDER_3D, u) else "auto"
            args = {"prompt": orig.strip()}
            if quality != "standard":
                args["quality"] = quality
            if mode != "auto":
                args["mode"] = mode
            return "basic", [("generate_3d_model", args)], "", None
    if not viewer_active:
        return None
    # ----- lệnh viewer (chỉ khi đang mở) -----
    if re.fullmatch(r"(tach|thao|bung|mo)( roi)?( cac| tat ca| toan bo)?( bo phan| chi tiet| linh kien| mo hinh| assembly)?"
                    r"( ra)?( di| giup (anh|toi))?|exploded? view|che do tach|xem (dang|kieu) tach", u) and \
            not re.search(r"\btach rieng\b", u) and (re.search(r"\b(tach|bung|thao|exploded?)\b", u)):
        return "basic", [("explode_3d_assembly", {})], "", None
    if re.fullmatch(r"(lap|ghep|rap|thu|gom)( mo hinh| cac bo phan| cac chi tiet| lai mo hinh)?( lai)?( nhu cu)?( di)?|"
                    r"collapse|lap lai|ghep lai", u) and re.search(r"\b(lap|ghep|rap|thu|gom|collapse)\b", u):
        return "basic", [("collapse_3d_assembly", {})], "", None
    if re.fullmatch(r"(hien|hien thi|mo)( lai)? (toan bo|tat ca|het|day du)( mo hinh| bo phan| cac bo phan)?|hien lai( het)?", u):
        return "basic", [("show_all_3d_parts", {})], "", None
    if re.fullmatch(r"(dat lai|khoi phuc|reset|ve)( lai)? (goc nhin|camera|goc xem|view)( ban dau| mac dinh)?|goc nhin ban dau", u):
        return "basic", [("reset_3d_view", {})], "", None
    if re.fullmatch(r"(dung|tat|ngung|tam dung|ngat)( het)? (chuyen dong|hoat dong|animation|hoat hinh|chay|mo phong)"
                    r"( lai)?( cua)?( mo hinh| no)?( di| lai)?|cho (mo hinh |no )?(dung|ngung)( lai| chuyen dong)?( di)?|"
                    r"(mo hinh )?dung chuyen dong", u):
        return "basic", [("set_3d_motion", {"on": False})], "", None
    if re.fullmatch(r"(cho |bat |kich hoat |bat dau )?(mo hinh |no |cac bo phan )?(chuyen dong|hoat dong|van hanh|mo phong( hoat dong| chuyen dong)?)"
                    r"( mo hinh| thu| di| len| nao| xem| cho (anh|toi|em) xem)*|"
                    r"(bat|mo) (che do )?(chuyen dong|animation|hoat hinh)( di)?|(cho |bat )?chay (thu( mo hinh)?|mo hinh( thu)?)( di| xem)?|"
                    r"cho (mo hinh |no )?chay( thu)?( di| xem)?|animate", u):
        return "basic", [("set_3d_motion", {"on": True})], "", None
    m = re.fullmatch(r"(che do )?(x ?quang|x-?ray|xuyen thau|khung day|wireframe|binh thuong|thuong)( di)?", u)
    if m:
        w = m.group(2)
        mode = "xray" if re.search(r"quang|ray|xuyen", w) else "wireframe" if re.search(r"khung|wire", w) else "normal"
        return "basic", [("set_3d_render_mode", {"mode": mode})], "", None
    m = re.fullmatch(r"(quay|xoay)( mo hinh| goc nhin)?( sang| qua| len| xuong)? ?(trai|phai|len|xuong)(?: (\d{1,3}) (do|°))?", u)
    if m:
        d = {"trai": "left", "phai": "right", "len": "up", "xuong": "down"}[m.group(4)]
        args = {"direction": d}
        if m.group(5):
            args["degrees"] = float(max(1, min(180, int(m.group(5)))))
        return "basic", [("rotate_3d_view", args)], "", None
    if re.fullmatch(r"(phong to|zoom in|lai gan|to len)( mo hinh| len| them)?", u):
        return "basic", [("zoom_3d_view", {"direction": "in"})], "", None
    if re.fullmatch(r"(thu nho|zoom out|ra xa|lui ra)( mo hinh| lai)?( mo hinh)?", u) and ("mo hinh" in u or "zoom" in u or "ra" in u):
        return "basic", [("zoom_3d_view", {"direction": "out"})], "", None
    # ----- lệnh nhắm bộ phận -----
    m = re.match(r"^(quay|xoay) (bo phan nay|chi tiet nay|cai nay|(.+?)) (-?\d{1,3}) (do|°)(?: quanh truc (x|y|z))?$", u)
    if m:
        part = "bộ phận này" if m.group(3) is None else orig[m.start(3):m.end(3)].strip()
        if m.group(3) is None or part_known is None or part_known(part):
            args = {"part": part, "degrees": float(m.group(4))}
            if m.group(6):
                args["axis"] = m.group(6)
            return "basic", [("rotate_3d_part", args)], "", None
    m = re.match(r"^(dua|tra|lap)( lai)? (bo phan nay|chi tiet nay|cai nay|(.+?)) (ve|lai) (vi tri (lap|cu|ban dau)|cho cu)$", u)
    if m:
        part = "bộ phận này" if m.group(4) is None else orig[m.start(4):m.end(4)].strip()
        if m.group(4) is None or part_known is None or part_known(part):
            return "basic", [("reset_3d_part", {"part": part})], "", None
    patterns = [
        (r"^(an|giau|tat hien thi|bo)( di)? (?P<p>.+)$", "hide_3d_part"),
        (r"^(tach rieng|chi xem|chi hien|co lap|xem rieng) (?P<p>.+)$", "isolate_3d_part"),
        (r"^(thong tin|chuc nang|kich thuoc|cong dung)( cua)? (?P<p>.+)$", "show_3d_part_info"),
        (r"^(?P<p>.+?) (la gi|dung de lam gi|co chuc nang gi|kich thuoc bao nhieu)$", "show_3d_part_info"),
        (r"^(xem chi tiet|xem ky|phong to|zoom vao|zoom|soi|focus|cho (toi|anh|em|minh) xem|xem|nhin|hien)( vao)? (?P<p>.+)$",
         "focus_3d_part"),
    ]
    for pat, tool in patterns:
        m = re.match(pat, u)
        if not m:
            continue
        part = orig[m.start("p"):m.end("p")].strip(" .?!,")    # orig và fold cùng độ dài (IntentRouter._Text)
        if not part:
            continue
        if re.fullmatch(r"(cua so|ung dung|man hinh|trang|tab)( nay)?.*", m.group("p")):
            return None                                 # "phóng to cửa sổ" … là lệnh cửa sổ cũ
        if part_known is not None and not part_known(part):
            continue
        return "basic", [(tool, {"part": part})], "", None
    return None
