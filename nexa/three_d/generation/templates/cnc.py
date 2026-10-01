"""Máy phay CNC router kiểu giàn di động (hệ X trước, Y trái, Z lên; mm).

Hành trình máy: X máy (`travel_x_mm`, đầu phay chạy ngang giàn) = trục Y kỹ thuật; Y máy (`travel_y_mm`, giàn chạy
trước–sau) = trục X kỹ thuật; Z đứng. Kết cấu:
- Đế: 2 dầm thép hộp 80×120 sơn tĩnh điện + các thanh ngang 80×80, chân tăng chỉnh; bàn máy nhôm rãnh T (rãnh T8
  cách 50 mm) tựa trên thanh ngang.
- Trục Y máy: ray HIWIN HGR20 (HGR25 khi hành trình > 900 mm) trên đỉnh 2 dầm, mỗi bên 2 con trượt; 2 vít me bi
  SFU1605/2005 chạy ngoài dầm trên gối BK/BF bắt vào tai gá, 2 động cơ NEMA 23 sau + khớp nối vấu (jaw) cỡ 19.
- Giàn: 2 tấm hông nhôm 20 mm đứng trên tấm đế con trượt, dầm giàn nhôm hộp; mặt trước dầm có 2 ray + vít me trục X
  máy (động cơ gá ngoài tấm hông, khớp nối xuyên lỗ tấm).
- Bàn trượt X (saddle) mang 2 ray đứng + vít me Z SFU1605, động cơ Z trên giá đỉnh; tấm Z mang kẹp trục chính.
- Trục chính làm mát nước theo công suất (0,8 kW Ø65 ER11 … 5,5 kW Ø125 ER25), đai ốc kẹp collet + dao phay ngón.
- Hộp điều khiển trước máy: nút dừng khẩn cấp, công tắc nguồn, núm chỉnh tốc độ trục chính, màn hình.

Số đo chuẩn: HIWIN HGR/HGH-CA, TBI SFU + THK BK/BF, NEMA ICS 16 (NEMA 23), khớp nối vấu DIN 740 (cỡ 19),
collet ER (DIN 6499).
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d import standards as S
from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.generation.templates.printer3d import box_at, frame_map
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec

TO_X = np.array([[0, 0, 1.0, 0], [1.0, 0, 0, 0], [0, 1.0, 0, 0]])     # Z → X
N23 = S.NEMA[23]
CPL = 19
CPL_D, CPL_L, _CPL_BORE = S.JAW_COUPLINGS[CPL]
# công suất tối đa (kW) → (Ø thân, dài thân, collet, Ø đai ốc collet, cao đai ốc, Ø dao)
SPINDLES = [(0.8, 65.0, 190.0, "ER11", 19.0, 11.5, 3.175), (1.5, 80.0, 200.0, "ER16", 28.0, 17.5, 6.0),
            (2.2, 80.0, 220.0, "ER20", 34.0, 19.0, 6.0), (3.2, 100.0, 240.0, "ER20", 34.0, 19.0, 6.0),
            (5.5, 125.0, 265.0, "ER25", 42.0, 20.0, 8.0)]


def rev_x(profile, segments: int = 64) -> K.Solid:
    return K.revolve(profile, segments=segments).transform(TO_X)


def _sector_prism(r0: float, r1: float, a0: float, a1: float, x0: float, length: float) -> K.Solid:
    """Khối hình quạt vành khuyên (góc a0→a1 độ, bán kính r0→r1) dọc trục X từ x0."""
    n = 10
    angs = np.radians(np.linspace(a0, a1, n))
    poly = [(r1 * math.cos(a), r1 * math.sin(a)) for a in angs] + [(r0 * math.cos(a), r0 * math.sin(a)) for a in angs[::-1]]
    return K.extrude([P.ensure_ccw(poly)], length).transform(TO_X).translate(x0, 0, 0)


def screw_axis(key: str, travel: float, motor_len: float, gap_face: float, clear: float = 0.0,
               max_tri: int = 70_000) -> dict:
    """Cụm trục vít me bi hệ cục bộ: trục dọc +X từ đầu truyền động x = 0, mặt lắp gối (đế BK/BF) z = 0, tâm trục
    z = zc. Động cơ NEMA 23 (mặt bích tại x_face, thân về −X) → khớp nối vấu → đầu trục → đai ốc khóa → BK → đoạn ren
    → BF. Đai ốc bi (mặt bích tại x = 0, thân về +X) trả riêng để đặt ở x_nut ∈ [n0, n0 + travel]; giá đai ốc (dày
    12) nằm ở [x_nut − 12, x_nut]."""
    t = S.BALL_SCREWS[key]
    d, lead = int(t["d"]), int(t["lead"])
    sup = S.SCREW_SUPPORTS[d]
    jd = float(sup["journal"])
    dr = jd - 2.0
    zc, W, H, Lb = float(sup["center_h"]), float(sup["w"]), float(sup["h"]), float(sup["l"])
    l_dr, l_th, l_bk = 15.0 + 0.5 * dr, 12.0, Lb + 2.0
    l_bf = Lb * 0.8 + 6.0
    x_thr0 = l_dr + l_th + l_bk
    x_bk = l_dr + l_th + 1.0
    nl, fl, ft = float(t["nut_l"]), float(t["flange_d"]), float(t["flange_t"])
    cx0 = l_dr - CPL_L
    x_face = cx0 - gap_face
    n0 = max(x_bk + Lb + 20.0, x_face + clear)
    thr_len = n0 + travel + nl + 12.0 - x_thr0
    Lt = x_thr0 + thr_len + l_bf
    # ---- trục ----
    rod = MC.ball_screw_rod(d, lead, t["ball"], thr_len, z0=0.0, max_triangles=max_tri).transform(TO_X).translate(x_thr0, 0, 0)
    ends = rev_x([(0, 0), (dr / 2 - 0.5, 0), (dr / 2, 0.5), (dr / 2, l_dr), (jd / 2 - 0.2, l_dr), (jd / 2 - 0.2, l_dr + l_th),
                  (jd / 2, l_dr + l_th), (jd / 2, x_thr0 + 0.01), (0, x_thr0 + 0.01)], 48)
    rf = jd / 2 - (2.0 if jd > 10 else 1.0)
    tail = rev_x([(0, Lt - l_bf - 0.01), (rf, Lt - l_bf - 0.01), (rf, Lt - 0.5), (rf - 0.5, Lt), (0, Lt)], 48)
    tail = tail - rev_x([(rf - 0.8, Lt - 3.5), (rf + 1, Lt - 3.5), (rf + 1, Lt - 2.4), (rf - 0.8, Lt - 2.4)], 48)
    kw = max(3.0, round(0.3 * dr))
    keyway = K.rounded_box(l_dr * 0.7, kw, kw * 0.6 + 1, kw * 0.49).translate(l_dr * 0.45, 0, dr / 2 - kw * 0.3 + 0.5)
    shaft = ((rod + ends + tail) - keyway).translate(0, 0, zc)
    # ---- đai ốc SFU (tâm trục z = 0, mặt bích x ∈ [0, ft]) ----
    nut = rev_x([(d / 2 + 0.02, 0), (fl / 2, 0), (fl / 2, ft), (t["nut_d"] / 2, ft + 0.8), (t["nut_d"] / 2, nl - 0.8),
                 (t["nut_d"] / 2 - 0.8, nl), (d / 2 + 0.02, nl)], 96)
    flat = fl / 2 - (fl - t["nut_d"]) * 0.22
    nut = nut - K.box(ft + 2, fl, fl).translate(ft / 2, 0, -(flat + fl / 2))
    nut = nut.subtract_all([K.cylinder(t["hole_d"] / 2, ft + 2, segments=16).transform(TO_X).translate(
        -1, t["pcd"] / 2 * math.cos(a), t["pcd"] / 2 * math.sin(a)) for a in np.radians(np.array([30, 90, 150, 210, 270, 330]))])
    r_w = d / 2 + 0.3 * (t["nut_d"] - d) / 2 + 1.0
    wipers = K.Solid.union_all([rev_x([(d / 2 + 0.02, 0), (r_w, 0), (r_w, 2.0), (d / 2 + 0.02, 2.0)], 64).translate(x0, 0, 0)
                                for x0 in (nl, nl + 2.0 - 0.01)][:1])
    r_n = t["nut_d"] / 2
    tr = 0.35 * t["ball"] + 1.0
    span = nl - ft - 6.0
    xs0, xs1 = ft + 3.0, ft + 3.0 + span
    tube_pts = np.array([[xs0, 0, r_n - 1.0], [xs0, 0, r_n + tr + 1.5], [xs0 + span * 0.2, 0, r_n + tr * 2 + 1.5],
                         [xs1 - span * 0.2, 0, r_n + tr * 2 + 1.5], [xs1, 0, r_n + tr + 1.5], [xs1, 0, r_n - 1.0]])
    tube = K.tube(P.spline_through(tube_pts, 40), tr, 14)
    nipple = (K.cylinder(1.8, 5.0, segments=12).rotate(90, 0, 0).translate(nl - 7.0, -(r_n - 0.5), 0) +
              K.sphere(1.6, 10).translate(nl - 7.0, -(r_n + 4.3), 0))
    nut_parts = [(nut, "steel_black_oxide"), (wipers, "plastic_black"), (tube, "stainless"), (nipple, "brass")]
    # ---- gối BK (cố định) + BF (tự do) ----
    blocks = []
    x_bf = Lt - l_bf + 3.0
    for tag, x0, lw in (("fixed", x_bk, Lb), ("floating", x_bf, Lb * 0.8)):
        base = K.chamfer_box(lw, W, 0.35 * zc, 0.8).translate(lw / 2, 0, 0.175 * zc)
        tower = K.hull([K.box(lw, W * 0.62, 0.01).translate(lw / 2, 0, 0.35 * zc),
                        K.cylinder(H - zc, lw, segments=64).transform(TO_X).translate(0, 0, zc)])
        blk = (base + tower) - K.cylinder(jd / 2 if tag == "fixed" else rf, lw + 2, segments=48).transform(TO_X).translate(-1, 0, zc)
        blk = blk.subtract_all([K.cylinder(0.055 * W + 1.2, 0.35 * zc + 2, segments=16).translate(lw / 2, sy * W * 0.4, -1) for sy in (1, -1)])
        blk = blk.translate(x0, 0, 0)
        if tag == "fixed":
            blk = blk + rev_x([(jd / 2 + 0.5, 0), (H - zc - 2.0, 0), (H - zc - 2.0, 3.0), (jd / 2 + 0.5, 3.0)], 64).translate(x0 + lw - 0.01, 0, zc)
            scr = K.Solid.union_all([MC.socket_screw(3.0, 6.0).transform(TO_X).translate(x0 + lw + 3.0, (H - zc - 5.0) * math.cos(a),
                                                                                           zc + (H - zc - 5.0) * math.sin(a))
                                     for a in np.radians([90, 210, 330])])
            blocks.append((blk, scr))
        else:
            blocks.append((blk, None))
    lock = MC._hex_chamfered(jd * 1.6 + 4, 6.0, both=True) - K.cylinder(jd / 2 - 0.2, 20, segments=48).translate(0, 0, -5)
    lock = lock.transform(np.array([[0, 0, -1.0, 0], [1.0, 0, 0, 0], [0, -1.0, 0, 0]])).translate(x_bk - 0.01, 0, zc)
    # ---- khớp nối vấu: 2 moay-ơ nhôm + 3 vấu mỗi bên + đệm sao polyurethane ----
    R = CPL_D / 2
    a_h = (CPL_L - 14.0) / 2
    hub_m = rev_x([(N23["shaft_d"] / 2, 0), (R - 0.8, 0), (R, 0.8), (R, a_h), (N23["shaft_d"] / 2, a_h)], 64).translate(cx0, 0, 0)
    hub_s = rev_x([(dr / 2, 0), (R, 0), (R, a_h - 0.8), (R - 0.8, a_h), (dr / 2, a_h)], 64).translate(l_dr - a_h, 0, 0)
    lugs_m = [_sector_prism(dr / 2 + 2.0, R, a, a + 40, cx0 + a_h - 0.01, 14.02) for a in (-20, 100, 220)]
    lugs_s = [_sector_prism(dr / 2 + 2.0, R, a, a + 40, cx0 + a_h - 0.01, 14.02) for a in (40, 160, 280)]
    hubs = K.Solid.union_all([hub_m, hub_s] + lugs_m + lugs_s)
    spider = rev_x([(dr / 2 + 2.5, 0), (R - 1.5, 0), (R - 1.5, 14.0), (dr / 2 + 2.5, 14.0)], 48).translate(cx0 + a_h, 0, 0)
    spider = spider.subtract_all([_sector_prism(0, R + 1, a - 1, a + 41, cx0 + a_h - 1, 16) for a in (-20, 100, 220, 40, 160, 280)])
    cscr = K.Solid.union_all([MC.socket_screw(4.0, 6.0).translate(xm, 0, R - 0.5) for xm in (cx0 + a_h / 2, l_dr - a_h / 2)])
    coupling = [(hubs.translate(0, 0, zc), "aluminum"), (spider.translate(0, 0, zc), "polyurethane"),
                (cscr.translate(0, 0, zc), "steel_black_oxide")]
    # ---- động cơ NEMA 23 ----
    nm = MC.nema_stepper(23, motor_len)
    cores = nm["shaft_core"] + nm["screw_cores"]
    to_m = lambda s: s.transform(TO_X).translate(x_face, 0, zc)
    motor = [(to_m(nm["front"] - cores), "cast_aluminum"), (to_m(nm["stack"] - cores), "steel_dark"),
             (to_m(nm["rear"] - cores), "cast_aluminum"), (to_m(nm["screws"]), "steel_black_oxide"), (to_m(nm["shaft"]), "stainless")]
    return {"key": key, "d": d, "lead": lead, "sup": sup, "zc": zc, "W": W, "H": H, "Lb": Lb, "jd": jd, "rf": rf,
            "fl": fl, "ft": ft, "nl": nl, "flat": flat, "r_w": r_w, "Lt": Lt, "x_bk": x_bk, "x_bf": x_bf, "x_face": x_face,
            "cx0": cx0, "n0": n0, "travel": travel, "motor_len": motor_len,
            "shaft": shaft, "nut": nut_parts, "bk": blocks[0], "bf": blocks[1][0], "lock": lock, "coupling": coupling, "motor": motor}


def nut_bracket(ax: dict, x_nut: float, z0: float, z1: float, extra: float = 5.0) -> K.Solid:
    """Giá đai ốc bi (hệ cục bộ trục vít): tấm dày 12 tại [x_nut − 12, x_nut], lỗ thoát phớt + 6 lỗ vít bích."""
    w = ax["fl"] / 2 + extra
    blk = box_at(x_nut - 12.0, x_nut, -w, w, z0, z1)
    blk = blk - K.cylinder(ax["r_w"] + 0.6, 30, segments=48).transform(TO_X).translate(x_nut - 20, 0, ax["zc"])
    t = S.BALL_SCREWS[ax["key"]]
    return blk.subtract_all([K.cylinder(t["hole_d"] / 2 - 0.4, 14, segments=12).transform(TO_X).translate(
        x_nut - 13, t["pcd"] / 2 * math.cos(a), ax["zc"] + t["pcd"] / 2 * math.sin(a))
        for a in np.radians(np.array([30, 90, 150, 210, 270, 330]))])


def tslot_table(x0, x1, y0, y1, z0, z1, pitch: float = 50.0) -> K.Solid:
    """Bàn nhôm rãnh T8 dọc X (miệng 8 × 7, khoang 16 × 6) cách đều `pitch`."""
    body = box_at(x0, x1, y0, y1, z0, z1)
    n = max(2, int((y1 - y0 - 30) // pitch) + 1)
    yc0 = (y0 + y1) / 2 - (n - 1) * pitch / 2
    cuts = []
    for k in range(n):
        yc = yc0 + k * pitch
        cuts.append(box_at(x0 - 1, x1 + 1, yc - 4.0, yc + 4.0, z1 - 7.0, z1 + 1))
        cuts.append(box_at(x0 - 1, x1 + 1, yc - 8.0, yc + 8.0, z1 - 13.0, z1 - 6.99))
    return body.subtract_all(cuts)


def _place(parts: list, Mx: np.ndarray) -> list:
    return [(s.transform(Mx), m) for s, m in parts]


def _shapes(parts: list) -> list[Shape]:
    """Gộp (khối, vật liệu) theo vật liệu (giữ thứ tự xuất hiện) → danh sách Shape."""
    by: dict[str, list] = {}
    for s, m in parts:
        by.setdefault(m, []).append(s)
    return [Shape(K.Solid.union_all(v) if len(v) > 1 else v[0], m, 35.0) for m, v in by.items()]


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    Tx = float(p.get("travel_x_mm", 600.0))                          # đầu phay chạy dọc Y kỹ thuật
    Ty = float(p.get("travel_y_mm", 400.0))                          # giàn chạy dọc X kỹ thuật
    Tz = float(p.get("travel_z_mm", 100.0))
    kw = float(p.get("spindle_kw", 2.2))
    series = "HGR25" if max(Tx, Ty) > 900 else "HGR20"
    G = S.LINEAR_GUIDES[series]
    key_y = "2005" if Ty > 900 else "1605"
    key_x = "2005" if Tx > 900 else "1605"
    kw_max, D, Ls, er, nut_d, nut_h, tool_d = next((s for s in SPINDLES if kw <= s[0] + 1e-6), SPINDLES[-1])
    mats = MC.tech_materials(spec, primary="#1f5aa6", secondary="#2b2e33", accent="#e86a1a")
    mats["estop_red"] = M.material("estop_red", "plastic", "#c8161d", 0.0, 0.35, name="Nhựa đỏ nút dừng khẩn")
    mats["lcd"] = M.material("lcd", "glass", "#0e2a3a", 0.2, 0.1, name="Màn hình LCD")
    mats["carbide"] = M.material("carbide", "metal", "#8e949a", 1.0, 0.25, name="Hợp kim cứng (dao phay)")
    name = spec.name or f"Máy CNC router {Tx:g}×{Ty:g}×{Tz:g} trục chính {kw:g} kW"
    b = AssemblyBuilder(name, "cnc_router", mats)
    contacts: list[list[str]] = []

    car_l, car_w, h, rail_h = float(G["car_l"]), float(G["car_w"]), float(G["h"]), float(G["rail_h"])
    car = MC.carriage(G)
    Lsp = 2 * car_l + 60.0                                           # dài tấm đế con trượt giàn
    Wsad = 2 * car_l + 50.0                                          # rộng bàn trượt X
    bd = 80.0 if series == "HGR20" else 100.0                        # sâu dầm giàn
    hg = 160.0 if series == "HGR20" else 190.0                       # cao dầm giàn
    ts = 15.0                                                        # dày bàn trượt X / tấm Z
    ez = max(60.0, 35.0 + car_w / 2)                                 # nửa khoảng cách 2 ray Z
    Wz = 2 * ez + car_w + 16.0

    ax_y = screw_axis(key_y, Ty, 76.0, 10.0, max_tri=60_000)
    ax_x = screw_axis(key_x, Tx, 76.0, 2.0, clear=Wsad / 2 + 46.0, max_tri=60_000)
    ax_z = screw_axis("1605", Tz, 56.0, 10.0, max_tri=40_000)
    riser = lambda ax: max(0.0, ax["zc"] + ax["fl"] / 2 + 4.0 - h)
    r_x, r_z = riser(ax_x), riser(ax_z)

    # ---------- cao độ ----------
    z_f, zb_top = 40.0, 160.0                                        # đáy dầm / đỉnh dầm = mặt bàn
    table_top = zb_top
    zct = zb_top + h                                                 # đỉnh con trượt Y
    z_gb0 = table_top + Tz + 60.0
    z_gb1 = z_gb0 + hg
    z_x = (z_gb0 + z_gb1) / 2                                        # tâm vít X
    zs = zb_top - 40.0                                               # tâm vít Y (ngoài dầm)
    z_tip = table_top + Tz + 10.0                                    # mũi dao ở vị trí gốc (Z trên cùng)
    stick = 22.0
    z_nose = z_tip + stick + nut_h + 1.0
    zp1 = z_nose + Ls + 30.0
    Hp = max(0.8 * Ls + 40.0, 2 * car_l + 50.0)
    zp0 = zp1 - Hp
    n0z = ax_z["n0"]
    z_o = zp1 - 15.0 + n0z - 12.0                                    # z thế giới của x cục bộ = 0 (trục Z, đầu trên)

    # ---------- bề ngang (Y) ----------
    x_face_x = ax_x["x_face"]
    Yb = max(Tx / 2 + 110.0, (ax_x["Lt"] - x_face_x) / 2 + 4.0,
             (ax_x["n0"] + Tx + Wsad / 2 - x_face_x) / 2 + 2.0)
    y_s = Yb + 40.0 + ax_y["fl"] / 2 + 11.0                         # trục vít Y (hai bên, ngoài dầm)
    y0x = Yb + 10.0 + x_face_x                                       # y thế giới của x cục bộ = 0 (vít X)
    xn_x = ax_x["n0"] + Tx / 2                                       # đai ốc X giữa hành trình
    y_sad = y0x - xn_x + 6.0

    # ---------- chiều dọc (X) ----------
    xg = 0.0                                                         # giàn ở giữa hành trình
    xn_y = ax_y["n0"] + Ty / 2
    x0w = xg + 6.0 - xn_y                                            # x thế giới của x cục bộ = 0 (vít Y)
    xs0 = xg + bd / 2 + r_x + h                                      # mặt sau bàn trượt X
    xs1 = xs0 + ts
    xz0 = xs1 + r_z + h                                              # mặt sau tấm Z
    xzf = xz0 + ts
    x_sp = xzf + 12.0 + D / 2                                        # tâm trục chính
    tx0, tx1 = x_sp - Ty / 2 - 50.0, x_sp + Ty / 2 + 50.0             # bàn máy
    rx0, rx1 = -Ty / 2 - Lsp / 2 - 5.0, Ty / 2 + Lsp / 2 + 5.0         # ray Y
    bx0 = min(rx0, tx0 - 10.0, x0w + ax_y["x_face"])
    bx1 = max(rx1, tx1 + 10.0, x0w + ax_y["Lt"] + 5.0)
    ty = Yb - 42.0

    # ============================================================ đế
    fr = []
    for sy in (1, -1):
        beam = box_at(bx0, bx1, sy * Yb - 40, sy * Yb + 40, z_f, zb_top) - box_at(bx0 - 1, bx1 + 1, sy * Yb - 36, sy * Yb + 36, z_f + 4, zb_top - 4)
        fr.append(beam)
    ncm = max(2, int(math.ceil((bx1 - bx0 - 80) / 450.0)) + 1)
    xcm = [bx0 + 40 + k * (bx1 - bx0 - 80) / (ncm - 1) for k in range(ncm)]
    for xc in xcm:
        cm = box_at(xc - 40, xc + 40, -(Yb - 40), Yb - 40, z_f, z_f + 80) - box_at(xc - 36, xc + 36, -(Yb - 40) - 1, Yb - 40 + 1, z_f + 4, z_f + 76)
        fr.append(cm)
    fr += [box_at(x, x + 5.0 * s, sy * Yb - 40, sy * Yb + 40, z_f, zb_top) for x, s in ((bx0, 1), (bx1, -1)) for sy in (1, -1)]   # nắp đầu dầm
    base = K.Solid.union_all(fr)
    b.add("base", "Đế thép hộp", "Welded steel base", "frame", Shape(base, "paint_blue", 35.0), required=True,
          aliases=["đế", "khung", "khung máy", "đế máy", "dầm", "base", "frame", "thân máy"],
          function=f"2 dầm thép hộp 80×120 dày 4 mm + {ncm} thanh ngang 80×80, sơn tĩnh điện.",
          position_tag="bottom", dimensions={"length": bx1 - bx0, "width": 2 * Yb + 80, "height": zb_top})
    fx = [bx0 + 60, bx1 - 60] + ([(bx0 + bx1) / 2] if bx1 - bx0 > 1200 else [])
    pads, studs = [], []
    for x in fx:
        for sy in (1, -1):
            pads.append(K.cylinder(35.0, 10.0, segments=40).translate(x, sy * Yb, 0))
            studs.append(K.cylinder(8.0, z_f - 10.0, segments=24).translate(x, sy * Yb, 10.0) +
                         MC._hex_chamfered(24.0, 10.0, both=True).translate(x, sy * Yb, z_f - 10.0))
    b.add("feet", "Chân tăng chỉnh", "Levelling feet", "foot", [Shape(K.Solid.union_all(pads), "nbr", 35.0),
                                                                 Shape(K.Solid.union_all(studs), "steel_zinc", 35.0)],
          parent_id="base", required=True, aliases=["chân", "chân tăng chỉnh", "chân máy", "feet"],
          function=f"{len(pads)} chân đế cao su + ty ren M16 + ê cu chỉnh cân máy.", position_tag="bottom",
          explode_dir=(0, 0, -1), explode_distance=60.0, explode_order=1)
    table = tslot_table(tx0, tx1, -ty, ty, z_f + 80.0, table_top)
    b.add("table", "Bàn máy nhôm rãnh T", "T-slot aluminium table", "table", Shape(table, "aluminum", 35.0), parent_id="base",
          required=True, aliases=["bàn máy", "bàn gá", "bàn rãnh T", "mặt bàn", "table", "bàn làm việc"],
          function=f"Bàn nhôm định hình {tx1 - tx0:.0f}×{2 * ty:.0f} mm, rãnh T8 cách 50 mm để kẹp phôi.",
          position_tag="center", explode_dir=(0, 0, 1), explode_distance=120.0, explode_order=3,
          dimensions={"length": tx1 - tx0, "width": 2 * ty})

    # ============================================================ trục Y máy (giàn chạy dọc X)
    Lry = rx1 - rx0
    rails_y = K.Solid.union_all([MC.linear_rail(G, Lry).translate((rx0 + rx1) / 2, sy * Yb, zb_top) for sy in (1, -1)])
    b.add("y_rails", f"Ray trục Y {series}", f"Y rails {series}", "rail", Shape(rails_y, "bearing_steel", 35.0), parent_id="base",
          required=True, aliases=["ray", "ray trượt", "ray Y", "ray dẫn hướng", "rail", "thanh trượt"],
          function=f"2 ray {series} dài {Lry:.0f} mm bắt trên đỉnh dầm.", position_tag="center", dimensions={"length": Lry})
    cxy = [xg + sx * (car_l / 2 + 15.0) for sx in (1, -1)]
    cb, cc = [], []
    for sy in (1, -1):
        for cx in cxy:
            cb.append(car["body"].translate(cx, sy * Yb, zb_top))
            cc.append((car["caps"] + car["seals"] + car["nipple"]).translate(cx, sy * Yb, zb_top))
    b.add("y_carriages", "Con trượt trục Y", "Y carriages", "carriage",
          [Shape(K.Solid.union_all(cb), "bearing_steel", 35.0), Shape(K.Solid.union_all(cc), "plastic_black", 35.0)],
          parent_id="y_rails", required=True, aliases=["con trượt", "block trượt", "carriage", "con trượt Y"],
          function=f"4 con trượt {series.replace('R', 'H', 1)}CA mang giàn.", position_tag="center", joint_axis=(1, 0, 0),
          explode_dir=(0, 0, 1), explode_distance=80.0, explode_order=4)

    # giàn: tấm đế + tấm hông
    zu0 = zct + 15.0
    top_x0, top_x1 = xg - bd / 2 - 20.0, xg + bd / 2 + ax_x["zc"] + 45.0
    poly = [(xg - Lsp / 2, zu0), (xg + Lsp / 2, zu0), (xg + Lsp / 2, zu0 + 0.3 * (z_gb1 - zu0)), (top_x1, z_gb1), (top_x0, z_gb1),
            (xg - Lsp / 2, zu0 + 0.3 * (z_gb1 - zu0))]
    gs = []
    x_cpl = xg + bd / 2 + ax_x["zc"]                                 # tâm lỗ khớp nối X trên tấm hông +Y
    for sy in (1, -1):
        up = K.extrude([P.ensure_ccw(poly)], 20.0).transform(frame_map((1, 0, 0), (0, 0, 1), (0, -1, 0), (0, sy * Yb + 10.0, 0)))
        if sy == 1:
            up = up - K.cylinder(CPL_D / 2 + 5.0, 40, segments=48).rotate(90, 0, 0).translate(x_cpl, Yb + 20.0, z_x)
            hs = N23["hole_spacing"] / 2
            up = up.subtract_all([K.cylinder(N23["hole_d"] / 2, 40, segments=12).rotate(90, 0, 0).translate(x_cpl + a, Yb + 20.0, z_x + c)
                                  for a in (hs, -hs) for c in (hs, -hs)])
        yi, yo = sy * (Yb - car_w / 2 - 5.0), sy * (y_s + ax_y["fl"] / 2 + 6.0)
        gs.append(up)
        gs.append(box_at(xg - Lsp / 2, xg + Lsp / 2, yi, yo, zct, zu0))
    b.add("gantry_sides", "Tấm hông giàn", "Gantry side plates", "frame", Shape(K.Solid.union_all(gs), "aluminum", 35.0),
          parent_id="y_carriages", required=True, aliases=["tấm hông", "chân giàn", "tấm hông giàn", "gantry side", "tấm đế giàn"],
          function="2 tấm nhôm 20 mm đứng trên tấm đế con trượt 15 mm; tấm +Y làm giá động cơ trục X.",
          position_tag="center", joint_axis=(1, 0, 0), explode_dir=(0, 0, 1), explode_distance=140.0, explode_order=3)
    gb = box_at(xg - bd / 2, xg + bd / 2, -(Yb - 10), Yb - 10, z_gb0, z_gb1)
    gb = gb - box_at(xg - bd / 2 + 6, xg + bd / 2 - 6, -(Yb - 9), Yb - 9, z_gb0 + 6, z_gb1 - 6)
    zr_lo, zr_hi = z_gb0 + car_w / 2 + 8.0, z_gb1 - car_w / 2 - 8.0
    if r_x > 0:
        gb = gb + K.Solid.union_all([box_at(xg + bd / 2 - 0.01, xg + bd / 2 + r_x, -(Yb - 10), Yb - 10, zr - G["rail_w"] / 2 - 3, zr + G["rail_w"] / 2 + 3)
                                     for zr in (zr_lo, zr_hi)])
    b.add("gantry_beam", "Dầm giàn", "Gantry beam", "frame", Shape(gb, "aluminum_dark", 35.0), parent_id="gantry_sides", required=True,
          aliases=["dầm giàn", "giàn", "xà ngang", "gantry", "dầm ngang"],
          function=f"Dầm nhôm hộp {bd:g}×{hg:g} dày 6 mm, gờ đỡ ray trục X {r_x:.0f} mm.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=200.0, explode_order=2, dimensions={"length": 2 * (Yb - 10), "height": hg})

    # vít me Y (2 bên)
    MY = {sy: frame_map((1, 0, 0), (0, 1, 0), (0, 0, 1), (x0w, sy * y_s, zs - ax_y["zc"])) for sy in (1, -1)}
    ay = ax_y
    mnt, bks, bfs, shafts_y, nuts_y, brk_y, locks_y, cpl_y, mot_y = [], [], [], [], [], [], [], [], []
    for sy in (1, -1):
        Mx = MY[sy]
        yb_face = sy * (Yb + 40.0)
        wy = ay["W"] / 2 + 2.0
        # tai gá sau (kèm tấm động cơ) + tai gá trước: tấm ngang 12 mm bắt vào mặt ngoài dầm
        z_sh = zs - ay["zc"]
        m = [box_at(x0w + ay["x_face"], x0w + ay["x_bk"] + ay["Lb"] + 3.0, yb_face, sy * (y_s + wy), z_sh - 12.0, z_sh),
             box_at(x0w + ay["x_bf"] - 3.0, x0w + ay["x_bf"] + 0.8 * ay["Lb"] + 3.0, yb_face, sy * (y_s + wy), z_sh - 12.0, z_sh)]
        pl = box_at(ay["x_face"], ay["x_face"] + 8.0, -N23["flange"] / 2 - 4, N23["flange"] / 2 + 4, -12.0, ay["zc"] + N23["flange"] / 2 + 4)
        pl = pl - K.cylinder(N23["pilot_d"] / 2 + 0.3, 20, segments=48).transform(TO_X).translate(ay["x_face"] - 5, 0, ay["zc"])
        hs = N23["hole_spacing"] / 2
        pl = pl.subtract_all([K.cylinder(N23["hole_d"] / 2, 20, segments=12).transform(TO_X).translate(ay["x_face"] - 5, a, ay["zc"] + c)
                              for a in (hs, -hs) for c in (hs, -hs)])
        m.append(pl.transform(Mx))
        # tấm gá động cơ nằm sát mép ngoài dầm → nối vào dầm bằng gân
        mnt += m
        bks.append((ay["bk"][0].transform(Mx), "steel_black_oxide"))
        bks.append((ay["bk"][1].transform(Mx), "steel_black_oxide"))
        bfs.append((ay["bf"].transform(Mx), "steel_black_oxide"))
        shafts_y.append((ay["shaft"].transform(Mx), "steel"))
        nuts_y += _place([(s.translate(xn_y, 0, ay["zc"]), mt) for s, mt in ay["nut"]], Mx)
        zb1 = zct - (zs - ay["zc"])                                   # đáy tấm đế giàn (cục bộ)
        brk_y.append((nut_bracket(ay, xn_y, ay["zc"] - ay["fl"] / 2 - 5.0, zb1).transform(Mx), "aluminum"))
        locks_y.append((ay["lock"].transform(Mx), "steel_black_oxide"))
        cpl_y += _place(ay["coupling"], Mx)
        mot_y += _place(ay["motor"], Mx)
    b.add("y_mounts", "Tai gá vít me Y", "Y screw mounts", "bracket", Shape(K.Solid.union_all(mnt), "steel_zinc", 35.0), parent_id="base",
          required=True, aliases=["tai gá", "giá gối", "giá động cơ Y", "bracket"],
          function="Tai thép 12 mm bắt mặt ngoài dầm đỡ gối BK/BF; tấm 8 mm gá mặt bích động cơ.", position_tag="left",
          explode_dir=(0, 1, 0), explode_distance=60.0, explode_order=4)
    b.add("y_supports", f"Gối đỡ {ay['sup']['bk']}/{ay['sup']['bk'].replace('BK', 'BF')} trục Y", "Y screw supports", "bearing",
          _shapes(bks + bfs), parent_id="y_mounts", required=True, aliases=["gối đỡ", "gối BK", "gối BF", "ổ đỡ", "support"],
          function="Gối BK (cặp ổ tiếp xúc góc, cố định) phía động cơ, gối BF (ổ bi rãnh sâu, tự do) phía trước.",
          position_tag="left", explode_dir=(0, 0, 1), explode_distance=50.0, explode_order=3)
    b.add("y_screws", f"Vít me bi SFU{key_y} trục Y", "Y ball screws", "shaft", _shapes(shafts_y), parent_id="y_supports", required=True,
          aliases=["vít me", "vít me bi", "trục vít", "ball screw", "vít me Y"],
          function=f"2 vít me bi Ø{ay['d']} bước {ay['lead']} dài {ay['Lt']:.0f} mm, dẫn động kép hai bên giàn.",
          position_tag="left", joint_axis=(1, 0, 0), dimensions={"diameter": ay["d"], "lead": ay["lead"], "length": ay["Lt"]})
    b.add("y_nuts", f"Đai ốc bi SFU{key_y} trục Y", "Y ball nuts", "nut", _shapes(nuts_y), parent_id="y_screws", required=True,
          aliases=["đai ốc bi", "đai ốc", "ball nut", "con chạy"], function="Đai ốc bi mặt bích, ống hồi bi ngoài, phớt gạt.",
          position_tag="left", explode_dir=(0, 0, 1), explode_distance=60.0, explode_order=2)
    b.add("y_nut_brackets", "Giá đai ốc trục Y", "Y nut brackets", "bracket", _shapes(brk_y), parent_id="gantry_sides", required=True,
          aliases=["giá đai ốc", "gá đai ốc", "nut bracket"], function="Tấm nhôm 12 mm treo dưới tấm đế giàn, bắt bích đai ốc bi.",
          position_tag="left", explode_dir=(0, 0, 1), explode_distance=40.0, explode_order=2)
    b.add("y_lock_nuts", "Đai ốc khóa trục Y", "Y lock nuts", "nut", _shapes(locks_y), parent_id="y_screws",
          aliases=["đai ốc khóa", "ê cu hãm", "lock nut"], function="Đai ốc khóa ép cặp ổ gối BK.", position_tag="back",
          explode_dir=(-1, 0, 0), explode_distance=30.0, explode_order=1)
    b.add("y_motors", "Động cơ NEMA 23 trục Y", "Y stepper motors", "motor", _shapes(mot_y), parent_id="y_mounts", required=True,
          aliases=["động cơ", "động cơ bước", "động cơ Y", "stepper", "motor", "NEMA 23"],
          function=f"2 động cơ bước NEMA 23 thân {ay['motor_len']:g} mm (≈2,2 N·m) chạy đồng bộ.", position_tag="back",
          explode_dir=(-1, 0, 0), explode_distance=90.0, explode_order=2)
    b.add("y_couplings", f"Khớp nối vấu cỡ {CPL} trục Y", "Y jaw couplings", "coupling", _shapes(cpl_y), parent_id="y_motors",
          required=True, aliases=["khớp nối", "khớp nối mềm", "coupling", "khớp nối vấu"],
          function=f"Khớp nối vấu Ø{CPL_D:g}×{CPL_L:g} mm, đệm sao polyurethane 98 ShA.", position_tag="back",
          explode_dir=(-1, 0, 0), explode_distance=50.0, explode_order=1)
    contacts += [["y_nuts", "y_nut_brackets"], ["y_couplings", "y_screws"], ["y_lock_nuts", "y_supports"]]

    # ============================================================ trục X máy (đầu phay chạy dọc Y)
    MXa = frame_map((0, -1, 0), (0, 0, -1), (1, 0, 0), (xg + bd / 2, y0x, z_x))
    Lrx = 2 * (Yb - 10.0) - 2.0
    rail_M = lambda zr: frame_map((0, 1, 0), (0, 0, 1), (1, 0, 0), (xg + bd / 2 + r_x, 0, zr))
    rails_x = K.Solid.union_all([MC.linear_rail(G, Lrx).transform(rail_M(zr)) for zr in (zr_lo, zr_hi)])
    b.add("x_rails", f"Ray trục X {series}", f"X rails {series}", "rail", Shape(rails_x, "bearing_steel", 35.0), parent_id="gantry_beam",
          required=True, aliases=["ray X", "ray giàn", "ray trượt ngang"], function=f"2 ray {series} dài {Lrx:.0f} mm trên mặt trước dầm giàn.",
          position_tag="top", dimensions={"length": Lrx})
    cb, cc = [], []
    for zr in (zr_lo, zr_hi):
        for dy in (car_l / 2 + 15.0, -(car_l / 2 + 15.0)):
            Mc = rail_M(zr)
            cb.append(car["body"].translate(y_sad + dy, 0, 0).transform(Mc))
            cc.append((car["caps"] + car["seals"] + car["nipple"]).translate(y_sad + dy, 0, 0).transform(Mc))
    b.add("x_carriages", "Con trượt trục X", "X carriages", "carriage",
          [Shape(K.Solid.union_all(cb), "bearing_steel", 35.0), Shape(K.Solid.union_all(cc), "plastic_black", 35.0)],
          parent_id="x_rails", required=True, aliases=["con trượt X", "block X"], function="4 con trượt mang bàn trượt X.",
          position_tag="top", joint_axis=(0, 1, 0), explode_dir=(1, 0, 0), explode_distance=60.0, explode_order=4)
    zsd0 = min(zp0 - Tz - 10.0, z_gb0 - 10.0, z_o - ax_z["Lt"] - 5.0)
    zsd1 = max(z_gb1 + 10.0, z_o - ax_z["x_face"])
    sad = box_at(xs0, xs1, y_sad - Wsad / 2, y_sad + Wsad / 2, zsd0, zsd1)
    zr0, zr1 = zp0 - Tz, zp1 + 15.0                                 # nắp chặn con trượt trên không vượt đầu ray
    if r_z > 0:
        sad = sad + K.Solid.union_all([box_at(xs1 - 0.01, xs1 + r_z, y_sad + sy * ez - G["rail_w"] / 2 - 3, y_sad + sy * ez + G["rail_w"] / 2 + 3, zr0, zr1)
                                       for sy in (1, -1)])
    b.add("saddle", "Bàn trượt X", "X saddle plate", "carriage", Shape(sad, "aluminum", 35.0), parent_id="x_carriages", required=True,
          aliases=["bàn trượt X", "bàn trượt", "tấm trượt X", "saddle", "cụm trượt ngang"],
          function=f"Tấm nhôm {ts:g} mm {Wsad:.0f}×{zsd1 - zsd0:.0f} mm; mặt trước mang ray + vít me Z.", position_tag="front",
          joint_axis=(0, 1, 0), explode_dir=(1, 0, 0), explode_distance=120.0, explode_order=3)
    ax = ax_x
    b.add("x_supports", f"Gối đỡ {ax['sup']['bk']}/{ax['sup']['bk'].replace('BK', 'BF')} trục X", "X screw supports", "bearing",
          _shapes(_place([(ax["bk"][0], "steel_black_oxide"), (ax["bk"][1], "steel_black_oxide"), (ax["bf"], "steel_black_oxide")], MXa)),
          parent_id="gantry_beam", required=True, aliases=["gối đỡ X", "gối BK X"], function="Gối BK/BF bắt mặt trước dầm giàn.",
          position_tag="top", explode_dir=(1, 0, 0), explode_distance=40.0, explode_order=3)
    b.add("x_screw", f"Vít me bi SFU{key_x} trục X", "X ball screw", "shaft", Shape(ax["shaft"].transform(MXa), "steel", 35.0),
          parent_id="x_supports", required=True, aliases=["vít me X", "trục vít X"],
          function=f"Vít me bi Ø{ax['d']} bước {ax['lead']} dài {ax['Lt']:.0f} mm.", position_tag="top", joint_axis=(0, 1, 0),
          dimensions={"diameter": ax["d"], "lead": ax["lead"], "length": ax["Lt"]})
    b.add("x_nut", f"Đai ốc bi SFU{key_x} trục X", "X ball nut", "nut",
          _shapes(_place([(s.translate(xn_x, 0, ax["zc"]), mt) for s, mt in ax["nut"]], MXa)), parent_id="x_screw", required=True,
          aliases=["đai ốc X", "đai ốc bi X"], function="Đai ốc bi SFU mặt bích.", position_tag="top",
          explode_dir=(1, 0, 0), explode_distance=50.0, explode_order=2)
    b.add("x_nut_bracket", "Giá đai ốc trục X", "X nut bracket", "bracket",
          Shape(nut_bracket(ax, xn_x, 1.0, bd / 2 * 0 + r_x + h).transform(MXa), "aluminum", 35.0), parent_id="saddle", required=True,
          aliases=["giá đai ốc X"], function="Tấm nhôm 12 mm sau bàn trượt, nằm giữa 4 con trượt, bắt bích đai ốc.",
          position_tag="top", explode_dir=(-1, 0, 0), explode_distance=40.0, explode_order=2)
    b.add("x_lock_nut", "Đai ốc khóa trục X", "X lock nut", "nut", Shape(ax["lock"].transform(MXa), "steel_black_oxide", 35.0),
          parent_id="x_screw", aliases=["đai ốc khóa X"], function="Đai ốc khóa gối BK.", position_tag="left",
          explode_dir=(0, 1, 0), explode_distance=30.0, explode_order=1)
    b.add("x_motor", "Động cơ NEMA 23 trục X", "X stepper motor", "motor", _shapes(_place(ax["motor"], MXa)), parent_id="gantry_sides",
          required=True, aliases=["động cơ X", "động cơ giàn"], function=f"NEMA 23 thân {ax['motor_len']:g} mm gá ngoài tấm hông trái.",
          position_tag="left", explode_dir=(0, 1, 0), explode_distance=90.0, explode_order=2)
    b.add("x_coupling", f"Khớp nối vấu cỡ {CPL} trục X", "X jaw coupling", "coupling", _shapes(_place(ax["coupling"], MXa)),
          parent_id="x_motor", required=True, aliases=["khớp nối X"], function="Khớp nối vấu xuyên lỗ tấm hông.", position_tag="left",
          explode_dir=(0, 1, 0), explode_distance=50.0, explode_order=1)
    contacts += [["x_nut", "x_nut_bracket"], ["x_coupling", "x_screw"], ["x_lock_nut", "x_supports"]]

    # ============================================================ trục Z
    MZ = frame_map((0, 0, -1), (0, 1, 0), (1, 0, 0), (xs1, y_sad, z_o))
    zrail_M = lambda sy, zc_: frame_map((0, 0, 1), (0, -1, 0), (1, 0, 0), (xs1 + r_z, y_sad + sy * ez, zc_))
    Lrz = zr1 - zr0
    rails_z = K.Solid.union_all([MC.linear_rail(G, Lrz).transform(zrail_M(sy, (zr0 + zr1) / 2)) for sy in (1, -1)])
    b.add("z_rails", f"Ray trục Z {series}", f"Z rails {series}", "rail", Shape(rails_z, "bearing_steel", 35.0), parent_id="saddle",
          required=True, aliases=["ray Z", "ray đứng"], function=f"2 ray {series} dài {Lrz:.0f} mm đứng trên bàn trượt X.",
          position_tag="front", dimensions={"length": Lrz})
    zcu, zcl = zp1 - car_l / 2 - 5.0, zp0 + car_l / 2 + 5.0
    cb, cc = [], []
    for sy in (1, -1):
        for zc_ in (zcu, zcl):
            Mc = zrail_M(sy, zc_)
            cb.append(car["body"].transform(Mc))
            cc.append((car["caps"] + car["seals"] + car["nipple"]).transform(Mc))
    b.add("z_carriages", "Con trượt trục Z", "Z carriages", "carriage",
          [Shape(K.Solid.union_all(cb), "bearing_steel", 35.0), Shape(K.Solid.union_all(cc), "plastic_black", 35.0)],
          parent_id="z_rails", required=True, aliases=["con trượt Z", "block Z"], function="4 con trượt mang tấm Z.",
          position_tag="front", joint_axis=(0, 0, 1), explode_dir=(1, 0, 0), explode_distance=60.0, explode_order=4)
    zpl = box_at(xz0, xzf, y_sad - Wz / 2, y_sad + Wz / 2, zp0, zp1)
    b.add("z_plate", "Tấm trượt Z", "Z plate", "carriage", Shape(zpl, "aluminum", 35.0), parent_id="z_carriages", required=True,
          aliases=["tấm Z", "bàn trượt Z", "cụm Z", "z plate"], function=f"Tấm nhôm {ts:g} mm {Wz:.0f}×{Hp:.0f} mm mang kẹp trục chính.",
          position_tag="front", joint_axis=(0, 0, 1), explode_dir=(1, 0, 0), explode_distance=160.0, explode_order=3)
    az = ax_z
    b.add("z_supports", "Gối đỡ BK12/BF12 trục Z", "Z screw supports", "bearing",
          _shapes(_place([(az["bk"][0], "steel_black_oxide"), (az["bk"][1], "steel_black_oxide"), (az["bf"], "steel_black_oxide")], MZ)),
          parent_id="saddle", required=True, aliases=["gối đỡ Z"], function="Gối BK trên, BF dưới bắt mặt trước bàn trượt X.",
          position_tag="front", explode_dir=(1, 0, 0), explode_distance=40.0, explode_order=3)
    b.add("z_screw", "Vít me bi SFU1605 trục Z", "Z ball screw", "shaft", Shape(az["shaft"].transform(MZ), "steel", 35.0),
          parent_id="z_supports", required=True, aliases=["vít me Z", "trục vít Z"],
          function=f"Vít me bi Ø16 bước 5 dài {az['Lt']:.0f} mm.", position_tag="front", joint_axis=(0, 0, 1),
          dimensions={"diameter": 16, "lead": 5, "length": az["Lt"]})
    b.add("z_nut", "Đai ốc bi SFU1605 trục Z", "Z ball nut", "nut", _shapes(_place([(s.translate(n0z, 0, az["zc"]), mt) for s, mt in az["nut"]], MZ)),
          parent_id="z_screw", required=True, aliases=["đai ốc Z"], function="Đai ốc bi SFU1605.", position_tag="front",
          explode_dir=(1, 0, 0), explode_distance=50.0, explode_order=2)
    b.add("z_nut_bracket", "Giá đai ốc trục Z", "Z nut bracket", "bracket",
          Shape(nut_bracket(az, n0z, 3.0, r_z + h).transform(MZ), "aluminum", 35.0), parent_id="z_plate", required=True,
          aliases=["giá đai ốc Z"], function="Tấm nhôm 12 mm sau tấm Z, giữa 2 ray, bắt bích đai ốc.", position_tag="front",
          explode_dir=(-1, 0, 0), explode_distance=40.0, explode_order=2)
    b.add("z_lock_nut", "Đai ốc khóa trục Z", "Z lock nut", "nut", Shape(az["lock"].transform(MZ), "steel_black_oxide", 35.0),
          parent_id="z_screw", aliases=["đai ốc khóa Z"], function="Đai ốc khóa gối BK.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=30.0, explode_order=1)
    # giá động cơ Z: tấm ngang 8 mm + 2 má bắt mặt trước bàn trượt
    xf = az["x_face"]
    zmp = box_at(xf, xf + 8.0, -N23["flange"] / 2 - 4, N23["flange"] / 2 + 4, 0.0, az["zc"] + N23["flange"] / 2 + 4)
    zmp = zmp - K.cylinder(N23["pilot_d"] / 2 + 0.3, 20, segments=48).transform(TO_X).translate(xf - 5, 0, az["zc"])
    hs = N23["hole_spacing"] / 2
    zmp = zmp.subtract_all([K.cylinder(N23["hole_d"] / 2, 20, segments=12).transform(TO_X).translate(xf - 5, a, az["zc"] + c)
                            for a in (hs, -hs) for c in (hs, -hs)])
    ck = [box_at(xf, xf + 50.0, s * (CPL_D / 2 + 3.0), s * (CPL_D / 2 + 11.0), 0.0, az["zc"] + CPL_D / 2 + 4.0) for s in (1, -1)]
    b.add("z_motor_mount", "Giá động cơ Z", "Z motor mount", "bracket", Shape((zmp + K.Solid.union_all(ck)).transform(MZ), "aluminum", 35.0),
          parent_id="saddle", required=True, aliases=["giá động cơ Z", "gá động cơ"], function="Tấm 8 mm + 2 má ôm khớp nối, bắt đỉnh bàn trượt.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=60.0, explode_order=3)
    b.add("z_motor", "Động cơ NEMA 23 trục Z", "Z stepper motor", "motor", _shapes(_place(az["motor"], MZ)), parent_id="z_motor_mount",
          required=True, aliases=["động cơ Z"], function=f"NEMA 23 thân {az['motor_len']:g} mm, trục hướng xuống.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=100.0, explode_order=2)
    b.add("z_coupling", f"Khớp nối vấu cỡ {CPL} trục Z", "Z jaw coupling", "coupling", _shapes(_place(az["coupling"], MZ)),
          parent_id="z_motor", required=True, aliases=["khớp nối Z"], function="Khớp nối vấu giữa động cơ và vít me Z.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=60.0, explode_order=1)
    contacts += [["z_nut", "z_nut_bracket"], ["z_coupling", "z_screw"], ["z_lock_nut", "z_supports"]]

    # ============================================================ trục chính
    hc = min(80.0, 0.4 * Ls)
    zcl_ = z_nose + 0.6 * Ls
    wcl = D / 2 + 18.0
    clamp = box_at(xzf, x_sp + D / 2 + 10.0, y_sad - wcl, y_sad + wcl, zcl_ - hc / 2, zcl_ + hc / 2)
    clamp = clamp - K.cylinder(D / 2, hc + 2, segments=96).translate(x_sp, y_sad, zcl_ - hc / 2 - 1)
    clamp = clamp - box_at(x_sp, x_sp + D / 2 + 11.0, y_sad - 1.5, y_sad + 1.5, zcl_ - hc / 2 - 1, zcl_ + hc / 2 + 1)
    cb_ = K.Solid.union_all([MC.socket_screw(6.0, 12.0).rotate(90, 0, 0).translate(x_sp + D / 2 + 5.0, y_sad + wcl, zcl_ + s * hc / 4)
                             for s in (1, -1)] +
                            [MC.socket_screw(6.0, 12.0).rotate(0, 90, 0).translate(xzf + 0.0, y_sad + a * (wcl - 9), zcl_ + s * hc / 4)
                             for a in (1, -1) for s in (1, -1)][:0])
    b.add("spindle_clamp", f"Kẹp trục chính Ø{D:g}", "Spindle clamp", "bracket",
          [Shape(clamp, "aluminum_dark", 35.0), Shape(cb_, "steel_black_oxide", 35.0)], parent_id="z_plate", required=True,
          aliases=["kẹp trục chính", "gá spindle", "spindle mount", "kẹp spindle"],
          function=f"Khối nhôm xẻ rãnh ôm trục chính Ø{D:g}, siết 2 vít M6.", position_tag="front",
          explode_dir=(1, 0, 0), explode_distance=80.0, explode_order=2)
    zn = z_nose
    sp_prof = [(0, zn), (0.3 * D, zn), (D / 2 - 3.0, zn + 8.0), (D / 2, zn + 12.0), (D / 2, zn + Ls - 14.0), (D / 2 - 2.0, zn + Ls - 12.0),
               (D / 2 - 3.0, zn + Ls - 12.0), (D / 2 - 3.0, zn + Ls - 1.0), (D / 2 - 4.0, zn + Ls), (0, zn + Ls)]
    body = K.revolve(sp_prof, segments=96).translate(x_sp, y_sad, 0)
    body = body.subtract_all([K.revolve([(D / 2 - 1.0, zn + z), (D / 2 + 1, zn + z), (D / 2 + 1, zn + z + 2.0), (D / 2 - 1.0, zn + z + 2.0)],
                                        segments=96).translate(x_sp, y_sad, 0) for z in (18.0, 24.0, Ls - 24.0, Ls - 30.0)])
    plug = (K.cylinder(9.0, 18.0, segments=32) + K.cylinder(11.0, 4.0, segments=32)).translate(x_sp - D / 4, y_sad, zn + Ls - 0.01)
    fit = K.Solid.union_all([(MC._hex_chamfered(12.0, 6.0, both=True) + K.cylinder(4.0, 16.0, segments=20).translate(0, 0, 5.99) +
                              K.cylinder(4.8, 2.0, segments=20).translate(0, 0, 14.0)).translate(x_sp + D / 5, y_sad + s * D / 5, zn + Ls - 0.01)
                             for s in (1, -1)])
    b.add("spindle", f"Trục chính {kw:g} kW làm mát nước", "Water-cooled spindle", "spindle",
          [Shape(body, "stainless", 35.0), Shape(plug, "steel_dark", 35.0), Shape(fit, "brass", 35.0)], parent_id="spindle_clamp",
          required=True, aliases=["trục chính", "spindle", "đầu phay", "motor spindle", "động cơ trục chính"],
          function=f"Trục chính {kw:g} kW Ø{D:g}×{Ls:g} mm làm mát nước, 24 000 v/ph, đầu collet {er}; 2 đầu nối ống nước + giắc nguồn.",
          position_tag="front", joint_axis=(0, 0, 1), explode_dir=(0, 0, -1), explode_distance=0.0, explode_order=2,
          dimensions={"diameter": D, "length": Ls})
    cn = (K.cylinder(nut_d / 2, nut_h, segments=48) - K.cylinder(tool_d / 2 + 1.5, nut_h + 2, segments=24).translate(0, 0, -1))
    cn = cn.subtract_all([K.box(8.0, 6.0, nut_h * 0.5).translate(math.cos(a) * nut_d / 2, math.sin(a) * nut_d / 2, nut_h * 0.5)
                          for a in np.radians(np.arange(0, 360, 60))])
    stub = K.cylinder(0.3 * D, 1.0, segments=48).translate(0, 0, nut_h - 0.01)
    collet = (cn + stub).translate(x_sp, y_sad, zn - 1.0 - nut_h)
    b.add("collet_nut", f"Đai ốc collet {er}", f"{er} collet nut", "nut", Shape(collet, "steel", 35.0), parent_id="spindle", required=True,
          aliases=["collet", "đai ốc collet", "đầu kẹp dao", "collet nut"], function=f"Collet {er} (DIN 6499) + đai ốc kẹp dao.",
          position_tag="front", explode_dir=(0, 0, -1), explode_distance=40.0, explode_order=1)
    flute = z_tip + 0.0
    tool = (K.cylinder(tool_d / 2 * 0.6, 1.0, radius_top=tool_d / 2, segments=24).translate(0, 0, 0) +
            K.cylinder(tool_d / 2, stick + nut_h - 1.0, segments=24).translate(0, 0, 0.99))
    gro = [MC.orient(K.tube(MC.helix_path(tool_d / 2, [(1.6, tool_d * 2.2)], z0=0.0, per_turn=24), tool_d * 0.14, 6), (0, 0, 1.0 + k * tool_d * 1.1), (0, 0, 1))
           for k in range(2)]
    tool = tool.subtract_all(gro).translate(x_sp, y_sad, flute)
    b.add("tool", f"Dao phay ngón Ø{tool_d:g}", "End mill", "tool", Shape(tool, "carbide", 35.0), parent_id="collet_nut", required=True,
          aliases=["dao", "dao phay", "mũi phay", "end mill", "mũi dao"], function=f"Dao phay ngón hợp kim 2 me Ø{tool_d:g}.",
          position_tag="bottom", explode_dir=(0, 0, -1), explode_distance=70.0, explode_order=1)

    # ============================================================ hộp điều khiển
    wb = min(230.0, Yb - 30.0)
    cx0_, cx1_ = bx1, bx1 + 150.0
    cz0, cz1 = z_f + 5.0, zb_top - 10.0
    box = box_at(cx0_, cx1_, -wb, wb, cz0, cz1)
    box = box - box_at(cx0_ + 2, cx1_ - 2, -wb + 2, wb - 2, cz0 + 2, cz1 - 2)
    vents = [box_at(cx0_ + 30 + k * 12, cx0_ + 36 + k * 12, wb - 3, wb + 1, cz0 + 25, cz1 - 25) for k in range(7)]
    box = box.subtract_all(vents)
    b.add("control_box", "Hộp điều khiển", "Control box", "housing", Shape(box, "paint_gray", 35.0), parent_id="base", required=True,
          aliases=["hộp điều khiển", "tủ điện", "tủ điều khiển", "control box", "bộ điều khiển"],
          function="Hộp thép sơn chứa driver động cơ bước, biến tần trục chính, nguồn 48 V, bo điều khiển.",
          position_tag="front", explode_dir=(1, 0, 0), explode_distance=120.0, explode_order=1,
          dimensions={"length": 150.0, "width": 2 * wb, "height": cz1 - cz0})
    zc_p = (cz0 + cz1) / 2
    es = (K.cylinder(20.0, 8.0, segments=48).rotate(0, 90, 0).translate(cx1_ - 0.01, -wb * 0.55, zc_p))
    mush = (K.cylinder(6.0, 8.0, segments=24) + K.revolve([(0, 0), (17.0, 0), (18.0, 2.0), (17.0, 7.0), (12.0, 10.0), (0, 11.0)], segments=48)
            .translate(0, 0, 8.0)).rotate(0, 90, 0).translate(cx1_ + 8.0 - 0.01, -wb * 0.55, zc_p)
    b.add("estop", "Nút dừng khẩn cấp", "Emergency stop", "estop", [Shape(mush, "estop_red", 35.0), Shape(es, "plastic_yellow", 35.0)],
          parent_id="control_box", required=True, aliases=["nút dừng khẩn cấp", "nút khẩn", "e-stop", "estop", "nút đỏ", "dừng khẩn"],
          function="Nút nấm đỏ Ø36 trên đế vàng (IEC 60947-5-5), ngắt nguồn động lực.", position_tag="front",
          explode_dir=(1, 0, 0), explode_distance=60.0, explode_order=1)
    sw = K.box(4.0, 24.0, 16.0).translate(cx1_ + 2.0 - 0.01, wb * 0.1, zc_p + 18.0)
    knob = (K.cylinder(12.0, 14.0, segments=32).rotate(0, 90, 0) + K.box(3.0, 2.0, 8.0).translate(14.0, 0, 7.0)).translate(cx1_ - 0.01, wb * 0.1, zc_p - 18.0)
    b.add("controls", "Công tắc + núm tốc độ", "Power switch & speed knob", "button",
          [Shape(knob, "plastic_black", 35.0), Shape(sw, "estop_red", 35.0)], parent_id="control_box", required=True,
          aliases=["công tắc", "núm", "núm tốc độ", "công tắc nguồn", "biến trở", "switch", "knob"],
          function="Công tắc nguồn và núm chỉnh tốc độ trục chính (biến tần).", position_tag="front",
          explode_dir=(1, 0, 0), explode_distance=50.0, explode_order=1)
    lcd_w = min(90.0, wb * 0.55)
    bez = box_at(cx1_ - 0.01, cx1_ + 3.0, wb * 0.35, wb * 0.35 + lcd_w, zc_p - 22.0, zc_p + 22.0)
    scr_ = box_at(cx1_ + 3.0 - 0.01, cx1_ + 3.6, wb * 0.35 + 4, wb * 0.35 + lcd_w - 4, zc_p - 17.0, zc_p + 17.0)
    b.add("display", "Màn hình điều khiển", "Control display", "display", [Shape(bez, "plastic_black", 35.0), Shape(scr_, "lcd", 35.0)],
          parent_id="control_box", aliases=["màn hình", "LCD", "display"], function="Màn hình hiển thị tọa độ / tốc độ.",
          position_tag="front", explode_dir=(1, 0, 0), explode_distance=50.0, explode_order=1)

    b.metadata["contacts"] = contacts
    b.note_stage(1, "Tháo dao, collet, trục chính, hộp điều khiển")
    b.note_stage(2, "Tháo động cơ, khớp nối, đai ốc khóa")
    b.note_stage(3, "Tháo tấm Z, bàn trượt X, dầm giàn, gối đỡ")
    b.note_stage(4, "Tách ray, con trượt, bàn máy khỏi đế")
    b.place_on_ground(center_xy=True)
    b.metadata.update({
        "travel_mm": [Tx, Ty, Tz], "spindle_kw": kw, "spindle_d_mm": D, "spindle_len_mm": Ls, "collet": er, "tool_d_mm": tool_d,
        "rail": series, "screws": {"x": f"SFU{key_x}", "y": f"SFU{key_y}", "z": "SFU1605"},
        "screw_len_mm": {"x": round(ax_x["Lt"], 1), "y": round(ax_y["Lt"], 1), "z": round(ax_z["Lt"], 1)},
        "screw_travel_mm": {"x": Tx, "y": Ty, "z": Tz}, "lead_mm": 5, "coupling": f"jaw {CPL} (Ø{CPL_D:g}×{CPL_L:g})",
        "motors": "NEMA 23", "table_mm": [round(tx1 - tx0, 1), round(2 * ty, 1)],
        "rail_len_mm": {"x": round(Lrx, 1), "y": round(Lry, 1), "z": round(Lrz, 1)},
        "gantry_clearance_mm": round(z_gb0 - table_top, 1), "tip_home_above_table_mm": round(z_tip - table_top, 1),
        "standard": "HIWIN HGR/HGH-CA, TBI SFU (DIN 69051) + THK BK/BF, NEMA 23 (ICS 16), khớp nối vấu DIN 740, collet ER (DIN 6499)",
        "strict_overlap": True})
    return b.build()
