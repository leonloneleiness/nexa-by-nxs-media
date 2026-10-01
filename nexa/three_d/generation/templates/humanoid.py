"""Robot hình người: đầu có kính che mặt, cổ, thân trên/bụng/hông, pin lưng, tay (vai – cánh tay – khuỷu – cẳng tay
– bàn tay) và chân (hông – đùi – gối – cẳng chân – cổ chân – bàn chân). Tư thế chữ A nhẹ để tay không chạm thân.

Mỗi khớp là một bộ phận có trục khớp (joint_axis). Tách theo trục lắp: khớp vai/hông tách ngang theo trục khớp,
các đoạn tay/chân tách dọc trục chi, đầu nhấc lên, pin lưng rút ra phía sau.
"""
from __future__ import annotations

import math
from typing import Callable, Sequence

import numpy as np

from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import details as D
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec


def limb(z_top: float, z_bot: float, w_top: float, w_bot: float, d_top: float, d_bot: float, bulge: float = 0.08,
         x_off: float = 0.0, samples: int = 14, ring: int = 40, exponent: float = 2.4) -> K.Solid:
    """Đoạn chi dọc trục Z (từ trên xuống): loft siêu elip với bụng cơ nhẹ ở 1/3 trên."""
    secs = []
    for t in np.linspace(0, 1, samples):
        z = z_top + (z_bot - z_top) * t
        swell = 1 + bulge * math.sin(math.pi * min(1.0, t * 1.4))
        w = (w_top + (w_bot - w_top) * t) * swell
        d = (d_top + (d_bot - d_top) * t) * swell
        prof = P.superellipse(d, w, exponent, ring)
        secs.append(np.column_stack([prof[:, 0] + x_off * math.sin(math.pi * t), prof[:, 1], np.full(ring, z)]))
    return K.loft(secs)


def joint_cyl(radius: float, width: float, axis: str = "y") -> K.Solid:
    j = K.revolve(P.fillet_polygon([(0, -width / 2), (radius, -width / 2), (radius, width / 2), (0, width / 2)],
                                   [0, radius * 0.25, radius * 0.25, 0], 5), segments=56)
    return j.rotate(90, 0, 0) if axis == "y" else (j.rotate(0, 90, 0) if axis == "x" else j)


def actuator(radius: float, width: float, axis: str, at: Sequence[float], housing: str = "aluminum_dark",
             place: Callable[[K.Solid], K.Solid] | None = None, bolts: int = 6) -> list[Shape]:
    """Cụm khớp servo thật: vỏ bo tròn + mặt bích màu nhấn hai bên + vòng ốc (ISO 7380) trên mỗi mặt."""
    body = joint_cyl(radius, width, "z")
    flange = K.cylinder(radius * 0.5, width * 0.06, segments=48).translate(0, 0, width / 2 - width * 0.02)
    flange = flange + flange.mirror((0, 0, 1))
    ang = np.radians(np.arange(bolts) * 360.0 / bolts + 15)
    pts = [(radius * 0.66 * math.cos(a), radius * 0.66 * math.sin(a)) for a in ang]
    ring = D.screws_at([(x, y, width / 2) for x, y in pts], (0, 0, 1), radius * 0.11) + \
        D.screws_at([(x, y, -width / 2) for x, y in pts], (0, 0, -1), radius * 0.11)

    def orient(s: K.Solid) -> K.Solid:
        s = s.rotate(90, 0, 0) if axis == "y" else (s.rotate(0, 90, 0) if axis == "x" else s)
        s = s.translate(*at)
        return place(s) if place is not None else s
    return [Shape(orient(body), housing, 40.0), Shape(orient(flange), "paint_accent", 40.0), Shape(orient(ring), "steel", 40.0)]


def seams(solid: K.Solid, zs: Sequence[float], H: float) -> K.Solid:
    """Rãnh ghép tấm vòng quanh đoạn chi/thân tại các cao độ z."""
    return solid - D.panel_lines(solid, [("z", z) for z in zs], width=0.0028 * H, depth=0.003 * H)


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    H = float(p.get("height_mm", 1650))
    style = spec.style or {}
    primary = M.color_from_name(style.get("primary_color"), "#e9ecef")
    secondary = M.color_from_name(style.get("secondary_color"), "#2b2e33")
    accent = M.color_from_name(style.get("accent_color"), "#22d3ee")
    mats = M.library(primary, secondary, accent)
    industrial = p.get("style") == "industrial"
    shell = "paint_primary"
    jmat = "aluminum_dark"
    b = AssemblyBuilder(spec.name or "Robot hình người", "humanoid", mats)
    z = {"ankle": 0.05 * H, "knee": 0.285 * H, "hip": 0.5 * H, "pelvis": 0.53 * H, "waist": 0.6 * H,
         "chest": 0.7 * H, "shoulder": 0.815 * H, "neck": 0.85 * H, "head": 0.925 * H}

    # ---------- thân trên (gốc cây lắp ráp) ----------
    secs = []
    ring = 56
    for t in np.linspace(0, 1, 16):
        zz = z["waist"] + 0.02 * H + t * (z["shoulder"] + 0.045 * H - z["waist"] - 0.02 * H)
        w = H * (0.2 + 0.1 * math.sin(math.pi * min(1.0, t * 0.9)) - 0.06 * t ** 4)
        d = H * (0.12 + 0.03 * math.sin(math.pi * t))
        prof = P.superellipse(d, w, 2.8 if not industrial else 4.0, ring)
        secs.append(np.column_stack([prof[:, 0] + 0.008 * H * t, prof[:, 1], np.full(ring, zz)]))
    torso = K.loft(secs)
    # tấm giáp ngực/bụng: rãnh ngang + rãnh dọc giữa, khe tản nhiệt hai bên ngực
    torso = torso - D.panel_lines(torso, [("z", z["chest"] - 0.045 * H), ("z", z["waist"] + 0.05 * H), ("y", 0.0)],
                                  width=0.003 * H, depth=0.004 * H)
    torso = torso - K.Solid.union_all([D.vent_cutter((0.078 * H, side * 0.075 * H, z["chest"] + 0.035 * H), (1, 0, 0), (0, 0, 1),
                                                     0.05 * H, 0.03 * H, 5, 0.012 * H) for side in (1, -1)])
    chest_light = K.rounded_box(0.012 * H, 0.06 * H, 0.02 * H, 0.006 * H).translate(0.075 * H, 0, z["chest"] + 0.02 * H)
    b.add("torso", "Thân trên", "Upper torso", "torso",
          [Shape(torso, shell, 45.0), Shape(chest_light, "led_white" if not accent else "paint_accent", 45.0)], required=True,
          aliases=["thân", "ngực", "thân trên", "torso", "chest", "thân chính", "lớp vỏ ngực"],
          function="Khung thân chịu lực, chứa bộ xử lý trung tâm và cảm biến IMU.", position_tag="center",
          dimensions={"height": round(0.24 * H, 1)})
    # ---------- pin lưng ----------
    pack = K.rounded_box(0.07 * H, 0.18 * H, 0.2 * H, 0.02 * H).translate(-0.095 * H, 0, z["chest"])
    vents = [K.box(0.02 * H, 0.14 * H, 0.006 * H).translate(-0.13 * H, 0, z["chest"] + dz) for dz in np.linspace(-0.06 * H, 0.06 * H, 6)]
    back_x = -0.13 * H                                     # mặt sau khối pin
    pack_screws = D.screws_at([(back_x, y, zz) for y in (0.075 * H, -0.075 * H) for zz in (z["chest"] + 0.085 * H,
                                                                                        z["chest"] - 0.085 * H)],
                              (-1, 0, 0), 0.008 * H)
    grip = D.handle_bar((-0.11 * H, 0.05 * H, z["chest"] + 0.1 * H), (-0.11 * H, -0.05 * H, z["chest"] + 0.1 * H), (0, 0, 1),
                        0.035 * H, 0.006 * H)
    leds = K.Solid.union_all([K.sphere(0.005 * H, 12).scale(0.5, 1, 1).translate(back_x, y, z["chest"] - 0.075 * H)
                              for y in (-0.02 * H, 0.0, 0.02 * H)])
    b.add("backpack", "Pin lưng", "Back battery", "battery",
          [Shape(pack.subtract_all(vents), "paint_secondary", 40.0), Shape(pack_screws, "stainless", 40.0),
           Shape(grip, "aluminum_dark", 40.0), Shape(leds, "led_green", 40.0)], parent_id="torso", required=True,
          aliases=["pin", "pin lưng", "ba lô", "battery", "khối pin", "nguồn"],
          function="Khối pin và bộ quản lý năng lượng, tháo lắp từ phía sau.", position_tag="rear",
          explode_dir=(-1, 0, 0), explode_distance=0.12 * H, explode_order=1)
    # ---------- bụng + hông ----------
    abdomen = K.Solid.union_all([joint_cyl(0.07 * H, 0.05 * H, "z").translate(0, 0, z["waist"] + 0.005 * H)] +
                                [K.torus(0.072 * H, 0.006 * H, segments=56, tube_segments=10).translate(0, 0, z["waist"] - 0.01 * H + k * 0.013 * H)
                                 for k in range(3)])
    b.add("abdomen", "Khớp eo", "Waist joint", "joint", Shape(abdomen, jmat, 40.0), parent_id="torso", required=True,
          aliases=["eo", "bụng", "khớp eo", "waist", "khớp bụng"], function="Khớp xoay eo cho phép thân trên quay quanh trục đứng.",
          position_tag="center", joint_axis=(0, 0, 1), explode_dir=(0, 0, -1), explode_distance=0.04 * H, explode_order=2)
    pelvis = limb(z["waist"] - 0.03 * H, z["hip"] - 0.02 * H, 0.2 * H, 0.17 * H, 0.12 * H, 0.1 * H, bulge=0.02, exponent=3.0)
    b.add("pelvis", "Hông", "Pelvis", "pelvis", Shape(pelvis, shell, 45.0), parent_id="abdomen", required=True,
          aliases=["hông", "xương chậu", "pelvis", "vùng hông"], function="Khung hông nối hai chân với thân.",
          position_tag="center", explode_dir=(0, 0, -1), explode_distance=0.05 * H, explode_order=2)
    # ---------- cổ + đầu ----------
    neck = actuator(0.035 * H, 0.05 * H, "z", (0, 0, z["neck"]), jmat)
    b.add("neck", "Khớp cổ", "Neck joint", "joint", neck, parent_id="torso", required=True,
          aliases=["cổ", "khớp cổ", "neck"], function="Khớp xoay đầu quanh trục đứng.", position_tag="top",
          joint_axis=(0, 0, 1), explode_dir=(0, 0, 1), explode_distance=0.05 * H, explode_order=2)
    hr = 0.065 * H
    cage = [K.sphere(hr, 48).scale(1.05, 0.92, 1.1).translate(0, 0, z["head"]),
            K.sphere(hr * 0.8, 40).scale(1.0, 0.9, 0.8).translate(-0.01 * H, 0, z["head"] - 0.035 * H)]
    head = K.hull(cage)
    # kính che mặt: vỏ mỏng 4% bán kính NẰM NGOÀI mặt đầu (mặt trong trùng mặt cầu đầu → bị che, không nhiễu sọc)
    visor_zone = K.box(hr * 1.4, hr * 3, hr * 0.7).translate(hr * 0.75, 0, z["head"] + 0.004 * H)
    ell = lambda r: K.sphere(r, 64).scale(1.05, 0.92, 1.1).translate(0, 0, z["head"])  # noqa: E731
    visor = (ell(hr * 1.04) & visor_zone) - ell(hr * 1.0)          # kính cong dày 4% bán kính
    head = head - (ell(hr * 1.06) & visor_zone)                      # khoét ô mặt dưới kính
    face = ell(hr * 0.94) & visor_zone                               # mặt nạ cảm biến lùi sâu, không trùng mặt kính
    eyes = K.Solid.union_all([K.sphere(hr * 0.09, 20).scale(0.6, 1.3, 0.7).translate(hr * 0.92, side * hr * 0.3,
                                                                                     z["head"] + 0.004 * H)
                              for side in (1, -1)])
    head = head - D.panel_lines(head, [("z", z["head"] + hr * 0.62), ("y", 0.0)], width=0.0025 * H, depth=0.003 * H)
    ears = [joint_cyl(0.018 * H, 0.012 * H, "y").translate(0, side * hr * 0.96, z["head"]) for side in (1, -1)]
    head_shapes = [Shape(head, shell, 45.0), Shape(visor, "glass_tinted", 45.0), Shape(face, "sensor_black", 45.0),
                   Shape(eyes, "led_white", 45.0), Shape(K.Solid.union_all(ears), "paint_accent", 45.0)]
    if p.get("head_sensor") == "camera":
        cams = [K.cylinder(0.012 * H, 0.02 * H, segments=32).rotate(0, 90, 0).translate(hr * 0.9, side * 0.025 * H, z["head"]) for side in (1, -1)]
        head_shapes.append(Shape(K.Solid.union_all(cams), "lens", 45.0))
    b.add("head", "Đầu", "Head", "head", head_shapes, parent_id="neck", required=True,
          aliases=["đầu", "mặt", "head", "kính che mặt", "visor"],
          function="Chứa camera/cảm biến nhận dạng và kính che mặt.", position_tag="top",
          dimensions={"height": round(2.2 * hr, 1)}, explode_dir=(0, 0, 1), explode_distance=0.12 * H, explode_order=1)

    # ---------- tay ----------
    a_pose = 9.0
    for side, st, vi in ((1, "left", "trái"), (-1, "right", "phải")):
        sy = side * 0.145 * H
        sz = z["shoulder"]
        pivot = np.array([0.0, sy, sz])
        arm_dir = np.array([0.0, side * math.sin(math.radians(a_pose)), -math.cos(math.radians(a_pose))])

        def arm_place(sol: K.Solid) -> K.Solid:
            return sol.rotate_axis((1, 0, 0), side * a_pose, pivot)

        sh = actuator(0.05 * H, 0.06 * H, "y", (0, sy, sz), jmat)
        cap = K.sphere(0.058 * H, 40).scale(1, 0.8, 1).translate(0, sy + side * 0.01 * H, sz + 0.01 * H) & \
            K.box(0.2 * H, 0.2 * H, 0.2 * H).translate(0, sy, sz + 0.1 * H - 0.005 * H)
        b.add(f"shoulder_{st}", f"Khớp vai {vi}", f"{st.title()} shoulder", "joint",
              sh + [Shape(cap, shell, 45.0)], parent_id="torso", required=True,
              aliases=["vai", "khớp vai", "shoulder"], function="Khớp vai 2 bậc tự do: nâng/hạ và xoay cánh tay.",
              position_tag=st, joint_axis=(0, 1, 0), group=f"arm_{st}",
              explode_dir=(0, side, 0), explode_distance=0.07 * H, explode_order=2)
        ua = arm_place(seams(limb(sz - 0.035 * H, sz - 0.17 * H, 0.07 * H, 0.055 * H, 0.07 * H, 0.055 * H),
                             [sz - 0.07 * H, sz - 0.14 * H], H).translate(0, sy, 0))
        b.add(f"upper_arm_{st}", f"Cánh tay trên {vi}", f"{st.title()} upper arm", "arm_segment", Shape(ua, shell, 45.0),
              parent_id=f"shoulder_{st}", required=True, aliases=["cánh tay", "bắp tay", "tay trên", "upper arm"],
              function="Đoạn tay trên chứa động cơ khuỷu tay.", position_tag=st, group=f"arm_{st}",
              explode_dir=tuple(arm_dir), explode_distance=0.05 * H, explode_order=3)
        ez = sz - 0.19 * H
        el = actuator(0.034 * H, 0.05 * H, "y", (0, sy, ez), jmat, place=arm_place)
        b.add(f"elbow_{st}", f"Khớp khuỷu tay {vi}", f"{st.title()} elbow", "joint", el,
              parent_id=f"upper_arm_{st}", required=True, aliases=["khuỷu tay", "cùi chỏ", "khớp khuỷu", "elbow"],
              function="Khớp gập khuỷu tay.", position_tag=st, joint_axis=(0, 1, 0), group=f"arm_{st}",
              explode_dir=tuple(arm_dir), explode_distance=0.04 * H, explode_order=3)
        fa = arm_place(seams(limb(ez - 0.025 * H, ez - 0.17 * H, 0.055 * H, 0.042 * H, 0.058 * H, 0.045 * H, bulge=0.12),
                             [ez - 0.12 * H], H).translate(0, sy, 0))
        b.add(f"forearm_{st}", f"Cẳng tay {vi}", f"{st.title()} forearm", "arm_segment", Shape(fa, shell, 45.0),
              parent_id=f"elbow_{st}", required=True, aliases=["cẳng tay", "tay dưới", "forearm"],
              function="Đoạn cẳng tay chứa cơ cấu xoay cổ tay.", position_tag=st, group=f"arm_{st}",
              explode_dir=tuple(arm_dir), explode_distance=0.05 * H, explode_order=4)
        hz = ez - 0.185 * H
        if p.get("hands") == "gripper":
            base = K.rounded_box(0.05 * H, 0.05 * H, 0.03 * H, 0.008 * H).translate(0, sy, hz)
            jaws = [K.rounded_box(0.012 * H, 0.04 * H, 0.07 * H, 0.004 * H).translate(k * 0.018 * H, sy, hz - 0.045 * H) for k in (1, -1)]
            hand = [Shape(base, jmat, 40.0), Shape(K.Solid.union_all(jaws), "plastic_black", 40.0)]
        else:
            palm = K.rounded_box(0.035 * H, 0.055 * H, 0.06 * H, 0.012 * H).translate(0, sy, hz)
            fingers, knuckles = [], []
            for k, yy in enumerate(np.linspace(-0.02, 0.02, 4)):
                ln = 0.045 * H * (0.85 if k in (0, 3) else 1.0)
                pts = [(0.0, sy + yy * H, hz - 0.028 * H), (0.004 * H, sy + yy * H, hz - 0.028 * H - ln * 0.55),
                       (0.012 * H, sy + yy * H, hz - 0.028 * H - ln)]
                path = P.spline_through(pts, 12)
                fingers.append(K.tube(path, 0.0065 * H, 12, rounded_ends=True))
                # đốt khớp ngón (khớp servo nhỏ) tại gốc và giữa ngón
                knuckles += [joint_cyl(0.0078 * H, 0.011 * H, "y").translate(*pts[0]),
                             joint_cyl(0.0072 * H, 0.0105 * H, "y").translate(*path[len(path) // 2])]
            thumb = K.tube(P.spline_through([(0.012 * H, sy - side * 0.028 * H, hz - 0.005 * H),
                                             (0.025 * H, sy - side * 0.03 * H, hz - 0.03 * H)], 10), 0.007 * H, 12, rounded_ends=True)
            back_screws = D.screws_at([(0.0175 * H, sy + yy, hz + dz) for yy in (-0.018 * H, 0.018 * H) for dz in (0.018 * H, -0.012 * H)],
                                      (1, 0, 0), 0.004 * H)
            hand = [Shape(palm, jmat, 40.0), Shape(K.Solid.union_all(fingers + [thumb]), "plastic_black", 45.0),
                    Shape(K.Solid.union_all(knuckles), "aluminum", 40.0), Shape(back_screws, "steel", 40.0)]
        hand = [Shape(arm_place(sh2.solid), sh2.material, sh2.sharp_angle) for sh2 in hand]
        b.add(f"hand_{st}", f"Bàn tay {vi}", f"{st.title()} hand", "hand", hand, parent_id=f"forearm_{st}", required=True,
              aliases=["bàn tay", "tay", "hand", "kẹp", "gripper", "ngón tay"],
              function="Bàn tay/cơ cấu kẹp để cầm nắm vật.", position_tag=st, group=f"arm_{st}",
              explode_dir=tuple(arm_dir), explode_distance=0.05 * H, explode_order=4)

    # ---------- chân ----------
    for side, st, vi in ((1, "left", "trái"), (-1, "right", "phải")):
        hy = side * 0.062 * H
        hip = actuator(0.048 * H, 0.06 * H, "y", (0, hy, z["hip"]), jmat)
        b.add(f"hip_{st}", f"Khớp hông {vi}", f"{st.title()} hip", "joint", hip, parent_id="pelvis",
              required=True, aliases=["hông", "khớp hông", "hip"], function="Khớp hông 3 bậc tự do điều khiển chân.",
              position_tag=st, joint_axis=(0, 1, 0), group=f"leg_{st}",
              explode_dir=(0, side, 0), explode_distance=0.05 * H, explode_order=2)
        th = seams(limb(z["hip"] - 0.03 * H, z["knee"] + 0.03 * H, 0.085 * H, 0.06 * H, 0.09 * H, 0.065 * H, bulge=0.1),
                   [z["hip"] - 0.09 * H, z["knee"] + 0.08 * H], H).translate(0, hy, 0)
        b.add(f"thigh_{st}", f"Đùi {vi}", f"{st.title()} thigh", "leg_segment", Shape(th, shell, 45.0), parent_id=f"hip_{st}",
              required=True, aliases=["đùi", "bắp đùi", "thigh", "chân trên"], function="Đoạn đùi chứa động cơ gối.",
              position_tag=st, group=f"leg_{st}", explode_dir=(0, 0, -1), explode_distance=0.06 * H, explode_order=3)
        kn = actuator(0.042 * H, 0.06 * H, "y", (0, hy, z["knee"]), jmat)
        cap = K.sphere(0.035 * H, 32).scale(0.7, 1, 1).translate(0.035 * H, hy, z["knee"])
        b.add(f"knee_{st}", f"Khớp gối {vi}", f"{st.title()} knee", "joint", kn + [Shape(cap, "paint_accent", 45.0)],
              parent_id=f"thigh_{st}", required=True, aliases=["gối", "đầu gối", "khớp gối", "knee"],
              function="Khớp gối gập duỗi cẳng chân.", position_tag=st, joint_axis=(0, 1, 0), group=f"leg_{st}",
              explode_dir=(0, 0, -1), explode_distance=0.04 * H, explode_order=3)
        sh_ = seams(limb(z["knee"] - 0.03 * H, z["ankle"] + 0.03 * H, 0.068 * H, 0.045 * H, 0.075 * H, 0.05 * H, bulge=0.14,
                         x_off=-0.008 * H), [z["knee"] - 0.1 * H], H).translate(0, hy, 0)
        b.add(f"shin_{st}", f"Cẳng chân {vi}", f"{st.title()} shin", "leg_segment", Shape(sh_, shell, 45.0), parent_id=f"knee_{st}",
              required=True, aliases=["cẳng chân", "ống chân", "shin", "chân dưới"], function="Đoạn cẳng chân chứa cơ cấu cổ chân.",
              position_tag=st, group=f"leg_{st}", explode_dir=(0, 0, -1), explode_distance=0.06 * H, explode_order=4)
        an = actuator(0.03 * H, 0.05 * H, "y", (0, hy, z["ankle"]), jmat)
        b.add(f"ankle_{st}", f"Khớp cổ chân {vi}", f"{st.title()} ankle", "joint", an, parent_id=f"shin_{st}",
              required=True, aliases=["cổ chân", "mắt cá", "khớp cổ chân", "ankle"], function="Khớp cổ chân giữ thăng bằng.",
              position_tag=st, joint_axis=(0, 1, 0), group=f"leg_{st}", explode_dir=(0, 0, -1), explode_distance=0.03 * H,
              explode_order=4)
        foot = K.rounded_box(0.16 * H, 0.07 * H, 0.035 * H, 0.014 * H).translate(0.03 * H, hy, 0.0175 * H + 0.006 * H)
        # rãnh tách mũi bàn chân (khớp ngón) + đế cao su có gai ngang chống trượt
        foot = foot - D.panel_lines(foot, [("x", 0.075 * H)], width=0.003 * H, depth=0.004 * H)
        sole = K.rounded_box(0.165 * H, 0.072 * H, 0.012 * H, 0.005 * H).translate(0.03 * H, hy, 0.006 * H)
        treads = [K.box(0.006 * H, 0.08 * H, 0.004 * H).translate(x, hy, 0.0015 * H)
                  for x in np.linspace(-0.04 * H, 0.1 * H, 9)]
        sole = sole.subtract_all(treads)
        b.add(f"foot_{st}", f"Bàn chân {vi}", f"{st.title()} foot", "foot", [Shape(foot - sole.scale(1.0, 1.0, 1.0), shell, 45.0),
                                                                          Shape(sole, "rubber", 40.0)],
              parent_id=f"ankle_{st}", required=True, aliases=["bàn chân", "chân", "foot", "đế"],
              function="Bàn chân có cảm biến lực và đế cao su chống trượt.", position_tag=st, group=f"leg_{st}",
              explode_dir=(0, 0, -1), explode_distance=0.05 * H, explode_order=5)
    b.note_stage(1, "Nhấc đầu, rút pin lưng")
    b.note_stage(2, "Tách khớp vai/hông theo trục khớp, tách eo và cổ")
    b.note_stage(3, "Tách cánh tay trên, khuỷu, đùi, gối dọc trục chi")
    b.note_stage(4, "Tách cẳng tay, bàn tay, cẳng chân, cổ chân")
    b.note_stage(5, "Tách bàn chân")
    b.metadata.update({"height_mm": H, "ground_z_mm": 0.0})
    return b.build()
