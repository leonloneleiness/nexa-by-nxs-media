"""Bồn chứa thép: bồn đứng đáy phẳng (kiểu API 650: vỏ các khoang tôn cao 2 m, mái côn dốc 1:6 hoặc mái vòm, móng vòng
bê tông) hoặc bồn nằm (thân trụ + 2 đáy elip 2:1, 2 yên đỡ đặt ở 0,2 L theo Zick, bệ bê tông).

Phụ kiện: thang leo có lồng bảo vệ (ISO 14122-4: lồng từ 2,2 m khi leo > 3 m, bậc cách 300 mm) + sàn đỉnh + lan can,
cửa người chui DN600 (mặt bích mù + bu-lông + cần treo), vòi nạp / xả / xả đáy có mặt bích EN 1092-1 PN16 + van, ống
thở mái (cổ ngỗng), thước đo mức phao, cửa mái. Dung tích = thể tích trong lòng vỏ tới mép trên thân (bồn đứng) hoặc toàn
thể tích trong (bồn nằm).
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d import standards as S
from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.generation.templates.pump import flange
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec


def box_at(x0, x1, y0, y1, z0, z1) -> K.Solid:
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    z0, z1 = sorted((z0, z1))
    return K.box(x1 - x0, y1 - y0, z1 - z0).translate((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)


def nozzle(dn: int, base: np.ndarray, direction: np.ndarray, length: float, valve: bool = True) -> tuple[K.Solid, K.Solid, K.Solid]:
    """Vòi ống DN: ống từ `base` theo `direction` dài `length`, mặt bích PN16 ở đầu, (van bi thân đúc giữa hai bích).
    Trả (ống + bích, van, lõi khoét lỗ vỏ)."""
    d = direction / np.linalg.norm(direction)
    od = S.PIPE_OD[dn]
    pipe = MC.orient(K.cylinder(od / 2, length, segments=40) - K.cylinder(od / 2 - S.PIPE_WALL[dn], length + 2, segments=40).translate(0, 0, -1), base, d)
    fl = MC.orient(flange(dn, 0.0, "z", +1), base + d * length, d)      # mặt tựa ở đầu ống hướng ra, thân bích về phía ống
    core = MC.orient(K.cylinder(od / 2 - S.PIPE_WALL[dn], 3 * length, segments=40).translate(0, 0, -length), base, d)
    vbody = None
    if valve:
        D = S.FLANGE_PN16[dn][0]
        ftf = S.VALVE_FTF[dn]
        v = K.cylinder(D / 2, S.FLANGE_PN16[dn][5], segments=40) + K.cylinder(D / 2, S.FLANGE_PN16[dn][5], segments=40).translate(0, 0, ftf - S.FLANGE_PN16[dn][5]) + \
            K.sphere(0.45 * D, segments=32).translate(0, 0, ftf / 2) + \
            K.cylinder(0.1 * D, 0.35 * D, segments=16).rotate(0, 90, 0).translate(0.38 * D, 0, ftf / 2)          # cổ trục van (theo +X cục bộ)
        lever = K.box(0.06 * D, 0.1 * D, 1.4 * D).translate(0.75 * D, 0, ftf / 2 + 0.5 * D)                    # tay gạt ăn vào đầu cổ trục
        vbody = MC.orient(v + lever, base + d * length, d)
    return pipe + fl, vbody, core


def ladder(z0: float, z1: float, r_shell: float, ang: float, cage_from: float, t_shell: float) -> tuple[K.Solid, K.Solid, int]:
    """Thang leo ngoài vỏ trụ tại góc `ang`: 2 tay vịn + bậc 300 mm, giá bắt vỏ, lồng bảo vệ (vòng + nẹp) từ cage_from."""
    u = np.array([math.cos(ang), math.sin(ang), 0.0])
    t = np.array([-math.sin(ang), math.cos(ang), 0.0])
    r_l = r_shell + 200.0
    rails, rungs, brackets, cage = [], [], [], []
    for s_ in (1, -1):
        p = u * r_l + t * s_ * 225.0
        rails.append(K.box(60.0, 12.0, z1 - z0).rotate(0, 0, math.degrees(ang)).translate(p[0], p[1], (z0 + z1) / 2))
    n_r = 0
    for z in np.arange(z0 + 300.0, z1 - 100.0, 300.0):
        p = u * r_l
        rungs.append(MC.orient(K.cylinder(12.0, 450.0, segments=12).translate(0, 0, -225.0), p + np.array([0, 0, z]), t))
        n_r += 1
    for z in np.arange(z0 + 600.0, z1, 2500.0):
        for s_ in (1, -1):
            a = u * math.sqrt((r_shell - 0.5 * t_shell) ** 2 - 225.0 ** 2) + t * s_ * 225.0   # chân giá nằm giữa bề dày vỏ
            b_ = u * (r_l - 6.0) + t * s_ * 225.0
            brackets.append(K.tube(np.array([a + [0, 0, z], b_ + [0, 0, z]]), 15.0, 10))
    if z1 - z0 > 3000.0:
        c_c = u * (r_l + 350.0)
        for z in np.arange(cage_from, z1, 900.0):
            hoop = (K.cylinder(370.0, 10.0, segments=40) - K.cylinder(355.0, 12.0, segments=40).translate(0, 0, -1)).translate(c_c[0], c_c[1], z)
            hoop = hoop & K.cylinder(10 * r_l, 20.0, segments=8).translate(0, 0, z - 5.0) - K.cylinder(r_l + 5.0, 30.0, segments=96).translate(0, 0, z - 10.0)
            cage.append(hoop)
        for a in np.radians(np.linspace(-150, 150, 5)):
            p = c_c + (math.cos(a) * u + math.sin(a) * t) * 362.0
            if np.linalg.norm(p[:2]) > r_l + 20.0:
                cage.append(K.box(40.0, 8.0, z1 - cage_from).rotate(0, 0, math.degrees(ang) + math.degrees(a)).translate(p[0], p[1], (cage_from + z1) / 2))
    return K.Solid.union_all(rails + rungs + brackets), (K.Solid.union_all(cage) if cage else None), n_r


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    ori = p.get("orientation", "vertical")
    V = float(p.get("capacity_m3", 50.0)) * 1e9                         # mm³
    mats = MC.tech_materials(spec, primary="#e6e8ea", secondary="#3a3d42", accent="#f2b705")
    mats["concrete"] = M.material("concrete", "stone", "#a3a39b", 0.0, 0.85, name="Bê tông móng")
    mats["galvanized"] = M.material("galvanized", "metal", "#b3b9bf", 0.85, 0.42, name="Thép mạ kẽm")
    b = AssemblyBuilder(spec.name or f"Bồn chứa {'đứng' if ori == 'vertical' else 'nằm'} {V / 1e9:g} m³", "storage_tank", mats)
    if ori == "vertical":
        meta = _vertical(b, V, p)
    else:
        meta = _horizontal(b, V, p)
    b.place_on_ground(center_xy=True)
    b.metadata.update({"orientation": ori, "capacity_m3": V / 1e9, **meta, "strict_overlap": True})
    return b.build()


def _vertical(b: AssemblyBuilder, V: float, p: dict) -> dict:
    if p.get("diameter_mm"):
        D = float(p["diameter_mm"])
        H = 4 * V / (math.pi * D * D)
    else:
        D = (4 * V / math.pi) ** (1 / 3)
        H = D
        if H > 12000.0:
            H = 12000.0
            D = math.sqrt(4 * V / (math.pi * H))
    t = 6.0 if D < 15000 else 8.0
    Ri = D / 2                                                          # D = đường kính trong
    zf = 400.0                                                         # mặt móng vòng
    tb = 8.0                                                           # tôn đáy
    z_s0 = zf + tb
    z_s1 = z_s0 + H
    ring = K.cylinder(Ri + t + 400.0, zf, segments=96) - K.cylinder(Ri - 600.0, zf + 2, segments=96).translate(0, 0, -1)
    pad = K.cylinder(Ri - 600.0 + 1.0, zf, segments=96)
    b.add("foundation", "Móng vòng bê tông", "Ringwall foundation", "foundation", [Shape(ring, "concrete", 35.0), Shape(pad, "concrete", 35.0)],
          required=True, aliases=["móng", "móng bồn", "móng vòng", "foundation"], function="Móng vòng bê tông + lớp cát đệm dưới đáy bồn.", position_tag="bottom")
    bottom = K.cylinder(Ri + t + 60.0, tb, segments=128).translate(0, 0, zf)
    shell = K.cylinder(Ri + t, H, segments=128).translate(0, 0, z_s0) - K.cylinder(Ri, H + 2, segments=128).translate(0, 0, z_s0 - 1)
    seams = K.Solid.union_all([K.cylinder(Ri + t + 2.0, 8.0, segments=128).translate(0, 0, z) - K.cylinder(Ri + t - 1.0, 10.0, segments=128).translate(0, 0, z - 1.0)
                               for z in np.arange(z_s0 + 2000.0, z_s1 - 100.0, 2000.0)])
    angle = K.cylinder(Ri + t + 65.0, 8.0, segments=128).translate(0, 0, z_s1 - 8.0) - K.cylinder(Ri + t - 1.0, 10.0, segments=128).translate(0, 0, z_s1 - 9.0)
    roof_kind = p.get("roof", "cone")
    if roof_kind == "cone":
        rise = (Ri + t) / 6.0
        roof = K.cylinder(Ri + t + 40.0, rise, 60.0, segments=128).translate(0, 0, z_s1) - K.cylinder(Ri + t + 40.0 - 8.0, rise - 8.0, 52.0, segments=128).translate(0, 0, z_s1 - 0.01)
    else:
        Rd = 1.0 * D
        rise = Rd - math.sqrt(Rd * Rd - (Ri + t) ** 2)
        dome = K.sphere(Rd, segments=128).translate(0, 0, z_s1 + rise - Rd) & K.cylinder(Ri + t + 40.0, rise + 10.0, segments=128).translate(0, 0, z_s1)
        roof = dome - K.sphere(Rd - 8.0, segments=128).translate(0, 0, z_s1 + rise - Rd)
    z_roof_top = z_s1 + rise
    b.add("shell", f"Thân bồn Ø{D / 1000:.2f} × {H / 1000:.2f} m + đáy", "Shell & bottom", "tank_shell",
          [Shape(shell + angle, "paint_primary", 35.0), Shape(bottom, "paint_secondary", 35.0), Shape(seams, "paint_primary", 35.0)], parent_id="foundation",
          required=True, aliases=["thân bồn", "vỏ bồn", "đáy bồn", "bồn", "khoang tôn", "shell"],
          function=f"Vỏ thép tấm {t:g} mm hàn các khoang cao 2 m, tôn đáy {tb:g} mm, thép góc mép trên.", position_tag="center",
          dimensions={"diameter": D, "height": H})
    b.add("roof", "Mái " + ("côn dốc 1:6" if roof_kind == "cone" else "vòm"), "Roof", "tank_roof", Shape(roof, "paint_primary", 35.0), parent_id="shell",
          required=True, aliases=["mái bồn", "nắp bồn", "mái côn", "mái vòm", "roof"], function="Mái tôn tự đỡ hàn vào thép góc mép thân.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=0.3 * H, explode_order=2)
    # vòi + cửa người chui
    parts_n, valves, cores = [], [], []
    for dn, z, ang, L_, v_ in ((80, z_s1 - 600.0, 30.0, 250.0, True), (100, z_s0 + 450.0, 150.0, 300.0, True), (50, z_s0 + 150.0, 210.0, 250.0, True)):
        u = np.array([math.cos(math.radians(ang)), math.sin(math.radians(ang)), 0.0])
        pn, vb, co = nozzle(dn, u * (Ri - 1.0) + np.array([0, 0, z]), u, L_ + t, v_)
        parts_n.append(pn)
        cores.append(co)
        if vb is not None:
            valves.append(vb)
    b.cut("shell", K.Solid.union_all(cores))
    b.add("nozzles", "Vòi nạp / xả / xả đáy (mặt bích PN16)", "Nozzles", "pipe", Shape(K.Solid.union_all(parts_n), "steel", 35.0), parent_id="shell",
          required=True, aliases=["vòi bồn", "vòi nạp", "vòi xả", "ống xả đáy", "mặt bích", "nozzle"], function="Vòi nạp DN80 (trên), xả DN100, xả đáy DN50, mặt bích EN 1092-1 PN16.",
          position_tag="side", explode_dir=(1, 0, 0), explode_distance=600.0, explode_order=1)
    b.add("valves", "Van bi tay gạt (3)", "Ball valves", "valve_body", Shape(K.Solid.union_all(valves), "cast_iron", 35.0), parent_id="nozzles", required=True,
          aliases=["van", "van bi", "van tay gạt", "valve"], function="Van bi mặt bích PN16 trên các vòi.", position_tag="side",
          explode_dir=(1, 0, 0), explode_distance=900.0, explode_order=1)
    # cửa người chui DN600
    a_m = math.radians(270.0)
    um = np.array([math.cos(a_m), math.sin(a_m), 0.0])
    zm = z_s0 + 750.0
    neck = MC.orient(K.cylinder(330.0, 250.0 + t, segments=64) - K.cylinder(300.0, 260.0 + t, segments=64).translate(0, 0, -5.0), um * (Ri - 1.0) + [0, 0, zm], um)
    b.cut("shell", MC.orient(K.cylinder(300.0, 3 * t + 10.0, segments=64).translate(0, 0, -t - 5.0), um * Ri + [0, 0, zm], um))
    mflange = MC.orient(K.cylinder(420.0, 20.0, segments=64) - K.cylinder(300.0, 30.0, segments=64).translate(0, 0, -5.0), um * (Ri + 250.0 + t - 20.0) + [0, 0, zm], um)
    cover = MC.orient(K.cylinder(420.0, 20.0, segments=64), um * (Ri + 250.0 + t) + [0, 0, zm], um)
    mbolts = K.Solid.union_all([MC.orient(MC.hex_bolt(20.0, 50.0), um * (Ri + 250.0 + t + 20.0) + [0, 0, zm] +
                                          (np.array([-math.sin(a_m), math.cos(a_m), 0]) * math.cos(q) + np.array([0, 0, 1.0]) * math.sin(q)) * 380.0, um)
                                for q in np.radians(np.arange(0, 360, 22.5))])
    b.add("manway", "Cửa người chui DN600 + nắp mù", "Manway DN600", "manway",
          [Shape(neck + mflange, "paint_primary", 35.0), Shape(cover, "paint_secondary", 35.0), Shape(mbolts, "steel_dark", 35.0)], parent_id="shell",
          required=True, aliases=["cửa người chui", "manway", "nắp mù", "cửa kiểm tra"], function="Cửa người chui DN600 cổ hàn, nắp mù 16 bu-lông M20.",
          position_tag="side", explode_dir=tuple(float(v) for v in um), explode_distance=700.0, explode_order=1)
    contacts: list[list[str]] = []
    # thang + sàn đỉnh + lan can mái
    a_l = math.radians(90.0)
    rails, cage, n_r = ladder(zf, z_s1 + 100.0, Ri + t, a_l, zf + 2200.0, t)
    ul = np.array([math.cos(a_l), math.sin(a_l), 0.0])
    plat = box_at(-500.0, 500.0, Ri + t - 200.0, Ri + t + 700.0, z_s1 + 100.0, z_s1 + 140.0).rotate(0, 0, math.degrees(a_l) - 90.0)
    plat = plat - K.cylinder(Ri + t + 2.0, 1000.0, segments=128).translate(0, 0, z_s1 - 500.0)
    hand = K.Solid.union_all([K.tube(np.array([[x, Ri + t + 690.0, z_s1 + 140.0], [x, Ri + t + 690.0, z_s1 + 1240.0]]), 20.0, 10) for x in (-490.0, 490.0)]
                             + [K.tube(np.array([[-490.0, Ri + t + 690.0, z_s1 + 1240.0], [490.0, Ri + t + 690.0, z_s1 + 1240.0]]), 20.0, 10)])
    lad_shapes = [Shape(rails, "galvanized", 35.0), Shape(plat + hand, "galvanized", 35.0)]
    if cage is not None:
        lad_shapes.append(Shape(cage, "galvanized", 35.0))
    b.add("ladder", "Thang leo có lồng + sàn đỉnh + lan can", "Caged ladder & top platform", "ladder", lad_shapes, parent_id="shell", required=True,
          aliases=["thang", "thang leo", "lồng thang", "sàn thao tác", "lan can", "ladder"],
          function=f"Thang thép mạ kẽm {n_r} bậc cách 300 mm" + (", lồng bảo vệ từ 2,2 m" if cage is not None else "") + ", sàn đỉnh có lan can.",
          position_tag="side", explode_dir=tuple(float(v) for v in ul), explode_distance=800.0, explode_order=1)
    contacts += [["ladder", "roof"]]
    # ống thở mái + thước đo mức
    vent = K.tube(np.array([[0, 0, z_roof_top - 60.0], [0, 0, z_roof_top + 450.0], [0, 180.0, z_roof_top + 600.0], [0, 300.0, z_roof_top + 450.0]]), 55.0, 20)
    ag = math.radians(0.0)
    ug = np.array([math.cos(ag), math.sin(ag), 0.0])
    board = box_at(Ri + t + 150.0, Ri + t + 165.0, -40.0, 40.0, z_s0 + 300.0, z_s1 - 300.0)
    guide = K.Solid.union_all([K.tube(np.array([ug * (Ri + t - 2.0) + [0, 0, z], ug * (Ri + t + 152.0) + [0, 0, z]]), 12.0, 8) for z in (z_s0 + 500.0, z_s1 - 500.0)])
    b.add("fittings", "Ống thở mái + thước đo mức phao", "Vent & level gauge", "gauge",
          [Shape(vent, "paint_secondary", 35.0), Shape(board, "paint_accent", 35.0), Shape(guide, "galvanized", 35.0)], parent_id="roof", required=True,
          aliases=["ống thở", "ống thông hơi", "thước đo mức", "đồng hồ mức", "vent", "level gauge"], function="Ống thở cổ ngỗng có lưới chặn lửa, thước đo mức kiểu phao.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=900.0, explode_order=1)
    contacts += [["fittings", "shell"]]
    b.metadata["contacts"] = contacts
    b.note_stage(1, "Tháo vòi, van, cửa người chui, thang, ống thở")
    b.note_stage(2, "Nhấc mái")
    return {"diameter_mm": D, "shell_height_mm": H, "shell_t_mm": t, "roof": roof_kind, "rungs": n_r, "has_cage": cage is not None,
            "inner_radius_mm": Ri, "shell_z0_mm": z_s0, "contacts": contacts,
            "standard": "Bồn đáy phẳng kiểu API 650 (khoang 2 m, mái côn 1:6), thang ISO 14122-4, mặt bích EN 1092-1 PN16"}


def _horizontal(b: AssemblyBuilder, V: float, p: dict) -> dict:
    if p.get("diameter_mm"):
        D = float(p["diameter_mm"])
        Lc = max(0.5 * D, (V - math.pi * D ** 3 / 12) / (math.pi * D * D / 4))
    else:
        D = (12 * V / (10 * math.pi)) ** (1 / 3)
        Lc = 3 * D
    t = 6.0 if D < 2500 else 8.0
    Ri = D / 2
    hh = D / 4                                                         # đáy elip 2:1
    z_ax = max(400.0 + 0.62 * D, D / 2 + 700.0)                        # đáy bồn đủ cao cho vòi xả + van dưới đáy
    shell = (K.cylinder(Ri + t, Lc, segments=128) - K.cylinder(Ri, Lc + 2, segments=128).translate(0, 0, -1)).rotate(0, 90, 0).translate(-Lc / 2, 0, z_ax)
    heads = []
    for s_ in (1, -1):
        outer = K.ellipsoid(hh + t, Ri + t, Ri + t, segments=96) & K.box(3 * D, 3 * D, 3 * D).translate(s_ * 1.5 * D, 0, 0)
        inner = K.ellipsoid(hh, Ri, Ri, segments=96) & K.box(3 * D, 3 * D, 3 * D).translate(s_ * 1.5 * D - s_ * 0.01, 0, 0)
        heads.append((outer - inner).translate(s_ * Lc / 2, 0, z_ax))
    seams = K.Solid.union_all([(K.cylinder(Ri + t + 2.0, 8.0, segments=128) - K.cylinder(Ri + t - 1.0, 10.0, segments=128).translate(0, 0, -1)).rotate(0, 90, 0)
                               .translate(x, 0, z_ax) for x in (-Lc / 2, Lc / 2)])
    b.add("shell", f"Thân bồn nằm Ø{D / 1000:.2f} × {Lc / 1000:.2f} m + 2 đáy elip", "Shell & heads", "tank_shell",
          [Shape(shell + K.Solid.union_all(heads), "paint_primary", 35.0), Shape(seams, "paint_primary", 35.0)], parent_id="saddles", required=True,
          aliases=["thân bồn", "vỏ bồn", "đáy elip", "bồn nằm", "shell"], function=f"Thân trụ thép {t:g} mm + 2 đáy elip 2:1 dập.", position_tag="center",
          explode_dir=(0, 0, 1), explode_distance=0.4 * D, explode_order=2, dimensions={"diameter": D, "length": Lc})
    sad = []
    pads = []
    for x in (-0.3 * Lc, 0.3 * Lc):
        web = K.box(12.0, 1.1 * D, z_ax - 400.0 - 0.3 * D).translate(x, 0, 400.0 + (z_ax - 400.0 - 0.3 * D) / 2)
        cradle = (K.cylinder(Ri + t + 12.0, 220.0, segments=96) - K.cylinder(Ri + t, 240.0, segments=96).translate(0, 0, -10.0)).rotate(0, 90, 0).translate(x - 110.0, 0, z_ax)
        cradle = cradle & box_at(x - 120.0, x + 120.0, -0.55 * D, 0.55 * D, 0.0, z_ax - 0.3 * D + 20.0)
        base = K.box(240.0, 1.2 * D, 16.0).translate(x, 0, 400.0 + 8.0)
        webs = web + K.hull([K.box(12.0, 1.1 * D, 1.0).translate(x, 0, z_ax - 0.3 * D), K.box(12.0, 0.9 * D, 1.0).translate(x, 0, z_ax - 0.3 * D + 0.1 * D)]) & \
            (K.box(3 * D, 3 * D, 3 * D).translate(0, 0, 0) - K.cylinder(Ri + t + 12.0, 3 * D, segments=96).rotate(0, 90, 0).translate(-1.5 * D, 0, z_ax))
        sad.append(webs + cradle + base)
        pads.append(K.box(500.0, 1.4 * D, 400.0).translate(x, 0, 200.0))
    b.add("foundation", "Bệ bê tông (2)", "Concrete piers", "foundation", Shape(K.Solid.union_all(pads), "concrete", 35.0), required=True,
          aliases=["bệ bồn", "móng", "foundation"], function="2 bệ bê tông đỡ yên.", position_tag="bottom")
    b.add("saddles", "Yên đỡ (2) tại 0,2 L", "Saddles", "saddle", Shape(K.Solid.union_all(sad), "paint_secondary", 35.0), parent_id="foundation", required=True,
          aliases=["yên đỡ", "chân bồn", "saddle"], function="Yên thép hàn ôm 120°, đặt cách đáy ~0,2 L (phương pháp Zick).", position_tag="bottom",
          explode_dir=(0, 0, -1), explode_distance=300.0, explode_order=3)
    parts_n, valves, cores = [], [], []
    for dn, x, down, v_ in ((80, 0.35 * Lc, False, True), (50, 0.12 * Lc, False, False), (100, -0.1 * Lc, True, True)):   # vòi xả tránh bệ yên
        d = np.array([0, 0, -1.0 if down else 1.0])
        base = np.array([x, 0.0, z_ax]) + d * (Ri - 1.0)
        pn, vb, co = nozzle(dn, base, d, 200.0 + t, v_)
        parts_n.append(pn)
        cores.append(co)
        if vb is not None:
            valves.append(vb)
    mw = np.array([0.0, 0.0, z_ax + Ri - 1.0])
    neck = K.cylinder(290.0, 250.0 + t, segments=64).translate(*mw) - K.cylinder(260.0, 270.0 + t, segments=64).translate(*(mw - [0, 0, 5.0]))
    cover = K.cylinder(380.0, 20.0, segments=64).translate(*(mw + [0, 0, 250.0 + t]))
    cores.append(K.cylinder(260.0, 3 * t + 10.0, segments=64).translate(*(mw - [0, 0, t + 5.0])))
    b.cut("shell", K.Solid.union_all(cores))
    b.add("nozzles", "Vòi nạp / thở / xả + cửa người chui DN500", "Nozzles & manway", "pipe",
          [Shape(K.Solid.union_all(parts_n) + neck, "steel", 35.0), Shape(cover, "paint_secondary", 35.0)], parent_id="shell", required=True,
          aliases=["vòi bồn", "vòi nạp", "vòi xả", "cửa người chui", "nozzle", "manway"], function="Vòi nạp DN80, thở DN50 (trên), xả DN100 (dưới), cửa người chui DN500 trên đỉnh.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=600.0, explode_order=1)
    b.add("valves", "Van bi (2)", "Ball valves", "valve_body", Shape(K.Solid.union_all(valves), "cast_iron", 35.0), parent_id="nozzles", required=True,
          aliases=["van", "van bi", "valve"], function="Van bi mặt bích PN16.", position_tag="side", explode_dir=(0, 0, 1), explode_distance=900.0, explode_order=1)
    b.metadata["contacts"] = []
    b.note_stage(1, "Tháo vòi, van, cửa người chui")
    b.note_stage(2, "Nhấc thân bồn khỏi yên")
    b.note_stage(3, "Tháo yên")
    return {"diameter_mm": D, "cyl_length_mm": Lc, "shell_t_mm": t, "inner_radius_mm": Ri, "head_depth_mm": hh, "contacts": [],
            "standard": "Bồn nằm thân trụ + đáy elip 2:1, yên đỡ theo Zick, mặt bích EN 1092-1 PN16"}
