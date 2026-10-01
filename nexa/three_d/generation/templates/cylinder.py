"""Xi lanh khí nén kiểu thanh giằng ISO 15552 (nòng 32–125) hoặc xi lanh thủy lực thanh giằng (tỷ lệ ISO 6020-2).

Nòng ống nhôm (khí nén) / thép mạ crôm (thủy lực), nắp trước/sau vuông vát góc có gờ lồng vào nòng + đệm cao su
cuối hành trình, 4 thanh giằng + 8 đai ốc tại khoảng tâm TG (ISO 15552), piston 2 vòng làm kín + vòng nam châm,
cần piston mạ crôm ren KK + đai ốc cần, cổng khí/dầu có đầu nối, vít chỉnh giảm chấn. Hành trình = khoảng piston
chạy giữa hai đệm (đo lại trên khối). Trạng thái thu / giữa / duỗi. Trục xi lanh theo +X, đặt trên mặt đất.

Tháo: đai ốc thanh giằng, đầu nối → nắp trước → rút cần + piston, rút thanh giằng → nắp sau khỏi nòng.
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

TO_X = np.array([[0, 0, 1.0, 0], [1.0, 0, 0, 0], [0, 1.0, 0, 0]])     # trục +Z → +X
TO_NX = np.array([[0, 0, -1.0, 0], [1.0, 0, 0, 0], [0, -1.0, 0, 0]])  # trục +Z → −X
TO_NY = np.array([[1.0, 0, 0, 0], [0, 0, -1.0, 0], [0, 1.0, 0, 0]])   # trục +Z → −Y


def dims(kind: str, bore: float) -> dict:
    """Kích thước chính: khí nén theo ISO 15552, thủy lực theo tỷ lệ ISO 6020-2 (cần ≈ 0,5–0,7 nòng)."""
    if kind == "pneumatic":
        t = dict(S.ISO15552[int(round(bore))])
        t.update(wall=max(1.6, 0.04 * bore), cap_l=max(18.0, 0.42 * t["e"]), piston_l=max(14.0, 0.34 * bore))
        return t
    rod = min(bore * 0.7, max(bore * 0.5, 12.0))
    e = bore * 1.45 + 12
    return dict(rod=round(rod), kk_d=round(rod * 0.75), kk=f"M{round(rod * 0.75)}×2", tg=round(e * 0.72, 1), e=round(e),
                port=f"G{'1/4' if bore < 50 else '1/2' if bore < 100 else '3/4'}", wall=max(4.0, 0.08 * bore),
                cap_l=max(28.0, 0.5 * e), piston_l=max(22.0, 0.45 * bore))


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    kind = p.get("cylinder_type", "pneumatic")
    bore = float(p.get("bore_mm", 50.0))
    stroke = float(p.get("stroke_mm", 100.0))
    ext = {"retracted": 0.0, "mid": 0.5, "extended": 1.0}[p.get("state", "retracted")]
    t = dims(kind, bore)
    R = bore / 2
    E, TG, cap_l, pl, wall = float(t["e"]), float(t["tg"]), float(t["cap_l"]), float(t["piston_l"]), float(t["wall"])
    rod_d, kk = float(t["rod"]), float(t["kk_d"])
    mats = MC.tech_materials(spec, accent="#1f5aa6")
    b = AssemblyBuilder(spec.name or ("Xi lanh khí nén" if kind == "pneumatic" else "Xi lanh thủy lực") + f" Ø{bore:g}×{stroke:g}",
                        "cylinder", mats)
    spig = min(6.0, 0.25 * cap_l)                   # gờ nắp lồng vào nòng
    bt = 2.5 if kind == "pneumatic" else 4.0        # đệm cuối hành trình
    L_bore = stroke + pl + 2 * bt + 2 * spig        # chiều dài ống nòng
    x_r = cap_l                                     # mặt ngoài nắp sau ở x = 0
    x_f = x_r + L_bore
    barrel = (K.cylinder(R + wall, L_bore, segments=96) - K.cylinder(R, L_bore + 2, segments=96).translate(0, 0, -1)).transform(TO_X)
    b.add("barrel", "Nòng xi lanh", "Barrel", "cylinder_barrel",
          Shape(barrel.translate(x_r, 0, 0), "aluminum" if kind == "pneumatic" else "chrome", 40.0), required=True,
          aliases=["nòng", "ống xi lanh", "thân xi lanh", "barrel", "tube"],
          function=f"Ống nòng Ø{bore:g} mm, mặt trong mài bóng cho piston trượt.", position_tag="center",
          dimensions={"bore": bore, "length": L_bore})

    def cap(front: bool) -> tuple[K.Solid, K.Solid]:
        sq = K.chamfer_box(cap_l, E, E, 0.08 * E).translate(cap_l / 2, 0, 0)
        c = sq + K.cylinder(R, spig, segments=96).transform(TO_X).translate(cap_l, 0, 0)
        r_in = rod_d / 2 + 2.0 if front else 0.3 * R
        bump = K.revolve([(r_in, 0), (0.75 * R, 0), (0.75 * R, bt), (r_in, bt)], segments=64).transform(TO_X).translate(cap_l + spig, 0, 0)
        if front:
            core = K.cylinder(rod_d / 2, cap_l + spig + bt + 4, segments=48).transform(TO_X).translate(-2, 0, 0)
            c, bump = c - core, bump - core
        return c, bump
    rear, bump_r = cap(False)
    front, bump_f = cap(True)
    front = front.mirror((1, 0, 0)).translate(x_f + x_r, 0, 0)
    bump_f = bump_f.mirror((1, 0, 0)).translate(x_f + x_r, 0, 0)
    # thanh giằng + đai ốc
    tr_d = max(6.0, float(round(0.12 * bore + 2)))
    x_out = x_f + x_r
    rods, nuts = [], []
    for sy in (1, -1):
        for sz in (1, -1):
            y, z = sy * TG / 2, sz * TG / 2
            rods.append(K.cylinder(tr_d / 2, x_out + tr_d + 4, segments=20).transform(TO_X).translate(-0.5 * tr_d - 2, y, z))
            nuts.append(MC.hex_nut(tr_d).transform(TO_NX).translate(0, y, z))
            nuts.append(MC.hex_nut(tr_d).transform(TO_X).translate(x_out, y, z))
    tie = K.Solid.union_all(rods)
    rear, front = rear - tie, front - tie
    # cổng khí/dầu (trên nắp) + vít chỉnh giảm chấn (bên hông)
    port_r = {"G1/8": 4.9, "G1/4": 6.6, "G3/8": 8.3, "G1/2": 10.5, "G3/4": 13.2}.get(t["port"], 6.6)
    ports = {}
    for key, x_c in (("rear", cap_l * 0.5), ("front", x_out - cap_l * 0.5)):
        thread = K.cylinder(port_r * 0.95, 6.0, segments=24).translate(x_c, 0, E / 2 - 6.0)
        hexn = MC._hex_chamfered(port_r * 2.1, 5.0).translate(x_c, 0, E / 2)
        if kind == "pneumatic":
            head = K.cylinder(port_r * 0.9, 6.5, segments=24).translate(x_c, 0, E / 2 + 5.0)
            collar = K.cylinder(port_r * 0.75, 1.5, segments=24).translate(x_c, 0, E / 2 + 11.5)
            ports[key] = [Shape(thread + hexn, "brass", 40.0), Shape(head, "plastic_black", 40.0), Shape(collar, "paint_blue", 40.0)]
        else:
            nipple = K.cylinder(port_r * 0.7, 10, segments=24).translate(x_c, 0, E / 2 + 5.0)
            ports[key] = [Shape(thread + hexn + nipple, "steel_zinc", 40.0)]
        core = thread + K.cylinder(port_r * 0.45, E / 2, segments=16).translate(x_c, 0, 0)
        screw = K.cylinder(2.5, 5.5, segments=16).transform(TO_NY).translate(x_c, -E / 2 + 4.0, 0) - K.box(0.8, 3.2, 6).translate(x_c, -E / 2 - 1.5, 0)
        scr_core = K.cylinder(2.5, 4.02, segments=16).transform(TO_NY).translate(x_c, -E / 2 + 4.0, 0)
        if key == "rear":
            rear = rear - core - scr_core
            rear_scr = screw
        else:
            front = front - core - scr_core
            front_scr = screw
    b.add("rear_cap", "Nắp sau", "Rear end cap", "housing",
          [Shape(rear, "cast_aluminum", 40.0), Shape(bump_r, "nbr", 40.0), Shape(rear_scr, "brass", 40.0)],
          parent_id="barrel", required=True, aliases=["nắp sau", "nắp đáy", "rear cap", "vít giảm chấn", "đệm cao su"],
          function="Nắp sau: gờ lồng nòng, đệm cao su cuối hành trình, cổng sau, vít chỉnh giảm chấn.", position_tag="rear",
          explode_dir=(-1, 0, 0), explode_distance=cap_l * 1.5 + 20, explode_order=4)
    b.add("front_cap", "Nắp trước", "Front end cap", "housing",
          [Shape(front, "cast_aluminum", 40.0), Shape(bump_f, "nbr", 40.0), Shape(front_scr, "brass", 40.0)],
          parent_id="barrel", required=True, aliases=["nắp trước", "đầu xi lanh", "front cap", "bạc dẫn hướng", "phớt gạt bụi"],
          function="Nắp trước: bạc dẫn hướng cần + phớt gạt bụi, cổng trước, đệm cuối hành trình.", position_tag="front",
          explode_dir=(1, 0, 0), explode_distance=cap_l * 1.5 + 20, explode_order=2)
    b.add("tie_rods", "4 thanh giằng", "Tie rods (4)", "tie_rod", Shape(tie, "steel_zinc", 40.0), parent_id="rear_cap",
          required=True, aliases=["thanh giằng", "ty giằng", "tie rod", "bu lông giằng"],
          function=f"4 thanh giằng M{tr_d:g} tại khoảng tâm TG = {TG:g} mm ép hai nắp vào nòng.", position_tag="center",
          explode_dir=(-1, 0, 0), explode_distance=x_f * 0.9 + 40, explode_order=3)
    b.add("tie_nuts", "Đai ốc thanh giằng", "Tie-rod nuts", "nut", Shape(K.Solid.union_all(nuts), "steel_zinc", 40.0),
          parent_id="tie_rods", required=True, aliases=["đai ốc", "ê cu", "tán", "nuts"],
          function="8 đai ốc siết thanh giằng.", position_tag="center",
          explode_dir=(1, 0, 0), explode_distance=cap_l + 30, explode_order=1)
    for key in ("rear", "front"):
        b.add(f"port_{key}", "Cổng " + ("khí" if kind == "pneumatic" else "dầu") + (" sau" if key == "rear" else " trước"),
              f"{key.capitalize()} port", "fitting", ports[key], parent_id=f"{key}_cap",
              aliases=["cổng khí", "đầu nối", "cút nối", "port", "fitting", "cổng dầu"],
              function=f"Cổng {t['port']} " + ("(đầu nối nhanh ống khí)" if kind == "pneumatic" else "(đầu nối ống thủy lực)"),
              position_tag="top", explode_dir=(0, 0, 1), explode_distance=E * 0.6 + 10, explode_order=1)
    # piston + cần
    xp = x_r + spig + bt + ext * stroke
    piston = K.revolve(P.fillet_polygon([(rod_d / 2, 0), (R - 0.02, 0), (R - 0.02, pl), (rod_d / 2, pl)], [0, 0.4, 0.4, 0], 3), segments=96)
    seals = []
    for zz in (0.12 * pl, 0.74 * pl):
        h_ = 0.14 * pl
        piston = piston - K.revolve([(R - 2.0, zz), (R + 1, zz), (R + 1, zz + h_), (R - 2.0, zz + h_)], segments=96)
        seals.append(K.revolve([(R - 2.0, zz), (R - 0.02, zz + 0.3), (R - 0.02, zz + h_ - 0.3), (R - 2.0, zz + h_)], segments=96))
    zm, hm = 0.43 * pl, 0.1 * pl
    piston = piston - K.revolve([(R - 3.0, zm), (R + 1, zm), (R + 1, zm + hm), (R - 3.0, zm + hm)], segments=96)
    magnet = K.revolve([(R - 3.0, zm), (R - 0.5, zm), (R - 0.5, zm + hm), (R - 3.0, zm + hm)], segments=96)
    b.add("piston", "Piston", "Piston", "piston",
          [Shape(piston.transform(TO_X).translate(xp, 0, 0), "cast_aluminum", 40.0),
           Shape(K.Solid.union_all(seals).transform(TO_X).translate(xp, 0, 0), "nbr", 40.0),
           Shape(magnet.transform(TO_X).translate(xp, 0, 0), "steel_dark", 40.0)],
          parent_id="piston_rod", required=True, aliases=["piston", "pít tông", "vòng làm kín", "nam châm"],
          function="Piston có 2 vòng làm kín hai chiều và vòng nam châm cho cảm biến hành trình.", position_tag="center",
          explode_dir=(-1, 0, 0), explode_distance=pl + 20, explode_order=3, dimensions={"length": pl})
    x_tip = x_out + 20 + kk * 1.6 + ext * stroke
    rod_len = x_tip - xp
    rod = K.cylinder(rod_d / 2, rod_len - kk * 1.6, segments=48) + \
        K.cylinder(kk / 2, kk * 1.6, segments=32).translate(0, 0, rod_len - kk * 1.6 - 0.01)
    rod = rod.transform(TO_X).translate(xp, 0, 0)
    rnut = MC.hex_nut(kk).transform(TO_X).translate(x_tip - kk * 1.6 + 1.0, 0, 0)
    b.add("piston_rod", "Cần piston", "Piston rod", "rod", [Shape(rod, "chrome", 40.0), Shape(rnut, "steel_zinc", 40.0)],
          parent_id="barrel", required=True, aliases=["cần piston", "ty xi lanh", "cần đẩy", "piston rod", "đai ốc cần"],
          function=f"Cần Ø{rod_d:g} mm mạ crôm cứng, đầu ren {t['kk']} kèm đai ốc cần.", position_tag="front",
          joint_axis=(1, 0, 0), explode_dir=(1, 0, 0), explode_distance=stroke + cap_l * 3 + 60, explode_order=3,
          dimensions={"rod_d": rod_d, "stroke": stroke})
    b.note_stage(1, "Tháo đai ốc thanh giằng, đầu nối")
    b.note_stage(2, "Tháo nắp trước")
    b.note_stage(3, "Rút cần + piston, rút thanh giằng")
    b.note_stage(4, "Tháo nắp sau khỏi nòng")
    b.place_on_ground(center_xy=False)
    b.metadata.update({"cylinder_type": kind, "bore_mm": bore, "stroke_mm": stroke, "rod_d_mm": rod_d, "tg_mm": TG,
                       "cap_e_mm": E, "extension": ext, "standard": "ISO 15552:2018" if kind == "pneumatic" else "tỷ lệ ISO 6020-2",
                       "strict_overlap": True,
                       "contacts": [["piston", "barrel"], ["piston_rod", "front_cap"], ["tie_nuts", "*_cap"],
                                    ["tie_rods", "front_cap"], ["piston", "rear_cap"], ["piston", "front_cap"]]})
    return b.build()
