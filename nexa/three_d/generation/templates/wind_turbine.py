"""Tuabin gió trục ngang 3 cánh (tỷ lệ kiểu Vestas V90-2 MW: rotor Ø90 m, tâm rotor 80 m, cánh 44 m).

- Móng bê tông + tháp thép ống côn 3 đoạn (Ø đáy ≈ 0,046 D → Ø đỉnh ≈ 0,026 D, vỏ mỏng, cửa ra vào, vành nối bích).
- Vỏ máy (nacelle) composite có thể mở nắp (bản lề sau), bên trong: bệ máy trên ổ quay hướng + 4 động cơ quay hướng,
  trục chính + ổ trục chính, hộp số (cấp hành tinh + cấp song song), khớp nối, máy phát, tủ biến tần; trên nóc: bộ làm mát,
  cột đo gió (phong kế + chong chóng hướng gió).
- Rotor: moay-ơ đúc + 3 ổ đổi bước (pitch), chóp mũi; cánh loft mặt cắt NACA 44xx (dày 40 % gốc → 12 % mũi) dọc bán
  kính, dây cung lớn nhất 0,078 R ở 0,2 R, xoắn 13° → 0°, gốc tròn Ø0,021 D. Trục rotor ngẩng 5°, cánh nghiêng côn 2°,
  rotor đón gió phía trước tháp (overhang ≈ 0,043 D).
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec

# (r/R, dây cung/R, xoắn °, bề dày %) — gốc tròn ở r/R 0,05
BLADE = [(0.05, None, 13.0, 100), (0.10, 0.060, 13.0, 40), (0.20, 0.078, 11.0, 30), (0.35, 0.066, 7.0, 24), (0.50, 0.054, 4.5, 21),
         (0.65, 0.043, 2.5, 18), (0.80, 0.033, 1.0, 15), (0.93, 0.024, 0.3, 13), (0.99, 0.012, 0.0, 12)]
TILT, CONE = 5.0, 2.0


def blade_solid(R: float, root_d: float, span: float, samples: int = 48) -> tuple[K.Solid, list]:
    """Cánh dọc +Z từ gốc (z = 0 tại mặt bích gốc): dây cung dọc Y (tiếp tuyến, mép trước về +Y = chiều quay), bề dày dọc X
    (trục rotor); xoắn quay dây cung từ mặt rotor về phía trục."""
    secs, table = [], []
    ref = P.naca4("4440", 1.0, samples)
    xc = 0.3
    phis = np.arctan2(ref[:, 1] - 0.0, ref[:, 0] - xc)
    for rr, c, tw, th in BLADE:
        z = (rr - BLADE[0][0]) / (BLADE[-1][0] - BLADE[0][0]) * span      # mũi cánh đúng bán kính rotor
        if c is None:
            pts = np.column_stack([np.cos(phis), np.sin(phis)]) * (root_d / 2)
        else:
            af = P.naca4(f"44{min(th, 99):02d}", 1.0, samples)
            pts = (af - np.array([xc, 0.0])) * c * R
        # (dây cung, bề dày) → (Y, X): mép trước (x nhỏ) về +Y; xoắn quanh trục bước (Z)
        yx = np.column_stack([-pts[:, 0], pts[:, 1]])                  # (y, x) trước khi xoắn
        t = math.radians(tw)
        rot = np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]])
        yx = yx @ rot.T
        secs.append(np.column_stack([yx[:, 1], yx[:, 0], np.full(len(yx), z)]))
        table.append((rr, c, tw, th))
    return K.loft(secs), table


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    D = float(p.get("rotor_diameter_mm", 90000.0))
    Hh = float(p.get("hub_height_mm", 80000.0))
    nb = int(p.get("blades", 3))
    open_ = bool(p.get("nacelle_open", False))
    R = D / 2
    k = D / 90000.0
    mats = MC.tech_materials(spec, primary="#eef0f2", secondary="#c8ccd0", accent="#c1121f")
    mats["gfrp"] = M.material("gfrp", "plastic", "#f4f5f6", 0.0, 0.35, name="Composite sợi thủy tinh (cánh, vỏ)")
    mats["concrete"] = M.material("concrete", "stone", "#a3a39b", 0.0, 0.85, name="Bê tông móng")
    b = AssemblyBuilder(spec.name or f"Tuabin gió {nb} cánh rotor Ø{D / 1000:g} m", "wind_turbine", mats)
    contacts: list[list[str]] = []
    # ---------- móng + tháp ----------
    Db, Dt = 0.046 * D, 0.026 * D
    z_f = 500.0
    L_n, W_n, H_n = 0.115 * D, 0.038 * D, 0.042 * D
    z_yaw = Hh - 0.5 * H_n - 0.35 * H_n                               # đỉnh tháp (mặt ổ quay hướng)
    found = K.extrude(P.circle(0.075 * D, 8, start=math.pi / 8), z_f)
    b.add("foundation", "Móng bê tông", "Foundation", "foundation", Shape(found, "concrete", 35.0), required=True,
          aliases=["móng", "móng tuabin", "foundation"], function="Bệ móng bê tông bát giác đỡ tháp (phần nổi).", position_tag="bottom")
    wall = 0.006 * Db + 12.0
    h_t = z_yaw - z_f
    prof = [(Db / 2 - wall, 0.0), (Db / 2, 0.0), (Dt / 2, h_t), (Dt / 2 - wall, h_t)]
    tower = K.revolve(prof, segments=96).translate(0, 0, z_f)
    door = K.rounded_box(Db, 900.0 * min(1.0, k * 1.5), 2100.0 * min(1.0, k * 1.5), 300.0 * min(1.0, k * 1.5), segments=8).translate(-Db / 2, 0, z_f + 1600.0)
    tower = tower - door
    rings = []
    for f in (1 / 3, 2 / 3):
        z = z_f + f * h_t
        r = Db / 2 + (Dt / 2 - Db / 2) * f
        rings.append(K.cylinder(r + 25.0, 120.0, segments=96).translate(0, 0, z - 60.0) - K.cylinder(r - 5.0, 200.0, segments=96).translate(0, 0, z - 100.0))
    door_frame = (K.rounded_box(Db * 0.2, 1100.0 * min(1.0, k * 1.5), 2300.0 * min(1.0, k * 1.5), 350.0, segments=8).translate(-Db / 2, 0, z_f + 1600.0)
                  & (K.cylinder(Db / 2 + 60.0, 4000.0, segments=96).translate(0, 0, z_f) - K.cylinder(Db / 2 - 1.0, 4200.0, segments=96).translate(0, 0, z_f - 100.0))) \
        - door
    b.add("tower", "Tháp thép ống côn (3 đoạn)", "Tubular steel tower", "tower",
          [Shape(tower, "paint_secondary", 35.0), Shape(K.Solid.union_all(rings) + door_frame, "paint_secondary", 35.0)], parent_id="foundation",
          required=True, aliases=["tháp", "thân tháp", "trụ tuabin", "tháp thép", "tower", "cửa tháp"],
          function=f"Tháp thép ống côn Ø{Db / 1000:.2f} → Ø{Dt / 1000:.2f} m, 3 đoạn nối bích, cửa ra vào ở chân.", position_tag="center",
          dimensions={"base_diameter": Db, "top_diameter": Dt, "height": h_t})
    # ---------- ổ quay hướng + bệ máy ----------
    # ổ quay hướng răng trong; 4 động cơ quay hướng treo dưới bệ máy, nằm trong lòng đỉnh tháp (kích thước theo tỷ lệ k)
    hy = 250.0 * k
    yaw_ring = K.cylinder(Dt / 2 + 40.0 * k, hy, segments=96).translate(0, 0, z_yaw) -         K.cylinder(Dt / 2 - hy, 400.0 * k, segments=96).translate(0, 0, z_yaw - 50.0 * k)
    teeth = K.Solid.union_all([K.box(40.0 * k, 30.0 * k, 0.8 * hy).translate(Dt / 2 - hy - 19.0 * k, 0, z_yaw + hy / 2).rotate(0, 0, a)
                               for a in np.arange(0, 360, 3.0)])
    yaw_drives = []
    L_yd = 1200.0 * k
    for a in (35.0, 145.0, 215.0, 325.0):
        c = np.array([(Dt / 2 - 460.0 * k) * math.cos(math.radians(a)), (Dt / 2 - 460.0 * k) * math.sin(math.radians(a))])
        yaw_drives.append(K.cylinder(160.0 * k, L_yd, segments=24).translate(c[0], c[1], z_yaw + hy - L_yd))
    b.add("yaw_system", "Ổ quay hướng + 4 động cơ quay hướng", "Yaw system", "yaw",
          [Shape(yaw_ring + teeth, "steel", 35.0), Shape(K.Solid.union_all(yaw_drives), "paint_blue", 35.0)], parent_id="tower", required=True,
          aliases=["ổ quay hướng", "hệ quay hướng", "động cơ quay hướng", "yaw", "vành răng"],
          function="Ổ bi quay hướng vành răng ngoài + 4 động cơ hộp số quay nacelle theo hướng gió.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=0.02 * D, explode_order=3)
    z_bp = z_yaw + hy
    bed = K.hull([K.box(L_n * 0.55, W_n * 0.62, 10.0).translate(0.08 * L_n, 0, z_bp + 5.0), K.box(L_n * 0.45, W_n * 0.5, 10.0).translate(0.05 * L_n, 0, z_bp + 0.12 * H_n)])
    rear_frame = K.box(0.45 * L_n, W_n * 0.62, 0.05 * H_n).translate(-0.3 * L_n, 0, z_bp + 0.025 * H_n)
    # trục rotor ngẩng TILT, tâm moay-ơ phía trước tháp
    ax = np.array([math.cos(math.radians(TILT)), 0.0, math.sin(math.radians(TILT))])
    hub_c = np.array([0.043 * D + 0.5 * L_n * 0.0 + 0.36 * L_n, 0.0, Hh])
    z_ax = lambda x: Hh + (x - hub_c[0]) * math.tan(math.radians(TILT))  # noqa: E731
    x_mb = 0.28 * L_n
    r_sh = 0.0075 * D
    bearing_h = K.cylinder(2.2 * r_sh, 0.05 * L_n, segments=48).rotate(0, 90, 0).translate(x_mb, 0, z_ax(x_mb))
    pedestal = K.box(0.05 * L_n, 3.6 * r_sh, z_ax(x_mb) - (z_bp + 0.12 * H_n)).translate(x_mb + 0.025 * L_n, 0, (z_ax(x_mb) + z_bp + 0.12 * H_n) / 2)
    b.add("bedplate", "Bệ máy + gối trục chính", "Bedplate & main bearing housing", "bedplate",
          [Shape(bed + rear_frame + pedestal, "cast_iron", 35.0), Shape(bearing_h, "cast_iron", 35.0)], parent_id="yaw_system", required=True,
          aliases=["bệ máy", "khung bệ", "gối trục", "ổ trục chính", "bedplate"], function="Bệ máy gang đúc trên ổ quay hướng, gối ổ trục chính.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=0.03 * D, explode_order=2)
    contacts.append(["bedplate", "yaw_system"])
    # trục chính: từ mặt bích moay-ơ tới hộp số
    x_gb0 = 0.02 * L_n
    x_hub_flange = hub_c[0] - 0.012 * D
    sh_len = x_hub_flange - x_gb0
    shaft = MC.orient(K.cylinder(r_sh, sh_len, segments=36), [x_gb0, 0, z_ax(x_gb0)], ax)
    flange = MC.orient(K.cylinder(2.0 * r_sh, 0.004 * D, segments=36), [x_hub_flange - 0.004 * D * ax[0], 0, z_ax(x_hub_flange) - 0.004 * D * ax[2]], ax)
    b.add("main_shaft", "Trục chính (trục chậm)", "Main shaft", "shaft", Shape(shaft + flange, "steel", 35.0), parent_id="bedplate", required=True,
          aliases=["trục chính", "trục chậm", "trục rotor", "main shaft"], function="Trục rèn nối moay-ơ với hộp số, đỡ bởi ổ trục chính.",
          position_tag="top", joint_axis=tuple(float(v) for v in ax), explode_dir=(1, 0, 0), explode_distance=0.03 * D, explode_order=2)
    # hộp số: cấp hành tinh (trụ) + cấp song song (hộp)
    gb_L = 0.2 * L_n
    x_gb1 = x_gb0 - gb_L
    ring_gb = MC.orient(K.cylinder(0.33 * W_n, 0.45 * gb_L, segments=48), [x_gb0 - 0.45 * gb_L, 0, z_ax(x_gb0)], ax)
    box_gb = K.rounded_box(0.55 * gb_L, 0.6 * W_n, 0.62 * W_n, 0.05 * W_n, segments=8).translate(x_gb1 + 0.275 * gb_L, 0, z_ax(x_gb0) - 0.04 * W_n)
    arms = K.Solid.union_all([K.box(0.15 * gb_L, 0.1 * W_n, z_ax(x_gb0) - (z_bp + 0.12 * H_n) + 0.0).translate(x_gb0 - 0.3 * gb_L, s * 0.25 * W_n,
                                                                                                                  (z_ax(x_gb0) + z_bp + 0.12 * H_n) / 2)
                              for s in (1, -1)])
    b.add("gearbox", "Hộp số (hành tinh + song song)", "Gearbox", "gearbox", [Shape(ring_gb + box_gb + arms, "paint_blue", 35.0)],
          parent_id="bedplate", required=True, aliases=["hộp số", "hộp tăng tốc", "gearbox"], function="Hộp tăng tốc 1 cấp hành tinh + 2 cấp song song, tỷ số ≈ 1:100.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=0.05 * D, explode_order=2)
    contacts.append(["main_shaft", "gearbox"])
    # khớp nối + máy phát + tủ biến tần
    z_hs = z_ax(x_gb0) - 0.18 * W_n
    x_gen1 = x_gb1 - 0.06 * L_n
    gen_L = 0.18 * L_n
    coup = K.cylinder(0.05 * W_n, x_gb1 - x_gen1 + 1.0, segments=24).rotate(0, 90, 0).translate(x_gen1 - 0.5, 0, z_hs)
    gen = K.cylinder(0.24 * W_n, gen_L, segments=48).rotate(0, 90, 0).translate(x_gen1 - gen_L, 0, z_hs)
    fins = K.Solid.union_all([K.box(gen_L * 0.9, 0.02 * W_n, 0.06 * W_n).translate(x_gen1 - gen_L / 2, 0, z_hs + 0.26 * W_n).rotate_axis((1, 0, 0), a, (0, 0, z_hs))
                              for a in np.arange(0, 360, 20.0)])
    gen_feet = K.box(gen_L * 0.8, 0.4 * W_n, z_hs - 0.24 * W_n - (z_bp + 0.05 * H_n) + 1.0).translate(x_gen1 - gen_L / 2, 0,
                                                                                                      (z_hs - 0.24 * W_n + z_bp + 0.05 * H_n) / 2)
    conv = K.rounded_box(0.12 * L_n, 0.25 * W_n, 0.5 * H_n, 0.02 * W_n, segments=6).translate(-0.44 * L_n, 0.28 * W_n, z_bp + 0.05 * H_n + 0.25 * H_n)
    b.add("generator", "Máy phát + khớp nối + tủ biến tần", "Generator & converter", "generator",
          [Shape(gen + fins + gen_feet, "paint_blue", 35.0), Shape(coup, "steel", 35.0), Shape(conv, "paint_secondary", 35.0)], parent_id="bedplate",
          required=True, aliases=["máy phát", "máy phát điện", "khớp nối", "biến tần", "generator"],
          function="Máy phát không đồng bộ nguồn kép 2 MW, khớp nối mềm, tủ biến tần.", position_tag="rear",
          explode_dir=(-1, 0, 0.5), explode_distance=0.05 * D, explode_order=2)
    contacts += [["generator", "gearbox"]]
    # ---------- vỏ nacelle ----------
    x_n0, x_n1 = -0.62 * L_n, 0.38 * L_n
    z_n0 = z_bp - 0.02 * H_n
    outer = K.rounded_box(x_n1 - x_n0, W_n, H_n, 0.12 * H_n, segments=16).translate((x_n0 + x_n1) / 2, 0, z_n0 + H_n / 2)
    tcov = 0.012 * H_n + 20.0
    inner = K.rounded_box(x_n1 - x_n0 - 2 * tcov, W_n - 2 * tcov, H_n - 2 * tcov, 0.1 * H_n, segments=16).translate((x_n0 + x_n1) / 2, 0, z_n0 + H_n / 2)
    shell = outer - inner
    shell = shell - K.cylinder(Dt / 2 + 80.0, 3 * H_n, segments=64).translate(0, 0, z_n0 - H_n)          # lỗ sàn cho ổ quay hướng
    shell = shell - MC.orient(K.cylinder(2.6 * r_sh, 0.2 * L_n, segments=36), [x_n1 - 0.1 * L_n, 0, z_ax(x_n1 - 0.1 * L_n)], ax)   # lỗ trục ra moay-ơ
    z_lid = z_n0 + 0.72 * H_n
    lid = shell & K.box(3 * L_n, 3 * W_n, H_n).translate(0, 0, z_lid + H_n / 2)
    body = shell - K.box(3 * L_n, 3 * W_n, H_n).translate(0, 0, z_lid + H_n / 2)
    cooler = K.rounded_box(0.14 * L_n, 0.7 * W_n, 0.12 * H_n, 0.02 * W_n, segments=6).translate(x_n0 + 0.12 * L_n, 0, z_n0 + H_n + 0.06 * H_n - 1.0)
    mast = K.cylinder(0.006 * D, 0.2 * H_n, segments=12).translate(x_n0 + 0.3 * L_n, 0, z_n0 + H_n - 1.0)
    vane = K.box(0.03 * L_n, 0.004 * D, 0.03 * H_n).translate(x_n0 + 0.29 * L_n, 0, z_n0 + 1.2 * H_n) + K.sphere(0.008 * D, segments=12).translate(
        x_n0 + 0.31 * L_n, 0, z_n0 + 1.2 * H_n + 0.04 * H_n)
    roof_items = cooler + mast + vane
    if open_:
        hinge = np.array([x_n0 + tcov, 0.0, z_lid])
        lid = lid.rotate_axis((0, 1, 0), -65.0, hinge)
        roof_items = roof_items.rotate_axis((0, 1, 0), -65.0, hinge)
    b.add("nacelle_cover", "Vỏ nacelle (thân + nắp)", "Nacelle cover", "nacelle",
          [Shape(body, "gfrp", 35.0), Shape(lid, "gfrp", 35.0), Shape(roof_items, "paint_secondary", 35.0)], parent_id="bedplate", required=True,
          aliases=["vỏ máy", "nacelle", "buồng máy", "nắp nacelle", "phong kế", "cột đo gió"],
          function="Vỏ composite; nắp mở bằng bản lề sau để bảo trì" + (" (đang mở)" if open_ else "") + "; bộ làm mát, cột đo gió trên nóc.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=0.08 * D, explode_order=1, dimensions={"length": L_n, "width": W_n, "height": H_n})
    contacts += [["nacelle_cover", "yaw_system"], ["nacelle_cover", "main_shaft"], ["nacelle_cover", "generator"]]
    # ---------- rotor ----------
    hub_r = 0.03 * D
    hub = K.sphere(hub_r, segments=48).translate(*hub_c)
    root_d = 0.021 * D
    azimuths = [360.0 * i / nb for i in range(nb)]
    spinner = K.revolve([(0.0, 0.0), (1.12 * hub_r, 0.0)] + [(1.12 * hub_r * math.cos(t) ** 0.6, 1.5 * hub_r * math.sin(t)) for t in np.linspace(0.05, math.pi / 2, 10)],
                        segments=64)
    spinner = spinner - K.revolve([(0.0, -1.0), (1.08 * hub_r, -1.0)] + [(1.08 * hub_r * math.cos(t) ** 0.6, 1.46 * hub_r * math.sin(t)) for t in np.linspace(0.05, math.pi / 2, 10)],
                                  segments=64)
    spinner = MC.orient(spinner, hub_c + ax * 0.1 * hub_r, ax)
    r_root = hub_r * 0.92
    blade0, table = blade_solid(R, root_d, R / math.cos(math.radians(CONE)) - r_root)
    rot_axis = np.array([1.0, 0, 0])
    blades = []
    for az in azimuths:
        bl = blade0.translate(0, 0, r_root)                           # gốc cánh cách tâm moay-ơ
        ring = K.cylinder(root_d / 2 + 120.0, 250.0, segments=48).translate(0, 0, r_root - 250.0)
        cut = K.cylinder(root_d / 2 + 125.0, 3 * hub_r, segments=48).translate(0, 0, r_root - 250.0)
        # côn (nghiêng về phía trước ngược gió = −? rotor đón gió ở +X → cánh nghiêng về +X)
        bl = bl.rotate(0, CONE, 0)
        ring = ring.rotate(0, CONE, 0)
        cut = cut.rotate(0, CONE, 0)
        # phương vị quanh trục rotor (X), rồi ngẩng TILT quanh Y, dời về tâm moay-ơ
        tr = lambda s_: s_.rotate_axis(rot_axis, az).rotate(0, -TILT, 0).translate(*hub_c)   # noqa: E731
        blades.append((tr(bl), tr(ring), tr(cut)))
    hub_cut = K.Solid.union_all([c for _b, _r, c in blades])
    b.add("hub", "Moay-ơ + ổ đổi bước (pitch)", "Hub & pitch bearings", "hub",
          [Shape(hub - hub_cut + K.Solid.union_all([r for _b, r, _c in blades]), "cast_iron", 35.0)], parent_id="main_shaft", required=True,
          aliases=["moay-ơ", "hub", "ổ đổi bước", "pitch", "đầu rotor"], function=f"Moay-ơ gang cầu đúc, {nb} ổ đổi bước cánh (pitch) điện.",
          position_tag="front", joint_axis=tuple(float(v) for v in ax), explode_dir=(1, 0, 0), explode_distance=0.06 * D, explode_order=2)
    b.add("spinner", "Chóp mũi (spinner)", "Spinner", "spinner", Shape(spinner, "gfrp", 35.0), parent_id="hub", required=True,
          aliases=["chóp mũi", "spinner", "mũi rotor"], function="Chóp composite che moay-ơ.", position_tag="front",
          explode_dir=(1, 0, 0), explode_distance=0.05 * D, explode_order=1)
    for i, (bl, _r, _c) in enumerate(blades):
        az = azimuths[i]
        dv = np.array([0.0, -math.sin(math.radians(az)), math.cos(math.radians(az))])
        b.add(f"blade_{i + 1}", f"Cánh {i + 1}", "Rotor blade", "blade", Shape(bl, "gfrp", 35.0), parent_id="hub", required=True,
              aliases=["cánh", "cánh quạt", "cánh tuabin", "blade", f"cánh {i + 1}"],
              function=f"Cánh composite dài {R - r_root:.0f} mm, mặt cắt NACA 44xx, xoắn 13° → 0°, dây cung lớn nhất {0.078 * R:.0f} mm.",
              position_tag="top" if i == 0 else "side", joint_axis=tuple(float(v) for v in dv), explode_dir=tuple(float(v) for v in dv),
              explode_distance=0.08 * D, explode_order=1, dimensions={"length": R - r_root})
    contacts += [["blade_*", "spinner"]]
    b.note_stage(1, "Tháo cánh, chóp mũi, nắp nacelle")
    b.note_stage(2, "Tháo moay-ơ, trục chính, hộp số, máy phát")
    b.note_stage(3, "Nhấc bệ máy khỏi ổ quay hướng")
    b.place_on_ground(center_xy=False)
    b.metadata.update({"rotor_diameter_mm": D, "hub_height_mm": Hh, "blades": nb, "tilt_deg": TILT, "cone_deg": CONE, "tower_base_d_mm": Db,
                       "tower_top_d_mm": Dt, "blade_table": table, "root_d_mm": root_d, "hub_center": hub_c.tolist(), "rotor_axis": ax.tolist(),
                       "nacelle_open": open_, "blade_root_r_mm": r_root, "blade_span_mm": R / math.cos(math.radians(CONE)) - r_root,
                       "standard": "Tỷ lệ Vestas V90-2 MW (IEC 61400-1 cấp IIA); cánh NACA 44xx xoắn; chưa tính tải/ổn định",
                       "strict_overlap": True, "contacts": contacts})
    return b.build()
