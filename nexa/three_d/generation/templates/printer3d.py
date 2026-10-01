"""Máy in 3D FDM (hệ X trước, Y trái, Z lên; mm). Hai kiểu động học:

(a) "bedslinger" (kiểu Prusa i3 / Ender-3): khung nhôm định hình 2040 (đế chữ H + 2 cột + thanh đỉnh), bàn nhiệt chạy trục
    Y (trước–sau, kỹ thuật X) trên ray MGN12 + 2 con trượt, kéo bằng đai GT2 6 mm từ động cơ NEMA 17 sau → puly căng trước;
    bàn = tấm đỡ 4 mm + 4 lò xo cân bàn + núm vặn + bàn nhôm 3 mm + tấm PEI từ. Giàn X: 2 con trượt MGN12 trên ray đứng ở
    mặt trước hai cột, 2 tấm đầu X mang thanh 2040 ngang + ray MGN12 + cụm đầu in (tấm gá, hotend: tản nhiệt Ø22 + ống
    ngắt nhiệt + khối gia nhiệt + đầu phun 0,4 mm, quạt 40 mm) kéo bằng đai GT2; trục Z kép: 2 động cơ NEMA 17 + khớp nối
    + vít me T8 (bước 8 mm) + đai ốc đồng bắt trên tai tấm đầu X. Nguồn 24 V, hộp mạch + màn hình, giá cuộn nhựa.
(b) "corexy" (kiểu Voron): khung lập phương 2020 có ốp mica 3 mặt + cửa trước bản lề, giàn XY trên 2 ray MGN12 ở đỉnh,
    2 động cơ NEMA 17 góc sau kéo 2 vòng đai GT2 ở hai tầng (A trên, B dưới) qua puly căng góc trước + đầu giàn, bàn nhiệt
    đi lên xuống theo Z trên 2 ray đứng + 2 vít me T8 dẫn bằng 2 động cơ dưới đáy.

Số đo chuẩn: NEMA ICS 16 (NEMA 17), HIWIN MGN12, Gates GT2 (bước 2 mm), nhôm định hình 20 mm rãnh 6.
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d import standards as S
from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.generation.templates.fan import fan_parts
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec

G12 = S.LINEAR_GUIDES["MGN12"]
N17 = S.NEMA[17]
GT2 = S.BELTS["GT2"]
Z_PULLEY = 20                                                          # puly GT2 20 răng, PD 12,73 mm
BELT_W = 6.0
LEAD_T8 = 8.0


def box_at(x0, x1, y0, y1, z0, z1) -> K.Solid:
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    z0, z1 = sorted((z0, z1))
    return K.box(x1 - x0, y1 - y0, z1 - z0).translate((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)


def frame_map(u, v, w, origin) -> np.ndarray:
    """Ma trận 3×4 đưa hệ cục bộ (x, y, z) sang trục thế giới u, v, w tại `origin`."""
    return np.column_stack([np.asarray(u, float), np.asarray(v, float), np.asarray(w, float), np.asarray(origin, float)])


def extrusion(x0, x1, y0, y1, z0, z1) -> K.Solid:
    """Nhôm định hình 20xx (rãnh T6): hộp + rãnh chữ nhật 6,2 × 6 mm giữa mỗi ô 20 mm trên 4 mặt dọc chiều dài."""
    lo, hi = np.array([min(x0, x1), min(y0, y1), min(z0, z1)]), np.array([max(x0, x1), max(y0, y1), max(z0, z1)])
    size = hi - lo
    ax = int(np.argmax(size))
    body = box_at(lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])
    cuts = []
    for k in range(3):
        if k == ax:
            continue
        j = 3 - ax - k                                                # mặt vuông góc trục j chứa rãnh chạy theo ax, dàn theo k
        n = max(1, int(round(size[k] / 20.0)))
        for i in range(n):
            c = lo[k] + (i + 0.5) * size[k] / n
            for side in (lo[j], hi[j]):
                a, b = np.array(lo, float) - 1.0, np.array(hi, float) + 1.0
                a[ax], b[ax] = lo[ax] - 1.0, hi[ax] + 1.0
                a[k], b[k] = c - 3.1, c + 3.1
                if side == lo[j]:
                    a[j], b[j] = lo[j] - 1.0, lo[j] + 6.0
                else:
                    a[j], b[j] = hi[j] - 6.0, hi[j] + 1.0
                cuts.append(box_at(a[0], b[0], a[1], b[1], a[2], b[2]))
    return body.subtract_all(cuts)


def belt_loop(r1: float, r2: float, C: float, teeth: bool = True) -> tuple[K.Solid, float, int]:
    """Vòng đai GT2 hở quanh 2 puly (tâm (0,0) và (C,0), mặt phẳng XY, rộng BELT_W đối xứng z). Trả (khối, dài, số răng)."""
    path, _, _ = MC.open_belt_path(r1, r2, C, step=1.0)
    L = MC.path_length(path)
    n = int(round(L / GT2["pitch"]))
    pld, back = GT2["pld"], GT2["total_h"] - GT2["tooth_h"]
    section = MC.cs(P.offset_polygon(path, -pld + back)) - MC.cs(P.offset_polygon(path, -pld))
    if teeth:
        tooth = MC.belt_tooth_section("GT2")
        step = L / n
        tcs = []
        for k in range(n):
            pk, tk = MC.point_on_path(path, k * step)
            nk = np.array([-tk[1], tk[0]])
            tcs.append(MC.cs(pk + np.outer(pld + tooth[:, 1], nk) + np.outer(tooth[:, 0], tk)))
        section = section + MC.cs_union(tcs)
    return MC.extrude_cs(section, BELT_W, center=True), L, n


def pulley_r() -> float:
    return Z_PULLEY * GT2["pitch"] / (2 * math.pi)


def idler(r_belt: float) -> K.Solid:
    """Puly căng trơn (ổ bi 2 gờ) cho mặt răng đai: bán kính lăn = r_belt − PLD − cao răng; trục Z, tâm gốc."""
    r = r_belt - GT2["pld"] - GT2["tooth_h"]
    body = K.cylinder(r, BELT_W + 1.0, segments=48, center=True)
    fl = K.cylinder(r + 2.2, 0.8, segments=48)
    return body + fl.translate(0, 0, (BELT_W + 1.0) / 2) + fl.translate(0, 0, -(BELT_W + 1.0) / 2 - 0.8) - K.cylinder(2.5, 30, segments=20, center=True)


def stepper(mats_face: str = "cast_aluminum") -> tuple[dict, list]:
    """NEMA 17 thân 40 mm (mặt lắp z = 0, thân −Z, trục +Z) → (dict khối, danh sách (khối, vật liệu))."""
    nm = MC.nema_stepper(17, 40.0)
    cores = nm["shaft_core"] + nm["screw_cores"]
    parts = [(nm["front"] - cores, mats_face), (nm["stack"] - cores, "steel_dark"), (nm["rear"] - cores, mats_face),
             (nm["screws"], "steel_black_oxide"), (nm["shaft"], "stainless")]
    return nm, parts


def hotend(tip) -> dict:
    """Hotend kiểu V6 (trục Z, đầu phun tại `tip`): đầu phun đồng hex 7 + côn, khối gia nhiệt 20×16×11,5 lệch +X,
    ống ngắt nhiệt, tản nhiệt Ø22 × 26 mm 11 lá, cổ groove-mount Ø16. Trả z các mốc."""
    x, y, z = tip
    cone = K.cylinder(0.3, 2.5, radius_top=3.2, segments=32).translate(x, y, z)
    hexn = K.cylinder(4.04, 3.0, segments=6).translate(x, y, z + 2.5)
    block = box_at(x - 8.0, x + 12.0, y - 8.0, y + 8.0, z + 5.5, z + 17.0)
    block = block - K.cylinder(3.0, 17.0, segments=24).rotate(90, 0, 0).translate(x + 6.0, y + 8.5, z + 11.0)     # lỗ ống sưởi
    heater = K.cylinder(3.0, 20.0, segments=24).rotate(90, 0, 0).translate(x + 6.0, y + 10.0, z + 11.0)
    brk = K.cylinder(3.5, 4.0, segments=24).translate(x, y, z + 17.0)
    fins = [K.cylinder(3.5, 26.0, segments=24).translate(x, y, z + 21.0)]
    for k in range(11):
        fins.append(K.cylinder(11.0, 1.0, segments=64).translate(x, y, z + 21.0 + 0.5 + k * 2.45))
    sink = K.Solid.union_all(fins)
    neck = (K.cylinder(8.0, 3.7, segments=48) + K.cylinder(6.0, 6.0, segments=48).translate(0, 0, 3.7 - 0.01) +
            K.cylinder(8.0, 3.0, segments=48).translate(0, 0, 9.7 - 0.02)).translate(x, y, z + 47.0 - 0.01)
    return {"nozzle": cone + hexn, "block": block, "heater": heater, "break": brk, "sink": sink + neck,
            "z_mount": z + 47.0, "z_top": z + 59.7}


def spool(center, axis_len: float = 70.0, axis: str = "y") -> K.Solid:
    """Cuộn nhựa 1 kg: 2 vành Ø200 × 3, lõi Ø180 (chứa sợi), lỗ moay-ơ Ø54; trục Y (hoặc X) tại `center`."""
    prof = [(27.0, -axis_len / 2), (100.0, -axis_len / 2), (100.0, -axis_len / 2 + 3.0), (90.0, -axis_len / 2 + 3.0),
            (90.0, axis_len / 2 - 3.0), (100.0, axis_len / 2 - 3.0), (100.0, axis_len / 2), (27.0, axis_len / 2)]
    s = K.revolve(prof, segments=128)
    return (s.rotate(90, 0, 0) if axis == "y" else s.rotate(0, 90, 0)).translate(*center)


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    kin = p.get("kinematics", "bedslinger")
    Bx, By, Bz = float(p.get("build_x_mm", 220.0)), float(p.get("build_y_mm", 220.0)), float(p.get("build_z_mm", 250.0))
    mats = MC.tech_materials(spec, primary="#2b2e33", secondary="#1b1d21", accent="#e86a1a")
    mats["pei"] = M.material("pei", "plastic", "#c8a24a", 0.0, 0.55, name="Tấm PEI in nhám")
    mats["acrylic"] = M.material("acrylic", "glass", "#cfd8dc", 0.0, 0.05, alpha=0.28, name="Mica trong 3 mm")
    mats["filament"] = M.material("filament", "plastic", "#e86a1a", 0.0, 0.35, name="Sợi nhựa PLA")
    mats["heater_block"] = M.material("heater_block", "metal", "#b9bdc2", 1.0, 0.4, name="Nhôm khối gia nhiệt")
    name = spec.name or (f"Máy in 3D FDM {Bx:g}×{By:g}×{Bz:g}" + (" CoreXY" if kin == "corexy" else ""))
    b = AssemblyBuilder(name, "fdm_printer", mats)
    if kin == "corexy":
        meta = _corexy(b, Bx, By, Bz)
    else:
        meta = _bedslinger(b, Bx, By, Bz)
    b.note_stage(1, "Tháo cuộn nhựa, nguồn, hộp mạch")
    b.note_stage(2, "Tháo cụm đầu in, đai")
    b.note_stage(3, "Tháo bàn nhiệt, giàn X")
    b.note_stage(4, "Tách động cơ, ray, khung")
    b.place_on_ground(center_xy=True)
    b.metadata.update({"kinematics": kin, "build_mm": [Bx, By, Bz], **meta,
                       "standard": "NEMA 17 (ICS 16), ray HIWIN MGN12, đai Gates GT2 6 mm / puly 20 răng, vít me T8×8, nhôm định hình 20 mm",
                       "strict_overlap": True})
    return b.build()


# ============================================================================ bedslinger
def _bedslinger(b: AssemblyBuilder, Bx: float, By: float, Bz: float) -> dict:
    contacts: list[list[str]] = []
    rp = pulley_r()
    x_n = 100.0                                                        # trục hotend (cột đứng ở x ∈ [−20, 20])
    Yu = Bx / 2 + 50.0                                                 # tâm cột / thanh đế hai bên
    Lb = By + 250.0
    xb0, xb1 = x_n - Lb / 2, x_n + Lb / 2
    z_bt = 50.0                                                        # đỉnh đế
    bed_w_x, bed_w_y = By + 15.0, Bx + 15.0
    z_cp = z_bt + G12["h"]                                             # mặt trên con trượt Y (dưới tấm đỡ bàn)
    z_bed = z_cp + 4.0 + 8.0                                           # đáy bàn nhôm (trên lò xo 8 mm)
    bed_top = z_bed + 3.0 + 0.8
    tip_z = bed_top + 0.2                                              # đầu phun ở vị trí home (lớp đầu 0,2 mm)
    zc = tip_z + 60.0                                                  # tâm thanh X
    zm = zc + 32.0                                                     # tâm động cơ / puly X
    z_top = zc + Bz + 70.0                                             # đỉnh cột

    # ---------- khung ----------
    fr = [extrusion(xb0, xb1, sy * Yu - 10, sy * Yu + 10, 10.0, z_bt) for sy in (1, -1)]
    fr += [extrusion(x0, x0 + 40, -Yu + 10, Yu - 10, 10.0, 30.0) for x0 in (xb0, xb1 - 40)]
    fr.append(extrusion(xb0, xb1, -20.0, 20.0, 30.0, z_bt))
    fr += [extrusion(-20.0, 20.0, sy * Yu - 10, sy * Yu + 10, z_bt, z_top) for sy in (1, -1)]
    fr.append(extrusion(-20.0, 20.0, -Yu - 10, Yu + 10, z_top, z_top + 20.0))
    x_s, y_s = 10.0, Yu + 33.0                                         # vít me Z (ngoài cột)
    z_mp = 45.0                                                        # mặt lắp động cơ Z
    for sy in (1, -1):
        bot = box_at(x_s - 25, x_s + 25, sy * (Yu + 10), sy * (y_s + 25), z_mp, z_mp + 4.0)
        bot = bot - K.cylinder(N17["pilot_d"] / 2 + 0.3, 10, segments=48).translate(x_s, sy * y_s, z_mp - 3)
        top = box_at(x_s - 16, x_s + 16, sy * (Yu + 10), sy * (y_s + 16), z_top - 8.0, z_top)
        top = top - K.cylinder(4.05, 20, segments=32).translate(x_s, sy * y_s, z_top - 12)
        fr += [bot, top]
    frame = K.Solid.union_all(fr)
    b.add("frame", "Khung nhôm định hình 2040", "2040 aluminium frame", "frame", Shape(frame, "aluminum_dark", 35.0), required=True,
          aliases=["khung", "khung nhôm", "nhôm định hình", "frame", "thanh nhôm 2040"],
          function="Đế chữ H + 2 cột + thanh đỉnh nhôm 2040 rãnh T6; tai gá động cơ Z và ổ đỡ đầu vít me.",
          position_tag="center", dimensions={"length": Lb, "width": 2 * Yu + 20, "height": z_top + 20})
    feet = K.Solid.union_all([K.cylinder(12.0, 10.0, segments=40).translate(x, sy * Yu, 0) for x in (xb0 + 25, xb1 - 25) for sy in (1, -1)])
    b.add("feet", "Chân cao su", "Rubber feet", "foot", Shape(feet, "rubber", 35.0), parent_id="frame", required=True,
          aliases=["chân", "chân cao su", "feet"], function="4 chân cao su chống rung.", position_tag="bottom",
          explode_dir=(0, 0, -1), explode_distance=30.0, explode_order=1)

    # ---------- trục Y: ray, con trượt, bàn ----------
    L_yr = By + 135.0
    y_rail = MC.linear_rail(G12, L_yr).translate(x_n, 0, z_bt)
    b.add("y_rail", "Ray trục Y MGN12", "Y rail MGN12", "rail", Shape(y_rail, "bearing_steel", 35.0), parent_id="frame", required=True,
          aliases=["ray", "ray trượt", "ray Y", "thanh trượt", "rail"], function=f"Ray MGN12 dài {L_yr:g} mm bắt trên thanh đế giữa.",
          position_tag="center", dimensions={"length": L_yr})
    car = MC.carriage(G12)
    car_s = [car["body"].translate(x_n + sx * 40.0, 0, z_bt) for sx in (1, -1)]
    car_c = [(car["caps"] + car["seals"] + car["nipple"]).translate(x_n + sx * 40.0, 0, z_bt) for sx in (1, -1)]
    b.add("y_carriages", "Con trượt trục Y", "Y carriages", "carriage",
          [Shape(K.Solid.union_all(car_s), "bearing_steel", 35.0), Shape(K.Solid.union_all(car_c), "plastic_black", 35.0)], parent_id="y_rail",
          required=True, aliases=["con trượt", "block trượt", "carriage"], function="2 con trượt MGN12H cách 80 mm mang bàn.",
          position_tag="center", joint_axis=(1, 0, 0), explode_dir=(0, 0, 1), explode_distance=40.0, explode_order=4)
    cp = box_at(x_n - bed_w_x / 2 + 5, x_n + bed_w_x / 2 - 5, -bed_w_y / 2 + 5, bed_w_y / 2 - 5, z_cp, z_cp + 4.0)
    corners = [(x_n + sx * (bed_w_x / 2 - 12), sy * (bed_w_y / 2 - 12)) for sx in (1, -1) for sy in (1, -1)]
    cp = cp.subtract_all([K.cylinder(2.1, 10, segments=16).translate(cx, cy, z_cp - 3) for cx, cy in corners])
    y_bt = 28.0                                                        # mặt phẳng đai Y (bên +Y thanh giữa)
    zp_y = z_cp - 8.0 - 0.376 - rp                                     # tâm puly Y: nhánh trên đai sát kẹp dưới tấm đỡ
    clamp = box_at(x_n - 12, x_n + 12, y_bt - 6.0, y_bt + 6.0, zp_y + rp - 2.0, z_cp + 0.01)
    b.add("bed_carriage", "Tấm đỡ bàn + kẹp đai", "Bed carriage plate", "carriage",
          [Shape(cp, "aluminum", 35.0), Shape(clamp, "plastic_black", 35.0)], parent_id="y_carriages", required=True,
          aliases=["tấm đỡ bàn", "bàn trượt Y", "kẹp đai", "bed carriage"], function="Tấm nhôm 4 mm bắt trên 2 con trượt, kẹp đai Y.",
          position_tag="center", explode_dir=(0, 0, 1), explode_distance=60.0, explode_order=3)
    springs, knobs, screws = [], [], []
    for cx, cy in corners:
        springs.append(MC.orient(K.tube(MC.helix_path(4.2, [(0.6, 0.0), (4.0, 1.7), (0.6, 0.0)], z0=0.0, per_turn=16), 0.55, 8), (cx, cy, z_cp + 4.0 + 0.55), (0, 0, 1)))
        knobs.append(K.cylinder(9.0, 8.0, segments=32).translate(cx, cy, z_cp - 8.0))
        screws.append(K.cylinder(2.0, z_bed + 2.0 - (z_cp - 8.0), segments=16).translate(cx, cy, z_cp - 8.0))
    lev = [Shape(K.Solid.union_all(springs), "spring_steel", 35.0), Shape(K.Solid.union_all(knobs), "paint_accent", 35.0),
           Shape(K.Solid.union_all(screws), "steel", 35.0)]
    b.add("leveling", "Lò xo + núm cân bàn", "Bed levelling springs & knobs", "spring", lev, parent_id="bed_carriage", required=True,
          aliases=["lò xo", "núm cân bàn", "cân bàn", "leveling"], function="4 vít M4 + lò xo + núm vặn chỉnh phẳng bàn.",
          position_tag="center", explode_dir=(0, 0, -1), explode_distance=30.0, explode_order=2)
    bed = box_at(x_n - bed_w_x / 2, x_n + bed_w_x / 2, -bed_w_y / 2, bed_w_y / 2, z_bed, z_bed + 3.0)
    bed = bed.subtract_all([K.cylinder(2.1, 5, segments=16).translate(cx, cy, z_bed - 1) for cx, cy in corners])
    heater_pad = box_at(x_n - bed_w_x / 2 + 10, x_n + bed_w_x / 2 - 10, -bed_w_y / 2 + 10, bed_w_y / 2 - 10, z_bed - 0.8, z_bed)
    b.add("heated_bed", "Bàn nhiệt nhôm", "Heated bed", "bed", [Shape(bed, "aluminum", 35.0), Shape(heater_pad, "rubber", 35.0)],
          parent_id="bed_carriage", required=True, aliases=["bàn nhiệt", "bàn in", "heated bed", "bàn nóng", "hotbed"],
          function=f"Nhôm 3 mm {bed_w_x:g}×{bed_w_y:g} mm + tấm sưởi silicon 24 V dán đáy.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=90.0, explode_order=2, dimensions={"length": bed_w_x, "width": bed_w_y})
    contacts.append(["leveling", "heated_bed"])
    plate = box_at(x_n - bed_w_x / 2, x_n + bed_w_x / 2, -bed_w_y / 2, bed_w_y / 2, z_bed + 3.0, bed_top)
    b.add("build_plate", "Tấm PEI từ tính", "PEI build plate", "build_plate", Shape(plate, "pei", 35.0), parent_id="heated_bed", required=True,
          aliases=["tấm in", "tấm PEI", "mặt in", "build plate", "bề mặt in"], function=f"Thép lò xo phủ PEI, vùng in {Bx:g}×{By:g} mm.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=130.0, explode_order=1, dimensions={"length": By, "width": Bx})

    # ---------- truyền động Y ----------
    x_ym, x_id = xb0 - 25.0, xb1 + 20.0
    belt, Lbelt, nbelt = belt_loop(rp, rp, x_id - x_ym)
    xz = frame_map((1, 0, 0), (0, 0, 1), (0, -1, 0), (x_ym, y_bt, zp_y))
    b.add("y_belt", "Đai GT2 trục Y", "Y GT2 belt", "belt", Shape(belt.transform(xz), "rubber", 20.0), parent_id="bed_carriage", required=True,
          aliases=["đai", "dây đai", "đai GT2", "belt", "curoa"], function=f"Đai GT2 6 mm, {nbelt} răng (dài ≈ {Lbelt:.0f} mm).",
          position_tag="bottom", explode_dir=(0, 1, 0), explode_distance=40.0, explode_order=2, dimensions={"length": round(Lbelt, 1)})
    contacts += [["y_belt", "y_pulley"], ["y_belt", "y_idler"]]
    _motor_unit(b, "y", "Y", (x_ym, 43.5, zp_y), (0, -1, 0), y_bt, contacts)
    brk = box_at(x_ym - 25, xb0, 39.5, 43.5, 10.0, zp_y + 24.0)
    brk = brk - K.cylinder(N17["pilot_d"] / 2 + 0.3, 10, segments=48).rotate(90, 0, 0).translate(x_ym, 45.0, zp_y)
    ibr = box_at(xb1, x_id + 15, 36.0, 40.0, 10.0, zp_y + 14.0) + K.cylinder(2.5, 18.0, segments=20).rotate(90, 0, 0).translate(x_id, 40.0, zp_y)
    b.add("y_brackets", "Gá động cơ Y + gá puly căng", "Y motor & idler brackets", "bracket",
          [Shape(brk, "aluminum", 35.0), Shape(ibr, "aluminum", 35.0)], parent_id="frame", required=True,
          aliases=["gá động cơ", "gá puly", "bracket"], function="Tấm nhôm 4 mm bắt vào đầu thanh đế giữ động cơ và trục puly căng.",
          position_tag="rear", explode_dir=(0, 1, 0), explode_distance=40.0, explode_order=3)
    b.add("y_idler", "Puly căng trục Y", "Y idler", "pulley", Shape(idler(rp).rotate(90, 0, 0).translate(x_id, y_bt, zp_y), "steel", 35.0),
          parent_id="y_brackets", required=True, aliases=["puly căng", "puly trơn", "idler"], function="Puly trơn 2 gờ trên ổ bi 625.",
          position_tag="front", joint_axis=(0, 1, 0), explode_dir=(0, -1, 0), explode_distance=30.0, explode_order=1)

    # ---------- trục Z: ray, con trượt, tấm đầu X, vít me ----------
    zr0, zr1 = z_bt + 10.0, z_top - 10.0
    zrails, zcars_b, zcars_c = [], [], []
    to_z = frame_map((0, 0, -1), (0, 1, 0), (1, 0, 0), (0, 0, 0))     # ray dọc Z, đáy ray áp mặt x = 20 (mặt ray hướng +X)
    for sy in (1, -1):
        zrails.append(MC.linear_rail(G12, zr1 - zr0).transform(to_z).translate(20.0, sy * Yu, (zr0 + zr1) / 2))
        zcars_b.append(car["body"].transform(to_z).translate(20.0, sy * Yu, zc))
        zcars_c.append((car["caps"] + car["seals"] + car["nipple"]).transform(to_z).translate(20.0, sy * Yu, zc))
    x_pl = 20.0 + G12["h"]                                              # mặt sau tấm đầu X
    tag = {1: "l", -1: "r"}
    for i, sy in enumerate((1, -1)):
        b.add(f"z_rail_{tag[sy]}", f"Ray trục Z {'trái' if sy > 0 else 'phải'}", f"Z rail {tag[sy].upper()}", "rail",
              Shape(zrails[i], "bearing_steel", 35.0), parent_id="frame", required=True, aliases=["ray Z", "ray đứng", "rail"],
              function=f"Ray MGN12 dài {zr1 - zr0:g} mm ở mặt trước cột.", position_tag="left" if sy > 0 else "right",
              dimensions={"length": zr1 - zr0})
        b.add(f"z_carriage_{tag[sy]}", f"Con trượt Z {'trái' if sy > 0 else 'phải'}", f"Z carriage {tag[sy].upper()}", "carriage",
              [Shape(zcars_b[i], "bearing_steel", 35.0), Shape(zcars_c[i], "plastic_black", 35.0)], parent_id=f"z_rail_{tag[sy]}", required=True,
              aliases=["con trượt Z", "carriage"], function="Con trượt MGN12H mang tấm đầu X.", position_tag="left" if sy > 0 else "right",
              joint_axis=(0, 0, 1), explode_dir=(1, 0, 0), explode_distance=40.0, explode_order=4)
        z0p = zc - 40.0
        pl = box_at(x_pl, x_pl + 6.0, sy * (Yu - 25.0), sy * (Yu + (90.0 if sy > 0 else 48.0)), z0p, zc + 56.0)
        tab = box_at(x_s - 15.0, x_pl + 0.01, sy * (y_s - 15.0), sy * (y_s + 15.0), z0p, z0p + 5.0)
        tab = tab - K.cylinder(5.2, 20, segments=32).translate(x_s, sy * y_s, z0p - 5)
        xe = pl + tab
        if sy > 0:
            xe = xe - K.cylinder(N17["pilot_d"] / 2 + 0.3, 20, segments=48).rotate(0, 90, 0).translate(x_pl - 5, Yu + 67.0, zm)
        else:
            xe = xe + K.cylinder(2.5, 20.0, segments=20).rotate(0, 90, 0).translate(x_pl + 6.0 - 0.01, -(Yu + 20.0), zm)
        b.add(f"x_end_{tag[sy]}", f"Tấm đầu X {'trái' if sy > 0 else 'phải'}", f"X end plate {tag[sy].upper()}", "bracket",
              Shape(xe, "aluminum", 35.0), parent_id=f"z_carriage_{tag[sy]}", required=True,
              aliases=["tấm đầu X", "x-end", "gá trục X", "bracket"],
              function="Tấm nhôm 6 mm bắt con trượt Z, mang thanh X, tai đai ốc vít me" + (", động cơ X." if sy > 0 else ", puly căng X."),
              position_tag="left" if sy > 0 else "right", explode_dir=(1, 0, 0), explode_distance=70.0, explode_order=3)
        nut = (K.cylinder(11.0, 3.5, segments=48).translate(0, 0, 5.0) + K.cylinder(5.1, 15.0, segments=32).translate(0, 0, -10.0))
        nut = nut - K.cylinder(4.0, 40, segments=32, center=True)
        nut = nut.subtract_all([K.cylinder(1.7, 10, segments=12).translate(8.0 * math.cos(a), 8.0 * math.sin(a), 3.0)
                                for a in np.linspace(0, 2 * math.pi, 4, endpoint=False)])
        b.add(f"z_nut_{tag[sy]}", "Đai ốc đồng T8", "T8 brass nut", "nut", Shape(nut.translate(x_s, sy * y_s, z0p), "brass", 35.0),
              parent_id=f"x_end_{tag[sy]}", required=True, aliases=["đai ốc đồng", "đai ốc vít me", "nut"], function="Đai ốc T8 mặt bích 4 lỗ M3.",
              position_tag="left" if sy > 0 else "right", explode_dir=(0, 0, 1), explode_distance=30.0, explode_order=1)
        nm, mparts = stepper()
        up = frame_map((1, 0, 0), (0, 1, 0), (0, 0, 1), (x_s, sy * y_s, z_mp))
        b.add(f"z_motor_{tag[sy]}", f"Động cơ Z {'trái' if sy > 0 else 'phải'} NEMA 17", f"Z motor {tag[sy].upper()}", "motor",
              [Shape(s_.transform(up), m_, 30.0) for s_, m_ in mparts], parent_id="frame", required=True,
              aliases=["động cơ Z", "động cơ bước", "NEMA 17", "motor"], function="NEMA 17 thân 40 mm, trục lên.",
              position_tag="bottom", joint_axis=(0, 0, 1), explode_dir=(0, 0, -1), explode_distance=60.0, explode_order=2)
        cpl = K.cylinder(9.5, 25.0, segments=48).translate(0, 0, 10.0)
        cpl = cpl - K.cylinder(2.5, 15.01, segments=24).translate(0, 0, 9.99) - K.cylinder(4.0, 10.01, segments=24).translate(0, 0, 25.0)
        cpl = cpl.subtract_all([K.box(20, 20, 0.8).translate(0, 0, 13.0 + k * 1.6) - K.cylinder(4.2, 1.0, segments=24).translate(0, 0, 12.5 + k * 1.6)
                                for k in range(7)])
        b.add(f"z_coupling_{tag[sy]}", "Khớp nối mềm 5–8", "Flexible coupling", "coupling_hub", Shape(cpl.translate(x_s, sy * y_s, z_mp), "aluminum", 35.0),
              parent_id=f"z_motor_{tag[sy]}", required=True, aliases=["khớp nối", "coupling"], function="Khớp nối rãnh xoắn nhôm Ø19, lỗ 5–8 mm.",
              position_tag="bottom", joint_axis=(0, 0, 1), explode_dir=(0, 0, 1), explode_distance=20.0, explode_order=1)
        z_ls0, z_ls1 = z_mp + 25.0, z_top - 2.0
        ls = MC.ball_screw_rod(8.0, LEAD_T8, 1.6, z_ls1 - z_ls0, z0=z_ls0, max_triangles=20000).translate(x_s, sy * y_s, 0)
        b.add(f"z_screw_{tag[sy]}", f"Vít me T8 {'trái' if sy > 0 else 'phải'}", f"T8 lead screw {tag[sy].upper()}", "shaft", Shape(ls, "stainless", 30.0),
              parent_id=f"z_coupling_{tag[sy]}", required=True, aliases=["vít me", "trục vít", "lead screw", "T8"],
              function=f"Vít me inox T8 bước {LEAD_T8:g} mm, dài {z_ls1 - z_ls0:g} mm.", position_tag="left" if sy > 0 else "right",
              joint_axis=(0, 0, 1), explode_dir=(0, 0, 1), explode_distance=Bz * 0.4, explode_order=2, dimensions={"length": z_ls1 - z_ls0})
        contacts += [[f"z_screw_{tag[sy]}", f"z_nut_{tag[sy]}"], [f"z_screw_{tag[sy]}", "frame"], [f"z_screw_{tag[sy]}", f"z_motor_{tag[sy]}"]]

    # ---------- giàn X ----------
    x_b0, x_b1 = x_pl + 6.0, x_pl + 26.0
    xbeam = extrusion(x_b0, x_b1, -Yu - 20.0, Yu + 20.0, zc - 20.0, zc + 20.0)
    b.add("x_beam", "Thanh ngang X 2040", "X beam 2040", "frame", Shape(xbeam, "aluminum_dark", 35.0), parent_id="x_end_l", required=True,
          aliases=["thanh X", "giàn X", "thanh ngang", "gantry"], function="Nhôm 2040 bắt giữa 2 tấm đầu X.",
          position_tag="center", explode_dir=(1, 0, 0), explode_distance=110.0, explode_order=3, dimensions={"length": 2 * Yu + 40})
    contacts.append(["x_beam", "x_end_r"])
    L_xr = Bx + 90.0
    to_y = frame_map((0, 1, 0), (0, 0, -1), (1, 0, 0), (x_b1, 0, zc))  # ray dọc Y, đáy áp mặt trước thanh X (mặt ray +X)
    xr = MC.linear_rail(G12, L_xr).transform(to_y)
    b.add("x_rail", "Ray trục X MGN12", "X rail MGN12", "rail", Shape(xr, "bearing_steel", 35.0), parent_id="x_beam", required=True,
          aliases=["ray X", "ray trượt", "rail"], function=f"Ray MGN12 dài {L_xr:g} mm mặt trước thanh X.", position_tag="front",
          dimensions={"length": L_xr})
    b.add("x_carriage", "Con trượt trục X", "X carriage", "carriage",
          [Shape(car["body"].transform(to_y), "bearing_steel", 35.0), Shape((car["caps"] + car["seals"] + car["nipple"]).transform(to_y), "plastic_black", 35.0)],
          parent_id="x_rail", required=True, aliases=["con trượt X", "carriage"], function="Con trượt MGN12H mang cụm đầu in.",
          position_tag="front", joint_axis=(0, 1, 0), explode_dir=(1, 0, 0), explode_distance=50.0, explode_order=3)
    x_th = x_b1 + G12["h"]
    tip = (x_n, 0.0, tip_z)
    he = hotend(tip)
    x_belt = x_pl + 6.0 + 1.0 + 10.34 + 0.2                            # tâm bề rộng đai X (trước tấm đầu X, trên thanh X)
    th = box_at(x_th, x_th + 6.0, -22.0, 22.0, zc - 20.0, zm + 10.0)
    arm = box_at(x_belt - 5.0, x_th + 0.01, -12.0, 12.0, zc + 21.0, zm + 10.0)
    brk = box_at(x_th + 5.99, x_n + 22.0, -20.0, 20.0, he["z_mount"], he["z_mount"] + 6.0)
    brk = brk - K.cylinder(6.0, 8.0, segments=48).translate(x_n, 0, he["z_mount"] - 1.0)
    b.add("toolhead", "Tấm gá đầu in + kẹp đai X", "Toolhead carriage", "bracket",
          [Shape(th + brk, "aluminum", 35.0), Shape(arm, "plastic_black", 35.0)], parent_id="x_carriage", required=True,
          aliases=["đầu in", "cụm đầu in", "tấm gá đầu in", "toolhead"], function="Tấm nhôm 6 mm, gá kẹp groove-mount hotend, kẹp đai X.",
          position_tag="front", explode_dir=(1, 0, 0), explode_distance=80.0, explode_order=2)
    b.add("hotend", "Hotend + đầu phun 0,4 mm", "Hotend & 0.4 mm nozzle", "hotend",
          [Shape(he["sink"], "aluminum", 35.0), Shape(he["break"], "stainless", 35.0), Shape(he["block"], "heater_block", 35.0),
           Shape(he["heater"], "stainless", 35.0), Shape(he["nozzle"], "brass", 35.0)], parent_id="toolhead", required=True,
          aliases=["hotend", "đầu phun", "đầu đùn", "nozzle", "béc", "khối gia nhiệt"],
          function="Hotend kiểu V6: tản nhiệt Ø22, ống ngắt nhiệt, khối nhôm có ống sưởi 40 W + nhiệt điện trở, đầu phun đồng 0,4 mm.",
          position_tag="front", explode_dir=(0, 0, -1), explode_distance=60.0, explode_order=1)
    F = fan_parts(40, 7)
    to_fan = frame_map((0, 0, -1), (0, 1, 0), (1, 0, 0), (x_n + 12.0, 0, he["z_mount"] - 20.0))
    b.add("hotend_fan", "Quạt tản nhiệt hotend 40 mm", "40 mm hotend fan", "fan_frame",
          [Shape((F["frame"] + F["support"]).transform(to_fan), "plastic_black", 35.0), Shape(F["rotor"].transform(to_fan), "plastic_black", 35.0)],
          parent_id="toolhead", required=True, aliases=["quạt", "quạt hotend", "quạt tản nhiệt", "fan"], function="Quạt 40×10 mm thổi qua lá tản nhiệt.",
          position_tag="front", explode_dir=(1, 0, 0), explode_distance=40.0, explode_order=1)
    # đai X + động cơ X + puly căng
    y_mX, y_iX = Yu + 67.0, -(Yu + 20.0)
    xbelt, LX, nX = belt_loop(rp, rp, y_mX - y_iX)
    yz = frame_map((0, -1, 0), (0, 0, 1), (-1, 0, 0), (x_belt, y_mX, zm))
    b.add("x_belt", "Đai GT2 trục X", "X GT2 belt", "belt", Shape(xbelt.transform(yz), "rubber", 20.0), parent_id="toolhead", required=True,
          aliases=["đai X", "đai", "đai GT2", "belt"], function=f"Đai GT2 6 mm, {nX} răng (dài ≈ {LX:.0f} mm).", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=40.0, explode_order=1, dimensions={"length": round(LX, 1)})
    contacts += [["x_belt", "x_pulley"], ["x_belt", "x_idler"]]
    _motor_unit(b, "x", "X", (x_pl, y_mX, zm), (1, 0, 0), x_belt, contacts, parent="x_end_l")
    b.add("x_idler", "Puly căng trục X", "X idler", "pulley", Shape(idler(rp).rotate(0, 90, 0).translate(x_belt, y_iX, zm), "steel", 35.0),
          parent_id="x_end_r", required=True, aliases=["puly căng", "idler"], function="Puly trơn 2 gờ trên trục M5.", position_tag="right",
          joint_axis=(1, 0, 0), explode_dir=(1, 0, 0), explode_distance=30.0, explode_order=1)

    # ---------- điện, cuộn nhựa ----------
    psu = box_at(-137.0, -22.0, -Yu - 60.0, -Yu - 10.0, 12.0, 227.0)
    vents = K.Solid.union_all([box_at(-139.0, -130.0, -Yu - 58.0, -Yu - 12.0, 40.0 + k * 9.0, 43.0 + k * 9.0) for k in range(16)])
    b.add("psu", "Nguồn 24 V 350 W", "24 V 350 W PSU", "power_supply", [Shape(psu - vents, "steel_zinc", 35.0)], parent_id="frame", required=True,
          aliases=["nguồn", "bộ nguồn", "nguồn tổ ong", "PSU", "power supply"], function="Nguồn tổ ong 24 V 14,6 A bắt mặt ngoài thanh đế phải.",
          position_tag="rear", explode_dir=(0, -1, 0), explode_distance=80.0, explode_order=1)
    box = box_at(150.0, 280.0, Yu + 10.0, Yu + 45.0, 12.0, 48.0)
    board = box_at(158.0, 272.0, Yu + 12.0, Yu + 14.0, 15.0, 45.0)
    b.add("controller", "Hộp mạch điều khiển", "Controller box", "electronics",
          [Shape(box - box_at(155.0, 275.0, Yu + 12.0, Yu + 46.0, 14.0, 46.0) + box_at(155.0, 275.0, Yu + 43.0, Yu + 45.0, 14.0, 46.0), "plastic_black", 35.0),
           Shape(board, "pcb", 35.0)], parent_id="frame", required=True,
          aliases=["bo mạch", "mạch điều khiển", "mainboard", "hộp mạch", "controller"],
          function="Bo mạch 32-bit + driver TMC2209 êm trong hộp nhựa có quạt.", position_tag="left",
          explode_dir=(0, 1, 0), explode_distance=60.0, explode_order=1)
    lcd = box_at(xb1, xb1 + 14.0, -Yu + 15.0, -Yu + 105.0, 12.0, 70.0)
    scr = box_at(xb1 + 13.5, xb1 + 14.5, -Yu + 22.0, -Yu + 80.0, 25.0, 64.0)
    knob = K.cylinder(7.0, 10.0, segments=32).rotate(0, 90, 0).translate(xb1 + 14.0 - 0.01, -Yu + 93.0, 40.0)
    b.add("display", "Màn hình + núm xoay", "LCD & encoder", "display",
          [Shape(lcd - box_at(xb1 + 13.0, xb1 + 15.0, -Yu + 22.0, -Yu + 80.0, 25.0, 64.0), "plastic_black", 35.0),
           Shape(scr, "glass_tinted", 35.0), Shape(knob, "paint_accent", 35.0)], parent_id="frame", required=True,
          aliases=["màn hình", "LCD", "núm xoay", "display"], function="Màn hình 12864 + núm xoay mã hóa.",
          position_tag="front", explode_dir=(1, 0, 0), explode_distance=50.0, explode_order=1)
    axle_z = z_top + 150.0
    post = box_at(-10.0, 10.0, -55.0, -45.0, z_top + 20.0, axle_z + 15.0)
    axle = K.cylinder(12.0, 90.0, segments=48).rotate(-90, 0, 0).translate(0, -45.0 - 0.01, axle_z)
    b.add("spool_holder", "Giá cuộn nhựa", "Spool holder", "bracket", [Shape(post, "plastic_black", 35.0), Shape(axle, "plastic_gray", 35.0)],
          parent_id="frame", required=True, aliases=["giá cuộn nhựa", "giá treo cuộn", "spool holder"], function="Trụ + trục nhựa trên thanh đỉnh.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=60.0, explode_order=2)
    sp = spool((0, 0.0, axle_z - 15.0))
    sp_f = K.cylinder(89.99, 64.0, segments=128, center=True).rotate(90, 0, 0).translate(0, 0.0, axle_z - 15.0) - K.cylinder(50.0, 70, segments=64, center=True).rotate(90, 0, 0).translate(0, 0, axle_z - 15.0)
    b.add("spool", "Cuộn nhựa PLA 1 kg", "1 kg PLA spool", "spool", [Shape(sp, "plastic_black", 35.0), Shape(sp_f, "filament", 35.0)],
          parent_id="spool_holder", required=True, aliases=["cuộn nhựa", "sợi nhựa", "filament", "spool"], function="Cuộn Ø200 × 70 mm, sợi Ø1,75 mm.",
          position_tag="top", joint_axis=(0, 1, 0), explode_dir=(0, 0, 1), explode_distance=150.0, explode_order=1)
    contacts.append(["spool", "spool_holder"])
    b.metadata["contacts"] = contacts
    return {"nozzle_d_mm": 0.4, "belt_pitch_mm": GT2["pitch"], "pulley_teeth": Z_PULLEY, "lead_mm": LEAD_T8,
            "belts": {"y_belt": nbelt, "x_belt": nX}, "tip_gap_mm": 0.2, "rail": "MGN12",
            "y_rail_mm": L_yr, "x_rail_mm": L_xr, "z_rail_mm": zr1 - zr0, "y_car_span_mm": 80.0 + G12["car_l"],
            "home_tip_z_mm": tip_z, "z_carriage_home_mm": zc, "z_top_mm": z_top}


def _motor_unit(b: AssemblyBuilder, key: str, KEY: str, face, shaft_dir, belt_c: float, contacts: list, parent: str = "y_brackets") -> None:
    """Động cơ NEMA 17: mặt lắp tại `face`, trục theo `shaft_dir` (±X/±Y); puly 20 răng tâm ở tọa độ `belt_c` dọc trục."""
    d = np.asarray(shaft_dir, float)
    # dựng hệ: z cục bộ → d, x cục bộ → trục thế giới khác
    ex = np.array([0, 0, 1.0]) if abs(d[2]) < 0.9 else np.array([1.0, 0, 0])
    ey = np.cross(d, ex)
    mtx = frame_map(ex, ey, d, face)
    nm, mparts = stepper()
    b.add(f"{key}_motor", f"Động cơ trục {KEY} NEMA 17", f"{KEY} motor NEMA 17", "motor", [Shape(s_.transform(mtx), m_, 30.0) for s_, m_ in mparts],
          parent_id=parent, required=True, aliases=[f"động cơ {KEY}", "động cơ bước", "NEMA 17", "motor"], function="NEMA 17 thân 40 mm, 1,8°/bước.",
          position_tag="rear", joint_axis=tuple(d), explode_dir=tuple(-d), explode_distance=60.0, explode_order=2)
    k = int(np.argmax(np.abs(d)))
    off = (belt_c - float(face[k])) * float(np.sign(d[k]))              # khoảng từ mặt lắp tới tâm bề rộng đai
    pl = MC.timing_pulley(Z_PULLEY, "GT2", BELT_W + 1.0, N17["shaft_d"], hub_len=6.0).mirror((0, 0, 1)).translate(0, 0, off)
    b.add(f"{key}_pulley", f"Puly GT2 20 răng trục {KEY}", f"{KEY} GT2 pulley", "pulley", Shape(pl.transform(mtx), "aluminum", 30.0),
          parent_id=f"{key}_motor", required=True, aliases=["puly", "puly răng", "pulley"], function="Puly GT2 20 răng lỗ 5 mm, 2 vít hãm.",
          position_tag="rear", joint_axis=tuple(d), explode_dir=tuple(d), explode_distance=25.0, explode_order=1)
    contacts.append([f"{key}_motor", parent])


# ============================================================================ CoreXY
def fillet_route(corners, R: float, step_deg: float = 6.0) -> tuple[np.ndarray, list[tuple[float, float]]]:
    """Đường tâm đai hở qua các góc vuông `corners` (điểm đầu, các góc, điểm cuối), bo mỗi góc bán kính R quanh puly.
    Trả (điểm (N,2), tâm các puly — hai góc cách nhau 2R chung một tâm = vòng quấn 180°)."""
    pts, centers = [np.asarray(corners[0], float)], []
    for i in range(1, len(corners) - 1):
        c = np.asarray(corners[i], float)
        d1 = c - np.asarray(corners[i - 1], float)
        d2 = np.asarray(corners[i + 1], float) - c
        d1, d2 = d1 / np.linalg.norm(d1), d2 / np.linalg.norm(d2)
        left = d1[0] * d2[1] - d1[1] * d2[0] > 0
        n = (lambda d: np.array([-d[1], d[0]])) if left else (lambda d: np.array([d[1], -d[0]]))
        ctr = c + R * n(d1) + R * n(d2)
        a0 = math.atan2(*(-n(d1))[::-1])
        a1 = math.atan2(*(-n(d2))[::-1])
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        k = max(2, int(abs(math.degrees(da)) / step_deg))
        for t in np.linspace(0.0, 1.0, k + 1):
            pts.append(ctr + R * np.array([math.cos(a0 + da * t), math.sin(a0 + da * t)]))
        key = (round(ctr[0], 3), round(ctr[1], 3))
        if key not in centers:
            centers.append(key)
    pts.append(np.asarray(corners[-1], float))
    out = [pts[0]]
    for q in pts[1:]:
        if np.linalg.norm(q - out[-1]) > 1e-6:
            out.append(q)
    return np.array(out), centers


def strip(path: np.ndarray, thick: float, width: float, z_c: float) -> K.Solid:
    """Dải đai trơn dày `thick` quanh đường tâm hở `path` (XY), rộng `width` theo Z tâm z_c."""
    tang = np.gradient(path, axis=0)
    tang /= np.linalg.norm(tang, axis=1)[:, None]
    nrm = np.column_stack([-tang[:, 1], tang[:, 0]])
    poly = np.vstack([path + nrm * thick / 2, (path - nrm * thick / 2)[::-1]])
    return K.extrude([P.ensure_ccw(poly)], width).translate(0, 0, z_c - width / 2)


def _corexy(b: AssemblyBuilder, Bx: float, By: float, Bz: float) -> dict:
    contacts: list[list[str]] = []
    rp = pulley_r()
    R, tb = rp + 0.35, 1.2                                             # bán kính đường tâm đai quanh puly, bề dày đai trơn
    W, D = Bx + 170.0, By + 170.0                                      # khung ngoài (Y × X)
    z0, zt = 25.0, Bz + 200.0                                          # đáy / đỉnh khung
    xg = -45.0                                                         # tâm thanh X (đầu phun ở x = 0)
    y_r = W / 2 - 10.0                                                 # tâm ray Y trên thanh đỉnh
    zB, zA = zt + 47.0, zt + 57.0                                      # tâm hai tầng đai B (dưới) / A (trên)
    tip_z = zt - 50.0
    bed_top = tip_z - 0.2
    za = bed_top - 56.8                                                # đáy tay đỡ bàn
    zp = zt + 63.0                                                     # đáy tấm gá động cơ góc

    # ---------- khung + ốp ----------
    fr = []
    for sx in (1, -1):
        for sy in (1, -1):
            fr.append(extrusion(sx * D / 2, sx * (D / 2 - 20), sy * W / 2, sy * (W / 2 - 20), z0, zt))
    for zr in (z0, zt - 20.0):
        for sy in (1, -1):
            fr.append(extrusion(-D / 2 + 20, D / 2 - 20, sy * W / 2, sy * (W / 2 - 20), zr, zr + 20))
        for sx in (1, -1):
            fr.append(extrusion(sx * D / 2, sx * (D / 2 - 20), -W / 2 + 20, W / 2 - 20, zr, zr + 20))
    x_s, y_s = 30.0, W / 2 - 45.0                                      # vít me Z
    for sy in (1, -1):
        fr.append(extrusion(-20.0, 20.0, sy * (W / 2 - 20), sy * W / 2, z0 + 20, zt - 20))
        mp = box_at(8.0, 52.0, sy * (W / 2 - 70), sy * W / 2, z0 + 20, z0 + 24)
        fr.append(mp - K.cylinder(N17["pilot_d"] / 2 + 0.3, 10, segments=48).translate(x_s, sy * y_s, z0 + 15))
        tb_ = box_at(8.0, 52.0, sy * (W / 2 - 58), sy * (W / 2 - 20), zt - 28, zt - 20)
        fr.append(tb_ - K.cylinder(4.05, 20, segments=32).translate(x_s, sy * y_s, zt - 35))
    frame = K.Solid.union_all(fr)
    b.add("frame", "Khung lập phương nhôm 2020", "2020 cube frame", "frame", Shape(frame, "aluminum_dark", 35.0), required=True,
          aliases=["khung", "khung nhôm", "nhôm định hình", "frame"],
          function="12 thanh 2020 + 2 cột giữa 2040 mang ray Z, tấm gá động cơ Z và ổ đỡ đầu vít me.",
          position_tag="center", dimensions={"length": D, "width": W, "height": zt})
    feet = K.Solid.union_all([K.cylinder(12.0, z0, segments=40).translate(sx * (D / 2 - 10), sy * (W / 2 - 10), 0) for sx in (1, -1) for sy in (1, -1)])
    b.add("feet", "Chân cao su", "Rubber feet", "foot", Shape(feet, "rubber", 35.0), parent_id="frame", required=True,
          aliases=["chân", "chân cao su", "feet"], function="4 chân cao su 25 mm.", position_tag="bottom",
          explode_dir=(0, 0, -1), explode_distance=30.0, explode_order=1)
    pan = [box_at(-D / 2, D / 2, sy * W / 2, sy * (W / 2 + 3), z0, zt) for sy in (1, -1)] + [box_at(-D / 2 - 3, -D / 2, -W / 2 - 3, W / 2 + 3, z0, zt)]
    b.add("panels", "Ốp mica hông + sau", "Acrylic side & rear panels", "panel", Shape(K.Solid.union_all(pan), "acrylic", 35.0),
          parent_id="frame", required=True, aliases=["ốp", "ốp mica", "vách", "panel", "tấm che"], function="Mica trong 3 mm giữ nhiệt buồng in.",
          position_tag="left", explode_dir=(0, 1, 0), explode_distance=80.0, explode_order=1)
    door = box_at(D / 2, D / 2 + 3, -W / 2, W / 2, z0 + 22, zt)
    handle = box_at(D / 2 + 3, D / 2 + 15, -W / 2 + 20, -W / 2 + 32, (z0 + zt) / 2 - 40, (z0 + zt) / 2 + 40)
    handle = handle - box_at(D / 2 + 2, D / 2 + 10, -W / 2 + 19, -W / 2 + 33, (z0 + zt) / 2 - 30, (z0 + zt) / 2 + 30)
    hinges = K.Solid.union_all([K.cylinder(4.0, 30.0, segments=24).translate(D / 2 + 4.0, W / 2 - 4.0, zh) for zh in (z0 + 50, zt - 80)])
    b.add("door", "Cửa trước mica", "Front door", "door",
          [Shape(door, "acrylic", 35.0), Shape(handle, "plastic_black", 35.0), Shape(hinges, "steel", 35.0)], parent_id="frame", required=True,
          aliases=["cửa", "cửa trước", "door"], function="Cửa mica bản lề trái, tay nắm nhựa, khóa nam châm.", position_tag="front",
          joint_axis=(0, 0, 1), pivot=(D / 2 + 4.0, W / 2 - 4.0, zt / 2), explode_dir=(1, 0, 0), explode_distance=120.0, explode_order=1)

    # ---------- giàn XY ----------
    L_yr = D - 80.0
    rails = K.Solid.union_all([MC.linear_rail(G12, L_yr).translate(0, sy * y_r, zt) for sy in (1, -1)])
    b.add("y_rails", "Ray trục Y MGN12 (đôi)", "Y rails MGN12", "rail", Shape(rails, "bearing_steel", 35.0), parent_id="frame", required=True,
          aliases=["ray Y", "ray trượt", "rail"], function=f"2 ray MGN12 dài {L_yr:g} mm trên 2 thanh đỉnh hông.", position_tag="top",
          dimensions={"length": L_yr})
    car = MC.carriage(G12)
    cb = K.Solid.union_all([car["body"].translate(xg, sy * y_r, zt) for sy in (1, -1)])
    cc = K.Solid.union_all([(car["caps"] + car["seals"] + car["nipple"]).translate(xg, sy * y_r, zt) for sy in (1, -1)])
    b.add("y_carriages", "Con trượt trục Y", "Y carriages", "carriage", [Shape(cb, "bearing_steel", 35.0), Shape(cc, "plastic_black", 35.0)],
          parent_id="y_rails", required=True, aliases=["con trượt Y", "carriage"], function="2 con trượt MGN12H mang giàn X.",
          position_tag="top", joint_axis=(1, 0, 0), explode_dir=(0, 0, 1), explode_distance=40.0, explode_order=4)
    yA, yB1 = W / 2 - 8.0, W / 2 - 26.0
    yB2 = yB1 - 2 * R
    xr, xf = -D / 2 + 22.0 - R, D / 2 - 22.0 + R
    route_a = [(xg, 15.0), (xg, yA), (xr, yA), (xr, -yB1), (xf, -yB1), (xf, -yB2), (xg, -yB2), (xg, -15.0)]
    route_b = [(x, -y) for x, y in route_a]
    path_a, cen_a = fillet_route(route_a, R)
    path_b, cen_b = fillet_route(route_b, R)
    zc_i = lambda zl: (zl - (BELT_W + 1.0) / 2 - 0.8)                  # đáy puly căng (gờ dưới)
    g_posts, g_idlers = [], []
    for (cx, cy), zl in ((cen_a[0], zA), (cen_a[-1], zA), (cen_b[0], zB), (cen_b[-1], zB)):
        g_posts.append(K.cylinder(4.0, zc_i(zl) - (zt + 19.0), segments=24).translate(cx, cy, zt + 19.0))
        g_posts.append(K.cylinder(2.5, zl + 5.5 - zc_i(zl), segments=20).translate(cx, cy, zc_i(zl)))
        g_idlers.append(idler(R + GT2["pld"] + GT2["tooth_h"] - tb / 2).translate(cx, cy, zl))
    gp = K.Solid.union_all([box_at(xg - 20, xg + 20, sy * (W / 2 - 75), sy * (W / 2 + 3), zt + 13, zt + 19) for sy in (1, -1)])
    b.add("gantry_plates", "Tấm đầu giàn X + trục puly", "Gantry end plates", "bracket",
          [Shape(gp, "aluminum", 35.0), Shape(K.Solid.union_all(g_posts), "steel", 35.0)], parent_id="y_carriages", required=True,
          aliases=["tấm đầu giàn", "đầu giàn X", "bracket"], function="2 tấm nhôm 6 mm bắt con trượt Y, mang thanh X và 4 trục puly căng giàn.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=70.0, explode_order=3)
    b.add("gantry_idlers", "Puly căng đầu giàn", "Gantry idlers", "pulley", Shape(K.Solid.union_all(g_idlers), "steel", 35.0),
          parent_id="gantry_plates", required=True, aliases=["puly căng", "idler"], function="4 puly trơn 2 gờ chuyển hướng đai A/B ở hai đầu giàn.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=40.0, explode_order=2)
    xbeam = extrusion(xg - 10, xg + 10, -(W / 2 - 55), W / 2 - 55, zt + 19, zt + 39)
    b.add("x_beam", "Thanh ngang X 2020", "X beam 2020", "frame", Shape(xbeam, "aluminum_dark", 35.0), parent_id="gantry_plates", required=True,
          aliases=["thanh X", "giàn X", "gantry"], function="Nhôm 2020 bắt trên 2 tấm đầu giàn.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=100.0, explode_order=3, dimensions={"length": W - 110})
    zc = zt + 29.0
    L_xr = W - 120.0
    to_y = frame_map((0, 1, 0), (0, 0, -1), (1, 0, 0), (xg + 10, 0, zc))
    b.add("x_rail", "Ray trục X MGN12", "X rail MGN12", "rail", Shape(MC.linear_rail(G12, L_xr).transform(to_y), "bearing_steel", 35.0),
          parent_id="x_beam", required=True, aliases=["ray X", "ray trượt", "rail"], function=f"Ray MGN12 dài {L_xr:g} mm mặt trước thanh X.",
          position_tag="top", dimensions={"length": L_xr})
    b.add("x_carriage", "Con trượt trục X", "X carriage", "carriage",
          [Shape(car["body"].transform(to_y), "bearing_steel", 35.0), Shape((car["caps"] + car["seals"] + car["nipple"]).transform(to_y), "plastic_black", 35.0)],
          parent_id="x_rail", required=True, aliases=["con trượt X", "carriage"], function="Con trượt MGN12H mang cụm đầu in.",
          position_tag="top", joint_axis=(0, 1, 0), explode_dir=(1, 0, 0), explode_distance=50.0, explode_order=3)
    x_th = xg + 10 + G12["h"]
    he = hotend((0.0, 0.0, tip_z))
    th = box_at(x_th, x_th + 6.0, -22.0, 22.0, he["z_mount"] - 2.0, zt + 62.0)
    arm = box_at(xg - 6.0, x_th + 0.01, -15.0, 15.0, zt + 43.0, zt + 62.0)
    brk = box_at(x_th + 5.99, 22.0, -20.0, 20.0, he["z_mount"], he["z_mount"] + 6.0) - K.cylinder(6.0, 8.0, segments=48).translate(0, 0, he["z_mount"] - 1.0)
    b.add("toolhead", "Tấm gá đầu in + kẹp đai", "Toolhead carriage", "bracket",
          [Shape(th + brk, "aluminum", 35.0), Shape(arm, "plastic_black", 35.0)], parent_id="x_carriage", required=True,
          aliases=["đầu in", "cụm đầu in", "toolhead"], function="Tấm nhôm 6 mm gá hotend, khối kẹp 4 đầu đai A/B.",
          position_tag="top", explode_dir=(1, 0, 0), explode_distance=80.0, explode_order=2)
    b.add("hotend", "Hotend + đầu phun 0,4 mm", "Hotend & 0.4 mm nozzle", "hotend",
          [Shape(he["sink"], "aluminum", 35.0), Shape(he["break"], "stainless", 35.0), Shape(he["block"], "heater_block", 35.0),
           Shape(he["heater"], "stainless", 35.0), Shape(he["nozzle"], "brass", 35.0)], parent_id="toolhead", required=True,
          aliases=["hotend", "đầu phun", "đầu đùn", "nozzle", "béc"], function="Hotend kiểu V6, đầu phun đồng 0,4 mm.",
          position_tag="top", explode_dir=(0, 0, -1), explode_distance=60.0, explode_order=1)
    F = fan_parts(40, 7)
    to_fan = frame_map((0, 0, -1), (0, 1, 0), (1, 0, 0), (12.0, 0, he["z_mount"] - 20.0))
    b.add("hotend_fan", "Quạt tản nhiệt hotend 40 mm", "40 mm hotend fan", "fan_frame",
          [Shape((F["frame"] + F["support"]).transform(to_fan), "plastic_black", 35.0), Shape(F["rotor"].transform(to_fan), "plastic_black", 35.0)],
          parent_id="toolhead", required=True, aliases=["quạt", "quạt hotend", "fan"], function="Quạt 40×10 mm thổi qua lá tản nhiệt.",
          position_tag="top", explode_dir=(1, 0, 0), explode_distance=40.0, explode_order=1)

    # ---------- đai A/B, động cơ, puly góc ----------
    belt_a, belt_b = strip(path_a, tb, BELT_W, zA), strip(path_b, tb, BELT_W, zB)
    La, Lb_ = MC.path_length(path_a), MC.path_length(path_b)
    for pid, s_, zl, L_, cen in (("belt_a", belt_a, zA, La, cen_a), ("belt_b", belt_b, zB, Lb_, cen_b)):
        tagn = pid[-1].upper()
        b.add(pid, f"Đai GT2 vòng {tagn}", f"GT2 belt {tagn}", "belt", Shape(s_, "rubber", 20.0), parent_id="toolhead", required=True,
              aliases=[f"đai {tagn}", "đai", "đai GT2", "belt"], function=f"Đai GT2 6 mm tầng {'trên' if tagn == 'A' else 'dưới'}, dài ≈ {L_:.0f} mm, 2 đầu kẹp vào đầu in.",
              position_tag="top", explode_dir=(0, 0, 1), explode_distance=60.0 if tagn == "A" else 45.0, explode_order=1, dimensions={"length": round(L_, 1)})
        contacts += [[pid, f"{tagn.lower()}_pulley"], [pid, "gantry_idlers"], [pid, "corner_idlers"]]
    m_a, m_b = cen_a[1], cen_b[1]                                      # tâm động cơ A (sau trái), B (sau phải)
    c_idl = [(cen_a[2], zA), (cen_a[3], zA), (cen_b[2], zB), (cen_b[3], zB)]   # puly góc sau-phải A, trước-phải A, sau-trái B, trước-trái B
    plates, shafts, cidl = [], [], []
    for sx in (1, -1):
        for sy in (1, -1):
            xo = -D / 2 if sx < 0 else D / 2
            plates.append(box_at(xo, xo - sx * 8.0, sy * (W / 2 - 45), sy * W / 2, zt, zp))
            pl = box_at(xo, xo - sx * 45.0, sy * (W / 2 - 45), sy * (W / 2 + 8), zp, zp + 5.0)
            if sx < 0:
                mc = m_a if sy > 0 else m_b
                pl = pl - K.cylinder(N17["pilot_d"] / 2 + 0.3, 10, segments=48).translate(mc[0], mc[1], zp - 2)
            plates.append(pl)
    for (cx, cy), zl in c_idl:
        shafts.append(K.cylinder(2.5, zp - zc_i(zl) + 1.0, segments=20).translate(cx, cy, zc_i(zl) - 1.0))
        shafts.append(K.cylinder(4.0, zp - (zl + (BELT_W + 1.0) / 2 + 0.8), segments=24).translate(cx, cy, zl + (BELT_W + 1.0) / 2 + 0.8))
        cidl.append(idler(R + GT2["pld"] + GT2["tooth_h"] - tb / 2).translate(cx, cy, zl))
    b.add("corner_plates", "Tấm gá góc + trục puly", "Corner plates", "bracket",
          [Shape(K.Solid.union_all(plates), "aluminum", 35.0), Shape(K.Solid.union_all(shafts), "steel", 35.0)], parent_id="frame", required=True,
          aliases=["tấm gá góc", "gá động cơ", "bracket"], function="4 tấm nhôm 5 mm trên 4 cột góc: 2 gá động cơ AB phía sau, trục treo puly căng.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=90.0, explode_order=4)
    b.add("corner_idlers", "Puly căng góc", "Corner idlers", "pulley", Shape(K.Solid.union_all(cidl), "steel", 35.0), parent_id="corner_plates",
          required=True, aliases=["puly căng", "puly góc", "idler"], function="4 puly trơn 2 gờ (góc sau + góc trước) cho 2 vòng đai.",
          position_tag="top", explode_dir=(0, 0, -1), explode_distance=30.0, explode_order=2)
    for key, mc, zl in (("a", m_a, zA), ("b", m_b, zB)):
        _motor_unit(b, key, key.upper(), (mc[0], mc[1], zp + 5.0), (0, 0, -1), zl, contacts, parent="corner_plates")

    # ---------- trục Z + bàn ----------
    to_z = frame_map((0, 0, -1), (-1, 0, 0), (0, 1, 0), (0, 0, 0))    # ray dọc Z, mặt ray hướng −Y (cột trái), đảo cho cột phải
    zr0, zr1 = z0 + 30.0, zt - 25.0
    zcz = za + 10.0
    tag = {1: "l", -1: "r"}
    for sy in (1, -1):
        m = frame_map((0, 0, -1), (-sy, 0, 0), (0, -sy, 0), (0, sy * (W / 2 - 20), 0))
        zr = MC.linear_rail(G12, zr1 - zr0).transform(m).translate(0, 0, (zr0 + zr1) / 2)
        b.add(f"z_rail_{tag[sy]}", f"Ray trục Z {'trái' if sy > 0 else 'phải'}", f"Z rail {tag[sy].upper()}", "rail", Shape(zr, "bearing_steel", 35.0),
              parent_id="frame", required=True, aliases=["ray Z", "ray đứng", "rail"], function=f"Ray MGN12 dài {zr1 - zr0:g} mm trên cột giữa.",
              position_tag="left" if sy > 0 else "right", dimensions={"length": zr1 - zr0})
        b.add(f"z_carriage_{tag[sy]}", f"Con trượt Z {'trái' if sy > 0 else 'phải'}", f"Z carriage {tag[sy].upper()}", "carriage",
              [Shape(car["body"].transform(m).translate(0, 0, zcz), "bearing_steel", 35.0),
               Shape((car["caps"] + car["seals"] + car["nipple"]).transform(m).translate(0, 0, zcz), "plastic_black", 35.0)],
              parent_id=f"z_rail_{tag[sy]}", required=True, aliases=["con trượt Z", "carriage"], function="Con trượt MGN12H mang tay đỡ bàn.",
              position_tag="left" if sy > 0 else "right", joint_axis=(0, 0, 1), explode_dir=(0, -sy, 0), explode_distance=40.0, explode_order=4)
    y_in = W / 2 - 20 - G12["h"]                                        # mặt con trượt Z
    xa = By / 2 + 5.0
    yoke = [extrusion(-xa, xa, sy * y_in, sy * (y_in - 20), za, za + 20) for sy in (1, -1)]
    yoke = [s_ - K.cylinder(5.0, 40, segments=32).translate(x_s, sy * y_s, za - 10) for s_, sy in zip(yoke, (1, -1))]
    yoke += [extrusion(sx * (By / 2 - 15), sx * (By / 2 + 5), -(y_in - 2), y_in - 2, za + 20, za + 40) for sx in (1, -1)]
    stand = [K.cylinder(5.0, 10.0, segments=24).translate(sx * (By / 2 - 5), sy * (Bx / 2 - 5), za + 40) for sx in (1, -1) for sy in (1, -1)]
    b.add("bed_yoke", "Khung đỡ bàn (tay + thanh ngang)", "Bed yoke", "frame",
          [Shape(K.Solid.union_all(yoke), "aluminum_dark", 35.0), Shape(K.Solid.union_all(stand), "steel", 35.0)], parent_id="z_carriage_l",
          required=True, aliases=["khung đỡ bàn", "tay đỡ bàn", "bed frame"], function="2 tay 2020 bắt con trượt Z + 2 thanh ngang + 4 trụ đỡ bàn.",
          position_tag="center", explode_dir=(0, 0, -1), explode_distance=70.0, explode_order=3)
    contacts.append(["bed_yoke", "z_carriage_r"])
    bw_x, bw_y = By + 15.0, Bx + 15.0
    bed = box_at(-bw_x / 2, bw_x / 2, -bw_y / 2, bw_y / 2, za + 50, za + 56)
    pad = box_at(-bw_x / 2 + 20, bw_x / 2 - 20, -bw_y / 2 + 20, bw_y / 2 - 20, za + 49.2, za + 50)
    b.add("heated_bed", "Bàn nhiệt nhôm đúc 6 mm", "Heated bed", "bed", [Shape(bed, "cast_aluminum", 35.0), Shape(pad, "rubber", 35.0)],
          parent_id="bed_yoke", required=True, aliases=["bàn nhiệt", "bàn in", "heated bed", "hotbed"],
          function=f"Nhôm đúc MIC-6 {bw_x:g}×{bw_y:g} mm + tấm sưởi silicon 230 V.", position_tag="center",
          explode_dir=(0, 0, 1), explode_distance=90.0, explode_order=2, dimensions={"length": bw_x, "width": bw_y})
    plate = box_at(-bw_x / 2, bw_x / 2, -bw_y / 2, bw_y / 2, za + 56, bed_top)
    b.add("build_plate", "Tấm PEI từ tính", "PEI build plate", "build_plate", Shape(plate, "pei", 35.0), parent_id="heated_bed", required=True,
          aliases=["tấm in", "tấm PEI", "mặt in", "build plate"], function=f"Thép lò xo phủ PEI, vùng in {Bx:g}×{By:g} mm.",
          position_tag="center", explode_dir=(0, 0, 1), explode_distance=130.0, explode_order=1, dimensions={"length": By, "width": Bx})
    z_mp = z0 + 20.0
    for sy in (1, -1):
        nut = K.cylinder(11.0, 3.5, segments=48).translate(0, 0, -3.5) + K.cylinder(5.1, 12.0, segments=32).translate(0, 0, -15.5)
        nut = nut - K.cylinder(4.0, 40, segments=32, center=True)
        nut = nut.subtract_all([K.cylinder(1.7, 10, segments=12).translate(8.0 * math.cos(a), 8.0 * math.sin(a), -5.0)
                                for a in np.linspace(0, 2 * math.pi, 4, endpoint=False)])
        b.add(f"z_nut_{tag[sy]}", "Đai ốc đồng T8", "T8 brass nut", "nut", Shape(nut.translate(x_s, sy * y_s, za), "brass", 35.0),
              parent_id="bed_yoke", required=True, aliases=["đai ốc đồng", "đai ốc vít me", "nut"], function="Đai ốc T8 mặt bích bắt dưới tay đỡ bàn.",
              position_tag="left" if sy > 0 else "right", explode_dir=(0, 0, -1), explode_distance=30.0, explode_order=1)
        nm, mparts = stepper()
        up = frame_map((1, 0, 0), (0, 1, 0), (0, 0, 1), (x_s, sy * y_s, z_mp))
        b.add(f"z_motor_{tag[sy]}", f"Động cơ Z {'trái' if sy > 0 else 'phải'} NEMA 17", f"Z motor {tag[sy].upper()}", "motor",
              [Shape(s_.transform(up), m_, 30.0) for s_, m_ in mparts], parent_id="frame", required=True,
              aliases=["động cơ Z", "động cơ bước", "NEMA 17", "motor"], function="NEMA 17 thân 40 mm treo dưới tấm gá, trục lên.",
              position_tag="bottom", joint_axis=(0, 0, 1), explode_dir=(0, 0, -1), explode_distance=60.0, explode_order=2)
        cpl = K.cylinder(9.5, 25.0, segments=48).translate(0, 0, 10.0)
        cpl = cpl - K.cylinder(2.5, 15.01, segments=24).translate(0, 0, 9.99) - K.cylinder(4.0, 10.01, segments=24).translate(0, 0, 25.0)
        cpl = cpl.subtract_all([K.box(20, 20, 0.8).translate(0, 0, 13.0 + k * 1.6) - K.cylinder(4.2, 1.0, segments=24).translate(0, 0, 12.5 + k * 1.6)
                                for k in range(7)])
        b.add(f"z_coupling_{tag[sy]}", "Khớp nối mềm 5–8", "Flexible coupling", "coupling_hub", Shape(cpl.translate(x_s, sy * y_s, z_mp), "aluminum", 35.0),
              parent_id=f"z_motor_{tag[sy]}", required=True, aliases=["khớp nối", "coupling"], function="Khớp nối rãnh xoắn nhôm Ø19.",
              position_tag="bottom", joint_axis=(0, 0, 1), explode_dir=(0, 0, 1), explode_distance=20.0, explode_order=1)
        z_ls0, z_ls1 = z_mp + 25.0, zt - 22.0
        ls = MC.ball_screw_rod(8.0, LEAD_T8, 1.6, z_ls1 - z_ls0, z0=z_ls0, max_triangles=20000).translate(x_s, sy * y_s, 0)
        b.add(f"z_screw_{tag[sy]}", f"Vít me T8 {'trái' if sy > 0 else 'phải'}", f"T8 lead screw {tag[sy].upper()}", "shaft", Shape(ls, "stainless", 30.0),
              parent_id=f"z_coupling_{tag[sy]}", required=True, aliases=["vít me", "trục vít", "lead screw", "T8"],
              function=f"Vít me inox T8 bước {LEAD_T8:g} mm.", position_tag="left" if sy > 0 else "right", joint_axis=(0, 0, 1),
              explode_dir=(0, 0, 1), explode_distance=Bz * 0.4, explode_order=2, dimensions={"length": z_ls1 - z_ls0})
        contacts += [[f"z_screw_{tag[sy]}", f"z_nut_{tag[sy]}"], [f"z_screw_{tag[sy]}", "frame"], [f"z_screw_{tag[sy]}", f"z_motor_{tag[sy]}"]]

    # ---------- điện, màn hình, cuộn nhựa ----------
    deck = box_at(-D / 2 + 25, 5.0, -(W / 2 - 5), W / 2 - 5, z0 - 3, z0)
    b.add("deck", "Tấm đáy điện", "Electronics deck", "cover", Shape(deck, "steel_zinc", 35.0), parent_id="frame", required=True,
          aliases=["tấm đáy", "khoang điện", "deck"], function="Tôn mạ kẽm 3 mm bắt dưới đáy khung, mang nguồn và mạch.",
          position_tag="bottom", explode_dir=(0, 0, -1), explode_distance=50.0, explode_order=2)
    psu = box_at(-D / 2 + 25, -D / 2 + 140, -107.5, 107.5, z0, z0 + 50)
    vents = K.Solid.union_all([box_at(-D / 2 + 30 + k * 7.0, -D / 2 + 33 + k * 7.0, -100.0, 100.0, z0 + 48, z0 + 51) for k in range(15)])
    b.add("psu", "Nguồn 24 V 350 W", "24 V 350 W PSU", "power_supply", Shape(psu - vents, "steel_zinc", 35.0), parent_id="deck", required=True,
          aliases=["nguồn", "bộ nguồn", "PSU", "power supply"], function="Nguồn tổ ong 24 V 14,6 A.", position_tag="bottom",
          explode_dir=(0, 0, 1), explode_distance=60.0, explode_order=1)
    cbox = box_at(-D / 2 + 30, -D / 2 + 130, -60.0, 60.0, z0 + 50, z0 + 80)
    board = box_at(-D / 2 + 35, -D / 2 + 125, -55.0, 55.0, z0 + 52, z0 + 54)
    b.add("controller", "Hộp mạch điều khiển", "Controller box", "electronics",
          [Shape(cbox - box_at(-D / 2 + 32, -D / 2 + 128, -58.0, 58.0, z0 + 52, z0 + 78), "plastic_black", 35.0), Shape(board, "pcb", 35.0)],
          parent_id="psu", required=True, aliases=["bo mạch", "mạch điều khiển", "mainboard", "controller"],
          function="Bo mạch 32-bit + 4 driver TMC2209 + Raspberry Pi chạy Klipper.", position_tag="bottom",
          explode_dir=(0, 0, 1), explode_distance=90.0, explode_order=1)
    lcd = box_at(D / 2, D / 2 + 12.0, -50.0, 50.0, 8.0, z0 + 19.0)
    scr = box_at(D / 2 + 11.5, D / 2 + 12.5, -40.0, 20.0, 12.0, z0 + 15.0)
    knob = K.cylinder(6.0, 8.0, segments=32).rotate(0, 90, 0).translate(D / 2 + 12.0 - 0.01, 35.0, (8.0 + z0 + 19.0) / 2)
    b.add("display", "Màn hình + núm xoay", "LCD & encoder", "display",
          [Shape(lcd - box_at(D / 2 + 11.0, D / 2 + 13.0, -40.0, 20.0, 12.0, z0 + 15.0), "plastic_black", 35.0), Shape(scr, "glass_tinted", 35.0),
           Shape(knob, "paint_accent", 35.0)], parent_id="frame", required=True, aliases=["màn hình", "LCD", "display"],
          function="Màn hình mini12864 + núm xoay trên thanh đáy trước.", position_tag="front",
          explode_dir=(1, 0, 0), explode_distance=50.0, explode_order=1)
    axle_z = max(zt * 0.55, 140.0)
    post = box_at(-D / 2 - 18.0, -D / 2 - 3.0, -15.0, 15.0, axle_z - 40.0, axle_z + 15.0)
    axle = K.cylinder(12.0, 90.0, segments=48).rotate(0, -90, 0).translate(-D / 2 - 18.0 + 0.01, 0, axle_z)
    b.add("spool_holder", "Giá cuộn nhựa", "Spool holder", "bracket", [Shape(post, "plastic_black", 35.0), Shape(axle, "plastic_gray", 35.0)],
          parent_id="panels", required=True, aliases=["giá cuộn nhựa", "spool holder"], function="Giá nhựa bắt xuyên ốp sau vào khung.",
          position_tag="rear", explode_dir=(-1, 0, 0), explode_distance=60.0, explode_order=2)
    spc = (-D / 2 - 18.0 - 50.0, 0.0, axle_z - 15.0)
    sp = spool(spc, axis="x")
    fil = (K.cylinder(89.99, 64.0, segments=128, center=True) - K.cylinder(50.0, 70, segments=64, center=True)).rotate(0, 90, 0).translate(*spc)
    b.add("spool", "Cuộn nhựa ABS 1 kg", "1 kg ABS spool", "spool", [Shape(sp, "plastic_black", 35.0), Shape(fil, "filament", 35.0)],
          parent_id="spool_holder", required=True, aliases=["cuộn nhựa", "sợi nhựa", "filament", "spool"], function="Cuộn Ø200 × 70 mm, sợi Ø1,75 mm.",
          position_tag="rear", joint_axis=(1, 0, 0), explode_dir=(-1, 0, 0), explode_distance=150.0, explode_order=1)
    contacts.append(["spool", "spool_holder"])
    b.metadata["contacts"] = contacts
    return {"nozzle_d_mm": 0.4, "belt_pitch_mm": GT2["pitch"], "pulley_teeth": Z_PULLEY, "lead_mm": LEAD_T8,
            "belts": {"belt_a": round(La / GT2["pitch"]), "belt_b": round(Lb_ / GT2["pitch"])}, "tip_gap_mm": 0.2, "rail": "MGN12",
            "y_rail_mm": L_yr, "x_rail_mm": L_xr, "z_rail_mm": zr1 - zr0, "y_car_span_mm": G12["car_l"],
            "home_tip_z_mm": tip_z, "z_carriage_home_mm": zcz, "z_top_mm": zt}
