"""Robot bốn chân (robot chó): thân, vỏ trên, pin bụng, đầu cảm biến (camera stereo / LiDAR), tay nắm,
4 chân × (khớp dạng hông – khớp gập hông – đùi – khớp gối – cẳng chân – bàn chân cao su).
joints_per_leg = 3: dạng hông (trục X) + gập hông (trục Y) + gối (trục Y); = 2: bỏ khớp dạng hông.

Tư thế đứng: đùi chéo về sau, cẳng chân chéo về trước (gối hướng ra sau như robot thương mại phổ biến).
Tách: vỏ trên mở lên, pin rút xuống, đầu tiến ra trước, chân tách ngang theo trục khớp, các đoạn chân tách dọc chân.
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d.generation.assembly import POSITION_VI, AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import components as C
from nexa.three_d.generation.templates import details as D
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec


def _segment(a: np.ndarray, b: np.ndarray, w0: float, w1: float, d0: float, d1: float, ring: int = 36) -> K.Solid:
    """Đoạn chân thuôn nối hai khớp a → b (mặt cắt siêu elip, bề rộng theo trục Y)."""
    axis = b - a
    L = float(np.linalg.norm(axis))
    n = axis / L
    side = np.array([0.0, 1.0, 0.0])
    xa = np.cross(side, n)
    xa /= np.linalg.norm(xa)
    secs = []
    for t in np.linspace(0, 1, 12):
        sw = 1 + 0.12 * math.sin(math.pi * t)
        prof = P.superellipse((d0 + (d1 - d0) * t) * sw, (w0 + (w1 - w0) * t), 2.6, ring)
        c = a + axis * t
        secs.append(c + prof[:, :1] * xa + prof[:, 1:2] * side)
    return K.loft(secs)


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    L = float(p.get("length_mm", 700))
    jpl = int(p.get("joints_per_leg", 3))
    style = spec.style or {}
    primary = M.color_from_name(style.get("primary_color"), "#f4c20d")
    secondary = M.color_from_name(style.get("secondary_color"), "#23262b")
    accent = M.color_from_name(style.get("accent_color"), "#22d3ee")
    mats = M.library(primary, secondary, accent)
    jmat = "aluminum_dark"
    b = AssemblyBuilder(spec.name or "Robot chó", "quadruped", mats)
    body_l, body_w, body_h = 0.62 * L, 0.24 * L, 0.14 * L
    thigh_l = shin_l = 0.3 * L
    a_th, a_sh = math.radians(35), math.radians(30)
    hip_z = thigh_l * math.cos(a_th) + shin_l * math.cos(a_sh) + 0.02 * L
    zc = hip_z + 0.01 * L

    # ---------- thân (khung) ----------
    frame = K.rounded_box(body_l * 0.96, body_w * 0.8, body_h * 0.7, 0.03 * L).translate(0, 0, zc)
    b.add("body_frame", "Khung thân", "Body frame", "frame", Shape(frame, "aluminum_dark", 40.0), required=True,
          aliases=["thân", "khung", "khung thân", "thân chính", "body", "frame"],
          function="Khung chịu lực chứa bộ điều khiển, IMU và gắn bốn chân.", position_tag="center",
          dimensions={"length": round(body_l, 1), "width": round(body_w, 1), "height": round(body_h, 1)})
    secs = []
    ring = 56
    for t in np.linspace(0, 1, 18):
        x = -body_l / 2 + t * body_l
        w = body_w * (0.86 + 0.14 * math.sin(math.pi * t))
        h = body_h * 0.62 * (0.8 + 0.2 * math.sin(math.pi * t))
        prof = P.superellipse(w, 2 * h, 3.2, ring)
        secs.append(np.column_stack([np.full(ring, x), prof[:, 0], zc + 0.02 * L + prof[:, 1]]))
    cover = K.loft(secs) & K.box(body_l * 2, body_w * 2, body_h * 2).translate(0, 0, zc + 0.02 * L + body_h)
    inner = K.rounded_box(body_l * 0.9, body_w * 0.8, body_h * 0.72, 0.03 * L).translate(0, 0, zc)
    cover = cover - inner
    stripes = K.box(body_l * 0.5, body_w * 1.3, 0.012 * L).translate(0, 0, zc + 0.02 * L + body_h * 0.45) & cover
    cover = cover - stripes.scale(1.0)
    # vỏ thật: rãnh ghép ba mảng, khe tản nhiệt hai bên, ốc bắt vỏ, nút dừng khẩn cấp + đèn trạng thái phía sau
    cover_outer = K.loft(secs) & K.box(body_l * 2, body_w * 2, body_h * 2).translate(0, 0, zc + 0.02 * L + body_h)
    cover = cover - D.panel_lines(cover_outer, [("x", body_l * 0.2), ("x", -body_l * 0.22)], width=0.004 * L, depth=0.005 * L)
    z_side = zc + 0.02 * L + body_h * 0.2
    cover = cover - K.Solid.union_all([D.vent_cutter((-body_l * 0.3, side * body_w * 0.5, z_side), (0, side, 0), (1, 0, 0),
                                                     0.12 * L, 0.03 * L, 6, 0.02 * L) for side in (1, -1)])
    z_cov_top = zc + 0.02 * L + body_h * 0.62
    cov_screws = D.screws_at([(x, y, z_cov_top - 0.004 * L) for x in (body_l * 0.3, -body_l * 0.36) for y in (0.06 * L, -0.06 * L)],
                             (0, 0, 1), 0.008 * L)
    e_base, e_cap = D.estop_button(0.022 * L)
    e_base = e_base.translate(-body_l * 0.3, 0.0, z_cov_top - 0.006 * L)
    e_cap = e_cap.translate(-body_l * 0.3, 0.0, z_cov_top - 0.006 * L)
    status = K.rounded_box(0.012 * L, 0.08 * L, 0.012 * L, 0.004 * L).translate(-body_l / 2 - 0.003 * L, 0, z_side + 0.01 * L)
    b.add("shell_top", "Vỏ trên", "Top cover", "shell", [Shape(cover, "paint_primary", 40.0), Shape(stripes, "paint_secondary", 40.0),
                                                        Shape(cov_screws, "stainless", 40.0), Shape(e_base, "paint_yellow", 40.0),
                                                        Shape(e_cap, "paint_red", 40.0), Shape(status, "led_green", 40.0)],
          parent_id="body_frame", required=True, aliases=["vỏ", "vỏ trên", "nắp", "lớp vỏ", "cover", "shell"],
          function="Vỏ bảo vệ chống va đập và bụi nước.", position_tag="top", explode_dir=(0, 0, 1),
          explode_distance=0.18 * L, explode_order=1)
    handle = K.tube(P.spline_through([(-0.08 * L, 0.05 * L, zc + body_h * 0.62), (-0.05 * L, 0.05 * L, zc + body_h * 0.95),
                                      (0.05 * L, 0.05 * L, zc + body_h * 0.95), (0.08 * L, 0.05 * L, zc + body_h * 0.62)], 24),
                    0.009 * L, 14) + \
        K.tube(P.spline_through([(-0.08 * L, -0.05 * L, zc + body_h * 0.62), (-0.05 * L, -0.05 * L, zc + body_h * 0.95),
                                 (0.05 * L, -0.05 * L, zc + body_h * 0.95), (0.08 * L, -0.05 * L, zc + body_h * 0.62)], 24),
               0.009 * L, 14)
    b.add("handle", "Tay nắm", "Carry handle", "handle", Shape(handle, "aluminum", 40.0), parent_id="shell_top",
          aliases=["tay nắm", "quai xách", "handle"], function="Tay nắm để xách/đặt robot.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=0.06 * L, explode_order=1)
    batt = [Shape(sh.solid.translate(-0.02 * L, 0, zc - body_h * 0.42), sh.material, 35.0)
            for sh in C.battery_pack(0.34 * L, 0.14 * L, 0.06 * L)]
    b.add("battery", "Pin bụng", "Battery", "battery", batt, parent_id="body_frame", required=True,
          aliases=["pin", "ắc quy", "battery", "khối pin"], function="Pin lithium cấp điện ~1–2 giờ hoạt động.",
          position_tag="bottom", explode_dir=(0, 0, -1), explode_distance=0.16 * L, explode_order=1)
    # ---------- đầu cảm biến ----------
    hx = body_l / 2 + 0.04 * L
    head = K.rounded_box(0.12 * L, body_w * 0.8, body_h * 0.62, 0.035 * L).translate(hx, 0, zc + 0.01 * L)
    face = K.rounded_box(0.02 * L, body_w * 0.66, body_h * 0.36, 0.012 * L).translate(hx + 0.058 * L, 0, zc + 0.012 * L)
    lenses = [K.cylinder(0.018 * L, 0.012 * L, segments=40).rotate(0, 90, 0).translate(hx + 0.062 * L, s_ * 0.05 * L, zc + 0.012 * L)
              for s_ in (1, -1)]
    # dải đèn trên mặt, cảm biến độ sâu hai bên đầu, rãnh ghép nắp đầu
    head = head - D.panel_lines(head, [("z", zc + 0.01 * L + body_h * 0.2)], width=0.004 * L, depth=0.004 * L)
    eye_bar = K.rounded_box(0.006 * L, body_w * 0.5, 0.008 * L, 0.003 * L).translate(hx + 0.068 * L, 0, zc + 0.012 * L + body_h * 0.13)
    side_cams, side_glass = [], []
    for s_ in (1, -1):
        ring_s, face_s = D.ultrasonic_sensor(0.03 * L)
        side_cams.append(ring_s.rotate(0, 0, 90 * s_).translate(hx, s_ * body_w * 0.4, zc + 0.012 * L))
        side_glass.append(face_s.rotate(0, 0, 90 * s_).translate(hx, s_ * body_w * 0.4, zc + 0.012 * L))
    head_shapes = [Shape(head, "paint_primary", 40.0), Shape(face, "sensor_black", 40.0),
                   Shape(K.Solid.union_all(lenses), "lens", 40.0), Shape(eye_bar, "led_white", 40.0),
                   Shape(K.Solid.union_all(side_cams), "aluminum_dark", 40.0), Shape(K.Solid.union_all(side_glass), "lens", 40.0)]
    b.add("head", "Đầu cảm biến", "Sensor head", "head", head_shapes, parent_id="body_frame", required=True,
          aliases=["đầu", "mặt", "đầu cảm biến", "head", "camera", "mắt"],
          function="Cụm camera stereo đo chiều sâu, nhận biết địa hình và vật cản phía trước.", position_tag="front",
          explode_dir=(1, 0, 0), explode_distance=0.14 * L, explode_order=2)
    if p.get("head_sensor", "both") in ("lidar", "both"):
        lid = [Shape(sh.solid.translate(0.16 * L, 0, zc + body_h * 0.64), sh.material, 40.0) for sh in C.lidar_puck(0.1 * L, 0.07 * L)]
        b.add("lidar", "LiDAR", "LiDAR", "lidar", lid, parent_id="shell_top", required=True,
              aliases=["lidar", "cảm biến laser", "máy quét"], function="Quét laser 360° để lập bản đồ và định vị.",
              position_tag="top", explode_dir=(0, 0, 1), explode_distance=0.12 * L, explode_order=1)

    # ---------- chân ----------
    legs = [(1, 1, "front_left"), (1, -1, "front_right"), (-1, 1, "rear_left"), (-1, -1, "rear_right")]
    for fx, fy, tag in legs:
        vi = POSITION_VI[tag]
        hip = np.array([fx * body_l * 0.36, fy * (body_w * 0.4 + 0.045 * L), hip_z])
        parent = "body_frame"
        if jpl >= 3:
            ab = C.servo_actuator(0.085 * L, 0.07 * L, jmat, "paint_accent")
            ab_shapes = [Shape(sh.solid.rotate(0, 90, 0).translate(hip[0] - fx * 0.02 * L, hip[1] - fy * 0.035 * L, hip[2]),
                               sh.material, 40.0) for sh in ab]
            b.add(f"hip_ab_{tag}", f"Khớp dạng hông {vi}", f"Hip abduction {tag.replace('_', ' ')}", "joint", ab_shapes,
                  parent_id=parent, required=True, aliases=["khớp dạng hông", "khớp hông", "hông", "khớp vai", "hip"],
                  function="Khớp nghiêng chân ra/vào (trục dọc thân).", position_tag=tag, group=f"leg_{tag}",
                  joint_axis=(1, 0, 0), explode_dir=(0, fy, 0), explode_distance=0.08 * L, explode_order=2)
            parent = f"hip_ab_{tag}"
        hp = C.servo_actuator(0.095 * L, 0.06 * L, jmat, "paint_accent")
        hp_shapes = [Shape(sh.solid.rotate(90 * fy, 0, 0).translate(hip[0], hip[1] + fy * 0.02 * L, hip[2]), sh.material, 40.0)
                     for sh in hp]
        if jpl < 3:
            # không có khớp dạng hông: gá đỡ nối khớp gập hông vào hông khung
            y_in = fy * body_w * 0.36
            mount = K.tube(np.array([[hip[0], y_in, hip[2]], [hip[0], hip[1] - fy * 0.01 * L, hip[2]]]), 0.03 * L, 32)
            hp_shapes.append(Shape(mount, "aluminum_dark", 40.0))
        b.add(f"hip_{tag}", f"Khớp gập hông {vi}", f"Hip pitch {tag.replace('_', ' ')}", "joint", hp_shapes, parent_id=parent,
              required=True, aliases=["khớp gập hông", "khớp hông", "hông", "hip"], function="Khớp đưa đùi tiến/lùi (trục ngang).",
              position_tag=tag, group=f"leg_{tag}", joint_axis=(0, 1, 0), explode_dir=(0, fy, 0),
              explode_distance=0.06 * L, explode_order=3)
        knee = hip + np.array([-thigh_l * math.sin(a_th), 0, -thigh_l * math.cos(a_th)]) + np.array([0, fy * 0.035 * L, 0])
        thigh = _segment(hip + np.array([0, fy * 0.035 * L, 0]), knee, 0.05 * L, 0.04 * L, 0.085 * L, 0.06 * L)
        # ống cáp dọc mặt ngoài đùi (dây động cơ gối), ốc nắp hộp đai
        top_pt = hip + np.array([0, fy * 0.062 * L, 0])
        k_pt = knee + np.array([0, fy * 0.05 * L, 0.015 * L])
        th_cable, th_plug = D.cable([top_pt, (top_pt + k_pt) / 2 + np.array([0.01 * L, fy * 0.004 * L, 0]), k_pt], 0.006 * L)
        mid = (hip + knee) / 2 + np.array([0, fy * 0.058 * L, 0])
        th_screws = D.screws_at([mid + np.array([dx, 0, dz]) for dx, dz in ((0.03 * L, 0.03 * L), (-0.03 * L, -0.03 * L))],
                                (0, fy, 0), 0.007 * L)
        b.add(f"thigh_{tag}", f"Đùi {vi}", f"Thigh {tag.replace('_', ' ')}", "leg_segment",
              [Shape(thigh, "paint_primary", 40.0), Shape(th_cable, "rubber", 40.0), Shape(th_plug, "plastic_black", 40.0),
               Shape(th_screws, "stainless", 40.0)],
              parent_id=f"hip_{tag}", required=True, aliases=["đùi", "chân trên", "thigh"],
              function="Đoạn đùi chứa dây đai truyền động tới khớp gối.", position_tag=tag, group=f"leg_{tag}",
              explode_dir=(0, fy * 0.6, -0.8), explode_distance=0.07 * L, explode_order=4)
        kn = C.servo_actuator(0.07 * L, 0.055 * L, jmat, "paint_accent")
        kn_shapes = [Shape(sh.solid.rotate(90 * fy, 0, 0).translate(*knee), sh.material, 40.0) for sh in kn]
        b.add(f"knee_{tag}", f"Khớp gối {vi}", f"Knee {tag.replace('_', ' ')}", "joint", kn_shapes, parent_id=f"thigh_{tag}",
              required=True, aliases=["gối", "đầu gối", "khớp gối", "knee"], function="Khớp gối gập duỗi cẳng chân.",
              position_tag=tag, group=f"leg_{tag}", joint_axis=(0, 1, 0), explode_dir=(0, fy, 0),
              explode_distance=0.05 * L, explode_order=4)
        foot = knee + np.array([shin_l * math.sin(a_sh), 0, -shin_l * math.cos(a_sh)])
        foot[2] = 0.03 * L
        shin = _segment(knee, foot, 0.035 * L, 0.025 * L, 0.05 * L, 0.03 * L)
        b.add(f"shin_{tag}", f"Cẳng chân {vi}", f"Shin {tag.replace('_', ' ')}", "leg_segment", Shape(shin, "aluminum", 40.0),
              parent_id=f"knee_{tag}", required=True, aliases=["cẳng chân", "chân dưới", "shin", "ống chân"],
              function="Đoạn cẳng chân bằng nhôm nhẹ, cứng.", position_tag=tag, group=f"leg_{tag}",
              explode_dir=(0, 0, -1), explode_distance=0.06 * L, explode_order=5)
        pad = K.sphere(0.032 * L, 40).scale(1, 1, 0.9).translate(foot[0], foot[1], 0.03 * L)
        # rãnh bám quanh đệm chân (vòng gai)
        pad = pad.subtract_all([K.torus(0.031 * L, 0.0035 * L, segments=48, tube_segments=8).translate(foot[0], foot[1], 0.03 * L + dz)
                                for dz in (-0.008 * L, 0.004 * L)])
        b.add(f"foot_{tag}", f"Bàn chân {vi}", f"Foot {tag.replace('_', ' ')}", "foot", Shape(pad, "rubber", 40.0),
              parent_id=f"shin_{tag}", required=True, aliases=["bàn chân", "chân", "đệm chân", "foot"],
              function="Đệm cao su bám mặt đất, có cảm biến tiếp xúc.", position_tag=tag, group=f"leg_{tag}",
              explode_dir=(0, 0, -1), explode_distance=0.04 * L, explode_order=5)
    b.note_stage(1, "Mở vỏ trên, rút pin bụng, nhấc LiDAR")
    b.note_stage(2, "Tách đầu cảm biến, khớp dạng hông theo trục khớp")
    b.note_stage(3, "Tách khớp gập hông")
    b.note_stage(4, "Tách đùi và khớp gối")
    b.note_stage(5, "Tách cẳng chân và bàn chân")
    b.metadata.update({"joints_per_leg": jpl, "leg_count": 4, "ground_z_mm": 0.0})
    return b.build()
