"""Giàn thép mái (Pratt / Howe / Warren cánh song song, Fink tam giác) đặt trên hai cột thép H có móng bê tông.

Thanh thép góc đôi 2L kẹp bản mã ở mọi nút, bu-lông cường độ cao + đai ốc + vòng đệm xuyên lỗ (bộ dựng
`structures.PlanarTruss`). Tiết diện theo nhịp: ≤ 12 m 2L75×8 / 2L63×6, bản mã 10, M16; ≤ 20 m 2L100×10 / 2L75×8, bản mã 12,
M20; > 20 m 2L125×12 / 2L90×9, bản mã 14, M22 (thép góc đều cạnh TCVN 1656 / EN 10056-1).
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

NAMES = {"pratt": "Giàn Pratt", "howe": "Giàn Howe", "warren": "Giàn Warren", "fink": "Giàn Fink (tam giác)"}


def geometry(kind: str, S: float, H: float, n: int) -> tuple[list, list[Member]]:
    """Nút (x, z) và thanh; z = 0 là mép dưới thanh cánh dưới."""
    a = S / n
    mem: list[Member] = []
    if kind in ("pratt", "howe"):
        B = [(i * a, 0.0) for i in range(n + 1)]
        T = [(i * a, H) for i in range(n + 1)]
        nodes = B + T
        t = lambda i: n + 1 + i                                        # noqa: E731
        for i in range(n):
            mem.append(Member(i, i + 1, "bottom_chord", chord=True, inward=(0, 1)))
            mem.append(Member(t(i), t(i + 1), "top_chord", chord=True, inward=(0, -1)))
        for i in range(n + 1):
            mem.append(Member(i, t(i), "vertical"))
        for i in range(n):
            left = i < n // 2
            if kind == "pratt":                                        # xiên chịu kéo dốc xuống về giữa nhịp
                mem.append(Member(t(i), i + 1, "diagonal") if left else Member(t(i + 1), i, "diagonal"))
            else:                                                      # Howe: xiên chịu nén dốc lên về giữa nhịp
                mem.append(Member(i, t(i + 1), "diagonal") if left else Member(i + 1, t(i), "diagonal"))
    elif kind == "warren":
        B = [(i * a, 0.0) for i in range(n + 1)]
        T = [((i + 0.5) * a, H) for i in range(n)]
        nodes = B + T
        t = lambda i: n + 1 + i                                        # noqa: E731
        for i in range(n):
            mem.append(Member(i, i + 1, "bottom_chord", chord=True, inward=(0, 1)))
            mem.append(Member(i, t(i), "diagonal"))
            mem.append(Member(t(i), i + 1, "diagonal"))
        for i in range(n - 1):
            mem.append(Member(t(i), t(i + 1), "top_chord", chord=True, inward=(0, -1)))
    else:                                                              # Fink: W trong hai nửa kèo
        nodes = [(0.0, 0.0), (S / 3, 0.0), (2 * S / 3, 0.0), (S, 0.0), (S / 4, H / 2), (S / 2, H), (3 * S / 4, H / 2)]
        for a_, b_ in ((0, 1), (1, 2), (2, 3)):
            mem.append(Member(a_, b_, "bottom_chord", chord=True, inward=(0, 1)))
        for a_, b_ in ((0, 4), (4, 5), (5, 6), (6, 3)):
            mem.append(Member(a_, b_, "top_chord", chord=True, inward=(S / 2 - nodes[a_][0], -1.0)))
        for a_, b_ in ((4, 1), (1, 5), (5, 2), (2, 6)):
            mem.append(Member(a_, b_, "diagonal"))
    return nodes, mem


def h_column(h: float, b: float = 200.0, tw: float = 9.0, tf: float = 15.0) -> K.Solid:
    """Cột thép hình H (HEB 200): đùn theo Z từ 0 tới h."""
    prof = np.array([(-b / 2, -b / 2), (b / 2, -b / 2), (b / 2, -b / 2 + tf), (tw / 2, -b / 2 + tf), (tw / 2, b / 2 - tf),
                     (b / 2, b / 2 - tf), (b / 2, b / 2), (-b / 2, b / 2), (-b / 2, b / 2 - tf), (-tw / 2, b / 2 - tf),
                     (-tw / 2, -b / 2 + tf), (-b / 2, -b / 2 + tf)])
    return K.extrude(P.ensure_ccw(prof), h)


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    kind = p.get("truss_type", "pratt")
    S = float(p.get("span_mm", 12000.0))
    H = float(p.get("height_mm", S / 6))
    n = int(p.get("panels", 4))
    sec_key = "light" if S <= 12000 else ("medium" if S <= 20000 else "heavy")
    sec = SECTIONS[sec_key]
    mats = MC.tech_materials(spec, primary="#8d99ae", secondary="#2b2d42", accent="#ef233c")
    mats["concrete"] = M.material("concrete", "stone", "#a3a39b", 0.0, 0.85, name="Bê tông móng")
    mats["galvanized"] = M.material("galvanized", "metal", "#b9bec4", 0.85, 0.42, name="Thép mạ kẽm (bu-lông)")
    b = AssemblyBuilder(spec.name or f"{NAMES[kind]} nhịp {S / 1000:g} m", "steel_truss", mats)
    nodes, mem = geometry(kind, S, H, n)
    x0 = -S / 2
    nodes = [(x + x0, z) for x, z in nodes]
    # ---------- móng + cột ----------
    Hc, zp = 3000.0, 400.0
    Zt = zp + 20.0 + Hc + 20.0
    feet, cols, plates, anchors = [], [], [], []
    for xs in (x0, x0 + S):
        feet.append(K.chamfer_box(700.0, 700.0, zp, 20.0).translate(xs, 0, zp / 2))
        plates.append(K.box(400.0, 400.0, 20.0).translate(xs, 0, zp + 10.0))
        cols.append(h_column(Hc).rotate(0, 0, 90).translate(xs, 0, zp + 20.0))
        plates.append(K.box(320.0, 260.0, 20.0).translate(xs, 0, Zt - 10.0))
        for dx in (-140.0, 140.0):
            for dy in (-140.0, 140.0):
                anchors.append(K.cylinder(12.0, 60.0, segments=12).translate(xs + dx, dy, zp + 20.0) +
                               MC.orient(MC.hex_nut(24.0), [xs + dx, dy, zp + 20.0], (0, 0, 1)))
    b.add("foundation", "Móng bê tông (2 bệ)", "Concrete footings", "foundation", Shape(K.Solid.union_all(feet), "concrete", 40.0),
          required=True, aliases=["móng", "bệ móng", "móng bê tông", "foundation"], function="Bệ móng bê tông đỡ chân cột.",
          position_tag="bottom")
    b.add("columns", "Cột thép H + bản đế, bản đầu cột", "Steel columns", "column",
          [Shape(K.Solid.union_all(cols), "paint_secondary", 40.0), Shape(K.Solid.union_all(plates), "paint_secondary", 40.0),
           Shape(K.Solid.union_all(anchors), "galvanized", 40.0)], parent_id="foundation", required=True,
          aliases=["cột", "cột thép", "bản đế", "bu lông neo", "column"], function="Cột HEB200 cao 3 m, bản đế + 4 bu-lông neo M24, bản đầu cột đỡ giàn.",
          position_tag="bottom", explode_dir=(0, 0, -1), explode_distance=600.0, explode_order=5)
    # ---------- giàn ----------
    tr = PlanarTruss([(x, z + Zt) for x, z in nodes], mem, sec, y0=0.0)
    res = tr.build()
    Lc, tc = sec["chord"]
    Lw, tw = sec["web"]
    names = {"bottom_chord": ("Thanh cánh dưới", "Bottom chord", f"2L{Lc:g}×{tc:g}"), "top_chord": ("Thanh cánh trên", "Top chord", f"2L{Lc:g}×{tc:g}"),
             "vertical": ("Thanh đứng", "Verticals", f"2L{Lw:g}×{tw:g}"), "diagonal": ("Thanh xiên", "Diagonals", f"2L{Lw:g}×{tw:g}")}
    b.add("bottom_chord", names["bottom_chord"][0], names["bottom_chord"][1], "truss_member",
          Shape(res["members"]["bottom_chord"], "paint_primary", 40.0), parent_id="columns", required=True,
          aliases=["thanh cánh dưới", "cánh dưới", "thanh căng", "bottom chord", "thép góc"],
          function=f"Thanh cánh dưới {names['bottom_chord'][2]} (thép góc đôi).", position_tag="bottom",
          explode_dir=(0, 0, 1), explode_distance=0.2 * H + 300.0, explode_order=4, dimensions={"span": S})
    b.add("gussets", f"Bản mã ({res['n_gussets']} nút)", "Gusset plates", "gusset", Shape(res["gussets"], "paint_secondary", 40.0),
          parent_id="bottom_chord", required=True, aliases=["bản mã", "bản nút", "gusset", "tấm nối"],
          function=f"Bản mã dày {sec['g']:g} mm tại mọi nút, kẹp giữa hai thép góc.", position_tag="center",
          explode_dir=(0, -1, 0), explode_distance=400.0, explode_order=3)
    for grp in ("top_chord", "vertical", "diagonal"):
        if grp not in res["members"]:
            continue
        nm = names[grp]
        b.add(grp, nm[0], nm[1], "truss_member", Shape(res["members"][grp], "paint_primary", 40.0), parent_id="gussets", required=True,
              aliases=[nm[0].lower(), nm[1].lower(), "thanh giàn", "thép góc"] + (["cánh trên", "kèo"] if grp == "top_chord" else ["thanh bụng"]),
              function=f"{nm[0]} {nm[2]}.", position_tag="top" if grp == "top_chord" else "center",
              explode_dir=(0, 0, 1) if grp == "top_chord" else (0, 1, 0), explode_distance=0.25 * H + 300.0, explode_order=2)
    b.add("bolts", f"Bu-lông M{sec['d']:g} + đai ốc ({res['n_bolts']} bộ)", "Bolts & nuts", "bolt",
          [Shape(res["bolts"], "galvanized", 40.0, extra={"simplify": False}), Shape(res["nuts"], "galvanized", 40.0, extra={"simplify": False})],
          parent_id="gussets", required=True,
          aliases=["bu lông", "bulong", "đai ốc", "ốc", "bolt"], function=f"Bu-lông cường độ cao 8.8 M{sec['d']:g} + đai ốc + vòng đệm.",
          position_tag="center", explode_dir=(0, 1, 0), explode_distance=700.0, explode_order=1)
    b.note_stage(1, "Tháo bu-lông")
    b.note_stage(2, "Tháo thanh cánh trên, thanh bụng")
    b.note_stage(3, "Tháo bản mã")
    b.note_stage(4, "Nhấc thanh cánh dưới khỏi đầu cột")
    b.note_stage(5, "Hạ cột khỏi móng")
    sh = np.asarray(b.place_on_ground(center_xy=True), float)
    b.metadata.update({"truss_type": kind, "span_mm": S, "height_mm": H, "panels": n if kind != "fink" else 4, "section": sec_key,
                       "chord_section": [Lc, tc], "web_section": [Lw, tw], "gusset_t_mm": sec["g"], "bolt_d_mm": sec["d"],
                       "n_gussets": res["n_gussets"], "n_bolts": res["n_bolts"], "n_members": len(mem),
                       "supports": [[x0 + sh[0], sh[1], Zt + sh[2]], [x0 + S + sh[0], sh[1], Zt + sh[2]]],
                       "standard": "Thép góc đều cạnh TCVN 1656 / EN 10056-1; bu-lông 8.8 ISO 4014; bản mã kẹp giữa thép góc đôi",
                       "strict_overlap": True, "contacts": []})
    return b.build()
