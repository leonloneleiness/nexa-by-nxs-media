"""Phân tích câu tiếng Việt (có/không dấu) cho các nhóm CAD kỹ thuật mở rộng: mẫu nhận dạng loại + trích tham số.

LocalPlanner gọi `parse(cat, u, text, p, explicit, req, raw)` với `u` = câu đã bỏ dấu, chữ thường, "1,25" → "1.25".
Mọi số người dùng nói rõ được ghi vào `explicit` (đối chiếu kích thước sau khi dựng).
"""
from __future__ import annotations

import re
from typing import Callable

from nexa.three_d import standards as S

NUM = r"(\d+(?:\.\d+)?)"
VI_NUMS = {"mot": 1, "hai": 2, "ba": 3, "bon": 4, "tu": 4, "nam": 5, "sau": 6, "bay": 7, "tam": 8, "chin": 9, "muoi": 10}
NUMW = r"(\d+|mot|hai|ba|bon|tu|nam|sau|bay|tam|chin|muoi)"


def _n(g: str) -> int:
    return int(g) if g.isdigit() else VI_NUMS[g]


def _mm(val: str, unit: str | None, default: str = "mm") -> float:
    u = (unit or default).strip()
    return float(val) * {"mm": 1, "cm": 10, "m": 1000, "met": 1000, "inch": 25.4, "in": 25.4}.get(u, 1)


UNIT = r"\s*(mm|cm|met|m|inch|in)?\b"

# (category, mẫu, tầng ưu tiên). Tầng nhỏ thắng; cùng tầng → chỗ khớp xuất hiện SỚM NHẤT trong câu thắng.
# Tầng 50 = linh kiện tiêu chuẩn (sau robot/phương tiện/thiết bị, trước ốc vít/bánh răng/mặt bích đơn lẻ).
TECH_PATTERNS: list[tuple[str, str, int]] = [
    ("gearbox", r"hop so|hop giam toc|gearbox|hop banh rang|bo giam toc|hop truyen dong banh rang|reducer", 50),
    ("stepper_motor", r"dong co buoc|stepper|step motor|motor buoc|dong co step|\bnema ?(?:17|23|34)\b", 50),
    ("bearing", r"\bo bi\b|vong bi|bac dan|\bo lan\b|bearing|\b6[023]\d{2}(?:-| )?(?:2rs|zz|rs)\b", 50),
    ("cylinder", r"\bxi ?-?lanh\b|\bxylanh\b|\bcylinder\b|\bben (?:hoi|dau|khi)\b|pneumatic cylinder|hydraulic cylinder", 50),
    ("ball_valve", r"\bvan bi\b|ball valve|\bvan tay gat\b|\bvan khoa (?:bi|dn)", 50),
    ("pipe_fitting", r"\bcut (?:90|45|han|ong|dn)|\bco (?:90|45) ?do\b|\bco dn ?\d|\belbow\b|\bte (?:deu|ong|han|giam|dn ?\d)|"
                     r"\btee\b|\bong te\b|phu kien (?:duong )?ong|pipe fitting|mat bich (?:noi )?(?:duong )?ong|mat bich (?:dn|pn)|"
                     r"\bdn ?\d{2,3}\b.{0,40}mat bich|mat bich.{0,40}\bdn ?\d{2,3}\b|moi noi mat bich|ghep mat bich", 50),
    ("belt_drive", r"bo truyen dai|\bday dai\b|\bdai rang\b|\bdai thang\b|\bpu ?ly\b|\bpuli\b|curoa|\bgt2\b|\bhtd\b|timing belt|belt drive|"
                   r"\bdai (?:spz|spa|gt2|htd)", 50),
    ("chain_drive", r"bo truyen xich|dia xich|xich con lan|\bxich (?:0[68]|1[026]) ?b\b|\b(?:0[68]|1[026])b\b|chain drive|roller chain|"
                    r"nhong xich|truyen dong xich|\bsen xich\b", 50),
    ("shaft_coupling", r"khop noi|coupling|noi truc|\bkhop vau\b|\brotex\b|lovejoy", 50),
    ("ball_screw", r"vit me|vitme|ball ?screw|truc vit bi|\bsfu ?\d{4}\b|vit bi\b", 50),
    ("linear_guide", r"ray truot|ray dan huong|linear guide|linear rail|\bhg[rhw] ?(?:15|20|25|30)\b|\bmgn ?(?:7|9|12|15)\b|"
                     r"ray tuyen tinh|thanh truot tuyen tinh|con truot (?:hg|mgn)", 50),
    ("spring", r"\blo xo\b|\bloxo\b|\bspring\b", 50),
    # robot (tầng 9: trước robot hình người/chó và xe tự hành)
    ("robot_arm", r"canh tay robot|\btay robot\b|\btay may\b|robot (?:6|sau) (?:truc|bac)|robot cong nghiep|robot arm|\bcobot\b|"
                  r"robot (?:han|son|gap|boc xep|pick)\b|\bur ?(?:3|5|10|16)e?\b|\bkuka\b|abb irb|\bfanuc\b|robot cong tac", 9),
    ("robot_vacuum", r"robot hut bui|may hut bui (?:robot|tu dong|thong minh)|robot lau nha|robot vacuum|roomba|roborock|robot don nha|"
                     r"robot quet nha", 9),
    ("agv", r"\bagv\b|\bamr\b|robot giao hang|robot (?:van chuyen|kho|nang ke|cho hang|tu hanh kho)|xe tu hanh (?:kho|nang ke|cho hang)|"
            r"robot kiva|\bkiva\b|delivery robot|xe van chuyen tu dong", 9),
    # phương tiện / hàng không vũ trụ (tầng 13–20; trực thăng 12, thuyền 14, UAV đa rotor 16, xe tự hành 18 giữ nguyên)
    ("launch_vehicle", r"ten lua|\brocket\b|phong ve tinh|falcon ?9|ten lua day|launch vehicle|tau vu tru", 13),
    ("cubesat", r"cubesat|cube ?sat|\bve tinh\b|nano ?sat|pico ?sat|satellite", 13),
    ("train", r"tau hoa|tau dien|doan tau|dau may|toa tau|toa xe lua|xe lua|\bmetro\b|tau dien ngam|duong sat|locomotive|\btrain\b|"
              r"tau cao toc bac nam|tau khach|tau hang|tau thong nhat", 13),
    ("fixed_wing", r"may bay canh (?:bang|co dinh|thap|cao)|uav canh (?:bang|co dinh)|drone canh (?:bang|co dinh)|"
                   r"khong nguoi lai canh (?:bang|co dinh)|\bvtol\b|quadplane|cat ha canh thang dung|fixed.?wing|"
                   r"may bay (?:hang nhe|4 cho|bon cho|the thao|huan luyen|canh quat|chong chong|tu nhan|dan dung)|cessna|piper|diamond da40", 15),
    ("fixed_wing", r"\bmay bay\b|\bairplane\b|\baircraft\b|\bphi co\b|\btau bay\b", 17),
    ("excavator", r"may xuc|may dao|may cuoc|xe cuoc|xe xuc|\bexcavator\b|backhoe|xe dao|\bkomatsu\b|cat 320", 17),
    ("forklift", r"xe nang(?! (?:nguoi|cap))|forklift", 17),
    ("crane", r"xe cau\b|can cau\b|can truc|\bcrane\b|cau truc|cau ong long|may cau\b|\bcau\b", 17),   # "cẩu"/"cầu": phân xử theo dấu (planner)
    ("motorbike", r"xe may\b|xe mo ?to|\bmo ?to\b|motorbike|motorcycle|scooter|xe tay ga|xe con tay|xe so\b|xe dap dien|e-?bike|"
                  r"\bxe dap\b|\bvespa\b|honda (?:vision|sh|wave|air ?blade|winner)|yamaha (?:exciter|sirius|janus)|xe may dien|xe phan khoi", 19),
    ("car", r"\bo ?to\b|\boto\b|xe hoi|\bsedan\b|\bsuv\b|hatchback|\bcar\b|xe con\b|xe (?:4|5|7|bon|nam|bay) cho|vinfast|\bvf ?\d|tesla|"
            r"crossover|xe dien 4 banh", 20),
    # năng lượng & công trình
    ("wind_turbine", r"tua ?bin gio|turbine gio|dien gio|coi xay gio|wind turbine|may phat dien gio|tuabin", 12),
    ("solar_array", r"pin mat troi|pin nang luong mat troi|tam pin|dien mat troi|nang luong mat troi|\bsolar\b|quang dien|"
                    r"dien nang luong mat troi|he thong pin|trang trai dien", 20),
    ("generator_set", r"may phat dien|may phat\b|\bgenset\b|to may phat|may no\b|may phat diesel", 21),
    ("centrifugal_pump", r"may bom|bom ly tam|bom nuoc|\bbom\b|\bpump\b|bom cap nuoc|bom tuan hoan", 45),
    ("storage_tank", r"bon chua|be chua|bon nuoc|bon dau|bon xang|bon inox|\btec\b|thung chua|storage tank|\btank\b|bon ap luc|bon nam|bon dung", 45),
    ("bridge", r"cay cau|cau (?:treo|day vang|vom|gian|thep|duong sat|be tong|dam|vuot|nhip|song|di bo)|\bbridge\b|"
               r"(?<!xe )(?<!can )(?<!may )(?<!hai )(?<!mot )\bcau\b"
               r"(?! truc| ong long| thuy luc| sau| truoc| xe| chu dong| thang| chi\b| dao| long| noi| vong| hon)", 16),
    ("steel_truss", r"gian thep|gian mai|vi keo|keo thep|dan thep|\btruss\b|gian pratt|gian howe|gian warren|gian fink|kieu pratt|kieu howe|"
                    r"kieu warren|kieu fink|\bkeo mai\b", 17),
    ("lattice_tower", r"thap (?:dien|vien thong|thep|truyen hinh|bts|anten|ang ten|sat|truyen tai|song)|cot dien cao the|cot dien|cot vien thong|"
                      r"cot bts|\btower\b|thap anten|cot anten|cot thep|\bthap\b", 22),    # chế tạo & điện tử: máy in 3D / CNC tầng 8 (thắng "vít me", "ổ bi", "quạt"… là chi tiết của máy); tủ rack 30 thắng
    # "quạt" ("tủ rack có quạt"), tủ điện 31 thua hệ pin mặt trời (tầng 20, có tủ điện/biến tần); quạt, tản nhiệt,
    # bo mạch cùng tầng 40 → từ khóa xuất hiện trước thắng ("quạt tản nhiệt" là quạt, "tản nhiệt có quạt" là tản nhiệt)
    ("fdm_printer", r"may in (?:3 ?d|ba chieu|3 chieu|fdm|nhua|resin)|\b3d printer\b|\bprinter 3d\b|\bfdm\b|\bender ?-?[35]\b|\bprusa\b|"
                    r"\bbambu\b|\bvoron\b|\bin 3 ?d\b|\bcore ?xy\b|bedslinger", 8),
    ("cnc_router", r"\bcnc\b|may phay|may khac (?:go|cnc)|may dieu khac|cnc router|\brouter (?:go|cnc)\b|"
                   r"may cat cnc|may gia cong cnc", 8),
    ("server_rack", r"tu rack|tu mang|tu server|tu may chu|server rack|\brack (?:19|tu|server|mang|\d+ ?u)\b|tu 19 ?(?:inch|in)|"
                    r"\btu (?:\d+|mot|hai) ?u\b|\b\d+ ?u rack\b|\brack\b(?! (?:and|va) pinion)(?!.*thanh rang)|network cabinet", 30),
    ("electrical_enclosure", r"tu dien|hop dien|tu dieu khien|tu phan phoi|tu aptomat|electrical enclosure|vo tu dien|"
                             r"hop aptomat|tu dong luc|tu mcb|hop ky thuat dien", 31),
    ("axial_fan", r"quat (?:tan nhiet|may tinh|pc|case|12 ?v|5 ?v|24 ?v|dc|huong truc|hut|thong gio|\d{2,3} ?mm|noctua)|"
                  r"(?<!canh )(?<!chong )\bquat\b|axial fan|\bcase fan\b|\bfan (?:\d{2,3}|pc|case)\b", 40),
    ("heatsink", r"tan nhiet|heat ?sink|\bong dong\b|\btan (?:khi|thap|cpu|nhom)\b|cooler (?:cpu|thap)|\bcpu cooler\b", 40),
    ("dev_board", r"bo mach|arduino|raspberry|\brpi\b|\bpi ?4\b|mach (?:dien tu|vi dieu khien|phat trien|arduino)|\bpcb\b|"
                  r"board (?:mach|phat trien|arduino)|\bdev ?board\b|vi dieu khien|kit (?:arduino|phat trien)|\buno r3\b", 40),
]


def _dn(u: str) -> int | None:
    m = re.search(r"\bdn\s*(\d{2,3})\b", u)
    if m:
        return int(m.group(1))
    m = re.search(rf"{NUM}\s*(?:inch|in|\")\b", u)
    if m:
        nps = float(m.group(1))
        return next((dn for dn, v in S.NPS.items() if abs(v - nps) < 1e-6), None)
    m = re.search(r"\bphi\s*(\d{2,3})\b", u)                      # "phi 60" = đường kính ngoài ống
    if m:
        od = float(m.group(1))
        best = min(S.PIPE_OD, key=lambda dn: abs(S.PIPE_OD[dn] - od))
        if abs(S.PIPE_OD[best] - od) < 2.5:
            return best
    return None


def _length(u: str, words: str, default: str = "mm") -> float | None:
    m = re.search(rf"(?:{words})\s*(?:la|khoang|=|:)?\s*{NUM}{UNIT}", u)
    return _mm(m.group(1), m.group(2), default) if m else None


def _bearing(u: str, p: dict, ex: dict) -> None:
    m = re.search(r"\b(6[023]\d{2})\b", u)
    if m and m.group(1) in S.BEARINGS:
        p["designation"] = m.group(1)
    else:
        m = re.search(rf"{NUM}\s*[x×*]\s*{NUM}\s*[x×*]\s*{NUM}", u)
        if m:
            dd = tuple(float(m.group(i)) for i in (1, 2, 3))
            code = next((c for c, v in S.BEARINGS.items() if (v[0], v[1], v[2]) == dd), None)
            if code:
                p["designation"] = code
        if "designation" not in p:
            mb = re.search(r"(?:lo|trong|truc|bore|d)\s*(?:=|la)?\s*(\d{2})\b", u)
            ms = re.search(r"\b(?:day|series)\s*(60|62|63)\b", u)
            if mb:
                bore = int(mb.group(1))
                idx = {10: 0, 12: 1, 15: 2, 17: 3}.get(bore, bore // 5 if bore % 5 == 0 and bore >= 20 else None)
                series = ms.group(1)[1] if ms else "2"
                code = f"6{series}{idx:02d}" if idx is not None else None
                if code in S.BEARINGS:
                    p["designation"] = code
    if re.search(r"khong (?:co )?phot|kieu ho|\bde ho\b|\bo bi ho\b|\bloai ho\b", u):
        p["seal"] = "open"
    elif re.search(r"\b2 ?rs\b|phot cao su|che kin cao su|\bphot\b|phong bui cao su", u):
        p["seal"] = "2RS"
    elif re.search(r"\bzz\b|nap (?:chan )?thep|che (?:bui )?thep|nap sat", u):
        p["seal"] = "ZZ"
    if re.search(r"vong cach nhua|\bpa ?66\b|polyamide|re nhua", u):
        p["cage"] = "polyamide"
    if re.search(r"inox|khong gi|stainless", u):
        p["material"] = "stainless"


def _stepper(u: str, p: dict, ex: dict) -> None:
    m = re.search(r"\bnema\s*(17|23|34)\b", u)
    if m:
        p["frame_size"] = int(m.group(1))
    L = _length(u, r"than dai|dai than|chieu dai than|than|dai")
    if L and 20 <= L <= 200:
        p["body_length_mm"] = ex["body_length_mm"] = L
    if re.search(r"truc kep|hai dau truc|2 dau truc|truc hai dau|double shaft|truc sau", u):
        p["shaft"] = "double"


def _gearbox(u: str, p: dict, ex: dict) -> None:
    m = re.search(rf"{NUMW}\s*cap\b", u)
    if m and _n(m.group(1)) in (2, 3):
        p["stages"] = _n(m.group(1))
    m = re.search(rf"(?:ti so(?: truyen)?|ty so(?: truyen)?|ratio)\s*(?:la|=|:|i\s*=)?\s*(?:1\s*[:/]\s*)?{NUM}|\bi\s*=\s*{NUM}|{NUM}\s*:\s*1\b", u)
    if m:
        v = float(next(g for g in m.groups() if g))
        if 1 < v <= 150:
            p["ratio"] = ex["ratio"] = v
    m = re.search(rf"\bmodul[e]?\s*(?:=|la)?\s*{NUM}|\bm\s*=\s*{NUM}", u)
    if m:
        v = float(m.group(1) or m.group(2))
        if 1 <= v <= 6:
            p["module_mm"] = ex["module_mm"] = v
    if re.search(r"vo nhom|\bnhom\b|aluminum", u):
        p["housing"] = "aluminum"
    if "stages" not in p and p.get("ratio", 0) > 40:
        p["stages"] = 3


def _cylinder(u: str, p: dict, ex: dict) -> None:
    if re.search(r"thuy luc|\bben dau\b|\bdau\b|hydraulic", u):
        p["cylinder_type"] = "hydraulic"
    elif re.search(r"khi nen|\bhoi\b|pneumatic|\bkhi\b", u):
        p["cylinder_type"] = "pneumatic"
    m = re.search(rf"(?:\bphi|ø|\bnong|duong kinh(?: nong)?|\bbore|\bd)\s*(?:=|la)?\s*{NUM}", u)
    m2 = re.search(rf"\b{NUM}\s*[x×*]\s*{NUM}\b", u)
    if m:
        p["bore_mm"] = ex["bore_mm"] = float(m.group(1))
    elif m2:
        p["bore_mm"] = ex["bore_mm"] = float(m2.group(1))
    s = _length(u, r"hanh trinh|stroke|hanh trinh la")
    if s:
        p["stroke_mm"] = ex["stroke_mm"] = s
    elif m2:
        p["stroke_mm"] = ex["stroke_mm"] = float(m2.group(2))
    if re.search(r"(?:mot )?nua hanh trinh|\bgiua\b|\bmid\b|\bmot nua\b", u):
        p["state"] = "mid"
    elif re.search(r"duoi (?:het|ra|hoan toan)|dang duoi|\bduoi\b|day ra|extended|mo rong", u):
        p["state"] = "extended"
    elif re.search(r"\bthu\b|thu vao|thu het|retracted", u):
        p["state"] = "retracted"


def _valve(u: str, p: dict, ex: dict) -> None:
    dn = _dn(u)
    if dn:
        p["dn"] = dn
    if re.search(r"dang dong|dong lai|da dong|trang thai dong|\bclosed\b|vuong goc (?:voi )?ong|khoa lai|dang khoa", u):
        p["state"] = "closed"
    elif re.search(r"dang mo|mo hoan toan|trang thai mo|\bopen\b|da mo", u):
        p["state"] = "open"
    if re.search(r"inox|khong gi|stainless", u):
        p["material"] = "stainless"


def _fitting(u: str, p: dict, ex: dict) -> None:
    dn = _dn(u)
    if dn:
        p["dn"] = dn
    kinds = [("flange_joint", r"mat bich|flange"), ("tee", r"\bte\b|\btee\b|ba chac"),
             ("elbow45", r"\b45\b"), ("elbow90", r"\b90\b|\bco\b|\bcut\b|elbow")]
    for k, pat in kinds:
        if re.search(pat, u):
            p["fitting"] = k
            break
    if re.search(r"inox|khong gi|stainless", u):
        p["material"] = "stainless"
    if re.search(r"khong (?:co |kem )?(?:doan )?ong", u):
        p["pipe_stubs"] = False


def _teeth_pair(u: str) -> list[int]:
    return [int(m.group(1)) for m in re.finditer(r"\b(\d{1,3})\s*rang\b", u)]


def _belt(u: str, p: dict, ex: dict) -> None:
    if re.search(r"\bgt2\b", u):
        p["belt"] = "GT2"
    elif re.search(r"\bhtd\b|\b5m\b", u):
        p["belt"] = "HTD5M"
    elif re.search(r"\bspa\b", u):
        p["belt"] = "SPA"
    elif re.search(r"\bspz\b|dai thang|v ?-?belt|dai chu v", u):
        p["belt"] = "SPZ"
    t = _teeth_pair(u)
    if len(t) >= 1:
        p["teeth_driver"] = t[0]
    if len(t) >= 2:
        p["teeth_driven"] = t[1]
    m = re.search(rf"(?:ti so|ty so)\s*(?:truyen)?\s*(?:la|=|:)?\s*(?:1\s*[:/]\s*)?{NUM}", u)
    if m and len(t) == 1:
        p["teeth_driven"] = int(round(t[0] * float(m.group(1))))
    c = _length(u, r"khoang cach (?:tam|truc|hai truc)|cach tam|center")
    if c:
        p["center_distance_mm"] = ex["center_distance_mm"] = c
    w = _length(u, r"(?:ban |be )?rong")
    if w and w <= 60:
        p["width_mm"] = ex["width_mm"] = w
    m = re.search(rf"(?:puly|pu ly|puli)[^0-9]{{0,20}}{NUM}\s*(?:mm)?\s*(?:va|/|-|voi)\s*{NUM}", u)
    if m and p.get("belt") in ("SPZ", "SPA"):
        p["pulley_d_mm"], p["pulley2_d_mm"] = float(m.group(1)), float(m.group(2))
        ex.update(pulley_d_mm=p["pulley_d_mm"], pulley2_d_mm=p["pulley2_d_mm"])


def _chain(u: str, p: dict, ex: dict) -> None:
    m = re.search(r"\b(06|08|10|12|16)\s*b\b", u)
    if m:
        p["chain"] = f"{m.group(1)}B"
    t = _teeth_pair(u)
    if len(t) >= 1:
        p["teeth_driver"] = t[0]
    if len(t) >= 2:
        p["teeth_driven"] = t[1]
    c = _length(u, r"khoang cach (?:tam|truc|hai truc)|cach tam|center")
    if c:
        p["center_distance_mm"] = ex["center_distance_mm"] = c


def _coupling(u: str, p: dict, ex: dict) -> None:
    if re.search(r"\bcung\b|ong kep|\bkep\b|rigid", u):
        p["coupling_type"] = "rigid"
    elif re.search(r"\bmem\b|\bvau\b|\bsao\b|dan hoi|jaw|rotex|lovejoy", u):
        p["coupling_type"] = "jaw"
    m = re.search(rf"(?:lo|truc|bore|phi)\s*(?:truc)?\s*{NUM}\s*(?:mm)?\s*(?:sang|/|-|x|×|va|voi)\s*{NUM}", u)
    if m:
        p["bore_mm"], p["bore2_mm"] = float(m.group(1)), float(m.group(2))
        ex.update(bore_mm=p["bore_mm"], bore2_mm=p["bore2_mm"])
    else:
        m = re.search(rf"(?:lo|truc|bore|phi)\s*(?:truc)?\s*{NUM}", u)
        if m:
            p["bore_mm"] = ex["bore_mm"] = float(m.group(1))


def _ball_screw(u: str, p: dict, ex: dict) -> None:
    m = re.search(r"\bsfu\s*(\d{2})(\d{2})\b", u)
    if m:
        p["diameter_mm"], p["lead_mm"] = float(int(m.group(1))), float(int(m.group(2)))
    else:
        d = re.search(rf"(?:\bphi|duong kinh|\bd)\s*(?:=|la)?\s*{NUM}", u)
        if d:
            p["diameter_mm"] = float(d.group(1))
        ld = re.search(rf"\b(?:buoc|lead)\s*(?:vit|ren)?\s*(?:=|la)?\s*{NUM}", u)
        if ld:
            p["lead_mm"] = float(ld.group(1))
    L = _length(u, r"\bdai|chieu dai|length")
    if L:
        if L < 10:                                                    # "dài 1,2" không đơn vị → mét
            L *= 1000
        p["length_mm"] = ex["length_mm"] = L
    if re.search(r"khong (?:co |kem )?goi", u):
        p["supports"] = False


def _linear_guide(u: str, p: dict, ex: dict) -> None:
    m = re.search(r"\bhg[rhw]\s*(15|20|25|30)\b", u)
    if m:
        p["series"] = f"HGR{m.group(1)}"
    m = re.search(r"\bmgn\s*(7|9|12|15)\b", u)
    if m:
        p["series"] = f"MGN{m.group(1)}"
    L = _length(u, r"\bdai|chieu dai|length", "mm")
    if L:
        if L < 10:
            L *= 1000
        p["length_mm"] = ex["length_mm"] = L
    m = re.search(rf"{NUMW}\s*(?:con truot|block|con chay)", u)
    if m and 1 <= _n(m.group(1)) <= 4:
        p["carriages"] = _n(m.group(1))


def _spring(u: str, p: dict, ex: dict) -> None:
    if re.search(r"\bkeo\b|extension", u):
        p["spring_type"] = "extension"
    elif re.search(r"\bxoan\b|xoan ?oc chan|torsion", u):
        p["spring_type"] = "torsion"
    elif re.search(r"\bnen\b|compression", u):
        p["spring_type"] = "compression"
    m = re.search(rf"(?:\bday|soi|duong kinh day|phi day)\s*(?:=|la|phi)?\s*{NUM}", u)
    if m:
        p["wire_d_mm"] = ex["wire_d_mm"] = float(m.group(1))
    m = re.search(rf"(?:duong kinh ngoai|phi ngoai|\bngoai|\bod|\bphi)\s*(?:=|la)?\s*{NUM}", u)
    if m:
        p["outer_d_mm"] = ex["outer_d_mm"] = float(m.group(1))
    L = _length(u, r"chieu dai tu do|dai tu do|\bdai|chieu dai")
    if L:
        p["free_length_mm"] = ex["free_length_mm"] = L
    m = re.search(rf"{NUM}\s*vong", u)
    if m:
        p["active_coils"] = float(m.group(1))
    if re.search(r"mai phang|\bmai\b|ground", u):
        p["ends"] = "ground"
    elif re.search(r"khep kin|dau kin|closed", u):
        p["ends"] = "closed"
    elif re.search(r"dau ho|\bho\b|open", u):
        p["ends"] = "open"
    if re.search(r"inox|khong gi|stainless", u):
        p["material"] = "stainless"


def _robot_arm(u: str, p: dict, ex: dict) -> None:
    r = _length(u, r"tam voi|reach|ban kinh lam viec", "mm")
    if r:
        if r < 10:
            r *= 1000
        p["reach_mm"] = ex["reach_mm"] = r
    m = re.search(rf"(?:tai(?: trong)?|payload|nang)\s*(?:la|toi|=)?\s*{NUM}\s*kg|\b{NUM}\s*kg\b", u)
    if m:
        p["payload_kg"] = ex["payload_kg"] = float(m.group(1) or m.group(2))
    if re.search(r"cong nghiep|\bkuka\b|\babb\b|\bfanuc\b|son cam|khau duc", u):
        p["style"] = "industrial"
    elif re.search(r"\bcobot\b|cong tac|\bur ?(?:3|5|10|16)", u):
        p["style"] = "cobot"
    m = re.search(r"\bur ?(3|5|10|16)e?\b", u)
    if m and "reach_mm" not in p:
        p["reach_mm"] = {"3": 500.0, "5": 850.0, "10": 1300.0, "16": 900.0}[m.group(1)]
        p.setdefault("payload_kg", float(m.group(1)))
    if re.search(r"khong (?:co )?(?:tay kep|kep|dung cu|dau cong cu)", u):
        p["end_effector"] = "none"
    elif re.search(r"giac hut|hut chan khong|vacuum|cup hut|dau hut", u):
        p["end_effector"] = "vacuum"
    elif re.search(r"tay kep|\bkep\b|gripper|ngon kep", u):
        p["end_effector"] = "gripper"
    for pose, pat in (("reach", r"duoi thang|vuon xa|duoi dai|vuon toi"), ("upright", r"thang dung|dung thang|upright|tu the home"),
                      ("pick", r"gap hang|nhat hang|\bpick\b|cui xuong|gap vat"), ("ready", r"san sang|\bready\b")):
        if re.search(pat, u):
            p["pose"] = pose
            break
    for m in re.finditer(r"\b(?:khop|j)\s*([1-6])\s*(?:=|la|quay)?\s*(-?\d+(?:\.\d+)?)\s*(?:do|°)", u):
        p[f"j{m.group(1)}_deg"] = float(m.group(2))


def _robot_vacuum(u: str, p: dict, ex: dict) -> None:
    d = _length(u, r"duong kinh|\bphi|\bd")
    if d and 200 <= d <= 450:
        p["diameter_mm"] = ex["diameter_mm"] = d
    if re.search(r"khong (?:co )?lidar|khong (?:co )?thap laser", u):
        p["lidar"] = False
    elif re.search(r"lidar|\blds\b|laser", u):
        p["lidar"] = True
    m = re.search(rf"{NUMW}\s*choi canh", u)
    if m and _n(m.group(1)) in (1, 2):
        p["side_brushes"] = _n(m.group(1))
    if re.search(r"khong (?:co )?(?:lau|tam lau|mop)", u):
        p["mop"] = False
    elif re.search(r"lau nha|tam lau|\bmop\b|lau uot|\blau\b", u):
        p["mop"] = True
    if re.search(r"khong (?:co )?(?:de sac|dock|tram sac)", u):
        p["dock"] = False


def _agv(u: str, p: dict, ex: dict) -> None:
    if re.search(r"mecanum|da huong|omni|di ngang", u):
        p["drive"] = "mecanum"
    elif re.search(r"vi sai|differential|hai banh chu dong|2 banh chu dong", u):
        p["drive"] = "differential"
    # "robot giao hàng nâng kệ" → nâng kệ; "robot nâng kệ có thùng hàng" → thùng hàng: đặc điểm nói SAU cùng thắng
    last = []
    for kind, pat in (("lift", r"nang ke|kich nang|mam nang|\blift\b|kiva|nang hang"),
                      ("cargo", r"giao hang|thung hang|thung chua|cargo|hop hang|cho hang")):
        ms = list(re.finditer(pat, u))
        if ms:
            last.append((ms[-1].start(), kind))
    if last:
        p["top"] = max(last)[1]
    L = _length(u, r"\bdai|chieu dai")
    if L:
        if L < 10:
            L *= 1000
        p["length_mm"] = ex["length_mm"] = L
    if re.search(r"khong (?:co )?(?:lidar|may quet)", u):
        p["lidar"] = False


def _count(u: str, words: str) -> int | None:
    m = re.search(rf"{NUMW}\s*(?:{words})", u)
    return _n(m.group(1)) if m else None


def _train(u: str, p: dict, ex: dict) -> None:
    if re.search(r"tau dien|cap dien|can lay dien|pantograph|\bmetro\b|dien khi hoa|dau may dien", u):
        p["traction"] = "electric"
    elif re.search(r"diesel|dau may dau|d19e", u):
        p["traction"] = "diesel"
    n = _count(u, r"toa")
    if n is not None:
        p["wagons"] = ex["wagons"] = min(n, 4)
    elif re.search(r"\bdau may\b", u) and not re.search(r"\btoa\b|doan tau", u):
        p["wagons"] = 0
    if re.search(r"toa hang|cho hang|hang hoa|container|freight|tau hang", u):
        p["wagon_type"] = "freight"
    elif re.search(r"toa khach|cho khach|tau khach", u):
        p["wagon_type"] = "passenger"
    if re.search(r"1435|kho (?:tieu )?chuan|standard gauge|kho quoc te", u):
        p["gauge"] = "standard"
    elif re.search(r"kho met|kho 1000|kho 1 ?m\b|meter gauge", u):
        p["gauge"] = "meter"


def _cubesat(u: str, p: dict, ex: dict) -> None:
    m = re.search(r"\b(1|2|3|6|12) ?u\b", u)
    if m:
        p["units"] = ex["units"] = int(m.group(1))
    if re.search(r"khong (?:co )?(?:canh pin|tam pin|canh mo)", u):
        p["deployable_panels"] = False
    elif re.search(r"canh pin|tam pin (?:mo|bung)", u):
        p["deployable_panels"] = True


def _launch(u: str, p: dict, ex: dict) -> None:
    n = _count(u, r"tang")
    if n in (2, 3):
        p["stages"] = ex["stages"] = n
    h = _length(u, r"cao|chieu cao", "m")
    if h:
        p["height_mm"] = ex["height_mm"] = h if h > 1000 else h * 1000
    d = _length(u, r"duong kinh|\bphi", "m")
    if d:
        p["diameter_mm"] = ex["diameter_mm"] = d if d > 100 else d * 1000
    if re.search(r"khong (?:co )?canh", u):
        p["fins"] = False


def _fixed_wing(u: str, p: dict, ex: dict) -> None:
    if re.search(r"\bvtol\b|quadplane|cat ha canh thang dung|(?:4|bon) rotor nang", u):
        p["aircraft_type"] = "vtol"
    elif re.search(r"\buav\b|khong nguoi lai|\bdrone\b|may bay mo hinh", u):
        p["aircraft_type"] = "uav"
    elif re.search(r"hang nhe|(?:4|bon) cho|cessna|piper|the thao|huan luyen|tu nhan", u):
        p["aircraft_type"] = "light"
    b = _length(u, r"sai canh|wingspan", "m")
    if b:
        p["wingspan_mm"] = ex["wingspan_mm"] = b if b > 100 else b * 1000
    m = re.search(rf"(?:nhi dien|dihedral)\s*(?:la|=)?\s*{NUM}\s*(?:do|°)?", u)
    if m:
        p["dihedral_deg"] = ex["dihedral_deg"] = float(m.group(1))
    if re.search(r"duoi (?:chu )?v\b|v-?tail", u):
        p["tail"] = "v_tail"
    elif re.search(r"duoi (?:chu )?t\b|t-?tail", u):
        p["tail"] = "t_tail"


def _car(u: str, p: dict, ex: dict) -> None:
    if re.search(r"\bsuv\b|gam cao|crossover|(?:7|bay) cho|vf ?[789]\b", u):
        p["body_type"] = "suv"
    elif re.search(r"hatchback|\bhatch\b|co nho|vf ?[35]\b|xe do thi", u):
        p["body_type"] = "hatchback"
    elif re.search(r"\bsedan\b|(?:4|bon) cua|xe con", u):
        p["body_type"] = "sedan"
    L = _length(u, r"\bdai|chieu dai", "m")
    if L:
        p["length_mm"] = ex["length_mm"] = L if L > 100 else L * 1000
    if re.search(r"\bawd\b|\b4wd\b|2 motor|hai motor|dan dong (?:4|bon) banh|dual motor|hai cau", u):
        p["drive"] = "awd"
    elif re.search(r"\brwd\b|cau sau|1 motor|mot motor", u):
        p["drive"] = "rwd"


def _motorbike(u: str, p: dict, ex: dict) -> None:
    if re.search(r"xe dap dien|e-?bike|\bxe dap\b", u):
        p["bike_type"] = "ebike"
    elif re.search(r"tay ga|scooter|\bvespa\b|honda (?:vision|sh|air ?blade)|yamaha janus|xe may dien", u):
        p["bike_type"] = "scooter"
    elif re.search(r"mo ?to|con tay|xe so|exciter|winner|phan khoi|naked|motorcycle|\bmoto\b", u):
        p["bike_type"] = "motorcycle"


def _excavator(u: str, p: dict, ex: dict) -> None:
    if re.search(r"\bmini\b|may xuc nho|co nho", u):
        p["size_class"] = "mini"
    elif re.search(r"\blon\b|khong lo|co lon|hang nang", u):
        p["size_class"] = "large"
    m = re.search(rf"{NUM}\s*tan\b", u)
    if m:
        t = float(m.group(1))
        p["size_class"] = "mini" if t <= 8 else ("medium" if t <= 32 else "large")
    for pose, pat in (("transport", r"di chuyen|thu gon|van chuyen|gap can"), ("reach", r"vuon xa|duoi (?:can|thang)|vuon toi"),
                      ("dig", r"dang dao|tu the dao|\bdao\b|xuc dat")):
        if re.search(pat, u):
            p["pose"] = pose
            break
    m = re.search(r"(?:quay|xoay|swing)\s*(?:than tren|toa|mam)?\s*(-?\d+(?:\.\d+)?)\s*(?:do|°)", u)
    if m and -180 <= float(m.group(1)) <= 180:
        p["swing_deg"] = ex["swing_deg"] = float(m.group(1))


def _forklift(u: str, p: dict, ex: dict) -> None:
    m = re.search(rf"{NUM}\s*(tan|kg)\b", u)
    if m:
        q = float(m.group(1)) * (1000 if m.group(2) == "tan" else 1)
        if 1000 <= q <= 5000:
            p["capacity_kg"] = ex["capacity_kg"] = q
    if re.search(r"\bdau\b|diesel|dong co dot|may dau|chay dau", u):
        p["power"] = "diesel"
    elif re.search(r"\bdien\b|ac ?quy|battery", u):
        p["power"] = "electric"
    h = _length(u, r"nang (?:cao|len)|cang (?:o )?(?:do )?cao|chieu cao nang|nang toi", "m")
    if h is not None:
        h = h if h > 50 else h * 1000
        if 0 <= h <= 4500:
            p["fork_height_mm"] = ex["fork_height_mm"] = h


def _crane(u: str, p: dict, ex: dict) -> None:
    L = _length(u, r"can (?:dai|chinh dai|vuon)|dai can|chieu dai can|can", "m")
    if L:
        L = L if L > 100 else L * 1000
        if 9000 <= L <= 40000:
            p["boom_length_mm"] = ex["boom_length_mm"] = L
    m = re.search(rf"(?:goc (?:nang )?(?:can )?|nghieng |nang can )(?:la |=)?{NUM}\s*(?:do|°)", u)
    if m and 0 <= float(m.group(1)) <= 80:
        p["boom_angle_deg"] = ex["boom_angle_deg"] = float(m.group(1))
    n = _count(u, r"truc(?! vit)|cau xe")
    if n in (2, 3, 4):
        p["axles"] = ex["axles"] = n


def _wind(u: str, p: dict, ex: dict) -> None:
    d = _length(u, r"duong kinh rotor|rotor|duong kinh canh|duong kinh", "m")
    if d:
        p["rotor_diameter_mm"] = ex["rotor_diameter_mm"] = d if d > 1000 else d * 1000
    h = _length(u, r"cao|chieu cao thap|thap cao|tam rotor cao|cot cao", "m")
    if h:
        p["hub_height_mm"] = ex["hub_height_mm"] = h if h > 1000 else h * 1000
    n = _count(u, r"canh")
    if n in (2, 3):
        p["blades"] = ex["blades"] = n
    if re.search(r"mo nap|mo vo|nap mo|thay ben trong|mo nacelle|lo hop so|mo buong may", u):
        p["nacelle_open"] = True


def _solar(u: str, p: dict, ex: dict) -> None:
    n = _count(u, r"tam(?! nghieng)")
    if n:
        p["panels"] = ex["panels"] = min(n, 40)
    m = re.search(rf"{NUM}\s*kwp", u)
    if m and "panels" not in p:
        p["panels"] = ex["panels"] = max(1, min(40, round(float(m.group(1)) / 0.4)))
    r = _count(u, r"hang|day")
    if r and r <= 4:
        p["rows"] = ex["rows"] = r
    m = re.search(rf"(?:nghieng|goc nghieng|goc)\s*(?:la |=)?{NUM}\s*(?:do|°)", u)
    if m and 0 <= float(m.group(1)) <= 45:
        p["tilt_deg"] = ex["tilt_deg"] = float(m.group(1))
    if re.search(r"khong (?:co )?(?:bien tan|inverter)", u):
        p["inverter"] = False


def _genset(u: str, p: dict, ex: dict) -> None:
    m = re.search(rf"{NUM}\s*kva", u)
    if m:
        p["power_kva"] = ex["power_kva"] = float(m.group(1))
    else:
        m = re.search(rf"{NUM}\s*kw\b", u)
        if m:
            p["power_kva"] = ex["power_kva"] = round(float(m.group(1)) / 0.8)
    if re.search(r"khung tran|\bmo\b|khong (?:co )?vo|dang tran|open", u):
        p["enclosure"] = "open"
    elif re.search(r"vo cach am|cach am|chong on|silent|co vo|canopy", u):
        p["enclosure"] = "canopy"


def _pump(u: str, p: dict, ex: dict) -> None:
    m = re.search(r"\b(50-32|65-50|80-65|100-80|125-100)-(160|200|250)\b", u)
    sizes = ["50-32-160", "65-50-160", "80-65-160", "100-80-200", "125-100-250"]
    if m and m.group(0) in sizes:
        p["size"] = m.group(0)
    else:
        dn = _dn(u)
        if dn:
            best = next((s_ for s_ in sizes if int(s_.split("-")[0]) >= dn), sizes[-1])
            p["size"] = best
    m = re.search(rf"{NUM}\s*kw\b", u)
    if m and 0.75 <= float(m.group(1)) <= 90:
        p["motor_kw"] = ex["motor_kw"] = float(m.group(1))


def _tank(u: str, p: dict, ex: dict) -> None:
    if re.search(r"bon nam|nam ngang|dat nam|horizontal", u):
        p["orientation"] = "horizontal"
    elif re.search(r"bon dung|dung thang|vertical", u):
        p["orientation"] = "vertical"
    m = re.search(rf"{NUM}\s*(?:m3|m khoi|khoi\b|m³)", u)
    if m:
        p["capacity_m3"] = ex["capacity_m3"] = float(m.group(1))
    else:
        m = re.search(rf"{NUM}\s*(?:lit|l)\b", u)
        if m and float(m.group(1)) >= 1000:
            p["capacity_m3"] = ex["capacity_m3"] = float(m.group(1)) / 1000.0
    d = _length(u, r"duong kinh|\bphi", "m")
    if d:
        p["diameter_mm"] = ex["diameter_mm"] = d if d > 100 else d * 1000
    if re.search(r"mai vom|mai cau|dome", u):
        p["roof"] = "dome"
    elif re.search(r"mai con|mai non", u):
        p["roof"] = "cone"


def _bridge(u: str, p: dict, ex: dict) -> None:
    if re.search(r"day vang|cable.?stayed", u):
        p["bridge_type"] = "cable_stayed"
    elif re.search(r"\bvom\b|\barch\b", u):
        p["bridge_type"] = "arch"
    elif re.search(r"\bgian\b|\btruss\b|dan thep", u):
        p["bridge_type"] = "truss"
    L = _length(u, r"nhip|dai|chieu dai", "m")
    if L is None:                                                      # "cầu giàn 30 m": số đo trần có đơn vị m (không kèm "rộng")
        m = re.search(rf"(?<!rong )(?<!rong la ){NUM}\s*(?:m|met)\b", u)
        L = float(m.group(1)) if m else None
    if L:
        L = L if L > 1000 else L * 1000
        if 20000 <= L <= 120000:
            p["span_mm"] = ex["span_mm"] = L
    w = _length(u, r"rong|be rong|mat cau rong", "m")
    if w:
        w = w if w > 100 else w * 1000
        if 4000 <= w <= 20000:
            p["deck_width_mm"] = ex["deck_width_mm"] = w


def _truss(u: str, p: dict, ex: dict) -> None:
    for t in ("pratt", "howe", "warren", "fink"):
        if re.search(rf"\b{t}\b", u):
            p["truss_type"] = t
            break
    else:
        if re.search(r"tam giac|keo mai|mai doc", u):
            p["truss_type"] = "fink"
    L = _length(u, r"nhip|dai|khau do", "m")
    if L:
        L = L if L > 100 else L * 1000
        if 6000 <= L <= 30000:
            p["span_mm"] = ex["span_mm"] = L
    h = _length(u, r"cao|chieu cao", "m")
    if h:
        h = h if h > 50 else h * 1000
        if 800 <= h <= 6000:
            p["height_mm"] = ex["height_mm"] = h
    n = _count(u, r"khoang|o gian")
    if n and n % 2 == 0 and 4 <= n <= 12:
        p["panels"] = ex["panels"] = n


def _tower(u: str, p: dict, ex: dict) -> None:
    if re.search(r"vien thong|\bbts\b|anten|ang ten|truyen hinh|song di dong|phat song", u):
        p["tower_type"] = "telecom"
    elif re.search(r"cot dien|dien cao the|truyen tai|duong day|110 ?kv|220 ?kv|500 ?kv", u):
        p["tower_type"] = "power"
    h = _length(u, r"cao|chieu cao", "m")
    if h is None:                                                      # "cột điện cao thế 40 m": số đo trần có đơn vị m
        m = re.search(rf"{NUM}\s*(?:m|met)\b", u)
        h = float(m.group(1)) * 1000 if m else None
    if h:
        h = h if h > 1000 else h * 1000
        if 10000 <= h <= 60000:
            p["height_mm"] = ex["height_mm"] = h
    n = _count(u, r"chan")
    if n in (3, 4):
        p["legs"] = ex["legs"] = n


def _dims3(u: str) -> list[float] | None:
    """"300x300x400 mm", "600 x 400", "30×40 cm" → danh sách kích thước mm (2 hoặc 3 số)."""
    m = re.search(rf"{NUM}\s*[x×*]\s*{NUM}(?:\s*[x×*]\s*{NUM})?{UNIT}", u)
    if not m:
        return None
    return [_mm(v, m.group(4)) for v in m.groups()[:3] if v is not None]


def _in_range(p: dict, ex: dict, key: str, val: float | None, lo: float, hi: float) -> None:
    if val is not None and lo <= val <= hi:
        p[key] = ex[key] = float(val)


def _printer(u: str, p: dict, ex: dict) -> None:
    if re.search(r"core ?xy|hop kin|\bvoron\b|bambu (?:x1|p1)|\bbuong kin\b", u):
        p["kinematics"] = "corexy"
    elif re.search(r"\bi3\b|ban truot|bedslinger|\bender\b|prusa ?(?:mk|i3)|ban chay (?:truoc sau|y)", u):
        p["kinematics"] = "bedslinger"
    d = _dims3(u)
    if d:
        for key, v in zip(("build_x_mm", "build_y_mm", "build_z_mm"), d):
            _in_range(p, ex, key, v, 100, 450 if key == "build_z_mm" else 400)
    else:
        w = _length(u, r"vung in|kho in|ban in|kich thuoc in")
        _in_range(p, ex, "build_x_mm", w, 100, 400)
        _in_range(p, ex, "build_y_mm", w, 100, 400)
    _in_range(p, ex, "build_z_mm", _length(u, r"cao in|chieu cao in|in cao|in duoc cao|truc z|hanh trinh z"), 100, 450)


def _cnc(u: str, p: dict, ex: dict) -> None:
    m = re.search(r"\bcnc\s*(\d{2})(\d{2})\b|\b(\d{2})(\d{2})\s*cnc\b", u)       # "CNC 6040" = hành trình 600 × 400
    d = _dims3(u)
    if d:
        _in_range(p, ex, "travel_x_mm", d[0], 300, 1500)
        _in_range(p, ex, "travel_y_mm", d[1], 300, 1500)
        if len(d) > 2:
            _in_range(p, ex, "travel_z_mm", d[2], 60, 250)
    elif m:
        a, b_ = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        # 6040 → 600 × 400 (cm); 1325 → 1300 × 2500 (cặp < 30 tính theo trăm mm)
        for key, n in (("travel_x_mm", int(a)), ("travel_y_mm", int(b_))):
            p[key] = ex[key] = float(min(1500, max(300, n * 10 if n >= 30 else n * 100)))
    _in_range(p, ex, "travel_z_mm", _length(u, r"hanh trinh z|truc z|\bz"), 60, 250)
    m = re.search(rf"{NUM}\s*kw\b", u)
    if m:
        _in_range(p, ex, "spindle_kw", float(m.group(1)), 0.5, 5.5)
    else:
        m = re.search(rf"{NUM}\s*w\b", u)
        if m:
            _in_range(p, ex, "spindle_kw", float(m.group(1)) / 1000.0, 0.5, 5.5)


def _rack(u: str, p: dict, ex: dict) -> None:
    m = re.search(r"\b(\d{1,2})\s*u\b", u)
    if m and 6 <= int(m.group(1)) <= 48:
        p["rack_units"] = ex["rack_units"] = int(m.group(1))
    _in_range(p, ex, "depth_mm", _length(u, r"sau|chieu sau|do sau|depth"), 450, 1200)
    if re.search(r"khong (?:co |lap )?thiet bi|tu (?:trong|rong)|chua lap|vo tu", u):
        p["equipment"] = False


def _enclosure(u: str, p: dict, ex: dict) -> None:
    d = _dims3(u)
    if d:
        _in_range(p, ex, "width_mm", d[0], 200, 1200)
        _in_range(p, ex, "height_mm", d[1], 200, 1400)
        if len(d) > 2:
            _in_range(p, ex, "depth_mm", d[2], 120, 400)
    else:
        _in_range(p, ex, "width_mm", _length(u, r"rong|chieu rong|ngang"), 200, 1200)
        _in_range(p, ex, "height_mm", _length(u, r"cao|chieu cao"), 200, 1400)
    _in_range(p, ex, "depth_mm", _length(u, r"sau|chieu sau"), 120, 400)
    if re.search(r"khong (?:co )?(?:o )?kinh", u):
        p["window"] = False
    elif re.search(r"cua kinh|o kinh|kinh quan sat|cua so|mat kinh|window", u):
        p["window"] = True


def _fan(u: str, p: dict, ex: dict) -> None:
    m = re.search(r"\b(40|60|80|92|120|140)\s*(?:mm|ly)?\b", u)
    if m:
        p["size_mm"] = ex["size_mm"] = int(m.group(1))
    else:
        m = re.search(r"\b(4|6|8|12|14)\s*cm\b", u)
        if m:
            p["size_mm"] = ex["size_mm"] = int(m.group(1)) * 10
    n = _count(u, r"canh|la canh")
    if n and 5 <= n <= 11:
        p["blades"] = ex["blades"] = n
    if re.search(r"khong (?:co )?(?:luoi|guard)|bo luoi", u):
        p["guard"] = False
    elif re.search(r"co luoi|luoi bao ve|guard", u):
        p["guard"] = True


def _heatsink(u: str, p: dict, ex: dict) -> None:
    if re.search(r"nhom dun|tan (?:nhom|phang)|extruded|dang tam|tan nhiet nhom", u):
        p["heatsink_type"] = "extruded"
    elif re.search(r"\bthap\b|tower|ong dong|ong dan nhiet|heat ?pipe|cpu", u):
        p["heatsink_type"] = "tower"
    n = _count(u, r"ong (?:dong|dan nhiet|nhiet)|heat ?pipe")
    if n is not None and 0 <= n <= 8:
        p["heat_pipes"] = ex["heat_pipes"] = n
        p.setdefault("heatsink_type", "tower")
    if re.search(r"khong (?:co |kem )?quat", u):
        p["fan"] = False
    elif re.search(r"(?:co|kem|gan) quat", u):
        p["fan"] = True


def _board(u: str, p: dict, ex: dict) -> None:
    if re.search(r"raspberry|\brpi\b|\bpi ?4\b|may tinh nhung", u):
        p["board"] = "raspberry_pi"
    elif re.search(r"arduino|\buno\b|atmega", u):
        p["board"] = "arduino_uno"


PARSERS: dict[str, Callable[[str, dict, dict], None]] = {
    "bearing": _bearing, "stepper_motor": _stepper, "gearbox": _gearbox, "cylinder": _cylinder, "ball_valve": _valve,
    "pipe_fitting": _fitting, "belt_drive": _belt, "chain_drive": _chain, "shaft_coupling": _coupling,
    "ball_screw": _ball_screw, "linear_guide": _linear_guide, "spring": _spring,
    "robot_arm": _robot_arm, "robot_vacuum": _robot_vacuum, "agv": _agv,
    "train": _train, "cubesat": _cubesat, "launch_vehicle": _launch, "fixed_wing": _fixed_wing, "car": _car, "motorbike": _motorbike,
    "excavator": _excavator, "forklift": _forklift, "crane": _crane,
    "wind_turbine": _wind, "solar_array": _solar, "generator_set": _genset, "centrifugal_pump": _pump, "storage_tank": _tank,
    "bridge": _bridge, "steel_truss": _truss, "lattice_tower": _tower,
    "fdm_printer": _printer, "cnc_router": _cnc, "server_rack": _rack, "electrical_enclosure": _enclosure, "axial_fan": _fan,
    "heatsink": _heatsink, "dev_board": _board,
}


def parse(cat: str, u: str, text: str, p: dict, explicit: dict, req: list, raw: dict) -> None:
    fn = PARSERS.get(cat)
    if fn is not None:
        fn(u, p, explicit)


def default_name(cat: str, p: dict) -> str | None:
    if cat == "bearing":
        return f"Ổ bi {p['designation']}" + (f"-{p['seal']}" if p.get("seal") in ("2RS", "ZZ") else "") if "designation" in p else "Ổ bi"
    if cat == "stepper_motor":
        return f"Động cơ bước NEMA {p.get('frame_size', 17)}"
    if cat == "gearbox":
        return f"Hộp số {p.get('stages', 2)} cấp" + (f" i = {p['ratio']:g}" if "ratio" in p else "")
    if cat == "cylinder":
        kind = "thủy lực" if p.get("cylinder_type") == "hydraulic" else "khí nén"
        return f"Xi lanh {kind}" + (f" Ø{p['bore_mm']:g}" if "bore_mm" in p else "") + (f"×{p['stroke_mm']:g}" if "stroke_mm" in p else "")
    if cat == "ball_valve":
        return f"Van bi DN{p.get('dn', 50)}"
    if cat == "pipe_fitting":
        nm = {"flange_joint": "Mối nối mặt bích", "elbow45": "Co 45°", "tee": "Tê đều"}.get(p.get("fitting", ""), "Co 90°")
        return f"{nm} DN{p.get('dn', 50)}"
    if cat == "belt_drive":
        return f"Bộ truyền đai {p.get('belt', 'GT2')}"
    if cat == "chain_drive":
        return f"Bộ truyền xích {p.get('chain', '08B')}"
    if cat == "shaft_coupling":
        return "Khớp nối cứng" if p.get("coupling_type") == "rigid" else "Khớp nối mềm vấu"
    if cat == "ball_screw":
        return f"Vít me bi SFU{int(p.get('diameter_mm', 16)):02d}{int(p.get('lead_mm', 5)):02d}"
    if cat == "linear_guide":
        return f"Ray trượt {p.get('series', 'HGR20')}"
    if cat == "robot_arm":
        return ("Robot công nghiệp 6 trục" if p.get("style") == "industrial" else "Cánh tay robot 6 trục") + \
            (f" tầm với {p['reach_mm']:g} mm" if "reach_mm" in p else "")
    if cat == "robot_vacuum":
        return "Robot hút bụi" + (" lau nhà" if p.get("mop") else "")
    if cat == "agv":
        return "Robot giao hàng" if p.get("top") == "cargo" else "Robot AGV nâng kệ" + (" mecanum" if p.get("drive") == "mecanum" else "")
    if cat == "spring":
        return {"extension": "Lò xo kéo", "torsion": "Lò xo xoắn"}.get(p.get("spring_type", ""), "Lò xo nén")
    if cat == "train":
        n = p.get("wagons", 2)
        return ("Tàu điện" if p.get("traction") == "electric" else "Đầu máy diesel") + (f" + {n} toa" if n else "")
    if cat == "cubesat":
        return f"Vệ tinh CubeSat {p.get('units', 3)}U"
    if cat == "launch_vehicle":
        return f"Tên lửa {p.get('stages', 2)} tầng"
    if cat == "fixed_wing":
        return {"light": "Máy bay hạng nhẹ 4 chỗ", "uav": "UAV cánh cố định", "vtol": "UAV VTOL cánh cố định"}[p.get("aircraft_type", "light")]
    if cat == "car":
        return {"sedan": "Ô tô điện sedan", "suv": "Ô tô điện SUV", "hatchback": "Ô tô điện hatchback"}[p.get("body_type", "sedan")]
    if cat == "motorbike":
        return {"motorcycle": "Mô tô côn tay", "scooter": "Xe tay ga", "ebike": "Xe đạp điện"}[p.get("bike_type", "motorcycle")]
    if cat == "excavator":
        return {"mini": "Máy xúc mini", "medium": "Máy xúc bánh xích 20 tấn", "large": "Máy xúc cỡ lớn"}[p.get("size_class", "medium")]
    if cat == "forklift":
        return f"Xe nâng {'dầu' if p.get('power') == 'diesel' else 'điện'} {p.get('capacity_kg', 2500.0) / 1000:g} tấn"
    if cat == "crane":
        return f"Xe cẩu cần ống lồng {p.get('boom_length_mm', 18000.0) / 1000:g} m"
    if cat == "wind_turbine":
        return f"Tuabin gió rotor Ø{p.get('rotor_diameter_mm', 90000.0) / 1000:g} m"
    if cat == "solar_array":
        n = p.get("panels", 12)
        return f"Hệ điện mặt trời {n} tấm ({n * 0.4:g} kWp)"
    if cat == "generator_set":
        return f"Máy phát điện {p.get('power_kva', 100.0):g} kVA" + (" khung trần" if p.get("enclosure") == "open" else " vỏ cách âm")
    if cat == "centrifugal_pump":
        return f"Máy bơm ly tâm {p.get('size', '65-50-160')}"
    if cat == "storage_tank":
        return f"Bồn chứa {'nằm' if p.get('orientation') == 'horizontal' else 'đứng'} {p.get('capacity_m3', 50.0):g} m³"
    if cat == "bridge":
        return {"truss": "Cầu giàn thép", "cable_stayed": "Cầu dây văng", "arch": "Cầu vòm"}[p.get("bridge_type", "truss")] + \
            f" nhịp {p.get('span_mm', 60000.0) / 1000:g} m"
    if cat == "steel_truss":
        return f"Giàn thép {p.get('truss_type', 'pratt').title()} nhịp {p.get('span_mm', 12000.0) / 1000:g} m"
    if cat == "lattice_tower":
        return ("Cột điện cao thế" if p.get("tower_type", "power") == "power" else "Tháp viễn thông") + f" cao {p.get('height_mm', 30000.0) / 1000:g} m"
    if cat == "fdm_printer":
        kin = "CoreXY" if p.get("kinematics") == "corexy" else "kiểu i3"
        return f"Máy in 3D {kin} {p.get('build_x_mm', 220.0):g}×{p.get('build_y_mm', 220.0):g}×{p.get('build_z_mm', 250.0):g} mm"
    if cat == "cnc_router":
        return (f"Máy CNC router {p.get('travel_x_mm', 600.0):g}×{p.get('travel_y_mm', 400.0):g}×{p.get('travel_z_mm', 100.0):g}"
                f" trục chính {p.get('spindle_kw', 2.2):g} kW")
    if cat == "server_rack":
        return f"Tủ rack 19 inch {p.get('rack_units', 42)}U sâu {p.get('depth_mm', 1000.0):g} mm"
    if cat == "electrical_enclosure":
        return f"Tủ điện {p.get('width_mm', 600.0):g}×{p.get('height_mm', 800.0):g}×{p.get('depth_mm', 250.0):g} mm"
    if cat == "axial_fan":
        return f"Quạt tản nhiệt {p.get('size_mm', 120)} mm {p.get('blades', 7)} cánh"
    if cat == "heatsink":
        if p.get("heatsink_type") == "extruded":
            return "Tản nhiệt nhôm đùn"
        return f"Tản nhiệt tháp CPU {p.get('heat_pipes', 4)} ống đồng"
    if cat == "dev_board":
        return "Raspberry Pi 4 B" if p.get("board") == "raspberry_pi" else "Arduino Uno R3"
    return None


__all__ = ["TECH_PATTERNS", "PARSERS", "parse", "default_name"]
