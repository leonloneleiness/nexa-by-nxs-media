"""Cầu: giàn thép (Pratt chạy dưới, thanh xiên đầu), dây văng (2 tháp chữ H, 2 mặt dây, nhịp biên 0,4 L), vòm có thanh
căng (tied arch, sườn vòm parabol f = L/6, dây treo đứng).

- Mố bê tông hai đầu + gối cao su bản thép; hệ mặt cầu: dầm ngang + dầm dọc + bản bê tông 250 mm + gờ chắn bánh + lan can.
- Cầu giàn: hai giàn phẳng 2L200×20 kẹp bản mã 20 mm, bu-lông M24 (bộ dựng `structures.PlanarTruss`), thanh chống ngang
  trên đỉnh giàn; H ≈ L/7; bản mặt cầu nằm trong mép cánh ngang thanh cánh dưới.
- Dây văng: dây bọc HDPE Ø160 neo trong tháp và trên dầm biên (hộp neo); dầm hộp biên + dầm ngang; tháp cao ≈ 0,25 L trên
  mặt cầu. Vòm: sườn hộp quét theo parabol, dây treo cách đều, thanh giằng gió ở vùng đỉnh vòm (trên tĩnh không 6 m).
Nhịp = khoảng cách tâm gối (giàn, vòm) hoặc tâm hai tháp (dây văng).
"""
from __future__ import annotations

import numpy as np

from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.generation.templates.structures import SECTIONS, Member, PlanarTruss
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec


def box_at(x0, x1, y0, y1, z0, z1) -> K.Solid:
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    z0, z1 = sorted((z0, z1))
    return K.box(x1 - x0, y1 - y0, z1 - z0).translate((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)


def i_beam_y(x: float, y0: float, y1: float, z_top: float, h: float, b: float, tw: float, tf: float) -> K.Solid:
    """Dầm chữ I nằm ngang theo Y (dầm ngang) tại hoành độ x, từ y0 tới y1, mặt trên tại z_top."""
    prof = np.array([(-b / 2, -h), (b / 2, -h), (b / 2, -h + tf), (tw / 2, -h + tf), (tw / 2, -tf), (b / 2, -tf), (b / 2, 0), (-b / 2, 0),
                     (-b / 2, -tf), (-tw / 2, -tf), (-tw / 2, -h + tf), (-b / 2, -h + tf)])
    ex = K.extrude(P.ensure_ccw(prof), y1 - y0)                        # mặt cắt (x, z), đùn theo Z
    return ex.transform(np.array([[1.0, 0, 0, x], [0, 0, -1.0, y1], [0, 1.0, 0, z_top]]))   # đùn → −Y từ y1 (det = +1)


def i_beam_x(y: float, x0: float, x1: float, z_top: float, h: float, b: float, tw: float, tf: float) -> K.Solid:
    """Dầm chữ I dọc theo X (dầm dọc) tại tung độ y, mặt trên tại z_top."""
    prof = np.array([(-b / 2, -h), (b / 2, -h), (b / 2, -h + tf), (tw / 2, -h + tf), (tw / 2, -tf), (b / 2, -tf), (b / 2, 0), (-b / 2, 0),
                     (-b / 2, -tf), (-tw / 2, -tf), (-tw / 2, -h + tf), (-b / 2, -h + tf)])
    ex = K.extrude(P.ensure_ccw(prof), x1 - x0)                        # mặt cắt (y, z), đùn theo Z → +X
    return ex.transform(np.array([[0, 0, 1.0, x0], [1.0, 0, 0, y], [0, 1.0, 0, z_top]]))


def railings(x0: float, x1: float, y: float, z0: float, h: float = 1100.0) -> K.Solid:
    posts = [K.box(80.0, 80.0, h).translate(x, y, z0 + h / 2) for x in np.arange(x0 + 100.0, x1 - 50.0, 2000.0)]
    rails = [K.tube(np.array([[x0 + 60.0, y, z0 + zz], [x1 - 60.0, y, z0 + zz]]), 30.0 if zz == h - 30.0 else 20.0, 12) for zz in (400.0, 750.0, h - 30.0)]
    return K.Solid.union_all(posts + rails)


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    kind = p.get("bridge_type", "truss")
    S = float(p.get("span_mm", 60000.0))
    Wd = float(p.get("deck_width_mm", 8000.0))
    mats = MC.tech_materials(spec, primary="#b23a48", secondary="#2b2d42", accent="#f2b705")
    mats["concrete"] = M.material("concrete", "stone", "#b5b5ad", 0.0, 0.85, name="Bê tông")
    mats["asphalt"] = M.material("asphalt", "stone", "#3a3b3d", 0.0, 0.95, name="Bê tông nhựa mặt đường")
    mats["galvanized"] = M.material("galvanized", "metal", "#b9bec4", 0.85, 0.42, name="Thép mạ kẽm")
    mats["hdpe"] = M.material("hdpe", "plastic", "#e8e8e2", 0.0, 0.45, name="Ống bọc HDPE dây văng")
    names = {"truss": "Cầu giàn thép", "cable_stayed": "Cầu dây văng", "arch": "Cầu vòm thép"}
    b = AssemblyBuilder(spec.name or f"{names[kind]} nhịp {S / 1000:g} m", "bridge", mats)
    if kind == "truss":
        meta = _truss(b, S, Wd)
    elif kind == "cable_stayed":
        meta = _cable_stayed(b, S, Wd)
    else:
        meta = _arch(b, S, Wd)
    sh = np.asarray(b.place_on_ground(center_xy=True), float)
    meta["bearings"] = [(np.asarray(q, float) + sh).tolist() for q in meta.get("bearings", [])]
    b.metadata.update({"bridge_type": kind, "span_mm": S, "deck_width_mm": Wd, **meta, "strict_overlap": True})
    return b.build()


def _abutments(b: AssemblyBuilder, xs: list[float], W: float, z_seat: float, H: float, back_to: float, sign: list[int]) -> None:
    """Mố: tường thân + bệ gối (mặt gối tại z_seat) + tường đỉnh chắn đất đến back_to; cao H từ đáy móng."""
    parts = []
    for x, s in zip(xs, sign):
        body = box_at(x - s * 700.0, x + s * 2500.0, -W / 2, W / 2, z_seat - H, z_seat)
        back = box_at(x + s * 900.0, x + s * 1500.0, -W / 2, W / 2, z_seat, back_to)
        foot = box_at(x - s * 1500.0, x + s * 3500.0, -W / 2 - 500.0, W / 2 + 500.0, z_seat - H - 800.0, z_seat - H)
        parts.append(body + back + foot)
    b.add("abutments", "Mố cầu (2 đầu)", "Abutments", "abutment", Shape(K.Solid.union_all(parts), "concrete", 35.0), required=True,
          aliases=["mố", "mố cầu", "tường đỉnh", "móng mố", "abutment"], function="Mố bê tông cốt thép: thân mố, bệ kê gối, tường đỉnh, móng.",
          position_tag="bottom")


def _truss(b: AssemblyBuilder, S: float, Wd: float) -> dict:
    sec = SECTIONS["bridge"]
    Lc, tc = sec["chord"]
    g = sec["g"]
    n = max(6, 2 * round(S / (12000.0 if S <= 60000 else 15000.0)))    # khoang 6–7,5 m
    H = max(6000.0, S / 7.0)                                           # tĩnh không dưới thanh chống ≥ 4,75 m
    a = S / n
    Yt = Wd / 2 + g / 2 + Lc + 20.0 + 350.0                          # mặt phẳng giàn: bản mặt cầu + gờ nằm trong mép cánh ngang
    x0 = -S / 2
    nodes = [(x0 + i * a, 0.0) for i in range(n + 1)] + [(x0 + i * a, H) for i in range(1, n)]
    t = lambda i: n + i                                                # noqa: E731  nút trên i (1..n-1)
    mem = [Member(i, i + 1, "bottom_chord", chord=True, inward=(0, 1)) for i in range(n)]
    mem += [Member(t(i), t(i + 1), "top_chord", chord=True, inward=(0, -1)) for i in range(1, n - 1)]
    mem += [Member(0, t(1), "top_chord", chord=True, inward=(1, -1)), Member(t(n - 1), n, "top_chord", chord=True, inward=(-1, -1))]
    mem += [Member(i, t(i), "vertical") for i in range(1, n)]
    for i in range(1, n - 1):
        mem.append(Member(t(i), i + 1, "diagonal") if i < n // 2 else Member(t(i + 1), i, "diagonal"))
    res = [PlanarTruss(nodes, [Member(m.a, m.b, m.group, m.chord, m.inward) for m in mem], sec, y0=s * Yt).build() for s in (1, -1)]
    groups = {k: res[0]["members"][k] + res[1]["members"][k] for k in res[0]["members"]}
    # hệ mặt cầu: dầm ngang dưới mọi nút cánh dưới (mặt trên z = 0), dầm dọc, bản bê tông
    hf, hs, ts = 900.0, 500.0, 250.0
    fb = K.Solid.union_all([i_beam_y(x, -(Yt + 350.0), Yt + 350.0, 0.0, hf, 300.0, 16.0, 28.0) for x, _ in nodes[:n + 1]])
    y_s = np.linspace(-(Wd / 2 - 600.0), Wd / 2 - 600.0, 4)
    strs = K.Solid.union_all([i_beam_x(y, x0, x0 + S, hs, hs, 220.0, 11.0, 18.0) for y in y_s])
    slab = box_at(x0, x0 + S, -Wd / 2, Wd / 2, hs, hs + ts)
    pave = box_at(x0, x0 + S, -Wd / 2 + 400.0, Wd / 2 - 400.0, hs + ts, hs + ts + 70.0)
    curbs = K.Solid.union_all([box_at(x0, x0 + S, s * (Wd / 2 - 400.0), s * Wd / 2, hs + ts, hs + ts + 250.0) for s in (1, -1)])
    rail = K.Solid.union_all([railings(x0, x0 + S, s * (Wd / 2 - 150.0), hs + ts + 250.0) for s in (1, -1)])
    # gối + mố
    z_seat = -hf - 100.0
    pads = K.Solid.union_all([box_at(x - 250.0, x + 250.0, s * Yt - 300.0, s * Yt + 300.0, z_seat, -hf) for x in (x0, x0 + S) for s in (1, -1)])
    _abutments(b, [x0, x0 + S], 2 * Yt + 1500.0, z_seat, 6000.0, hs + ts, [-1, 1])
    b.add("bearings", "Gối cầu cao su bản thép (4)", "Elastomeric bearings", "bearing_pad", Shape(pads, "rubber", 35.0), parent_id="abutments",
          required=True, aliases=["gối cầu", "gối cao su", "bearing"], function="Gối cao su bản thép dưới đầu dầm ngang đầu nhịp.", position_tag="bottom")
    b.add("floor_beams", f"Dầm ngang ({n + 1}) + dầm dọc (4)", "Floor beams & stringers", "floor_beam",
          [Shape(fb, "paint_secondary", 35.0), Shape(strs, "paint_secondary", 35.0)], parent_id="bearings", required=True,
          aliases=["dầm ngang", "dầm dọc", "hệ mặt cầu", "floor beam", "stringer"], function="Dầm ngang I900 tại mọi nút + 4 dầm dọc I500 đỡ bản mặt cầu.",
          position_tag="bottom", explode_dir=(0, 0, -1), explode_distance=2500.0, explode_order=4)
    b.add("deck", "Bản mặt cầu + gờ + lan can", "Deck slab", "deck",
          [Shape(slab, "concrete", 35.0), Shape(pave, "asphalt", 35.0), Shape(curbs, "concrete", 35.0), Shape(rail, "galvanized", 35.0)],
          parent_id="floor_beams", required=True, aliases=["mặt cầu", "bản mặt cầu", "lan can", "gờ chắn bánh", "deck", "mặt đường"],
          function=f"Bản bê tông 250 mm rộng {Wd / 1000:g} m, lớp bê tông nhựa, gờ chắn bánh, lan can thép mạ kẽm.",
          position_tag="center", explode_dir=(0, 0, 1), explode_distance=H + 2000.0, explode_order=1, dimensions={"width": Wd})
    b.add("bottom_chord", "Thanh cánh dưới (2 giàn)", "Bottom chords", "truss_member", Shape(groups["bottom_chord"], "paint_primary", 35.0),
          parent_id="floor_beams", required=True, aliases=["thanh cánh dưới", "cánh dưới", "bottom chord"], function=f"2L{Lc:g}×{tc:g}.",
          position_tag="bottom", explode_dir=(0, 0, 1), explode_distance=0.3 * H, explode_order=3)
    gus = res[0]["gussets"] + res[1]["gussets"]
    b.add("gussets", f"Bản mã ({res[0]['n_gussets'] * 2} nút)", "Gusset plates", "gusset", Shape(gus, "paint_secondary", 35.0),
          parent_id="bottom_chord", required=True, aliases=["bản mã", "gusset"], function=f"Bản mã dày {g:g} mm.", position_tag="center",
          explode_dir=(0, 0, 1), explode_distance=0.2 * H, explode_order=2)
    for grp, vi in (("top_chord", "Thanh cánh trên + thanh xiên đầu"), ("vertical", "Thanh đứng"), ("diagonal", "Thanh xiên")):
        b.add(grp, vi + " (2 giàn)", grp, "truss_member", Shape(groups[grp], "paint_primary", 35.0), parent_id="gussets", required=True,
              aliases=[vi.lower(), "thanh giàn", grp.replace("_", " ")], function=f"Thép góc đôi {'2L200×20' if grp == 'top_chord' else '2L150×15'}.",
              position_tag="top" if grp == "top_chord" else "center", explode_dir=(0, 0, 1), explode_distance=0.35 * H, explode_order=2)
    bolts = res[0]["bolts"] + res[1]["bolts"]
    nuts = res[0]["nuts"] + res[1]["nuts"]
    b.add("bolts", f"Bu-lông M{sec['d']:g} ({res[0]['n_bolts'] * 2} bộ)", "Bolts", "bolt",
          [Shape(bolts, "galvanized", 35.0, extra={"simplify": False}), Shape(nuts, "galvanized", 35.0, extra={"simplify": False})],
          parent_id="gussets", required=True, aliases=["bu lông", "bulong", "đai ốc", "bolt"], function="Bu-lông cường độ cao 10.9 M24.",
          position_tag="center", explode_dir=(0, 1, 0), explode_distance=1500.0, explode_order=1)
    # thanh chống ngang tại mỗi nút trên, tì lên mặt cánh ngang hai thanh cánh trên (trên đầu bu-lông/đai ốc)
    ys = Yt + g / 2 + Lc
    struts = K.Solid.union_all([box_at(x - 150.0, x + 150.0, -ys, ys, H, H + 300.0) for x, _z in nodes[n + 1:]])
    b.add("top_struts", "Thanh chống ngang đỉnh giàn", "Top lateral struts", "strut", Shape(struts, "paint_primary", 35.0), parent_id="top_chord",
          required=True, aliases=["thanh chống", "giằng ngang", "strut", "giằng gió"], function="Thanh chống ngang hộp 300 tại các nút trên, giữ ổn định cánh trên.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=0.5 * H, explode_order=1)
    b.note_stage(1, "Nhấc bản mặt cầu, tháo bu-lông, thanh chống")
    b.note_stage(2, "Tháo thanh giàn, bản mã")
    b.note_stage(3, "Nhấc thanh cánh dưới")
    b.note_stage(4, "Hạ hệ dầm mặt cầu khỏi gối")
    b.metadata["contacts"] = []
    return {"truss_height_mm": H, "panels": n, "truss_planes_y_mm": Yt, "n_gussets": 2 * res[0]["n_gussets"], "n_bolts": 2 * res[0]["n_bolts"],
            "chord_section": [Lc, tc], "gusset_t_mm": g, "bearings": [[x, s * Yt, z_seat] for x in (x0, x0 + S) for s in (1, -1)],
            "standard": "Giàn Pratt chạy dưới, thép góc đôi, bu-lông 10.9; H ≈ L/7; tải trọng chưa kiểm toán (TCVN 11823)",
            "contacts": b.metadata["contacts"]}


def _cable_stayed(b: AssemblyBuilder, S: float, Wd: float) -> dict:
    side = 0.4 * S
    Ltot = S + 2 * side
    Zd = 9000.0                                                        # mặt trên bản mặt cầu
    hg, bg = 1400.0, 900.0                                             # dầm hộp biên
    yg = Wd / 2 + bg / 2
    z_bot = Zd - 250.0 - hg
    # mặt cầu
    girders = K.Solid.union_all([box_at(-Ltot / 2, Ltot / 2, s * (yg - bg / 2), s * (yg + bg / 2), z_bot, Zd - 250.0) -
                                 box_at(-Ltot / 2 - 1, Ltot / 2 + 1, s * (yg - bg / 2 + 20.0), s * (yg + bg / 2 - 20.0), z_bot + 20.0, Zd - 270.0)
                                 for s in (1, -1)])
    xs_cb = np.arange(-Ltot / 2 + 2500.0, Ltot / 2 - 2000.0, 5000.0)
    cross = K.Solid.union_all([i_beam_y(x, -(yg - bg / 2), yg - bg / 2, Zd - 250.0, 1000.0, 300.0, 14.0, 24.0) for x in xs_cb])
    slab = box_at(-Ltot / 2, Ltot / 2, -(yg + bg / 2), yg + bg / 2, Zd - 250.0, Zd)
    pave = box_at(-Ltot / 2, Ltot / 2, -Wd / 2 + 400.0, Wd / 2 - 400.0, Zd, Zd + 70.0)
    curbs = K.Solid.union_all([box_at(-Ltot / 2, Ltot / 2, s * (Wd / 2 - 400.0), s * Wd / 2, Zd, Zd + 250.0) for s in (1, -1)])
    rail = K.Solid.union_all([railings(-Ltot / 2, Ltot / 2, s * (Wd / 2 - 150.0), Zd + 250.0) for s in (1, -1)])
    # tháp chữ H
    Hp = Zd + 0.25 * S
    y_leg = yg + bg / 2 + 100.0 + 900.0                                # mép trong chân tháp cách dầm biên 100 mm
    towers = []
    nc = max(3, round(S / 2 / 9000.0))
    cables, anchors_d = [], []
    for xp in (-S / 2, S / 2):
        legs = [K.hull([box_at(xp - 1300.0, xp + 1300.0, s * (y_leg - 900.0), s * (y_leg + 900.0), 1500.0, 1501.0),
                        box_at(xp - 900.0, xp + 900.0, s * (y_leg - 700.0), s * (y_leg + 700.0), Hp - 1.0, Hp)]) for s in (1, -1)]
        lower = box_at(xp - 1200.0, xp + 1200.0, -y_leg, y_leg, z_bot - 1800.0, z_bot)
        upper = box_at(xp - 800.0, xp + 800.0, -y_leg, y_leg, Hp - 3500.0, Hp - 2000.0)
        footing = box_at(xp - 4000.0, xp + 4000.0, -y_leg - 2000.0, y_leg + 2000.0, 0.0, 1500.0)
        towers.append((xp, K.Solid.union_all(legs + [lower, upper, footing])))
        # dây: nc dây mỗi phía, neo trên thân tháp từ dưới xà trên xuống
        for k in range(nc):
            zp = Hp - 4500.0 - (nc - 1 - k) * 1400.0                    # dây xa nhất neo cao nhất (bán rẻ quạt, không cắt nhau)
            for side_s in (-1, 1):
                main = (side_s > 0) == (xp < 0)                                 # phía nhịp chính (về giữa cầu)
                xa = xp + side_s * (k + 1) / (nc + 0.5) * (S / 2 if main else side)
                for s in (1, -1):
                    pa = np.array([xp + side_s * 500.0, s * (y_leg - 450.0), zp])      # neo trong thân tháp
                    pd = np.array([xa, s * yg, Zd - 250.0 - 0.3 * hg])
                    cables.append(K.tube(np.array([pa - (pd - pa) / np.linalg.norm(pd - pa) * 300.0, pd + (pd - pa) / np.linalg.norm(pd - pa) * 500.0]),
                                         80.0, 16))
                    anchors_d.append(box_at(xa - 400.0, xa + 400.0, s * (yg - 300.0), s * (yg + 300.0), Zd, Zd + 350.0))
    pier_W = 2 * yg + 2000.0
    _abutments(b, [-Ltot / 2, Ltot / 2], pier_W, z_bot - 100.0, z_bot - 900.0, Zd, [-1, 1])       # móng mố chạm đất (z = 0)
    pads = K.Solid.union_all([box_at(x - 250.0, x + 250.0, s * yg - 300.0, s * yg + 300.0, z_bot - 100.0, z_bot) for x in (-Ltot / 2 + 300.0, Ltot / 2 - 300.0)
                              for s in (1, -1)])
    b.add("bearings", "Gối cầu (mố)", "Bearings", "bearing_pad", Shape(pads, "rubber", 35.0), parent_id="abutments", required=True,
          aliases=["gối cầu", "gối", "bearing"], function="Gối cao su bản thép tại mố.", position_tag="bottom")
    for i, (xp, tw) in enumerate(towers):
        b.add(f"pylon_{i + 1}", f"Tháp cầu {i + 1} (chữ H)", "Pylon", "pylon", Shape(tw, "concrete", 35.0), parent_id=None,
              required=True, aliases=["tháp cầu", "trụ tháp", "pylon", f"tháp {i + 1}", "móng tháp"],
              function=f"Tháp bê tông chữ H cao {Hp / 1000:.1f} m, xà dưới đỡ dầm, xà trên, vùng neo dây.", position_tag="center",
              dimensions={"height": Hp})
    b.add("deck", "Dầm hộp biên + dầm ngang + bản mặt cầu", "Deck", "deck",
          [Shape(slab, "concrete", 35.0), Shape(pave, "asphalt", 35.0), Shape(curbs, "concrete", 35.0), Shape(rail, "galvanized", 35.0),
           Shape(girders, "paint_primary", 35.0), Shape(cross, "paint_secondary", 35.0), Shape(K.Solid.union_all(anchors_d), "paint_secondary", 35.0)],
          parent_id="pylon_1", required=True, aliases=["mặt cầu", "dầm hộp", "dầm biên", "dầm ngang", "lan can", "deck"],
          function=f"Dầm hộp thép biên {bg:g}×{hg:g}, dầm ngang I1000 @5 m, bản bê tông 250 mm, tổng dài {Ltot / 1000:g} m.",
          position_tag="center", explode_dir=(0, 0, -1), explode_distance=3000.0, explode_order=2, dimensions={"width": Wd, "length": Ltot})
    b.add("stay_cables", f"Dây văng ({len(cables)} dây)", "Stay cables", "cable", Shape(K.Solid.union_all(cables), "hdpe", 35.0), parent_id="deck",
          required=True, aliases=["dây văng", "cáp văng", "dây cáp", "stay cable"], function="Dây văng bó cáp song song bọc HDPE Ø160, neo trong tháp và hộp neo dầm biên.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=0.3 * S, explode_order=1)
    b.note_stage(1, "Tháo dây văng")
    b.note_stage(2, "Hạ dầm mặt cầu")
    contacts = [["stay_cables", "pylon_*"], ["deck", "pylon_*"], ["deck", "bearings"]]
    b.metadata["contacts"] = contacts
    return {"pylon_height_mm": Hp, "cables": len(cables), "total_length_mm": Ltot, "side_span_mm": side,
            "bearings": [[x, s * yg, z_bot - 100.0] for x in (-Ltot / 2 + 300.0, Ltot / 2 - 300.0) for s in (1, -1)],
            "pylons_x": [-S / 2, S / 2],
            "standard": "Cầu dây văng 2 tháp chữ H, 2 mặt dây bán rẻ quạt, nhịp biên 0,4 L; chưa kiểm toán (TCVN 11823)", "contacts": contacts}


def _arch(b: AssemblyBuilder, S: float, Wd: float) -> dict:
    f = S / 6.0
    Ya = Wd / 2 + 900.0
    Zd = 0.0
    hg, bg = 1500.0, 1000.0
    # dầm căng (tie) biên + dầm ngang + bản
    ties = K.Solid.union_all([box_at(-S / 2 - 800.0, S / 2 + 800.0, s * (Ya - bg / 2), s * (Ya + bg / 2), Zd - hg, Zd) for s in (1, -1)])
    xs_cb = np.linspace(-S / 2, S / 2, max(7, round(S / 5000.0) + 1))
    cross = K.Solid.union_all([i_beam_y(x, -(Ya - bg / 2), Ya - bg / 2, Zd - 250.0, 1000.0, 300.0, 14.0, 24.0) for x in xs_cb])
    slab = box_at(-S / 2 - 800.0, S / 2 + 800.0, -(Ya - bg / 2), Ya - bg / 2, Zd - 250.0, Zd)
    pave = box_at(-S / 2 - 800.0, S / 2 + 800.0, -Wd / 2 + 400.0, Wd / 2 - 400.0, Zd, Zd + 70.0)
    curbs = K.Solid.union_all([box_at(-S / 2 - 800.0, S / 2 + 800.0, s * (Wd / 2 - 400.0), s * (Ya - bg / 2), Zd, Zd + 250.0) for s in (1, -1)])
    rail = K.Solid.union_all([railings(-S / 2 - 800.0, S / 2 + 800.0, s * (Wd / 2 - 150.0), Zd + 250.0) for s in (1, -1)])
    # sườn vòm
    hr, br = 1200.0, 900.0
    xs = np.linspace(-S / 2, S / 2, 61)
    ribs = []
    for s in (1, -1):
        path = np.column_stack([xs, np.full(len(xs), s * Ya), Zd + f * (1 - (2 * xs / S) ** 2) - hr / 2 + 0.0])
        ribs.append(K.sweep(P.rounded_rect(hr, br, 60.0, 3), path))         # (cao trong mặt vòm, rộng theo Y)
    nh = max(7, round(S / 6000.0))
    xh = [-S / 2 + (k + 1) * S / (nh + 1) for k in range(nh)]
    hangers = []
    for x in xh:
        zr = Zd + f * (1 - (2 * x / S) ** 2) - hr
        for s in (1, -1):
            hangers.append(K.cylinder(45.0, zr - Zd + 200.0, segments=16).translate(x, s * Ya, Zd - 50.0))
    # giằng gió ở vùng vòm cao hơn tĩnh không 6 m
    xb = [x for x in xh if f * (1 - (2 * x / S) ** 2) - hr > 6500.0]
    braces = K.Solid.union_all([box_at(x - 300.0, x + 300.0, -(Ya - br / 2 + 50.0), Ya - br / 2 + 50.0,
                                       Zd + f * (1 - (2 * x / S) ** 2) - hr / 2 - 400.0, Zd + f * (1 - (2 * x / S) ** 2) - hr / 2 + 400.0) for x in xb]) if xb else None
    z_seat = Zd - hg - 100.0
    _abutments(b, [-S / 2, S / 2], 2 * Ya + 2500.0, z_seat, 6000.0, Zd, [-1, 1])
    pads = K.Solid.union_all([box_at(x - 350.0, x + 350.0, s * Ya - 400.0, s * Ya + 400.0, z_seat, Zd - hg) for x in (-S / 2, S / 2) for s in (1, -1)])
    b.add("bearings", "Gối cầu (4)", "Bearings", "bearing_pad", Shape(pads, "rubber", 35.0), parent_id="abutments", required=True,
          aliases=["gối cầu", "bearing"], function="Gối chậu thép dưới chân vòm.", position_tag="bottom")
    b.add("deck", "Dầm căng + dầm ngang + bản mặt cầu", "Tie girders & deck", "deck",
          [Shape(slab, "concrete", 35.0), Shape(pave, "asphalt", 35.0), Shape(curbs, "concrete", 35.0), Shape(rail, "galvanized", 35.0),
           Shape(ties, "paint_secondary", 35.0), Shape(cross, "paint_secondary", 35.0)], parent_id="bearings", required=True,
          aliases=["mặt cầu", "dầm căng", "thanh căng", "dầm ngang", "deck", "lan can"], function="Dầm hộp căng chịu lực đẩy ngang của vòm, bản bê tông.",
          position_tag="center", explode_dir=(0, 0, -1), explode_distance=3000.0, explode_order=3, dimensions={"width": Wd})
    b.add("arch_ribs", "Sườn vòm (2)", "Arch ribs", "arch", Shape(K.Solid.union_all(ribs), "paint_primary", 35.0), parent_id="deck", required=True,
          aliases=["vòm", "sườn vòm", "arch", "vòm thép"], function=f"Sườn vòm hộp thép parabol, đường tên f = L/6 = {f / 1000:.1f} m.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=0.3 * f, explode_order=2, dimensions={"rise": f})
    b.add("hangers", f"Dây treo ({2 * nh})", "Hangers", "hanger", Shape(K.Solid.union_all(hangers), "galvanized", 35.0), parent_id="arch_ribs",
          required=True, aliases=["dây treo", "thanh treo", "hanger"], function="Dây treo thép cường độ cao Ø90 cách đều.", position_tag="center",
          explode_dir=(0, 1, 0), explode_distance=1500.0, explode_order=1)
    if braces is not None:
        b.add("wind_bracing", "Thanh giằng gió", "Wind bracing", "strut", Shape(braces, "paint_primary", 35.0), parent_id="arch_ribs", required=True,
              aliases=["giằng gió", "thanh giằng", "bracing"], function="Thanh giằng ngang giữa hai sườn vòm (trên tĩnh không 6 m).",
              position_tag="top", explode_dir=(0, 0, 1), explode_distance=2000.0, explode_order=1)
    b.note_stage(1, "Tháo dây treo, giằng gió")
    b.note_stage(2, "Nhấc sườn vòm")
    b.note_stage(3, "Hạ dầm mặt cầu")
    contacts = [["hangers", "deck"], ["arch_ribs", "deck"], ["wind_bracing", "arch_ribs"]]
    b.metadata["contacts"] = contacts
    return {"arch_rise_mm": f, "hangers": 2 * nh, "rib_section": [br, hr],
            "bearings": [[x, s * Ya, z_seat] for x in (-S / 2, S / 2) for s in (1, -1)],
            "standard": "Cầu vòm thép có thanh căng, sườn parabol f = L/6, dây treo đứng; chưa kiểm toán (TCVN 11823)", "contacts": contacts}
