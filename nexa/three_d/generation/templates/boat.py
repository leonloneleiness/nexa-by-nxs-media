"""Thuyền/tàu: ca nô cao tốc (bàn lái giữa + kính chắn gió), tàu cá (buồng lái + cột đèn), du thuyền (cabin thuôn +
sàn tắm sau), tàu tuần tra (cabin + cột radar). Máy gắn ngoài (1–3 máy) hoặc máy trong + trục + chân vịt + bánh lái.

Thân tàu = loft các mặt cắt ngang đáy chữ V: góc nghiêng đáy (deadrise) giảm dần về đuôi, mép gãy (chine) có gờ
chống bắn nước, mạn loe ra ở mũi, đường sống lưng (sheer) cong lên phía mũi, mũi nhọn cong lên (rocker). Tỷ lệ theo
loại tàu thật (beam/L ≈ 0,30–0,34). Đáy tàu tại z = 0 (ki tàu), mũi hướng +X.

Tách: boong và cabin nhấc lên, kính/lan can nhấc lên, máy + chân vịt kéo ra sau, bánh lái hạ xuống sau.
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import components as C
from nexa.three_d.generation.templates import details as D
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec

# beam/L, chiều cao mạn/L, deadrise ở giữa tàu (độ), kiểu thượng tầng, tên
TYPES = {
    "speedboat": (0.33, 0.13, 22.0, "console", "Ca nô cao tốc"),
    "fishing": (0.34, 0.16, 15.0, "wheelhouse", "Tàu cá"),
    "yacht": (0.30, 0.15, 18.0, "cabin", "Du thuyền"),
    "patrol": (0.31, 0.155, 20.0, "cabin", "Tàu tuần tra"),
}
N_STATIONS = 30
RING = 56


def _station(t: float, L: float, B: float, Dp: float, dr_deg: float) -> tuple[float, float, float, float]:
    """(nửa bề rộng, cao độ ki, cao độ mạn, deadrise) tại vị trí t ∈ [0 đuôi, 1 mũi]."""
    if t <= 0.5:
        hb = B / 2 * (0.93 + 0.07 * t / 0.5)                      # đuôi (transom) hẹp nhẹ
    else:
        u = (t - 0.5) / 0.5
        hb = B / 2 * max(0.0, 1 - u ** 2.1) ** 0.62                # thuôn dần tới mũi
    zk = Dp * 0.62 * max(0.0, (t - 0.62) / 0.38) ** 2.2            # mũi cong lên (rocker)
    zs = Dp * (1.0 + 0.2 * t ** 2.2)                               # đường mạn cao dần về mũi
    dr = math.radians(dr_deg * (0.75 + 0.9 * t ** 1.5))           # đáy V sâu hơn ở mũi (cắt sóng)
    return hb, zk, zs, dr


def _section(x: float, hb: float, zk: float, zs: float, dr: float) -> np.ndarray:
    """Mặt cắt kín (điểm 3D) tại x: ki → mép gãy (có gờ) → mạn loe → boong phẳng → đối xứng."""
    if hb < 1e-3:
        return np.repeat([[x, 0.0, zs]], RING, axis=0)
    yc = 0.82 * hb
    zc = min(zk + yc * math.tan(dr), zk + 0.8 * (zs - zk))
    half = [(0.0, zk), (yc * 0.55, zk + yc * 0.55 * math.tan(dr) * 0.97), (yc, zc), (yc * 1.04, zc + 0.012 * hb),
            (hb * 0.97, zc + (zs - zc) * 0.45), (hb, zs)]
    poly = half + [(-y, z) for y, z in reversed(half[1:])]
    pts = P.resample_closed(np.asarray(poly, float), RING)
    return np.column_stack([np.full(RING, x), pts[:, 0], pts[:, 1]])


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    kind = p.get("boat_type", "speedboat")
    beam_r, depth_r, dr_deg, sup, name = TYPES.get(kind, TYPES["speedboat"])
    L = float(p.get("length_mm", 6500))
    B, Dp = beam_r * L, depth_r * L
    n_eng = int(p.get("engines", 1))
    # bỏ trống → theo loại tàu thật: ca nô máy ngoài; tàu cá / tuần tra / du thuyền máy trong + chân vịt
    inboard = (p.get("propulsion") or ("outboard" if kind == "speedboat" else "inboard")) == "inboard"
    style = spec.style or {}
    primary = M.color_from_name(style.get("primary_color"), "#f4f6f8" if kind != "patrol" else "#dfe3e8")
    secondary = M.color_from_name(style.get("secondary_color"), {"patrol": "#1d3557", "fishing": "#2a6f97"}.get(kind, "#1d3557"))
    accent = M.color_from_name(style.get("accent_color"), "#e63946" if kind == "patrol" else "#f4a261")
    mats = M.object_library(primary, secondary, accent)
    mats["antifouling"] = M.material("antifouling", "paint", "#7a1f1f", 0.0, 0.7, name="Sơn chống hà (đáy tàu)")
    mats["teak"] = M.material("teak", "wood", "#a0703f", 0.0, 0.62, name="Gỗ tếch boong")
    M.apply_micro_textures(mats)
    mats["antifouling"].textures["normal"] = "textures/paint_normal.png"
    b = AssemblyBuilder(spec.name or name, "boat", mats)
    x0 = -L / 2                                                    # đuôi (transom)

    # ---------- thân tàu ----------
    ts = np.linspace(0, 1, N_STATIONS)
    geo = [_station(t, L, B, Dp, dr_deg) for t in ts]
    secs = [_section(x0 + t * L, *g) for t, g in zip(ts, geo)]
    hull_solid = K.loft(secs)
    deck_t = 0.012 * L
    deck_layer = hull_solid - hull_solid.translate(0, 0, -deck_t)  # lớp trên cùng dày deck_t bám theo đường mạn
    body = hull_solid - deck_layer
    # buồng lái hở (cockpit) cho ca nô / tàu cá: giếng sàn thấp hơn mạn
    well = None
    if kind in ("speedboat", "fishing"):
        well = K.rounded_box(0.42 * L, B * 0.74, Dp * 0.9, 0.04 * L).translate(x0 + 0.3 * L, 0, Dp * 0.55 + Dp * 0.45)
        body = body - well
        deck_layer = deck_layer - well
    # đường nước: dải sơn trang trí + sơn chống hà dưới nước
    wl = Dp * 0.36
    anti = body & K.box(L * 1.2, B * 1.5, wl).translate(0, 0, wl / 2 - 0.001 * L)
    boot = body & K.box(L * 1.2, B * 1.5, 0.018 * L).translate(0, 0, wl + 0.009 * L)
    topside = body - K.box(L * 1.2, B * 1.5, wl + 0.018 * L).translate(0, 0, (wl + 0.018 * L) / 2 - 0.001 * L)
    # gờ bảo vệ mạn (rub rail) dọc đường mạn hai bên
    rails = []
    for side in (1, -1):
        pts = [(x0 + t * L, side * (g[0] + 0.004 * L), g[2] - 0.01 * L) for t, g in zip(ts, geo) if 0.02 <= t <= 0.97]
        rails.append(K.tube(P.spline_through(np.asarray(pts), 80), 0.0065 * L, 14, rounded_ends=True))
    # tên/số đăng ký ở mũi hai bên
    bow_t = 0.8
    hb_b, _, zs_b, _ = _station(bow_t, L, B, Dp, dr_deg)
    plates = [D.label_plate(0.1 * L, 0.025 * L, 0.002 * L).rotate(0, 0, 90 * side).translate(x0 + bow_t * L, side * (hb_b * 0.96),
                                                                                           zs_b * 0.72)
              for side in (1, -1)]
    b.add("hull", "Thân tàu", "Hull", "hull",
          [Shape(topside, "paint_primary", 35.0), Shape(boot, "paint_secondary", 35.0), Shape(anti, "antifouling", 35.0),
           Shape(K.Solid.union_all(rails), "rubber" if kind != "yacht" else "stainless", 40.0),
           Shape(K.Solid.union_all(plates), "paint_secondary", 40.0)], required=True,
          aliases=["thân tàu", "thân thuyền", "vỏ tàu", "hull", "mạn tàu", "đáy tàu", "thân"],
          function="Thân tàu đáy chữ V tạo lực nổi và rẽ sóng; mép gãy có gờ chống bắn nước.", position_tag="center",
          dimensions={"length": round(L, 0), "beam": round(B, 0), "depth": round(Dp, 0)})
    b.add("deck", "Boong tàu", "Deck", "deck", Shape(deck_layer, "teak" if kind == "yacht" else "paint_primary", 35.0),
          parent_id="hull", required=True, aliases=["boong", "sàn tàu", "mặt boong", "deck"],
          function="Mặt boong chịu lực đi lại, kín nước phía trên thân tàu.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=0.12 * Dp + 0.05 * L, explode_order=1)

    z_deck = Dp * 1.02                                              # mặt boong giữa tàu
    z_floor = Dp * 0.55 if well is not None else z_deck             # sàn buồng lái hở (đáy giếng)
    # ---------- thượng tầng ----------
    if p.get("cabin", True):
        if sup == "console":                                        # bàn lái giữa + kính chắn gió cong
            cx = x0 + 0.46 * L
            con = K.rounded_box(0.13 * L, B * 0.36, Dp * 0.95, 0.02 * L).translate(cx, 0, z_floor + Dp * 0.47)
            dash = K.rounded_box(0.06 * L, B * 0.34, 0.02 * L, 0.006 * L).rotate(0, -25, 0).translate(cx + 0.03 * L, 0,
                                                                                                    z_floor + Dp * 0.97)
            wheel = K.torus(0.022 * L, 0.0028 * L, segments=40, tube_segments=10).rotate(0, 60, 0).translate(cx - 0.045 * L, 0.04 * L,
                                                                                                           z_floor + Dp * 0.9)
            glass = K.hull([K.box(0.004 * L, B * 0.4, 0.004 * L).translate(cx + 0.06 * L, 0, z_floor + Dp * 0.95),
                            K.box(0.004 * L, B * 0.36, 0.004 * L).translate(cx + 0.02 * L, 0, z_floor + Dp * 0.95 + 0.07 * L)])
            glass = K.hull([glass, glass.translate(-0.002 * L, 0, 0)])
            b.add("cabin", "Bàn lái", "Center console", "cabin",
                  [Shape(con, "paint_primary", 40.0), Shape(dash, "plastic_black", 40.0), Shape(wheel, "stainless", 40.0)],
                  parent_id="hull", required=True, aliases=["bàn lái", "buồng lái", "console", "tay lái", "vô lăng", "cabin"],
                  function="Bàn điều khiển: vô lăng, cần ga, màn hình định vị/sonar.", position_tag="center",
                  explode_dir=(0, 0, 1), explode_distance=0.35 * Dp, explode_order=2)
            b.add("windshield", "Kính chắn gió", "Windshield", "windshield", Shape(glass, "glass", 40.0), parent_id="cabin",
                  aliases=["kính chắn gió", "kính", "windshield"], function="Chắn gió và nước bắn cho người lái.",
                  position_tag="front", explode_dir=(0.3, 0, 1), explode_distance=0.25 * Dp, explode_order=3)
            seats = K.Solid.union_all([
                K.rounded_box(0.05 * L, 0.06 * L, 0.03 * L, 0.01 * L).translate(cx - 0.11 * L, s_ * 0.05 * L, z_floor + Dp * 0.32) +
                K.rounded_box(0.015 * L, 0.06 * L, 0.07 * L, 0.006 * L).translate(cx - 0.135 * L, s_ * 0.05 * L, z_floor + Dp * 0.55)
                for s_ in (1, -1)])
            posts = K.Solid.union_all([K.cylinder(0.008 * L, Dp * 0.3, segments=16).translate(cx - 0.11 * L, s_ * 0.05 * L, z_floor)
                                       for s_ in (1, -1)])
            b.add("seats", "Ghế lái", "Helm seats", "seat", [Shape(seats, "leather", 40.0), Shape(posts, "stainless", 40.0)],
                  parent_id="hull", aliases=["ghế", "ghế lái", "seat"], function="Ghế lái có đệm chống sốc.",
                  position_tag="center", explode_dir=(0, 0, 1), explode_distance=0.3 * Dp, explode_order=2)
        else:                                                       # buồng lái / cabin kín có cửa sổ
            if sup == "wheelhouse":
                cx, cl, cw, ch = x0 + 0.62 * L, 0.2 * L, B * 0.56, Dp * 0.95
                cab = K.rounded_box(cl, cw, ch, 0.015 * L).translate(cx, 0, z_deck + ch / 2)
                roof = K.rounded_box(cl * 1.15, cw * 1.08, 0.015 * L, 0.006 * L).translate(cx - 0.01 * L, 0, z_deck + ch + 0.0075 * L)
            else:
                cx, cl, cw, ch = x0 + 0.5 * L, 0.38 * L, B * 0.66, Dp * 0.8
                csecs = []
                for t in np.linspace(0, 1, 16):
                    xx = cx - cl / 2 + t * cl
                    w_ = cw * (1 - 0.55 * max(0.0, (t - 0.55) / 0.45) ** 1.6)
                    h_ = ch * (1 - 0.45 * max(0.0, (t - 0.45) / 0.55) ** 1.4)
                    prof = P.superellipse(w_, 2 * h_, 3.2, 48)
                    csecs.append(np.column_stack([np.full(48, xx), prof[:, 0], z_deck - 0.01 * L + np.maximum(prof[:, 1], 0) +
                                                  np.minimum(prof[:, 1], 0) * 0.02]))
                cab = K.loft(csecs) & K.box(L, B * 2, Dp * 4).translate(cx, 0, z_deck - 0.01 * L + Dp * 2)
                roof = K.rounded_box(cl * 0.55, cw * 0.8, 0.012 * L, 0.005 * L).translate(cx - cl * 0.12, 0, z_deck + ch * 0.98)
            # cửa sổ (kính khói) cắt vào vách hai bên và phía trước
            wins = []
            for k in range(3):
                wx = cx - cl * 0.3 + k * cl * 0.25
                for side in (1, -1):
                    wy = D.surface_at(cab, "y", (wx, 0, z_deck + ch * 0.62), positive=side > 0)
                    if wy is not None:
                        wins.append(K.rounded_box(cl * 0.18, 0.02 * L, ch * 0.28, 0.006 * L).translate(wx, wy - side * 0.004 * L,
                                                                                                      z_deck + ch * 0.62))
            fx_ = D.surface_at(cab, "x", (0, 0, z_deck + ch * 0.62), positive=True)
            if fx_ is not None:
                wins.append(K.rounded_box(0.02 * L, cw * 0.62, ch * 0.3, 0.008 * L).translate(fx_ - 0.004 * L, 0, z_deck + ch * 0.62))
            win_s = K.Solid.union_all(wins) & cab
            cab = cab - win_s
            cab = cab - D.panel_lines(cab, [("z", z_deck + ch * 0.35)], width=0.0025 * L, depth=0.003 * L)
            b.add("cabin", "Cabin" if sup == "cabin" else "Buồng lái", "Cabin" if sup == "cabin" else "Wheelhouse", "cabin",
                  [Shape(cab, "paint_primary", 40.0), Shape(roof, "paint_secondary", 40.0), Shape(win_s, "glass_tinted", 40.0)],
                  parent_id="deck", required=True, aliases=["cabin", "buồng lái", "ca bin", "phòng lái", "thượng tầng", "wheelhouse"],
                  function="Buồng lái kín có kính quan sát; chứa bàn điều khiển và thiết bị hải đồ.", position_tag="center",
                  explode_dir=(0, 0, 1), explode_distance=0.45 * Dp, explode_order=2)
            # cột đèn / radar trên nóc
            z_roof = z_deck + ch + 0.015 * L
            mast_x = cx - cl * 0.1
            mast = K.cylinder(0.006 * L, 0.12 * L, segments=16).translate(mast_x, 0, z_roof - 0.005 * L)
            yard = K.tube(np.array([[mast_x, -0.05 * L, z_roof + 0.09 * L], [mast_x, 0.05 * L, z_roof + 0.09 * L]]), 0.004 * L, 12)
            top_light = K.sphere(0.008 * L, 16).translate(mast_x, 0, z_roof + 0.12 * L)
            mast_shapes = [Shape(mast + yard, "stainless", 40.0), Shape(top_light, "led_white", 40.0)]
            if kind in ("patrol", "yacht"):
                dome = K.revolve(P.fillet_polygon([(0, 0), (0.04 * L, 0), (0.04 * L, 0.02 * L), (0, 0.03 * L)],
                                                  [0, 0.004 * L, 0.012 * L, 0], 4), segments=48)
                mast_shapes.append(Shape(dome.translate(mast_x + 0.06 * L, 0, z_roof - 0.004 * L), "plastic_white", 40.0))
            if kind == "patrol":
                beacon = K.cylinder(0.012 * L, 0.01 * L, segments=24).translate(mast_x, 0.05 * L, z_roof + 0.094 * L)
                mast_shapes.append(Shape(beacon, "led_red", 40.0))
            b.add("mast", "Cột đèn / radar", "Mast & radar", "mast", mast_shapes, parent_id="cabin",
                  aliases=["cột", "cột đèn", "radar", "ăng ten", "mast"], function="Đèn hành trình, ăng-ten VHF và radar hàng hải.",
                  position_tag="top", explode_dir=(0, 0, 1), explode_distance=0.3 * Dp, explode_order=3)

    # ---------- lan can mũi ----------
    if p.get("railings", True):
        stn = []
        rail_pts = {1: [], -1: []}
        for t in np.linspace(0.6, 0.97, 7):
            hb, zk, zs, _ = _station(t, L, B, Dp, dr_deg)
            for side in (1, -1):
                y = side * max(hb - 0.02 * L, 0.004 * L)
                stn.append(K.cylinder(0.0035 * L, 0.07 * L, segments=12).translate(x0 + t * L, y, zs - 0.002 * L))
                rail_pts[side].append((x0 + t * L, y, zs + 0.068 * L))
        tip = (x0 + 0.99 * L, 0.0, _station(0.99, L, B, Dp, dr_deg)[2] + 0.068 * L)
        path = rail_pts[1] + [tip] + list(reversed(rail_pts[-1]))
        rail = K.tube(P.spline_through(np.asarray(path), 90), 0.0045 * L, 14, rounded_ends=True)
        b.add("railing", "Lan can mũi", "Bow rail", "railing", [Shape(K.Solid.union_all(stn) + rail, "stainless", 40.0)],
              parent_id="deck", required=True, aliases=["lan can", "tay vịn", "lan can mũi", "railing", "rail"],
              function="Lan can inox giữ an toàn khi đi lại trên mũi tàu.", position_tag="front",
              explode_dir=(0, 0, 1), explode_distance=0.2 * Dp, explode_order=2)

    # ---------- phụ kiện boong: cọc buộc dây, đèn hàng hải ----------
    fittings = []
    for t, y_frac in ((0.9, 0.5), (0.06, 0.8)):
        hb, _, zs, _ = _station(t, L, B, Dp, dr_deg)
        for side in (1, -1):
            base = K.rounded_box(0.018 * L, 0.006 * L, 0.006 * L, 0.002 * L)
            horn = K.hull([K.sphere(0.004 * L, 12).translate(-0.012 * L, 0, 0.008 * L), K.sphere(0.004 * L, 12).translate(0.012 * L, 0, 0.008 * L),
                           K.box(0.008 * L, 0.006 * L, 0.004 * L)])
            fittings.append((base + horn).translate(x0 + t * L, side * hb * y_frac, zs - 0.001 * L))
    hb_n, _, zs_n, _ = _station(0.84, L, B, Dp, dr_deg)
    nav_l = K.rounded_box(0.012 * L, 0.004 * L, 0.008 * L, 0.002 * L).translate(x0 + 0.84 * L, hb_n + 0.002 * L, zs_n - 0.006 * L)
    nav_r = K.rounded_box(0.012 * L, 0.004 * L, 0.008 * L, 0.002 * L).translate(x0 + 0.84 * L, -hb_n - 0.002 * L, zs_n - 0.006 * L)
    stern_pole = K.cylinder(0.003 * L, 0.06 * L, segments=12).translate(x0 + 0.03 * L, -B * 0.3, Dp * 0.98)
    stern_light = K.sphere(0.006 * L, 12).translate(x0 + 0.03 * L, -B * 0.3, Dp * 0.98 + 0.062 * L)
    b.add("fittings", "Cọc buộc dây & đèn hàng hải", "Cleats & navigation lights", "fitting",
          [Shape(K.Solid.union_all(fittings) + stern_pole, "stainless", 40.0), Shape(nav_l, "led_red", 40.0),
           Shape(nav_r, "led_green", 40.0), Shape(stern_light, "led_white", 40.0)], parent_id="deck",
          aliases=["cọc buộc dây", "đèn hàng hải", "đèn mạn", "cleat", "đèn"],
          function="Cọc buộc dây neo đậu; đèn mạn đỏ (trái) / xanh (phải) và đèn đuôi trắng theo quy tắc COLREG.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=0.15 * Dp, explode_order=2)

    # ---------- động lực ----------
    zs0 = _station(0.0, L, B, Dp, dr_deg)[2]
    if not inboard:
        ys = [0.0] if n_eng == 1 else list(np.linspace(-B * 0.22, B * 0.22, n_eng))
        for k, y in enumerate(ys):
            mid = f"outboard_{k + 1}"
            s_ = max(0.6, min(2.2, L / 6500))                       # cỡ máy theo cỡ tàu
            cowl = K.hull([K.ellipsoid(0.07 * L / s_ ** 0.3 * 0.6, 0.045 * L / s_ ** 0.3 * 0.6, 0.06 * L / s_ ** 0.3 * 0.6)])
            cowl = cowl.translate(x0 - 0.05 * L, y, zs0 + 0.045 * L)
            leg = K.hull([K.box(0.03 * L, 0.018 * L, 0.004 * L).translate(x0 - 0.045 * L, y, zs0),
                          K.box(0.02 * L, 0.012 * L, 0.004 * L).translate(x0 - 0.05 * L, y, 0.012 * L)])
            plate = K.rounded_box(0.05 * L, 0.03 * L, 0.003 * L, 0.004 * L).translate(x0 - 0.055 * L, y, 0.03 * L)
            gear = K.capsule(0.009 * L, 0.06 * L).rotate(0, 90, 0).translate(x0 - 0.055 * L, y, 0.012 * L)
            skeg = K.hull([K.box(0.02 * L, 0.003 * L, 0.002 * L).translate(x0 - 0.055 * L, y, 0.006 * L),
                           K.box(0.008 * L, 0.002 * L, 0.002 * L).translate(x0 - 0.06 * L, y, -0.012 * L)])
            clamp = K.rounded_box(0.012 * L, 0.03 * L, 0.03 * L, 0.004 * L).translate(x0 - 0.005 * L, y, zs0 - 0.012 * L)
            decal = K.box(0.004 * L, 0.03 * L, 0.012 * L).translate(x0 - 0.05 * L + 0.07 * L / s_ ** 0.3 * 0.6 - 0.002 * L, y,
                                                                   zs0 + 0.05 * L) & cowl.translate(0.001 * L, 0, 0)
            b.add(mid, f"Máy gắn ngoài {k + 1}", f"Outboard engine {k + 1}", "motor",
                  [Shape(cowl, "paint_secondary", 40.0), Shape(leg + plate + gear + skeg, "aluminum_dark", 40.0),
                   Shape(clamp, "stainless", 40.0), Shape(decal, "paint_accent", 40.0)], parent_id="hull", required=True,
                  aliases=["máy", "máy gắn ngoài", "động cơ", "outboard", "máy đuôi tôm"],
                  function="Động cơ xăng gắn ngoài: nắp máy, trục đứng, hộp số chìm và tấm chống xoáy.", position_tag="rear",
                  explode_dir=(-1, 0, 0.2), explode_distance=0.08 * L, explode_order=2)
            prop = C.propeller(0.05 * L, 3, material="stainless")
            b.add(f"propeller_{k + 1}", f"Chân vịt {k + 1}", f"Propeller {k + 1}", "propeller",
                  [Shape(sh.solid.rotate(0, -90, 0).translate(x0 - 0.087 * L, y, 0.012 * L), sh.material, 50.0) for sh in prop],
                  parent_id=mid, required=True, aliases=["chân vịt", "cánh quạt", "propeller", "chong chóng"],
                  function="Chân vịt inox 3 lá tạo lực đẩy.", position_tag="rear",
                  explode_dir=(-1, 0, 0), explode_distance=0.06 * L, explode_order=3)
    else:
        ys = [0.0] if n_eng == 1 else list(np.linspace(-B * 0.18, B * 0.18, n_eng))
        z_p = -0.04 * L                                  # chân vịt nằm hẳn dưới đáy tàu (không xuyên thân)
        for k, y in enumerate(ys):
            shaft = K.tube(np.array([[x0 + 0.18 * L, y, 0.045 * L], [x0 + 0.05 * L, y, z_p]]), 0.004 * L, 14)
            strut = K.hull([K.box(0.012 * L, 0.004 * L, 0.002 * L).translate(x0 + 0.07 * L, y, 0.035 * L),
                            K.box(0.008 * L, 0.003 * L, 0.002 * L).translate(x0 + 0.07 * L, y, z_p + 0.006 * L)])
            b.add(f"shaft_{k + 1}", f"Trục chân vịt {k + 1}", f"Prop shaft {k + 1}", "motor",
                  [Shape(shaft + strut, "stainless", 40.0)], parent_id="hull", required=True,
                  aliases=["trục", "trục chân vịt", "shaft", "máy trong"], function="Trục truyền từ máy trong ra chân vịt.",
                  position_tag="rear", explode_dir=(0, 0, -1), explode_distance=0.05 * L, explode_order=3)
            prop = C.propeller(0.07 * L, 4, material="brass")
            b.add(f"propeller_{k + 1}", f"Chân vịt {k + 1}", f"Propeller {k + 1}", "propeller",
                  [Shape(sh.solid.rotate(0, -90, 0).translate(x0 + 0.045 * L, y, z_p), sh.material, 50.0) for sh in prop],
                  parent_id=f"shaft_{k + 1}", required=True, aliases=["chân vịt", "cánh quạt", "propeller"],
                  function="Chân vịt đồng 4 lá.", position_tag="rear", explode_dir=(-1, 0, -0.2),
                  explode_distance=0.06 * L, explode_order=3)
        rudders = []
        for y in (ys if n_eng > 1 else [0.0]):
            foil = P.naca4("0012", 0.06 * L, 32)
            r_ = K.extrude(foil, 0.075 * L).translate(-0.03 * L, 0, 0)
            r_ = r_.translate(x0 - 0.012 * L, y, -0.075 * L)          # sau chân vịt ~0,02L, dưới đuôi tàu
            stock = K.cylinder(0.003 * L, 0.05 * L, segments=12).translate(x0 - 0.012 * L, y, -0.002 * L)
            rudders.append(r_ + stock)
        b.add("rudder", "Bánh lái", "Rudder", "rudder", [Shape(K.Solid.union_all(rudders), "stainless", 40.0)], parent_id="hull",
              required=True, aliases=["bánh lái", "lái", "rudder"], function="Bánh lái profile NACA đổi hướng dòng nước sau chân vịt.",
              position_tag="rear", explode_dir=(-0.3, 0, -1), explode_distance=0.06 * L, explode_order=3)
    if kind == "yacht":
        swim = K.rounded_box(0.07 * L, B * 0.8, 0.012 * L, 0.004 * L).translate(x0 - 0.03 * L, 0, Dp * 0.42)
        b.add("swim_platform", "Sàn tắm sau", "Swim platform", "deck", [Shape(swim, "teak", 40.0)], parent_id="hull",
              aliases=["sàn tắm", "bậc sau", "swim platform"], function="Sàn sau lái để lên xuống nước.",
              position_tag="rear", explode_dir=(-1, 0, 0), explode_distance=0.05 * L, explode_order=2)
    b.note_stage(1, "Nhấc boong")
    b.note_stage(2, "Nhấc cabin/bàn lái, lan can, phụ kiện; kéo máy ra sau")
    b.note_stage(3, "Tháo chân vịt, trục, bánh lái, cột đèn/radar")
    b.metadata.update({"boat_type": kind, "length_mm": L, "beam_mm": B, "depth_mm": Dp, "ground_z_mm": 0.0,
                       "propulsion": "inboard" if inboard else "outboard", "engines": n_eng})
    return b.build()
