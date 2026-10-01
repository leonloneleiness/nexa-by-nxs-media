"""Xe cẩu (cần trục ô tô cần ống lồng) 25 t: xe cơ sở 2–4 trục, 4 chân chống có đế, bàn quay + cabin điều khiển,
đối trọng, tời, cần ống lồng 4–6 đoạn (tự thêm đoạn khi cần dài), xi lanh nâng cần, cáp tời + móc cẩu.

- Chiều dài cần = chốt chân cần → tâm puly đầu cần; các đoạn ống lồng rỗng lồng nhau có tấm trượt, đoạn chồng ≥ 1 m.
- Xi lanh nâng cần: vỏ cố định tính theo dải góc 0–80° (đóng hết ở 0°, đủ hành trình tới 80°), mắt ôm đúng chốt.
- Cáp tời: từ tang tời qua puly dẫn trên lưng cần tới puly đầu cần, hai nhánh thả thẳng đứng xuống cụm móc.
- Chân chống duỗi ngang (khẩu độ 6,2 m) + xi lanh chân + đế tì đất; bánh vẫn chạm đất.
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import components as C
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec

TIRE_D, TIRE_W = 1072.0, 385.0                                         # 385/65R22.5: 22,5 × 25,4 + 2 × 385 × 0,65


def box_at(x0, x1, y0, y1, z0, z1) -> K.Solid:
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    z0, z1 = sorted((z0, z1))
    return K.box(x1 - x0, y1 - y0, z1 - z0).translate((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)


def plan_sections(L: float) -> tuple[float, int, float, list[float]]:
    """(chiều dài đoạn gốc, số đoạn, độ ra mỗi đoạn e, chiều dài từng đoạn) sao cho đoạn chồng ≥ 1000 mm."""
    for Lb0 in (8400.0, 10500.0):
        for n in (4, 5, 6):
            Ls = [Lb0 - 300.0 * i for i in range(n)]
            const = -500.0 + 400.0 * (n - 1) + Ls[-1] + 300.0
            e = (L - const) / (n - 1)
            if e < 0:
                e = 0.0
            if all(Ls[i - 1] - 400.0 - e >= 1000.0 for i in range(1, n)):
                return Lb0, n, e, Ls
    raise ValueError("cần quá dài cho cấu hình ống lồng")


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    Lboom = float(p.get("boom_length_mm", 18000.0))
    ang = float(p.get("boom_angle_deg", 45.0))
    n_ax = int(p.get("axles", 3))
    mats = MC.tech_materials(spec, primary="#f2b705", secondary="#1b1d21", accent="#e63946")
    b = AssemblyBuilder(spec.name or "Xe cẩu ống lồng 25 tấn", "crane", mats)
    R = TIRE_D / 2
    contacts: list[list[str]] = []
    links, ram_info = [], {}
    # ---------- xe cơ sở ----------
    L_car = 7800.0 + 1400.0 * (n_ax - 2)
    xf0 = L_car / 2 - 1500.0
    fronts = [xf0] if n_ax < 4 else [xf0, xf0 - 1450.0]
    xr0 = -L_car / 2 + 1700.0
    rears = [xr0] if n_ax == 2 else [xr0, xr0 + 1450.0]
    axles_x = fronts + rears
    W = 2550.0
    z_fr0, z_fr1 = R + 150.0, R + 550.0                                # khung dọc
    z_deck = z_fr1 + 350.0
    rails = K.Solid.union_all([box_at(-L_car / 2, L_car / 2 - 300.0, sy * 350.0, sy * 650.0, z_fr0, z_fr1) for sy in (1, -1)])
    x_cab0 = L_car / 2 - 2300.0
    deck = box_at(-L_car / 2, x_cab0 - 100.0, -W / 2, W / 2, z_fr1, z_deck)
    wells = K.Solid.union_all([K.cylinder(R + 60.0, W + 20.0, segments=48).rotate(90, 0, 0).translate(x, W / 2 + 10.0, R) for x in axles_x])
    deck = deck - wells
    fend = K.Solid.union_all([(K.cylinder(R + 90.0, TIRE_W + 120.0, segments=48) - K.cylinder(R + 60.0, TIRE_W + 140.0, segments=48).translate(0, 0, -10.0))
                              .rotate(90, 0, 0).translate(x, sy * (W / 2 - TIRE_W / 2 - 60.0) + (TIRE_W + 120.0) / 2, R) & box_at(x - R - 200, x + R + 200, -W, W, R + 100.0, R + 800.0)
                              for x in axles_x for sy in (1, -1)])
    axle_s = K.Solid.union_all([K.cylinder(90.0, W - 2 * TIRE_W + 200.0, segments=20).rotate(90, 0, 0).translate(x, (W - 2 * TIRE_W + 200.0) / 2, R) for x in axles_x])
    hangers = K.Solid.union_all([box_at(x - 150.0, x + 150.0, sy * 350.0, sy * 650.0, R + 60.0, z_fr0 + 5.0) for x in axles_x for sy in (1, -1)])
    cab = K.rounded_box(1800.0, 1100.0, 1150.0, 120.0, segments=10).translate(x_cab0 + 1000.0, 650.0, z_fr1 + 575.0)
    cab = cab & box_at(x_cab0, L_car / 2 + 100.0, 0, W, z_fr1, 2400.0)
    cab_glass = (box_at(x_cab0 + 1850.0, x_cab0 + 2000.0, 250.0, 1050.0, z_fr1 + 650.0, z_fr1 + 1050.0) & cab) - cab.translate(-8.0, 0, 0)
    cab_rec = box_at(x_cab0 + 1850.0, x_cab0 + 2000.0, 250.0, 1050.0, z_fr1 + 650.0, z_fr1 + 1050.0) - cab.translate(-30.0, 0, 0)
    engine_box = box_at(x_cab0 + 100.0, x_cab0 + 1500.0, -1150.0, -150.0, z_fr1, z_fr1 + 900.0)
    b.add("carrier", f"Xe cơ sở {n_ax} trục", "Crane carrier", "carrier",
          [Shape(rails + deck + fend + engine_box, "paint_primary", 40.0), Shape(cab - cab_rec, "paint_primary", 40.0), Shape(cab_glass, "glass_tinted", 40.0),
           Shape(axle_s + hangers, "steel_dark", 40.0)], required=True,
          aliases=["xe cơ sở", "khung xe", "cabin lái xe", "sát xi", "carrier", "cầu xe"],
          function=f"Xe cơ sở {n_ax} trục: khung dọc thép, cabin lái thấp bên trái, khoang động cơ, chắn bùn.", position_tag="center",
          dimensions={"length": L_car, "width": W})
    ts, rs = C.wheel(TIRE_D, TIRE_W, spokes=10, tread=True)
    t0, r0 = K.Solid.union_all([q.solid for q in ts]), K.Solid.union_all([q.solid for q in rs])
    for i, x in enumerate(axles_x):
        for side, sy in (("left", 1), ("right", -1)):
            t_, r_ = t0, r0
            if sy < 0:
                t_, r_ = t_.mirror((0, 1, 0)), r_.mirror((0, 1, 0))
            yw = sy * (W / 2 - TIRE_W / 2 - 60.0)
            b.add(f"wheel_{i + 1}_{side}", f"Bánh trục {i + 1} {'trái' if sy > 0 else 'phải'}", "Wheel", "wheel",
                  [Shape(t_.translate(x, yw, R), "rubber", 40.0), Shape(r_.translate(x, yw, R), "steel", 40.0)], parent_id="carrier", required=True,
                  aliases=["bánh xe", "lốp", "wheel", f"bánh trục {i + 1}"], function=f"Lốp 385/65R22.5 (Ø{TIRE_D:.0f} mm).",
                  position_tag="left" if sy > 0 else "right", joint_axis=(0, 1, 0), explode_dir=(0, sy, 0), explode_distance=500.0, explode_order=1)
    # chân chống
    span = 6200.0
    for pos, xo in (("front", min(fronts) - R - 450.0), ("rear", -L_car / 2 + 450.0)):
        for side, sy in (("left", 1), ("right", -1)):
            beam = box_at(xo - 180.0, xo + 180.0, sy * 300.0, sy * (span / 2 + 150.0), z_fr0 + 20.0, z_fr0 + 330.0)
            box_o = box_at(xo - 230.0, xo + 230.0, sy * 300.0, sy * (W / 2 - 10.0), z_fr0 - 20.0, z_fr0 + 380.0)
            jack = K.cylinder(110.0, z_fr0 + 20.0 - 120.0, segments=24).translate(xo, sy * span / 2, 120.0)
            jack_b = K.cylinder(140.0, 500.0, segments=24).translate(xo, sy * span / 2, z_fr0 - 150.0)
            pad = K.cylinder(320.0, 80.0, segments=40).translate(xo, sy * span / 2, 0.0) + K.sphere(120.0, segments=20).translate(xo, sy * span / 2, 110.0)
            b.add(f"outrigger_{pos}_{side}", f"Chân chống {'trước' if pos == 'front' else 'sau'} {'trái' if sy > 0 else 'phải'}", "Outrigger", "outrigger",
                  [Shape(beam + box_o, "paint_primary", 40.0), Shape(jack_b, "paint_secondary", 40.0), Shape(jack, "chrome", 40.0), Shape(pad, "steel_dark", 40.0)],
                  parent_id="carrier", required=True, aliases=["chân chống", "chân chống thủy lực", "đế chân chống", "outrigger"],
                  function=f"Chân chống duỗi ngang (khẩu độ {span / 1000:g} m), xi lanh chân + đế tì đất Ø640.",
                  position_tag="left" if sy > 0 else "right", explode_dir=(0, sy, 0), explode_distance=900.0, explode_order=1)

    # ---------- bàn quay ----------
    x_ss = float(np.mean(rears)) + 250.0
    z_tt = z_deck + 350.0
    ring = K.cylinder(1100.0, z_tt - z_deck, segments=64).translate(x_ss, 0, z_deck)
    frame = box_at(x_ss - 2300.0, x_ss + 1300.0, -1150.0, 1150.0, z_tt, z_tt + 400.0)
    z_foot = z_tt + 1300.0
    F = np.array([x_ss + 900.0, 0.0, z_foot])
    towers = K.Solid.union_all([K.hull([box_at(x_ss + 300.0, x_ss + 1300.0, sy * 380.0, sy * 560.0, z_tt + 400.0, z_tt + 401.0),
                                        K.cylinder(260.0, 180.0, segments=32).rotate(90, 0, 0).translate(F[0], sy * 380.0 + (180.0 if sy > 0 else 0.0), F[2])])
                                for sy in (1, -1)])
    cw = box_at(x_ss - 2900.0, x_ss - 2000.0, -1200.0, 1200.0, z_tt + 50.0, z_tt + 1450.0)
    drum_c = np.array([x_ss - 1300.0, 0.0, z_tt + 900.0])
    drum = K.cylinder(330.0, 700.0, segments=40).rotate(90, 0, 0).translate(drum_c[0], 350.0, drum_c[2])
    drum_frame = K.Solid.union_all([box_at(drum_c[0] - 400.0, drum_c[0] + 400.0, sy * 370.0, sy * 450.0, z_tt + 400.0, drum_c[2] + 150.0) for sy in (1, -1)])
    ocab = K.rounded_box(1600.0, 900.0, 1500.0, 100.0, segments=10).translate(x_ss + 200.0, -1250.0 + 450.0 - 260.0, z_tt + 400.0 + 750.0)
    ocab = ocab & box_at(x_ss - 700.0, x_ss + 1100.0, -1800.0, -300.0 - 260.0 + 100.0, z_tt + 400.0, z_tt + 2000.0)
    og = (box_at(x_ss + 950.0, x_ss + 1100.0, -1500.0, -700.0, z_tt + 900.0, z_tt + 1750.0) & ocab) - ocab.translate(-8.0, 0, 0)
    og_rec = box_at(x_ss + 950.0, x_ss + 1100.0, -1500.0, -700.0, z_tt + 900.0, z_tt + 1750.0) - ocab.translate(-30.0, 0, 0)
    # xi lanh nâng cần: chân trên khung bàn quay phía trước
    P0 = np.array([x_ss + 1150.0, 0.0, z_tt + 250.0])
    lug0 = box_at(P0[0] - 200.0, P0[0] + 150.0, -180.0, 180.0, z_tt + 150.0, z_tt + 400.0)
    pinF = MC.pin(F, (0, 1, 0), 140.0, 1300.0)
    pin0 = MC.pin(P0, (0, 1, 0), 120.0, 420.0)
    b.add("turntable", "Bàn quay (khung quay, đối trọng, tời)", "Superstructure", "turntable",
          [Shape(frame + towers + lug0, "paint_primary", 40.0), Shape(ring, "steel_dark", 40.0), Shape(cw, "paint_secondary", 40.0),
           Shape(drum_frame, "paint_secondary", 40.0), Shape(drum, "steel", 40.0), Shape(pinF + pin0, "steel", 40.0),
           Shape(ocab - og_rec, "paint_primary", 40.0), Shape(og, "glass_tinted", 40.0)], parent_id="carrier", required=True,
          aliases=["bàn quay", "mâm quay", "đối trọng", "tời", "tang tời", "cabin điều khiển", "turntable"],
          function="Bàn quay trên ổ quay toàn vòng: tháp chân cần, đối trọng sau, tời cáp, cabin điều khiển bên phải.",
          position_tag="rear", joint_axis=(0, 0, 1), explode_dir=(0, 0, 1), explode_distance=1500.0, explode_order=4)
    # ---------- cần ống lồng ----------
    Lb0, n_sec, e, Ls = plan_sections(Lboom)
    d = np.array([math.cos(math.radians(ang)), 0.0, math.sin(math.radians(ang))])
    nn = np.array([-math.sin(math.radians(ang)), 0.0, math.cos(math.radians(ang))])
    to_w = lambda s_: s_.rotate(0, -ang, 0).translate(*F)              # noqa: E731  hệ cần (trục +X từ chốt chân) → thế giới
    h0, w0, wall = 1000.0, 760.0, 22.0
    sec_ids = []
    starts = []
    for i in range(n_sec):
        hi_, wi_ = h0 - 110.0 * i, w0 - 110.0 * i
        s0 = -500.0 + i * (400.0 + e)
        starts.append((s0, Ls[i], hi_, wi_))
        outer = K.box(Ls[i], wi_, hi_).translate(s0 + Ls[i] / 2, 0, 0)
        # rỗng, hở đầu trước (đoạn trong chui ra); đoạn trên cùng kín đầu (đầu cần); đáy sau kín dày = wall (không mặt trùng)
        tip_end = s0 + Ls[i] + 20.0 if i < n_sec - 1 else s0 + Ls[i] - 400.0
        inner = box_at(s0 + wall, tip_end, -(wi_ / 2 - wall), wi_ / 2 - wall, -(hi_ / 2 - wall), hi_ / 2 - wall)
        shapes = []
        body = outer - inner
        if i == 0:
            foot = K.cylinder(260.0, 760.0 - 2.0, segments=32).rotate(90, 0, 0).translate(0, 379.0, 0)
            lugb = box_at(0.38 * Lb0 - 250.0, 0.38 * Lb0 + 250.0, -200.0, 200.0, -hi_ / 2 - 260.0, -hi_ / 2 + 5.0)
            body = body + foot + lugb
            guide_c = np.array([400.0, 0.0, hi_ / 2 + 140.0])
            guide = K.cylinder(120.0, 60.0, segments=24).rotate(90, 0, 0).translate(guide_c[0], 30.0, guide_c[2]) + \
                box_at(300.0, 500.0, -60.0, 60.0, hi_ / 2 - 5.0, hi_ / 2 + 140.0)
            shapes.append(Shape(to_w(guide), "steel", 40.0))
        if i > 0:
            ph, pw = starts[i - 1][2] - 2 * wall, starts[i - 1][3] - 2 * wall          # lòng đoạn ngoài
            pads = K.Solid.union_all([box_at(s0 + 60.0, s0 + 360.0, -pw / 2 + 1.0, pw / 2 - 1.0, sz * hi_ / 2, sz * (ph / 2 + 1.5)) for sz in (1, -1)])
            shapes.append(Shape(to_w(pads), "ptfe", 40.0))
        if i == n_sec - 1:
            tip = s0 + Ls[i]
            head_c = np.array([tip + 300.0, 0.0, 0.0])
            r_sh = h0 / 2 + 140.0
            head = box_at(tip - 300.0, tip + 300.0, -wi_ / 2, wi_ / 2, -hi_ / 2, hi_ / 2)
            plates = K.Solid.union_all([box_at(tip - 100.0, tip + 300.0, sy * 150.0, sy * 190.0, -hi_ / 2, 0.0) for sy in (1, -1)])
            plates = plates + K.Solid.union_all([K.cylinder(160.0, 40.0, segments=24).rotate(90, 0, 0).translate(head_c[0], sy * 150.0 + (40.0 if sy > 0 else 0.0), 0)
                                                 for sy in (1, -1)])
            sheaves = K.Solid.union_all([K.cylinder(r_sh, 50.0, segments=48).rotate(90, 0, 0).translate(head_c[0], y + 25.0, 0) for y in (-65.0, 15.0)])
            axle = K.cylinder(60.0, 340.0, segments=20).rotate(90, 0, 0).translate(head_c[0], 170.0, 0)
            body = body + head + plates
            shapes.append(Shape(to_w(sheaves), "steel", 40.0))
            shapes.append(Shape(to_w(axle), "steel_dark", 40.0))
        shapes.insert(0, Shape(to_w(body), "paint_primary", 40.0))
        sid = "boom_base" if i == 0 else f"boom_section_{i + 1}"
        b.add(sid, "Đoạn cần gốc" if i == 0 else f"Đoạn cần ống lồng {i + 1}", "Boom base section" if i == 0 else f"Telescopic section {i + 1}", "boom",
              shapes, parent_id="turntable" if i == 0 else sec_ids[-1], required=True,
              aliases=(["cần", "cần cẩu", "đoạn cần gốc", "boom"] if i == 0 else ["đoạn cần", "ống lồng", f"đoạn cần {i + 1}", "cần"])
              + (["puly đầu cần", "đầu cần"] if i == n_sec - 1 else []),
              function=("Đoạn cần gốc hộp thép cường độ cao, chốt chân cần, tai xi lanh nâng cần." if i == 0 else
                        f"Đoạn ống lồng {i + 1} trượt trên tấm PTFE, ra {e:.0f} mm.") + (" Đầu cần 2 puly." if i == n_sec - 1 else ""),
              position_tag="top", joint_axis=(1, 0, 0) if i else (0, 1, 0), explode_dir=tuple(float(x) for x in d) if i else (0, 0, 1),
              explode_distance=(1500.0 if i else 1200.0), explode_order=2 if i else 3, dimensions={"length": Ls[i]})
        sec_ids.append(sid)
    head_w = F + head_c[0] * d
    # xi lanh nâng cần: vỏ cố định theo dải 0–80°
    pb_local = np.array([0.38 * Lb0, 0.0, -h0 / 2 - 130.0])
    def pb_at(a_deg: float) -> np.ndarray:
        c, s_ = math.cos(math.radians(a_deg)), math.sin(math.radians(a_deg))
        return F + np.array([pb_local[0] * c - pb_local[2] * s_, 0.0, pb_local[0] * s_ + pb_local[2] * c])
    L0, L80 = float(np.linalg.norm(pb_at(0.0) - P0)), float(np.linalg.norm(pb_at(80.0) - P0))
    bore = 280.0
    barrel = 0.93 * min(L0, L80) - 0.35 * bore - 0.53 * bore
    PB = pb_at(ang)
    r_ = MC.hyd_ram(P0, PB, bore, 200.0, barrel_len=barrel)
    ram_info["luffing_cylinder"] = [r_["closed"], r_["stroke"]]
    pinB = MC.pin(PB, (0, 1, 0), 120.0, 420.0)
    b.add("luffing_cylinder", "Xi lanh nâng cần", "Luffing cylinder", "hydraulic_cylinder",
          [Shape(r_["barrel"], "paint_secondary", 40.0), Shape(r_["rod"], "chrome", 40.0), Shape(pinB, "steel", 40.0)], parent_id="turntable", required=True,
          aliases=["xi lanh nâng cần", "xi lanh", "ben nâng cần", "luffing cylinder"],
          function=f"Xi lanh nâng cần Ø{bore:g}, góc cần {ang:g}° (dải 0–80°).", position_tag="front", joint_axis=(0, 1, 0),
          explode_dir=(0, 0, -1), explode_distance=600.0, explode_order=1)
    contacts.append(["luffing_cylinder", "boom_base"])
    links += [["luff@turntable", P0, ["luffing_cylinder", "turntable"]], ["luff@boom", PB, ["luffing_cylinder", "boom_base"]]]
    # ---------- cáp + móc ----------
    top = sec_ids[-1]
    r_sh = h0 / 2 + 140.0
    fall_x = head_w[0] + r_sh
    z_hook_top = max(1800.0, min(head_w[2] - 3000.0, head_w[2] - 1500.0))
    falls = K.Solid.union_all([K.cylinder(11.0, head_w[2] - z_hook_top - 10.0, segments=12).translate(fall_x, y, z_hook_top + 5.0) for y in (-40.0, 40.0)])
    guide_w = F + guide_c[0] * d + guide_c[2] * nn
    drum_top = drum_c + np.array([0.0, 0.0, 330.0])
    line = K.tube(np.array([drum_top + [0, 0, 11.0], guide_w + (120.0 + 11.0) * nn]), 11.0, 12) + \
        K.tube(np.array([guide_w + (120.0 + 11.0) * nn, head_w + (r_sh + 11.0) * nn]), 11.0, 12)
    b.add("hoist_rope", "Cáp tời", "Hoist rope", "rope", [Shape(falls + line, "steel_dark", 40.0)], parent_id=top, required=True,
          aliases=["cáp", "cáp tời", "dây cáp", "cáp thép", "rope"], function="Cáp thép chống xoắn 2 nhánh từ tang tời qua puly dẫn và puly đầu cần.",
          position_tag="top", explode_dir=(1, 0, 0), explode_distance=500.0, explode_order=1)
    contacts += [["hoist_rope", "boom_base"], ["hoist_rope", "turntable"], ["hoist_rope", "boom_section_*"]]
    blk = box_at(fall_x - 250.0, fall_x + 250.0, -150.0, 150.0, z_hook_top - 500.0, z_hook_top + 6.0)
    sh_b = K.Solid.union_all([K.cylinder(200.0, 40.0, segments=24).rotate(90, 0, 0).translate(fall_x, y + 20.0, z_hook_top - 200.0) for y in (-40.0, 40.0)]) \
        & box_at(fall_x - 300.0, fall_x + 300.0, -160.0, 160.0, z_hook_top - 520.0, z_hook_top)
    shank = K.cylinder(55.0, 300.0, segments=20).translate(fall_x, 0, z_hook_top - 800.0)
    hook = (K.torus(160.0, 55.0, segments=40, tube_segments=14).rotate(90, 0, 0).translate(fall_x + 160.0, 0, z_hook_top - 960.0)
            - box_at(fall_x + 160.0, fall_x + 400.0, -100.0, 100.0, z_hook_top - 960.0, z_hook_top - 700.0))
    b.add("hook_block", "Cụm móc cẩu", "Hook block", "hook", [Shape(blk, "paint_accent", 40.0), Shape(sh_b + shank + hook, "steel", 40.0)],
          parent_id="hoist_rope", required=True, aliases=["móc cẩu", "móc", "cụm móc", "hook", "puly móc"],
          function="Cụm móc 2 puly, móc rèn có chốt an toàn.", position_tag="top", explode_dir=(0, 0, -1), explode_distance=600.0, explode_order=1)
    b.note_stage(1, "Tháo cáp, móc, bánh, chân chống, xi lanh")
    b.note_stage(2, "Rút các đoạn ống lồng")
    b.note_stage(3, "Tháo đoạn cần gốc")
    b.note_stage(4, "Nhấc bàn quay")
    sh_ = np.asarray(b.place_on_ground(center_xy=True), float)
    b.metadata.update({"boom_length_mm": Lboom, "boom_angle_deg": ang, "axles": n_ax, "sections": n_sec, "section_extension_mm": e,
                       "outrigger_span_mm": span, "min_overlap_mm": min(Ls[i - 1] - 400.0 - e for i in range(1, n_sec)),
                       "pin_links": [[n_, (np.asarray(c_, float) + sh_).tolist(), ids_] for n_, c_, ids_ in links], "rams": ram_info,
                       "boom_foot": (F + sh_).tolist(), "tire": "385/65R22.5",
                       "standard": "Cần trục ô tô cần ống lồng (EN 13000), lốp 385/65R22.5; chiều dài cần = chốt chân → tâm puly đầu",
                       "strict_overlap": True, "contacts": contacts})
    return b.build()
