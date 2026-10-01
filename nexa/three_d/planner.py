"""Planner: câu yêu cầu tự nhiên → ModelSpec đã kiểm tra.

1) LocalPlanner (không cần mạng): nhận dạng nhóm và thông số bằng mẫu tiếng Việt/Anh ("bu-lông M8 dài 30 mm, bước ren
   1,25 mm", "UAV bốn cánh camera phía trước", "robot chó mỗi chân ba khớp"…). Luôn chạy để trích SỐ ĐO NGƯỜI DÙNG
   NÓI RÕ (explicit) — dùng để đối chiếu kết quả Gemini.
2) GeminiPlanner: Gemini trả JSON theo response_json_schema (MODEL_SPEC_SCHEMA); NEXA kiểm tra lại nghiêm ngặt bằng
   spec.validate_spec. Kết quả sai schema → dùng kết quả local (ghi cảnh báo). Số đo người dùng nói rõ luôn thắng.
3) Thiếu thông số BẮT BUỘC (ví dụ bu-lông không có chiều dài) → trả câu hỏi, không đoán.
4) Vật thể ngoài nhóm hỗ trợ: Gemini mô tả bằng CAD DSL (best effort) nếu không dùng dịch vụ cloud.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from nexa.three_d.spec import (CATEGORY_VI, MODEL_SPEC_SCHEMA, PARAM_SCHEMAS, ModelSpec, SpecError, is_complete,
                               normalize, validate_spec)
from nexa.utils.logging import get_logger
from nexa.utils.text import strip_accents

log = get_logger("3d.planner")


@dataclass
class PlanResult:
    spec: ModelSpec | None
    questions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source: str = "local"
    dsl_parts: list[dict] | None = None
    raw: dict | None = None


def _fold(text: str) -> str:
    t = strip_accents((text or "").lower())
    t = re.sub(r"(\d),(\d)", r"\1.\2", t)             # 1,25 → 1.25
    return re.sub(r"\s+", " ", t).strip()


NUM = r"(\d+(?:\.\d+)?)"
UNIT = r"\s*(mm|cm|m|met|milimet|centimet|inch|in|\")?"
VI_NUMS = {"mot": 1, "hai": 2, "ba": 3, "bon": 4, "tu": 4, "nam": 5, "sau": 6, "bay": 7, "tam": 8, "chin": 9, "muoi": 10}


def _to_mm(val: str, unit: str | None, default_unit: str = "mm") -> float:
    v = float(val)
    u = (unit or default_unit).strip().lower()
    return v * {"mm": 1, "milimet": 1, "cm": 10, "centimet": 10, "m": 1000, "met": 1000, "inch": 25.4, "in": 25.4,
                '"': 25.4}.get(u, 1)


def _count(u: str, noun: str) -> int | None:
    m = re.search(rf"\b(\d+|mot|hai|ba|bon|tu|nam|sau|bay|tam)\s+{noun}", u)
    if not m:
        return None
    g = m.group(1)
    return int(g) if g.isdigit() else VI_NUMS.get(g)


CATEGORY_PATTERNS: list[tuple[str, str]] = [
    ("quadruped", r"robot (hinh )?cho|cho robot|robot bon chan|robot 4 chan|quadruped|robot dog|robo dog"),
    ("humanoid", r"robot hinh nguoi|nguoi may|humanoid|robot nguoi\b|robot dang nguoi"),
    ("helicopter", r"truc thang|helicopter|may bay len thang"),
    ("boat", r"du thuyen|\bthuyen\b|ca no\b|\bcano\b|xuong may|\bxuong\b|tau thuy|tau ca\b|tau danh ca|tau tuan tra|"
             r"tau cao toc|tau canh sat bien|tau cuu ho|\bboat\b|\bship\b|\byacht\b|speedboat|"
             r"\btau\b(?! (?:hoa|dien|vu tru|luon|bay|con thoi|ngam|cao toc bac nam))"),
    ("uav", r"\buav\b|drone|flycam|may bay khong nguoi lai|quadcopter|quadrotor|hexacopter|octocopter|multirotor|"
            r"multicopter|phi co khong nguoi lai"),
    ("rover", r"xe tu hanh|rover|xe robot|robot xe|xe tu lai|xe tham hiem|robot di dong"),
    ("nut", r"dai oc|\be ?cu\b|con tan\b|\btan\b|\bnut\b"),
    ("washer", r"vong dem|long den|\bwasher\b"),
    ("bolt", r"bu ?-?long|bulong|\bbolt\b|\boc vit\b|\boc luc giac\b|\bvit\b|\bscrew\b|\boc\b"),
    ("gear", r"banh rang|\bnhong\b|\bgear\b"),
    ("flange", r"mat bich|\bflange\b"),
    ("bracket", r"gia do|ke goc|bat chu l|\bbracket\b|\bpat\b"),
]


# Tầng ưu tiên của nhóm gốc (giữ đúng thứ tự cũ); nhóm kỹ thuật mở rộng khai tầng trong parse_tech.TECH_PATTERNS.
_BASE_TIERS = {"quadruped": 10, "humanoid": 11, "helicopter": 12, "boat": 14, "uav": 16, "rover": 18, "nut": 60,
               "washer": 61, "bolt": 62, "gear": 63, "flange": 64, "bracket": 65}


def _all_patterns() -> list[tuple[str, str, int]]:
    from nexa.three_d.parse_tech import TECH_PATTERNS
    return [(c, pat, _BASE_TIERS[c]) for c, pat in CATEGORY_PATTERNS] + list(TECH_PATTERNS)


def detect_category(text: str) -> str:
    """Loại mô hình theo mẫu câu: tầng ưu tiên nhỏ hơn thắng; cùng tầng thì từ khóa xuất hiện sớm nhất trong câu thắng
    ("hộp số có ổ bi" là hộp số, "tủ rack có quạt" là tủ rack)."""
    u = _fold(text)
    best: tuple[tuple[int, int], str] | None = None
    for cat, pat, tier in _all_patterns():
        m = re.search(pat, u)
        if not m:
            continue
        # "đai ốc" chứa "ốc" — nut xét trước bolt; "bu lông có đai ốc" vẫn là bu-lông
        if cat in ("nut", "washer") and re.search(r"bu ?-?long|bulong|\bbolt\b", u):
            continue
        # "cầu" (cây cầu) và "cẩu" (xe cẩu) cùng bỏ dấu thành "cau": câu có dấu mà chỉ có "cầu" → không phải xe cẩu
        low = text.lower()
        if cat == "crane" and "cầu" in low and "cẩu" not in low and not re.search(r"crane|cần trục|cầu trục", low):
            continue
        if cat == "bridge" and "cẩu" in low and "cầu" not in low:
            continue
        # "từ điển" cũng bỏ dấu thành "tu dien"
        if cat == "electrical_enclosure" and "từ điển" in low and "tủ điện" not in low:
            continue
        # "tản nhiệt tháp" là tản nhiệt CPU; "thanh răng (rack)" là bánh răng, không phải tủ rack
        if cat == "lattice_tower" and "tan nhiet" in u:
            continue
        if cat == "server_rack" and re.search(r"thanh rang|banh rang|pinion", u) and not re.search(r"tu rack|server|\d+ ?u\b", u):
            continue
        key = (tier, m.start())
        if best is None or key < best[0]:
            best = (key, cat)
    return best[1] if best else "generic"


def _style(u: str, spec: dict) -> None:
    from nexa.three_d.geometry.materials import COLOR_NAMES
    style: dict[str, str] = {}
    # "thân carbon màu đen", "màu đỏ trắng", "sơn xanh"
    colors = []
    for m in re.finditer(r"(?:mau|son|than mau|vo mau)\s+([a-z ]{2,24})", u):
        seg = m.group(1)
        for name in sorted(COLOR_NAMES, key=len, reverse=True):
            for mm in re.finditer(rf"\b{name}\b", seg):
                colors.append((m.start(1) + mm.start(), name))
        # chỉ lấy tối đa 3 màu đầu
    seen = []
    for _pos, name in sorted(colors):
        if name not in seen:
            seen.append(name)
    keys = ["primary_color", "secondary_color", "accent_color"]
    for k, name in zip(keys, seen[:3]):
        style[k] = name
    if "carbon" in u or "soi cacbon" in u:
        style["finish"] = "carbon"
    elif re.search(r"\bbong\b|glossy", u):
        style["finish"] = "glossy"
    elif re.search(r"\bnham\b|matte", u):
        style["finish"] = "matte"
    if style:
        spec["style"] = style


class LocalPlanner:
    """Phân tích câu bằng mẫu — không bao giờ gọi mạng."""

    def parse(self, text: str) -> dict:
        u = _fold(text)
        cat = detect_category(text)
        p: dict[str, Any] = {}
        explicit: dict[str, float] = {}
        req: list[str] = []
        raw: dict[str, Any] = {"category": cat, "params": p}
        if re.search(r"che tao|san xuat|gia cong|(?<!may )in 3d|de lam that|manufactur", u):
            raw["intended_use"] = "manufacturing"
        if re.search(r"bang cloud|bang tripo|bang meshy|dich vu 3d|text to 3d|ai tao hinh|cloud|hugging ?face|trellis|"
                     r"hunyuan|\bhf\b|muc 3\b", u):
            raw["mode"] = "cloud"
        elif re.search(r"\bcad\b|tham so|parametric|cuc bo|offline|muc 2\b", u):
            raw["mode"] = "parametric"
        if re.search(r"chat luong cao|chi tiet cao|high quality|sieu chi tiet|dep nhat", u):
            raw["quality"] = "high"
        _style(u, raw)

        def length_after(words: str, key: str, default_unit: str = "mm") -> float | None:
            m = re.search(rf"(?:{words})\s*(?:la|khoang|=|:)?\s*{NUM}{UNIT}", u)
            if m:
                val = _to_mm(m.group(1), m.group(2), default_unit)
                explicit[key] = val
                return val
            return None

        if cat in ("bolt", "nut", "washer"):
            m = re.search(r"\bm\s?(\d+(?:\.\d+)?)(?:\s*[x×*]\s*(\d+(?:\.\d+)?))?(?:\s*[x×*]\s*(\d+(?:\.\d+)?))?", u)
            if m:
                p["diameter_mm"] = explicit["diameter_mm"] = float(m.group(1))
                if m.group(2) and cat == "bolt":
                    # "M8x1.25x30" hoặc "M8x30"
                    a, b = float(m.group(2)), float(m.group(3)) if m.group(3) else None
                    if b is not None:
                        p["pitch_mm"], p["length_mm"] = a, b
                        explicit.update(pitch_mm=a, length_mm=b)
                    elif a <= 6 and a < float(m.group(1)):
                        p["pitch_mm"] = explicit["pitch_mm"] = a
                    else:
                        p["length_mm"] = explicit["length_mm"] = a
            else:
                d = length_after(r"duong kinh|phi|dk", "diameter_mm")
                if d:
                    p["diameter_mm"] = d
            if cat == "bolt":
                L = length_after(r"dai|chieu dai|length", "length_mm")
                if L:
                    p["length_mm"] = L
                pm = re.search(rf"(?:buoc ren|buoc|pitch)\s*(?:la|=|:)?\s*{NUM}", u)
                if pm:
                    p["pitch_mm"] = explicit["pitch_mm"] = float(pm.group(1))
                if re.search(r"dau tru|luc giac chim|socket|dau lo luc giac|allen", u):
                    p["head"] = "socket_cap"
                elif re.search(r"dau con|dau bang|dau chim|countersunk", u):
                    p["head"] = "countersunk"
                if re.search(r"ren minh hoa|khong can ren that|ren gia|illustrative", u):
                    p["thread"] = "illustrative"
                if re.search(r"(kem|co|va|voi|them)( ca)? (dai oc|e cu|tan)\b", u):
                    p["include_nut"] = True
                if re.search(r"(kem|co|va|voi|them)( ca)? (vong dem|long den)", u):
                    p["include_washer"] = True
                g = re.search(r"cap ben\s*(\d+\.\d)", u)
                if g:
                    p["grade"] = g.group(1)
            if cat == "nut":
                pm = re.search(rf"(?:buoc ren|buoc|pitch)\s*(?:la|=|:)?\s*{NUM}", u)
                if pm:
                    p["pitch_mm"] = explicit["pitch_mm"] = float(pm.group(1))
                if re.search(r"chong xoay|nylon|nyloc|khoa", u):
                    p["type"] = "nyloc"
            mat = [("stainless", r"inox|khong gi|stainless"), ("brass", r"dong thau|\bdong\b|brass"),
                   ("titanium", r"titan"), ("black_oxide", r"nhuom den|\bden\b"), ("zinc", r"ma kem|kem"),
                   ("steel", r"\bthep\b|steel")]
            for key, pat in mat:
                if re.search(pat, u):
                    p["material"] = key
                    break
        elif cat == "gear":
            m = re.search(rf"module\s*{NUM}|\bmodun\s*{NUM}", u)
            if m:
                p["module_mm"] = explicit["module_mm"] = float(m.group(1) or m.group(2))
            z = re.search(r"(\d+)\s*rang\b|\bz\s*=?\s*(\d+)\b", u)
            if z:
                p["teeth"] = int(z.group(1) or z.group(2))
            w = length_after(r"day|be rong|rong", "face_width_mm")
            if w:
                p["face_width_mm"] = w
            bore = length_after(r"lo truc|lo|truc", "bore_mm")
            if bore:
                p["bore_mm"] = bore
            if re.search(r"nhua|plastic", u):
                p["material"] = "plastic"
            elif re.search(r"dong|brass", u):
                p["material"] = "brass"
        elif cat == "flange":
            od = length_after(r"duong kinh ngoai|duong kinh|dk ngoai|phi", "outer_d_mm")
            if od:
                p["outer_d_mm"] = od
            idd = length_after(r"lo trong|duong kinh trong|lo giua|dk trong", "inner_d_mm")
            if idd:
                p["inner_d_mm"] = idd
            t = length_after(r"day|do day", "thickness_mm")
            if t:
                p["thickness_mm"] = t
            n = _count(u, r"lo( bu ?long)?")
            if n:
                p["bolt_holes"] = n
            if re.search(r"inox|khong gi", u):
                p["material"] = "stainless"
            elif re.search(r"nhom|aluminum", u):
                p["material"] = "aluminum"
        elif cat == "bracket":
            m = re.search(rf"{NUM}\s*[x×*]\s*{NUM}\s*[x×*]\s*{NUM}{UNIT}", u)
            if m:
                vals = [_to_mm(m.group(i), m.group(4)) for i in (1, 2, 3)]
                p["width_mm"], p["height_mm"], p["depth_mm"] = vals
                explicit.update(width_mm=vals[0], height_mm=vals[1], depth_mm=vals[2])
            t = length_after(r"day|do day", "thickness_mm")
            if t:
                p["thickness_mm"] = t
            if re.search(r"inox", u):
                p["material"] = "stainless"
            elif re.search(r"thep", u):
                p["material"] = "steel"
        elif cat == "uav":
            n = None
            for word, val in (("quad", 4), ("hexa", 6), ("octo", 8), ("tri", 3)):
                if re.search(rf"\b{word}(copter|rotor)?\b", u):
                    n = val
            n = n or _count(u, r"(canh|rotor|dong co|motor|tay|truc)")
            if n:
                p["arm_count"] = n
                if n not in (3, 4, 6, 8):
                    raw["_note"] = f"{n} tay đòn"
            if re.search(r"\bmini\b|\bnho\b|ti hon", u):
                p["size_class"] = "mini"
            elif re.search(r"\blon\b|cong nghiep|nong nghiep|cho hang|heavy", u):
                p["size_class"] = "large"
            elif re.search(r"trung binh|medium", u):
                p["size_class"] = "medium"
            wb = length_after(r"khung|truc cheo|wheelbase|khoang cach truc|co", "wheelbase_mm")
            if wb and 100 <= wb <= 2500:
                p["wheelbase_mm"] = wb
            if re.search(r"carbon|cacbon", u):
                p["frame_material"] = "carbon"
            elif re.search(r"\bnhua\b|plastic", u):
                p["frame_material"] = "plastic"
            elif re.search(r"\bnhom\b|aluminum", u):
                p["frame_material"] = "aluminum"
            if re.search(r"khong (co )?camera", u):
                p["camera"] = "none"
            elif re.search(r"camera (o |phia |mat )?(duoi|bung|day)", u):
                p["camera"] = "bottom"
            elif "camera" in u:
                p["camera"] = "front"
                req.append("camera")
            if re.search(r"khong (co )?(gimbal|chong rung)", u):
                p["gimbal"] = False
            if re.search(r"khong (co )?(cang|chan) dap", u):
                p["landing_gear"] = False
            b = _count(u, r"la( canh)?")
            if b and 2 <= b <= 5:
                p["prop_blades"] = b
        elif cat == "rover":
            n = _count(u, r"banh")
            if n:
                p["wheel_count"] = n
            L = length_after(r"dai|chieu dai", "length_mm")
            if L:
                p["length_mm"] = L
            if "lidar" in u or "li da" in u:
                p["lidar"] = True
                req.append("lidar")
            elif re.search(r"khong (co )?lidar", u):
                p["lidar"] = False
            if "camera" in u:
                p["camera"] = not re.search(r"khong (co )?camera", u)
                if p["camera"]:
                    req.append("camera")
            if re.search(r"rocker|bogie", u):
                p["suspension"] = "rocker_bogie"
            elif re.search(r"treo doc lap|independent", u):
                p["suspension"] = "independent"
            if re.search(r"pin mat troi|solar", u):
                p["solar_panel"] = True
        elif cat == "humanoid":
            m = re.search(r"cao\s*(?:khoang|la)?\s*(\d+)\s*m\s*(\d+)\b", u)
            if m:
                p["height_mm"] = explicit["height_mm"] = float(m.group(1)) * 1000 + float(m.group(2)) * (100 if len(m.group(2)) == 1 else 10)
            else:
                h = length_after(r"cao|chieu cao", "height_mm", default_unit="mm")
                if h:
                    if h < 5:                              # "cao 1.7" (mét)
                        h *= 1000
                        explicit["height_mm"] = h
                    p["height_mm"] = h
            if re.search(r"tay kep|kep|gripper", u):
                p["hands"] = "gripper"
            if re.search(r"cong nghiep|industrial", u):
                p["style"] = "industrial"
            if re.search(r"camera", u):
                p["head_sensor"] = "camera"
        elif cat == "quadruped":
            j = re.search(r"(\d+|hai|ba)\s+khop", u)
            if j:
                g = j.group(1)
                p["joints_per_leg"] = int(g) if g.isdigit() else VI_NUMS[g]
            L = length_after(r"dai|chieu dai", "length_mm")
            if L:
                p["length_mm"] = L
            if "lidar" in u and "camera" in u:
                p["head_sensor"] = "both"
            elif "lidar" in u:
                p["head_sensor"] = "lidar"
            elif "camera" in u:
                p["head_sensor"] = "camera"
        elif cat == "boat":
            hits = []
            for kind, pat in (("yacht", r"du thuyen|yacht|sang trong"), ("fishing", r"tau ca\b|danh ca|cau ca|fishing|ghe"),
                              ("patrol", r"tuan tra|canh sat bien|cuu ho|bien phong|patrol"),
                              ("speedboat", r"ca no|\bcano\b|cao toc|speedboat|xuong may")):
                m_kind = re.search(pat, u)
                if m_kind:
                    hits.append((m_kind.start(), kind))
            if hits:
                p["boat_type"] = min(hits)[1]
            L = length_after(r"dai|chieu dai", "length_mm", default_unit="m")
            if L is None:                                       # "du thuyền 20 mét" (không có chữ "dài")
                m_len = re.search(rf"{NUM}\s*(m|met)\b", u)
                if m_len:
                    L = explicit["length_mm"] = _to_mm(m_len.group(1), m_len.group(2))
            if L and L < 1000:                                  # "dài 8" không đơn vị → mét (thuyền)
                p["length_mm"] = explicit["length_mm"] = L * 1000
            elif L:
                p["length_mm"] = L
            if re.search(r"may trong|inboard|chan vit|truc chan vit", u):
                p["propulsion"] = "inboard"
            elif re.search(r"may (gan |treo |dat )?ngoai|outboard|may duoi|may treo|duoi tom", u):
                p["propulsion"] = "outboard"
            k = _count(u, "(?:may|dong co)")
            if k and 1 <= k <= 3:
                p["engines"] = k
            if re.search(r"khong (co )?(cabin|mui|ca bin)", u):
                p["cabin"] = False
            if re.search(r"khong (co )?lan can", u):
                p["railings"] = False
        elif cat == "helicopter":
            # vai trò = từ khóa xuất hiện SỚM NHẤT ("trực thăng dân sự có tời cứu hộ" là dân sự)
            hits = []
            for role, pat in (("rescue", r"cuu ho|cuu nan|tim kiem"), ("medical", r"cuu thuong|y te|cap cuu"),
                              ("civil", r"dan su|du lich|cho khach"), ("utility", r"van tai|da dung|cong nghiep|cho hang")):
                m_role = re.search(pat, u)
                if m_role:
                    hits.append((m_role.start(), role))
            if hits:
                p["role"] = min(hits)[1]
            m = re.search(r"rotor chinh[^,.]*?(\d+|hai|ba|bon|nam|sau)\s*(canh|la)", u)
            if m:
                g = m.group(1)
                p["main_blades"] = int(g) if g.isdigit() else VI_NUMS[g]
            m = re.search(r"rotor duoi[^,.]*?(\d+|hai|ba|bon|nam|sau)\s*(canh|la)", u)
            if m:
                g = m.group(1)
                p["tail_rotor_blades"] = int(g) if g.isdigit() else VI_NUMS[g]
            if "rotor chinh" in u:
                req.append("rotor chính")
            if "rotor duoi" in u:
                req.append("rotor đuôi")
            if re.search(r"banh xe|cang banh|\bbanh\b", u):
                p["landing"] = "wheels"
            L = length_after(r"dai|chieu dai", "length_mm")
            if L:
                p["length_mm"] = L
            if re.search(r"khong (co )?toi", u):
                p["hoist"] = False
        elif cat in _tech_parsers():
            from nexa.three_d.parse_tech import parse as tech_parse
            tech_parse(cat, u, text, p, explicit, req, raw)
        else:
            m = re.search(rf"(?:dai|cao|rong|kich thuoc|co)\s*(?:khoang)?\s*{NUM}{UNIT}", u)
            if m:
                p["approx_size_mm"] = _to_mm(m.group(1), m.group(2))
                explicit["approx_size_mm"] = p["approx_size_mm"]      # người dùng nói rõ → dựng đúng cỡ này
            p["description"] = text.strip()[:500]
        raw["_explicit"] = explicit
        raw["requested_parts"] = req
        raw["name"] = _default_name(cat, p, text)
        return raw


def _tech_parsers() -> dict:
    from nexa.three_d.parse_tech import PARSERS
    return PARSERS


def _default_name(cat: str, p: dict, text: str) -> str:
    if cat in _tech_parsers():
        from nexa.three_d.parse_tech import default_name
        name = default_name(cat, p)
        if name:
            return name
    if cat == "bolt" and "diameter_mm" in p:
        return f"Bu-lông M{p['diameter_mm']:g}" + (f"×{p['length_mm']:g}" if "length_mm" in p else "")
    if cat in ("nut", "washer") and "diameter_mm" in p:
        return f"{CATEGORY_VI[cat].capitalize()} M{p['diameter_mm']:g}"
    if cat == "uav":
        return f"UAV {p.get('arm_count', 4)} cánh" + (" mini" if p.get("size_class", "mini") == "mini" else "")
    if cat == "rover":
        return f"Xe tự hành {p.get('wheel_count', 6)} bánh"
    if cat == "quadruped":
        return "Robot chó"
    if cat == "boat":
        base = {"speedboat": "Ca nô cao tốc", "fishing": "Tàu cá", "yacht": "Du thuyền",
                "patrol": "Tàu tuần tra"}.get(p.get("boat_type", "speedboat"), "Thuyền")
        return base + (f" {p['length_mm'] / 1000:g} m" if p.get("length_mm") else "")
    if cat == "helicopter":
        return {"rescue": "Trực thăng cứu hộ", "medical": "Trực thăng cứu thương"}.get(p.get("role", "rescue"), "Trực thăng")
    if cat == "generic":
        t = re.sub(r"^\s*(tạo|dựng|vẽ|thiết kế|làm)\s+(cho (anh|tôi|em)\s+)?(một\s+|1\s+)?(mô hình\s+)?(3d\s+|ba chiều\s+)?",
                   "", text.strip(), flags=re.IGNORECASE)
        # tên mô hình không mang theo tên dịch vụ: "dùng hugging face tạo cái cốc", "bình hoa bằng HF" → "cái cốc", "bình hoa"
        t = re.sub(r"^\s*(?:dùng\s+|bằng\s+)?(?:hugging\s*face|hf|tripo|meshy|trellis|hunyuan)\s+(?:để\s+)?"
                   r"(?:tạo|dựng|làm|gen)\s+(?:cho (?:anh|tôi|em)\s+)?(?:một\s+|1\s+)?(?:mô hình\s+)?", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*\b(bằng|dùng|qua|với)\s+(hugging\s*face|hf|tripo|meshy|trellis|hunyuan|cloud|dịch vụ\s*\w*)\b.*$", "",
                   t, flags=re.IGNORECASE)
        return (t or text).strip(" .")[:60] or "Mô hình"
    return CATEGORY_VI.get(cat, "Mô hình").capitalize()


GEMINI_SYSTEM = """Bạn là bộ lập kế hoạch mô hình 3D của NEXA. Nhiệm vụ: chuyển yêu cầu tiếng Việt thành ModelSpec JSON.
KHÔNG viết mã. Chỉ trả JSON đúng schema. Đơn vị mm. Không bịa kích thước người dùng không nói nếu đó là thông số bắt buộc;
khi thiếu thông số BẮT BUỘC, thêm câu hỏi ngắn tiếng Việt vào "missing". Thông số không bắt buộc thì bỏ trống (NEXA tự điền
theo tiêu chuẩn và ghi chú). Chọn "category" trong danh sách; vật thể khác → "generic" (best effort).
Tên (name) tiếng Việt ngắn. requested_parts: bộ phận người dùng nhắc rõ (camera, lidar, rotor đuôi…)."""


def _params_doc() -> str:
    lines = []
    for cat, sch in PARAM_SCHEMAS.items():
        props = []
        for k, v in sch["properties"].items():
            extra = f" ∈ {v['enum']}" if "enum" in v else (f" [{v.get('minimum')}..{v.get('maximum')}]" if "minimum" in v else "")
            props.append(f"{k}{extra}")
        req = sch.get("required") or []
        lines.append(f"- {cat}: " + ", ".join(props) + (f" (bắt buộc: {', '.join(req)})" if req else ""))
    return "\n".join(lines)


DSL_SCHEMA_FOR_GEMINI = {
    "type": "object", "properties": {"parts": {"type": "array", "items": {
        "type": "object", "properties": {
            "id": {"type": "string"}, "name_vi": {"type": "string"}, "name_en": {"type": "string"},
            "category": {"type": "string"}, "material": {"type": "string"}, "function": {"type": "string"},
            "aliases": {"type": "array", "items": {"type": "string"}}, "parent_id": {"type": "string"},
            "position_tag": {"type": "string"}, "explode_dir": {"type": "array", "items": {"type": "number"}},
            "explode_distance": {"type": "number"}, "shape": {"type": "object"}},
        "required": ["id", "name_vi", "shape"]}}}, "required": ["parts"]}


class Planner:
    def __init__(self, provider: Any = None, use_gemini: bool = True) -> None:
        self.provider = provider
        self.use_gemini = use_gemini
        self.local = LocalPlanner()

    def gemini_ready(self) -> bool:
        if not self.use_gemini or self.provider is None or not hasattr(self.provider, "generate_json"):
            return False
        try:
            return bool(self.provider.status()[0])
        except Exception:
            return False

    def plan(self, text: str, token: Any = None, overrides: dict | None = None) -> PlanResult:
        local = self.local.parse(text)
        explicit = dict(local.pop("_explicit", {}))
        note = local.pop("_note", None)
        warnings: list[str] = []
        if note:
            warnings.append(f"Yêu cầu {note}: NEXA hỗ trợ 3, 4, 6 hoặc 8 tay đòn.")
        raw = local
        source = "local"
        if self.gemini_ready() and token is not None:
            try:
                prompt = (f"Yêu cầu của người dùng: «{text.strip()[:800]}»\n\nTham số theo category (chỉ dùng đúng tên này):\n"
                          f"{_params_doc()}")
                try:            # chạy trong job nền 3D (không phải lượt trả lời giọng nói) → cho phép chờ lâu hơn
                    g = self.provider.generate_json(prompt, MODEL_SPEC_SCHEMA, token, system=GEMINI_SYSTEM, max_tokens=2048,
                                                    timeout_s=45)
                except TypeError:
                    g = self.provider.generate_json(prompt, MODEL_SPEC_SCHEMA, token, system=GEMINI_SYSTEM, max_tokens=2048)
                if isinstance(g, dict) and g.get("category"):
                    merged = dict(g)
                    merged["params"] = dict(g.get("params") or {})
                    # chế độ/chất lượng chỉ theo lời người dùng (từ khóa), không để AI tự chọn đường tạo
                    merged["mode"] = local.get("mode", "auto")
                    merged["quality"] = local.get("quality", "standard")
                    if local["category"] != "generic" and merged["category"] != local["category"]:
                        warnings.append(f"Gemini xếp loại '{merged['category']}', bộ phân tích local là "
                                        f"'{local['category']}' — dùng loại của Gemini.")
                    raw = merged
                    source = "gemini"
            except Exception as exc:   # lỗi mạng/quota/hủy → dùng local, ghi rõ
                from nexa.core.safety import Cancelled
                if isinstance(exc, Cancelled):
                    raise
                warnings.append(f"Không dùng được Gemini để phân tích ({getattr(exc, 'message', str(exc))[:80]}); "
                                "dùng bộ phân tích cục bộ.")
                log.info("Planner Gemini lỗi: %s", exc)
        # số đo người dùng nói rõ luôn thắng
        cat = raw.get("category", "generic")
        if cat == local["category"]:
            for k, v in explicit.items():
                old = raw["params"].get(k)
                if old is not None and abs(float(old) - float(v)) > 1e-6:
                    warnings.append(f"Gemini đề xuất {k}={old}, người dùng nói {v:g} — dùng số người dùng.")
                raw["params"][k] = v
            for k, v in local["params"].items():
                raw["params"].setdefault(k, v)
            if local.get("style") and not raw.get("style"):
                raw["style"] = local["style"]
        if overrides:
            raw.setdefault("params", {}).update(overrides.get("params", {}))
            for k in ("mode", "quality"):
                if overrides.get(k):
                    raw[k] = overrides[k]
        raw.setdefault("name", local.get("name", ""))
        raw.pop("_explicit", None)
        # câu hỏi cho thông số bắt buộc
        params = raw.get("params") or {}
        questions = [q["question"] for q in is_complete(ModelSpec(category=cat, params=params))]
        for m in raw.get("missing") or []:
            if isinstance(m, dict) and m.get("question") and m.get("field") in (PARAM_SCHEMAS.get(cat, {}).get("required") or []):
                if m["question"] not in questions and m.get("field") not in params:
                    questions.append(m["question"])
        if questions:
            return PlanResult(None, questions, warnings, source, raw=raw)
        raw["missing"] = []
        clean = {k: v for k, v in raw.items() if k in MODEL_SPEC_SCHEMA["properties"]}
        clean["params"] = {k: v for k, v in (raw.get("params") or {}).items()}
        try:
            spec = validate_spec(clean)
        except SpecError as exc:
            if source == "gemini":
                warnings.append(f"ModelSpec của Gemini không hợp lệ ({exc}); dùng bộ phân tích cục bộ.")
                return self._local_only(text, local, explicit, warnings)
            return PlanResult(None, [f"Thông số chưa hợp lệ: {exc}. Anh nói lại giúp em nhé."], warnings, source, raw=raw)
        spec.prompt = text.strip()
        spec.explicit = explicit
        spec.source = source
        spec.warnings += warnings
        normalize(spec)
        result = PlanResult(spec, [], spec.warnings, source, raw=raw)
        return result

    def _local_only(self, text: str, local: dict, explicit: dict, warnings: list[str]) -> PlanResult:
        clean = {k: v for k, v in local.items() if k in MODEL_SPEC_SCHEMA["properties"]}
        questions = [q["question"] for q in is_complete(ModelSpec(category=local["category"], params=local["params"]))]
        if questions:
            return PlanResult(None, questions, warnings, "local", raw=local)
        try:
            spec = validate_spec(clean)
        except SpecError as exc:
            return PlanResult(None, [f"Thông số chưa hợp lệ: {exc}."], warnings, "local", raw=local)
        spec.prompt, spec.explicit, spec.source = text.strip(), explicit, "local"
        spec.warnings += warnings
        normalize(spec)
        return PlanResult(spec, [], spec.warnings, "local", raw=local)

    def plan_dsl(self, spec: ModelSpec, token: Any) -> list[dict]:
        """Gemini mô tả vật thể ngoài nhóm hỗ trợ bằng CAD DSL (best effort). Ném lỗi nếu không có Gemini."""
        if not self.gemini_ready():
            raise RuntimeError("Cần Gemini để dựng vật thể ngoài nhóm hỗ trợ khi không dùng dịch vụ 3D cloud.")
        # Pipeline dùng DslDesigner trực tiếp (có vòng sửa lỗi + xem ảnh); hàm này giữ cho nơi gọi cũ.
        from nexa.three_d.generation.dsl_designer import DslDesigner
        return DslDesigner(self.provider).design(spec, token)["parts"]
