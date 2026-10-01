p = 'nexa/three_d/parse_tech.py'
s = open(p, encoding='utf-8').read()
old = '''                      r"cot bts|\\btower\\b|thap anten|cot anten|cot thep|\\bthap\\b", 22),
]'''
assert old in s
new = old[:-2] + '''    # chế tạo & điện tử: máy in 3D / CNC tầng 8 (thắng "vít me", "ổ bi", "quạt"… là chi tiết của máy); tủ rack 30 thắng
    # "quạt" ("tủ rack có quạt"), tủ điện 31 thua hệ pin mặt trời (tầng 20, có tủ điện/biến tần); quạt, tản nhiệt,
    # bo mạch cùng tầng 40 → từ khóa xuất hiện trước thắng ("quạt tản nhiệt" là quạt, "tản nhiệt có quạt" là tản nhiệt)
    ("fdm_printer", r"may in (?:3 ?d|ba chieu|3 chieu|fdm|nhua|resin)|\\b3d printer\\b|\\bprinter 3d\\b|\\bfdm\\b|\\bender ?-?[35]\\b|\\bprusa\\b|"
                    r"\\bbambu\\b|\\bvoron\\b|\\bin 3 ?d\\b|\\bcore ?xy\\b|bedslinger", 8),
    ("cnc_router", r"\\bcnc\\b|may phay|may khac (?:go|cnc)|may dieu khac|cnc router|\\brouter (?:go|cnc)\\b|"
                   r"may cat cnc|may gia cong cnc", 8),
    ("server_rack", r"tu rack|tu mang|tu server|tu may chu|server rack|\\brack (?:19|tu|server|mang|\\d+ ?u)\\b|tu 19 ?(?:inch|in)|"
                    r"\\btu (?:\\d+|mot|hai) ?u\\b|\\b\\d+ ?u rack\\b|\\brack\\b(?! (?:and|va) pinion)(?!.*thanh rang)|network cabinet", 30),
    ("electrical_enclosure", r"tu dien|hop dien|tu dieu khien|tu phan phoi|tu aptomat|electrical enclosure|vo tu dien|"
                             r"hop aptomat|tu dong luc|tu mcb|hop ky thuat dien", 31),
    ("axial_fan", r"quat (?:tan nhiet|may tinh|pc|case|12 ?v|5 ?v|24 ?v|dc|huong truc|hut|thong gio|\\d{2,3} ?mm|noctua)|"
                  r"(?<!canh )(?<!chong )\\bquat\\b|axial fan|\\bcase fan\\b|\\bfan (?:\\d{2,3}|pc|case)\\b", 40),
    ("heatsink", r"tan nhiet|heat ?sink|\\bong dong\\b|\\btan (?:khi|thap|cpu|nhom)\\b|cooler (?:cpu|thap)|\\bcpu cooler\\b", 40),
    ("dev_board", r"bo mach|arduino|raspberry|\\brpi\\b|\\bpi ?4\\b|mach (?:dien tu|vi dieu khien|phat trien|arduino)|\\bpcb\\b|"
                  r"board (?:mach|phat trien|arduino)|\\bdev ?board\\b|vi dieu khien|kit (?:arduino|phat trien)|\\buno r3\\b", 40),
]'''
s = s.replace(old, new)

old2 = '''PARSERS: dict[str, Callable[[str, dict, dict], None]] = {'''
fns = '''def _dims3(u: str) -> list[float] | None:
    """"300x300x400 mm", "600 x 400", "30×40 cm" → danh sách kích thước mm (2 hoặc 3 số)."""
    m = re.search(rf"{NUM}\\s*[x×*]\\s*{NUM}(?:\\s*[x×*]\\s*{NUM})?{UNIT}", u)
    if not m:
        return None
    return [_mm(v, m.group(4)) for v in m.groups()[:3] if v is not None]


def _in_range(p: dict, ex: dict, key: str, val: float | None, lo: float, hi: float) -> None:
    if val is not None and lo <= val <= hi:
        p[key] = ex[key] = float(val)


def _printer(u: str, p: dict, ex: dict) -> None:
    if re.search(r"core ?xy|hop kin|\\bvoron\\b|bambu (?:x1|p1)|\\bbuong kin\\b", u):
        p["kinematics"] = "corexy"
    elif re.search(r"\\bi3\\b|ban truot|bedslinger|\\bender\\b|prusa ?(?:mk|i3)|ban chay (?:truoc sau|y)", u):
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
    m = re.search(r"\\bcnc\\s*(\\d{2})(\\d{2})\\b|\\b(\\d{2})(\\d{2})\\s*cnc\\b", u)       # "CNC 6040" = hành trình 600 × 400
    d = _dims3(u)
    if d:
        _in_range(p, ex, "travel_x_mm", d[0], 300, 1500)
        _in_range(p, ex, "travel_y_mm", d[1], 300, 1500)
        if len(d) > 2:
            _in_range(p, ex, "travel_z_mm", d[2], 60, 250)
    elif m:
        a, b_ = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        p["travel_x_mm"] = ex["travel_x_mm"] = float(min(1500, max(300, int(a) * 10)))
        p["travel_y_mm"] = ex["travel_y_mm"] = float(min(1500, max(300, int(b_) * 10)))
    _in_range(p, ex, "travel_z_mm", _length(u, r"hanh trinh z|truc z|\\bz"), 60, 250)
    m = re.search(rf"{NUM}\\s*kw\\b", u)
    if m:
        _in_range(p, ex, "spindle_kw", float(m.group(1)), 0.5, 5.5)
    else:
        m = re.search(rf"{NUM}\\s*w\\b", u)
        if m:
            _in_range(p, ex, "spindle_kw", float(m.group(1)) / 1000.0, 0.5, 5.5)


def _rack(u: str, p: dict, ex: dict) -> None:
    m = re.search(r"\\b(\\d{1,2})\\s*u\\b", u)
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
    m = re.search(r"\\b(40|60|80|92|120|140)\\s*(?:mm|ly)?\\b", u)
    if m:
        p["size_mm"] = ex["size_mm"] = int(m.group(1))
    else:
        m = re.search(r"\\b(4|6|8|12|14)\\s*cm\\b", u)
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
    elif re.search(r"\\bthap\\b|tower|ong dong|ong dan nhiet|heat ?pipe|cpu", u):
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
    if re.search(r"raspberry|\\brpi\\b|\\bpi ?4\\b|may tinh nhung", u):
        p["board"] = "raspberry_pi"
    elif re.search(r"arduino|\\buno\\b|atmega", u):
        p["board"] = "arduino_uno"


'''
assert old2 in s
s = s.replace(old2, fns + old2)
old3 = '''    "bridge": _bridge, "steel_truss": _truss, "lattice_tower": _tower,
}'''
assert old3 in s
s = s.replace(old3, '''    "bridge": _bridge, "steel_truss": _truss, "lattice_tower": _tower,
    "fdm_printer": _printer, "cnc_router": _cnc, "server_rack": _rack, "electrical_enclosure": _enclosure, "axial_fan": _fan,
    "heatsink": _heatsink, "dev_board": _board,
}''')
old4 = '''        return ("Cột điện cao thế" if p.get("tower_type", "power") == "power" else "Tháp viễn thông") + f" cao {p.get('height_mm', 30000.0) / 1000:g} m"
    return None'''
assert old4 in s
s = s.replace(old4, old4[:-16] + '''
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
    return None''')
open(p, 'w', encoding='utf-8').write(s)
print("ok")
