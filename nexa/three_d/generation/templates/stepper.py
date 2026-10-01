"""Động cơ bước lai (hybrid) NEMA 17 / 23 / 34 theo NEMA ICS 16.

Kích thước lắp: cạnh mặt bích, khoảng cách tâm lỗ, gờ định tâm, đường kính/chiều dài trục (standards.NEMA). Thân gồm
nắp trước nhôm (lỗ ren M3 cỡ 17, tai bích lỗ xuyên cỡ 23/34), khối lá thép stator có rãnh lá ghép + lỗ rotor, rotor
răng trên trục (trục có mặt vát D), nắp sau có ụ ổ bi, 4 vít xuyên đầu chìm, đầu cắm JST (cỡ 17) hoặc ống luồn dây
(cỡ 23/34) với 4 dây A+/A−/B+/B− (đỏ/xanh dương/xanh lá/đen), nhãn thông số. Đứng trên nắp sau, trục hướng lên.

Tháo: 4 vít → nắp sau → stator → rút rotor + trục khỏi nắp trước.
"""
from __future__ import annotations

import numpy as np

from nexa.three_d import standards as S
from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    size = int(p.get("frame_size", 17))
    L = float(p.get("body_length_mm") or S.NEMA[size]["lengths"][2])
    n = MC.nema_stepper(size, L, double_shaft=p.get("shaft") == "double")
    t = S.NEMA[size]
    F, side, cap_t = n["flange"], n["side"], n["cap_t"]
    mats = MC.tech_materials(spec)
    b = AssemblyBuilder(spec.name or f"Động cơ bước NEMA {size}", "stepper_motor", mats)
    z_stack0, z_stack1 = -L + cap_t, -cap_t
    # stator: khối lá thép có lỗ rotor + răng cực
    r_bore = 0.29 * side
    stack = n["stack"] - K.cylinder(r_bore, L, segments=96).translate(0, 0, -L)
    teeth = [K.box(r_bore * 0.2, r_bore * 0.09, L).translate(r_bore - r_bore * 0.06, 0, -L / 2).rotate(0, 0, a)
             for a in np.arange(0, 360, 7.5)]
    stack = stack.subtract_all(teeth)
    label = K.box(0.25, side * 0.72, (z_stack1 - z_stack0) * 0.82).translate(0, 0, 0)
    label = label.translate(side / 2 + 0.125, 0, (z_stack0 + z_stack1) / 2)
    b.add("front_cap", "Nắp trước (mặt bích)", "Front end cap (flange)", "housing",
          Shape(n["front"], "cast_aluminum", 30.0), required=True,
          aliases=["nắp trước", "mặt bích", "mặt lắp", "flange", "front cap", "gờ định tâm"],
          function=f"Mặt lắp NEMA {size}: cạnh {F:g} mm, 4 lỗ cách {n['hole_spacing']:g} mm, gờ định tâm Ø{t['pilot_d']:g}.",
          position_tag="top", dimensions={"flange": F, "hole_spacing": n["hole_spacing"], "pilot_d": t["pilot_d"]})
    b.add("stator", "Stator (khối lá thép + cuộn dây)", "Stator lamination stack", "stator",
          [Shape(stack, "steel_dark", 30.0), Shape(label, "label_white", 30.0)], parent_id="front_cap", required=True,
          aliases=["stator", "thân động cơ", "lá thép", "cuộn dây", "thân"],
          function="Khối lá thép kỹ thuật điện 2 pha, 50 răng cực — tạo từ trường quay theo từng bước 1,8°.",
          position_tag="center", explode_dir=(0, 0, -1), explode_distance=0.35 * L + 12, explode_order=3)
    b.add("rear_cap", "Nắp sau", "Rear end cap", "housing", Shape(n["rear"], "cast_aluminum", 30.0), parent_id="stator",
          required=True, aliases=["nắp sau", "nắp đuôi", "rear cap", "ụ ổ bi sau"],
          function="Nắp sau đỡ ổ bi phía sau của trục rotor.", position_tag="bottom",
          explode_dir=(0, 0, -1), explode_distance=0.3 * L + 10, explode_order=2)
    b.add("screws", "4 vít xuyên thân", "Through screws (4)", "screw", Shape(n["screws"], "steel_black_oxide", 35.0),
          parent_id="rear_cap", required=True, aliases=["vít", "ốc", "vít xuyên", "screws"],
          function="4 vít lục giác chìm ép nắp trước – stator – nắp sau.", position_tag="bottom",
          explode_dir=(0, 0, -1), explode_distance=0.5 * L + 20, explode_order=1)
    for part in ("front_cap", "stator", "rear_cap"):
        b.cut(part, n["screw_cores"])
    b.cut("front_cap", n["shaft_core"])
    b.cut("rear_cap", n["shaft_core"])
    # rotor răng (hai cốc lệch nửa bước răng) trên trục — nằm trong lỗ stator, khe hở không khí 0,05 mm
    rr = r_bore - 0.05
    rotor_len = (z_stack1 - z_stack0) - 0.6
    rotor = K.cylinder(rr - 0.3, rotor_len, segments=96).translate(0, 0, z_stack0 + 0.3)
    grooves = [K.box(rr * 0.12, rr * 0.07, rotor_len * 0.46).translate(rr - rr * 0.04, 0, 0).rotate(0, 0, a)
               for a in np.arange(0, 360, 7.2)]
    cup1 = K.Solid.union_all([g.translate(0, 0, z_stack0 + 0.3 + rotor_len * 0.25) for g in grooves])
    cup2 = K.Solid.union_all([g.rotate(0, 0, 3.6).translate(0, 0, z_stack0 + 0.3 + rotor_len * 0.75) for g in grooves])
    rotor = rotor - cup1 - cup2
    magnet = K.cylinder(rr * 0.96, rotor_len * 0.06, segments=64).translate(0, 0, z_stack0 + 0.3 + rotor_len * 0.47)
    rotor = rotor - magnet
    b.add("rotor_shaft", "Trục + rotor", "Rotor & shaft", "shaft",
          [Shape(n["shaft"], "stainless", 35.0), Shape(rotor, "steel", 35.0), Shape(magnet.scale(0.999, 0.999, 1), "steel_dark", 35.0)],
          parent_id="front_cap", required=True, aliases=["trục", "trục động cơ", "rotor", "shaft", "mặt vát d"],
          function=f"Trục Ø{t['shaft_d']:g} mm có mặt vát D; rotor nam châm vĩnh cửu hai nửa răng lệch nửa bước.",
          position_tag="top", joint_axis=(0, 0, 1), explode_dir=(0, 0, 1), explode_distance=0.6 * L + 25, explode_order=4,
          dimensions={"shaft_d": t["shaft_d"], "shaft_len": t["shaft_len"]})
    # đầu cắm + dây
    z_rc = n["z_rear"] + cap_t / 2
    colors = ["wire_red", "wire_blue", "wire_green", "wire_black"]
    if size == 17:
        body = K.rounded_box(6.0, 13.0, 5.4, 0.5).translate(side / 2 - 2.99, 0, z_rc)
        conn_cut = K.box(6.02, 13.02, 5.42).translate(side / 2 - 3.0, 0, z_rc)
        plug = K.rounded_box(7.0, 12.0, 4.6, 0.6).translate(side / 2 + 3.5, 0, z_rc)
        b.cut("rear_cap", conn_cut)
        b.add("connector", "Đầu cắm JST-PH 6 chân", "JST-PH connector", "connector",
              [Shape(body, "nylon_white", 40.0), Shape(plug, "nylon_white", 40.0)], parent_id="rear_cap",
              aliases=["đầu cắm", "jack", "connector", "cổng dây"], function="Đầu cắm dây pha động cơ (2 cuộn: A, B).",
              position_tag="side", explode_dir=(1, 0, 0), explode_distance=15.0, explode_order=1)
        x0 = side / 2 + 7.0
        conn_id = "connector"
    else:
        boot = K.revolve(P.fillet_polygon([(0, 0), (4.5, 0), (4.5, 3.0), (3.2, 9.0), (0, 9.0)], [0, 0.5, 1.0, 0.5, 0], 3),
                         segments=32).rotate(0, 90, 0).translate(side / 2 - 0.5, 0, z_rc)
        b.cut("rear_cap", K.cylinder(4.5, 1.0, segments=32).rotate(0, 90, 0).translate(side / 2 - 0.5, 0, z_rc))
        b.add("connector", "Ống luồn dây cao su", "Cable grommet", "connector", Shape(boot, "rubber", 40.0), parent_id="rear_cap",
              aliases=["ống luồn dây", "chụp dây", "cổng dây", "grommet"], function="Chống gập và giữ dây ra khỏi nắp sau.",
              position_tag="side", explode_dir=(1, 0, 0), explode_distance=15.0, explode_order=1)
        x0 = side / 2 + 8.4
        conn_id = "connector"
    wires = []
    z_ground = n["z_rear"] - 1.2
    for k, mid in enumerate(colors):
        y = (k - 1.5) * 1.6
        path = [(x0 - 0.8, y, z_rc), (x0 + 14, y, z_rc + 1.0), (x0 + 30, y * 1.6, z_rc - 6),
                (x0 + 42, y * 2.0, z_ground + 0.8 + (z_rc - z_ground) * 0.2), (x0 + 70, y * 2.2 + 6, z_ground + 0.8)]
        wires.append(Shape(K.tube(P.spline_through(np.asarray(path), 48), 0.65, 10, rounded_ends=True), mid, 40.0))
    end_conn = K.rounded_box(6.0, 10.0, 5.0, 0.6).translate(x0 + 73.0, 6.0, z_ground + 2.5)
    wires.append(Shape(end_conn, "nylon_white", 40.0))
    b.add("cable", "Dây pha (4 dây A+/A−/B+/B−)", "Motor leads", "cable", wires, parent_id=conn_id,
          aliases=["dây", "dây điện", "cáp", "dây pha", "cable", "wire"],
          function="4 dây: đỏ A+, xanh dương A−, xanh lá B+, đen B− (thứ tự màu phổ biến; kiểm tra datasheet).",
          position_tag="side", explode_dir=(1, 0, 0), explode_distance=25.0, explode_order=1)
    b.note_stage(1, "Tháo 4 vít xuyên, rút đầu cắm/dây")
    b.note_stage(2, "Tháo nắp sau")
    b.note_stage(3, "Tháo stator")
    b.note_stage(4, "Rút rotor + trục khỏi nắp trước")
    b.place_on_ground(center_xy=False)
    b.metadata.update({"frame_size": size, "flange_mm": F, "hole_spacing_mm": n["hole_spacing"], "body_length_mm": L,
                       "shaft_d_mm": t["shaft_d"], "pilot_d_mm": t["pilot_d"], "standard": "NEMA ICS 16",
                       "strict_overlap": True,
                       "contacts": [["rotor_shaft", "rear_cap"], ["cable", "connector"]]})
    return b.build()

