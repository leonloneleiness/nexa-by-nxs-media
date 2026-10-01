"""Tản nhiệt: (a) tản tháp CPU — đế đồng mạ niken + khối kẹp nhôm, N ống dẫn nhiệt Ø6 chữ U (đoạn nằm trong rãnh đế, hai
nhánh đứng xuyên chồng lá), chồng lá nhôm dày 0,4 mm bước 1,8 mm có lỗ ống (lỗ khít, không giao khối), nắp đỉnh + đầu ống,
quạt 120 mm kẹp bằng 2 kẹp dây thép, thanh gá lắp + vít lò xo; (b) tản nhôm đùn — đế + lá liền khối (profile đùn), tùy chọn
quạt 60/80 mm bắt vít lên đỉnh lá.
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.generation.templates.fan import fan_parts
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec


def box_at(x0, x1, y0, y1, z0, z1) -> K.Solid:
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    z0, z1 = sorted((z0, z1))
    return K.box(x1 - x0, y1 - y0, z1 - z0).translate((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    kind = p.get("heatsink_type", "tower")
    with_fan = bool(p.get("fan", True))
    mats = MC.tech_materials(spec, primary="#c9ced4", secondary="#1b1d21", accent="#b87333")
    mats["copper_ni"] = M.material("copper_ni", "metal", "#c7c9cc", 0.95, 0.25, name="Đồng mạ niken")
    mats["copper_pipe"] = M.material("copper_pipe", "metal", "#b87333", 0.95, 0.3, name="Ống đồng")
    b = AssemblyBuilder(spec.name or ("Tản nhiệt tháp CPU" if kind == "tower" else "Tản nhiệt nhôm đùn"), "heatsink", mats)
    contacts: list[list[str]] = []
    if kind == "tower":
        n = max(2, int(p.get("heat_pipes", 4)))
        rp = 3.0                                                       # ống Ø6
        pitch_x = 8.5
        xs = [(i - (n - 1) / 2) * pitch_x for i in range(n)]
        yl = 15.0                                                      # hai nhánh đứng ở y = ±15
        Rb = 8.0
        zb = 6.0                                                       # tâm đoạn nằm của ống (mặt trên đế đồng)
        zf0, H_f = 42.0, 140.0
        zf1 = zf0 + H_f
        FW, FD = 125.0, 50.0
        # đế đồng + khối kẹp nhôm (rãnh ống khít)
        base = box_at(-20.0, 20.0, -20.0, 20.0, 0.0, 6.0)
        clamp = box_at(-20.0, 20.0, -20.0, 20.0, 6.0, 16.0)
        pipes, cores = [], []
        for x in xs:
            pts = [(x, -yl, zf1 - 2.0), (x, -yl, zb + Rb)]
            for a in np.linspace(0, math.pi / 2, 7)[1:]:
                pts.append((x, -yl + Rb - Rb * math.cos(a), zb + Rb - Rb * math.sin(a)))
            pts.append((x, yl - Rb, zb))
            for a in np.linspace(0, math.pi / 2, 7)[1:]:
                pts.append((x, yl - Rb + Rb * math.sin(a), zb + Rb - Rb * math.cos(a)))
            pts.append((x, yl, zf1 - 2.0))
            path = np.array(pts)
            pipes.append(K.tube(path, rp, 20))
            cores.append(K.tube(path, rp, 20))
        pipe_s = K.Solid.union_all(pipes)
        core_s = K.Solid.union_all(cores)
        base = base - core_s
        clamp = clamp - core_s
        # chồng lá
        pitch_f, tf = 1.8, 0.4
        nf = int(H_f / pitch_f)
        fins = K.Solid.union_all([box_at(-FW / 2, FW / 2, -FD / 2, FD / 2, zf0 + i * pitch_f, zf0 + i * pitch_f + tf) for i in range(nf)])
        notch = K.Solid.union_all([K.box(8.0, 30.0, H_f + 10).rotate(0, 0, 45).translate(sx * FW / 2, sy * FD / 2, zf0 + H_f / 2)
                                   for sx in (1, -1) for sy in (1, -1)])
        fins = fins - notch - core_s
        # nắp đỉnh (khoét lỗ đầu ống) + mũ ống
        cap = box_at(-FW / 2 - 1.0, FW / 2 + 1.0, -FD / 2 - 1.0, FD / 2 + 1.0, zf1, zf1 + 3.0)
        cap = cap - K.Solid.union_all([K.cylinder(rp, 10.0, segments=20).translate(x, sy * yl, zf1 - 3.0) for x in xs for sy in (1, -1)])
        pipe_caps = K.Solid.union_all([K.cylinder(rp, 2.0, segments=20).translate(x, sy * yl, zf1 - 2.0) for x in xs for sy in (1, -1)])
        # đỡ chồng lá: 2 cột nhôm từ khối kẹp lên lá dưới cùng (ống chịu lực chính)
        posts = K.Solid.union_all([box_at(-FW / 2 + 10.0, -FW / 2 + 16.0, -3.0, 3.0, 16.0, zf0 + 0.01) - core_s,
                                   box_at(FW / 2 - 16.0, FW / 2 - 10.0, -3.0, 3.0, 16.0, zf0 + 0.01) - core_s])
        b.add("base", "Đế đồng + khối kẹp ống", "Copper base & clamp", "heatsink_base",
              [Shape(base, "copper_ni", 35.0), Shape(clamp, "aluminum", 35.0)], required=True,
              aliases=["đế tản nhiệt", "đế đồng", "khối kẹp", "base"], function="Đế đồng mạ niken phẳng tiếp xúc CPU, khối kẹp nhôm ôm ống.",
              position_tag="bottom", dimensions={"contact": 40.0})
        b.add("heat_pipes", f"Ống dẫn nhiệt ({n} × Ø6)", "Heat pipes", "heat_pipe", [Shape(pipe_s + pipe_caps, "copper_pipe", 35.0)], parent_id="base",
              required=True, aliases=["ống đồng", "ống dẫn nhiệt", "heat pipe", "heatpipe"], function=f"{n} ống đồng Ø6 chữ U, lõi mao dẫn, chạy xuyên chồng lá.",
              position_tag="center", explode_dir=(0, 0, 1), explode_distance=40.0, explode_order=2, dimensions={"diameter": 6.0})
        b.add("fins", f"Chồng lá nhôm ({nf} lá, bước {pitch_f:g} mm)", "Fin stack", "fins",
              [Shape(fins, "aluminum", 35.0), Shape(cap, "paint_secondary", 35.0), Shape(posts, "aluminum", 35.0)], parent_id="heat_pipes", required=True,
              aliases=["lá tản nhiệt", "cánh tản nhiệt", "chồng lá", "fins", "nắp tản"], function=f"{nf} lá nhôm 0,4 mm ép khít ống, bước {pitch_f:g} mm, nắp đỉnh.",
              position_tag="top", explode_dir=(0, 0, 1), explode_distance=120.0, explode_order=3, dimensions={"width": FW, "depth": FD, "height": H_f})
        contacts.append(["fins", "base"])
        brk = box_at(-45.0, 45.0, -6.0, 6.0, 16.0, 19.0) - core_s
        screws = K.Solid.union_all([K.cylinder(2.0, 25.0, segments=16).translate(sx * 39.0, 0, -6.0) + K.cylinder(4.0, 4.0, segments=20).translate(sx * 39.0, 0, 19.0) +
                                    MC.orient(K.tube(MC.helix_path(3.5, [(5.0, 1.2)], z0=0.0, per_turn=12), 0.5, 6), (sx * 39.0, 0, 19.0 + 4.0), (0, 0, 1))
                                    for sx in (1, -1)])
        b.add("mount", "Thanh gá + vít lò xo", "Mounting bracket", "bracket", [Shape(brk, "steel_dark", 35.0), Shape(screws, "steel", 35.0)], parent_id="base",
              required=True, aliases=["thanh gá", "gá lắp", "vít lò xo", "bracket"], function="Thanh gá thép + 2 vít lò xo khoảng tâm 78 mm (LGA1700).",
              position_tag="bottom", explode_dir=(0, 0, 1), explode_distance=25.0, explode_order=1)
        contacts.append(["mount", "heat_pipes"])
        meta = {"heat_pipes": n, "fin_pitch_mm": pitch_f, "fin_t_mm": tf, "fins": nf, "pipe_d_mm": 2 * rp, "fin_stack_mm": [FW, FD, H_f],
                "fin_z0_mm": zf0}
        if with_fan:
            F = fan_parts(120, 7)
            yf = FD / 2 + 0.5                                           # quạt áp mặt bên chồng lá, thổi −Y qua khe lá
            to_side = lambda s_: s_.rotate(90, 0, 0).translate(0, yf + F["T"], zf0 + H_f / 2)   # noqa: E731
            fan_frame = to_side(F["frame"] + F["support"])
            fan_rot = to_side(F["rotor"])
            clips = K.Solid.union_all([K.tube(np.array([[sx * 60.0, yf + F["T"] - 2.0, zf0 + H_f / 2 + sz * 57.0], [sx * 64.0, yf + F["T"] - 2.0, zf0 + H_f / 2 + sz * 57.0],
                                                        [sx * 64.0, -FD / 2 + 6.0, zf0 + H_f / 2 + sz * 57.0], [sx * 60.0, -FD / 2 + 6.0, zf0 + H_f / 2 + sz * 57.0]]), 0.8, 8)
                                       for sx in (1, -1) for sz in (1, -1)])
            b.add("fan", "Quạt 120 mm + kẹp dây", "120 mm fan & clips", "fan_frame",
                  [Shape(fan_frame, "plastic_black", 35.0), Shape(fan_rot, "plastic_black", 35.0), Shape(clips, "steel", 35.0)], parent_id="fins",
                  required=True, aliases=["quạt", "quạt tản nhiệt", "kẹp quạt", "fan"], function="Quạt 120 mm PWM, kẹp dây thép vào rãnh lá.",
                  position_tag="side", explode_dir=(0, 1, 0), explode_distance=80.0, explode_order=1)
            contacts.append(["fan", "fins"])
    else:
        L, W, tb, hf, tfin, pf = 100.0, 80.0, 6.0, 30.0, 1.5, 5.0
        nf = int((W - tfin) / pf) + 1
        prof = [box_at(0, L, -W / 2, W / 2, 0, tb)] + [box_at(0, L, -W / 2 + i * pf, -W / 2 + i * pf + tfin, tb - 0.01, tb + hf) for i in range(nf)]
        body = K.Solid.union_all(prof).translate(-L / 2, 0, 0)
        pad = box_at(-20.0, 20.0, -20.0, 20.0, -0.5, 0.0)
        body = body - box_at(-21.0, 21.0, -21.0, 21.0, -1.0, 0.0)          # hốc dán tấm tản nhiệt
        b.add("base", "Tản nhôm đùn (đế + lá liền)", "Extruded heatsink", "heatsink_base",
              [Shape(body, "aluminum_anodized", 35.0), Shape(pad, "rubber_gray", 35.0)],
              required=True, aliases=["tản nhôm", "tản nhiệt", "lá tản nhiệt", "heatsink"], function=f"Nhôm 6063 đùn anod đen, {nf} lá dày {tfin:g} mm bước {pf:g} mm.",
              position_tag="center", dimensions={"length": L, "width": W})
        meta = {"fins": nf, "fin_pitch_mm": pf, "fin_t_mm": tfin, "base_t_mm": tb, "fin_h_mm": hf, "heat_pipes": 0}
        if with_fan:
            size = 60 if W < 70 else 80
            F = fan_parts(size, 7)
            fz = tb + hf
            fan_all = (F["frame"] + F["support"]).translate(0, 0, fz)
            rot = F["rotor"].translate(0, 0, fz)
            hs = F["hole_spacing"]
            sc = K.Solid.union_all([K.cylinder(1.4, F["T"] + 8.0, segments=12).translate(sx * hs / 2, sy * hs / 2, fz - 8.0) +
                                    K.cylinder(2.8, 2.0, segments=16).translate(sx * hs / 2, sy * hs / 2, fz + F["T"]) for sx in (1, -1) for sy in (1, -1)])
            b.add("fan", f"Quạt {size} mm", "Fan", "fan_frame", [Shape(fan_all, "plastic_black", 35.0), Shape(rot, "plastic_black", 35.0), Shape(sc, "steel", 35.0)],
                  parent_id="base", required=True, aliases=["quạt", "quạt tản nhiệt", "fan"], function=f"Quạt {size} mm bắt 4 vít vào khe lá.",
                  position_tag="top", explode_dir=(0, 0, 1), explode_distance=50.0, explode_order=1)
            contacts.append(["fan", "base"])
    b.note_stage(1, "Tháo quạt, gá lắp")
    b.note_stage(2, "Tháo ống dẫn nhiệt")
    b.note_stage(3, "Tách chồng lá")
    b.place_on_ground(center_xy=True)
    b.metadata.update({"heatsink_type": kind, **meta, "standard": "Tản tháp ống đồng Ø6 (kiểu 4 ống, lá 0,4 mm bước 1,8 mm); nhôm 6063 đùn",
                       "strict_overlap": True, "contacts": contacts})
    return b.build()
