"""Xe tự hành 4/6/8 bánh: khung gầm, vỏ thân cong, treo rocker-bogie (6 bánh) hoặc treo độc lập, motor trong bánh,
LiDAR, cụm camera stereo trên cột, ăng-ten, pin tháo phía sau, đèn pha.

Tách: vỏ thân mở lên, LiDAR nhấc lên, bánh xe tách sang hai bên theo trục bánh, motor và thanh treo theo sau,
pin rút ra phía sau, cột camera nhấc lên.
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


def _wheel_layout(n: int, L: float) -> list[tuple[float, str, str]]:
    """(x, hậu tố tag, tên vị trí VI) cho một bên, từ trước ra sau."""
    if n == 4:
        return [(0.32 * L, "front", "trước"), (-0.32 * L, "rear", "sau")]
    if n == 6:
        return [(0.34 * L, "front", "trước"), (0.0, "middle", "giữa"), (-0.34 * L, "rear", "sau")]
    xs = np.linspace(0.36 * L, -0.36 * L, 4)
    return [(float(x), f"{i + 1}", f"thứ {i + 1} từ trước") for i, x in enumerate(xs)]


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    n = int(p.get("wheel_count", 6))
    L = float(p.get("length_mm", 700))
    style = spec.style or {}
    primary = M.color_from_name(style.get("primary_color"), "#e9ecef")
    secondary = M.color_from_name(style.get("secondary_color"), "#2b2e33")
    accent = M.color_from_name(style.get("accent_color"), "#f77f00")
    mats = M.library(primary, secondary, accent)
    b = AssemblyBuilder(spec.name or f"Xe tự hành {n} bánh", "rover", mats)

    wheel_d = (0.3 if n == 4 else 0.25 if n == 6 else 0.21) * L
    wheel_w = 0.11 * L
    R = wheel_d / 2
    body_l, body_w, body_h = 0.64 * L, 0.4 * L, 0.15 * L
    track = body_w / 2 + wheel_w / 2 + 0.05 * L
    z_axle = R
    z_body = R + 0.08 * L                         # đáy khung gầm
    rocker_bogie = p.get("suspension", "rocker_bogie") == "rocker_bogie" and n == 6

    # ---------- khung gầm ----------
    base = K.rounded_box(body_l, body_w, 0.025 * L, 0.01 * L).translate(0, 0, z_body + 0.0125 * L)
    rails = [K.rounded_box(body_l * 0.96, 0.03 * L, 0.05 * L, 0.008 * L).translate(0, side * (body_w / 2 - 0.02 * L), z_body + 0.05 * L)
             for side in (1, -1)]
    bumper = K.rounded_box(0.05 * L, body_w * 1.02, 0.06 * L, 0.02 * L).translate(body_l / 2 + 0.02 * L, 0, z_body + 0.045 * L)
    # cảm biến siêu âm chống va trên cản trước, ốc bắt ray, móc kéo phía sau
    us_ring, us_face = [], []
    for y in (-0.13 * L, 0.0, 0.13 * L):
        ring, face = D.ultrasonic_sensor(0.028 * L)
        us_ring.append(ring.translate(body_l / 2 + 0.046 * L, y, z_body + 0.045 * L))
        us_face.append(face.translate(body_l / 2 + 0.046 * L, y, z_body + 0.045 * L))
    y_rail = body_w / 2 - 0.005 * L                    # mặt ngoài ray dọc
    rail_bolts = K.Solid.union_all([D.screws_at([(x, side * y_rail, z_body + 0.05 * L) for x in (-0.24 * L, -0.08 * L, 0.08 * L, 0.24 * L)],
                                                (0, side, 0), 0.007 * L) for side in (1, -1)])
    hook = K.tube(P.spline_through([(-body_l / 2 + 0.01 * L, 0, z_body + 0.03 * L), (-body_l / 2 - 0.035 * L, 0, z_body + 0.03 * L),
                                    (-body_l / 2 - 0.05 * L, 0, z_body + 0.055 * L)], 20), 0.009 * L, 16, rounded_ends=True)
    b.add("chassis", "Khung gầm", "Chassis", "frame",
          [Shape(K.Solid.union_all([base] + rails), "aluminum_dark", 35.0), Shape(bumper, "rubber", 35.0),
           Shape(K.Solid.union_all(us_ring) + rail_bolts, "stainless", 40.0), Shape(K.Solid.union_all(us_face), "sensor_black", 40.0),
           Shape(hook, "steel_dark", 40.0)], required=True,
          aliases=["khung gầm", "khung", "sàn xe", "gầm", "chassis", "thân chính", "frame"],
          function="Kết cấu chịu lực, gắn hệ treo, pin và thiết bị.", position_tag="center",
          dimensions={"length": round(body_l, 1), "width": round(body_w, 1)})

    # ---------- vỏ thân (rỗng) ----------
    z_shell = z_body + 0.025 * L
    wall = 0.01 * L
    outer = K.rounded_box(body_l * 0.98, body_w * 0.98, body_h, 0.035 * L).translate(0, 0, z_shell + body_h / 2)
    chamfer_cut = K.box(0.2 * L, body_w * 1.2, 0.2 * L).rotate(0, 35, 0).translate(body_l * 0.5 + 0.03 * L, 0, z_shell + body_h + 0.04 * L)
    outer = outer - chamfer_cut
    # vỏ rỗng mở đáy: lòng trong = vỏ ngoài thu nhỏ quanh tâm, hạ xuống để hở đáy
    c = np.array([0.0, 0.0, z_shell + body_h / 2])
    k = np.array([1 - 2 * wall / (body_l * 0.98), 1 - 2 * wall / (body_w * 0.98), 1 - wall / body_h])
    inner = outer.transform(np.array([[k[0], 0, 0, 0], [0, k[1], 0, 0], [0, 0, k[2], c[2] * (1 - k[2]) - wall * 1.5]]))
    shell = outer - inner
    # chi tiết thật: rãnh ghép tấm (nắp trên / thân, ba mảng trước–giữa–sau), khe tản nhiệt hai bên phía sau
    z_top = z_shell + body_h
    grooves = D.panel_lines(outer, [("x", 0.12 * L), ("x", -0.15 * L), ("z", z_shell + body_h * 0.8)],
                            width=0.004 * L, depth=wall * 0.45)
    vents = K.Solid.union_all([D.vent_cutter((-0.2 * L, side * body_w * 0.49, z_shell + body_h * 0.42), (0, side, 0),
                                             (1, 0, 0), 0.15 * L, 0.05 * L, 7, wall * 1.4) for side in (1, -1)])
    shell = shell - grooves - vents
    lights = [K.rounded_box(0.02 * L, 0.07 * L, 0.025 * L, 0.008 * L).translate(body_l * 0.49, side * body_w * 0.3, z_shell + body_h * 0.45)
              for side in (1, -1)]
    tail = [K.rounded_box(0.012 * L, 0.05 * L, 0.018 * L, 0.005 * L).translate(-body_l * 0.49, side * body_w * 0.32, z_shell + body_h * 0.5)
            for side in (1, -1)]
    band = K.box(body_l * 0.7, body_w * 1.2, 0.014 * L).translate(-0.04 * L, 0, z_shell + body_h * 0.62)
    stripe = shell & band                              # tách dải sơn khỏi vỏ: không có mặt trùng nhau
    shell = shell - band
    # ốc bắt nắp, tay cầm phía sau, nút dừng khẩn cấp, cổng sạc + nhãn cảnh báo ở đuôi
    lid_screws = D.screws_at([(x, y, z_top) for x in (0.16 * L, -0.02 * L, -0.27 * L) for y in (0.16 * L, -0.16 * L)],
                             (0, 0, 1), 0.009 * L)
    handle = D.handle_bar((-0.29 * L, 0.1 * L, z_top), (-0.29 * L, -0.1 * L, z_top), (0, 0, 1), 0.05 * L, 0.008 * L)
    e_base, e_cap = D.estop_button(0.03 * L)
    e_base, e_cap = e_base.translate(-0.2 * L, 0.14 * L, z_top - 0.002 * L), e_cap.translate(-0.2 * L, 0.14 * L, z_top - 0.002 * L)
    port, port_cap = D.charge_port(0.04 * L)
    port = port.rotate(0, 0, 180).translate(-body_l * 0.49, -0.1 * L, z_shell + body_h * 0.35)
    port_cap = port_cap.rotate(0, 0, 180).translate(-body_l * 0.49, -0.1 * L, z_shell + body_h * 0.35)
    label = D.label_plate(0.08 * L, 0.03 * L, 0.003 * L).rotate(0, 0, 180).translate(-body_l * 0.49 - 0.001 * L, 0.08 * L,
                                                                                    z_shell + body_h * 0.3)
    b.add("body_shell", "Vỏ thân", "Body shell", "shell",
          [Shape(shell, "paint_primary", 40.0), Shape(K.Solid.union_all(lights), "led_white", 40.0),
           Shape(K.Solid.union_all(tail), "led_red", 40.0), Shape(stripe, "paint_accent", 40.0),
           Shape(lid_screws + port, "stainless", 40.0), Shape(handle, "aluminum_dark", 40.0),
           Shape(e_base, "paint_yellow", 40.0), Shape(e_cap, "paint_red", 40.0), Shape(port_cap, "rubber", 40.0),
           Shape(label, "label_yellow", 40.0)], parent_id="chassis", required=True,
          aliases=["vỏ thân", "vỏ", "lớp vỏ", "nắp", "thân xe", "body", "shell", "vỏ xe"],
          function="Bảo vệ pin, bo mạch và dây điện khỏi bụi, nước; mang đèn pha.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=0.28 * L, explode_order=1)

    # ---------- pin + bo mạch trong thân ----------
    batt = [Shape(sh.solid.translate(-0.08 * L, 0, z_body + 0.025 * L + 0.045 * L), sh.material, 35.0)
            for sh in C.battery_pack(0.3 * L, 0.18 * L, 0.09 * L)]
    b.add("battery", "Khối pin", "Battery pack", "battery", batt, parent_id="chassis", required=True,
          aliases=["pin", "khối pin", "ắc quy", "battery", "nguồn"], function="Cấp điện cho động cơ và máy tính nhúng.",
          position_tag="center", explode_dir=(-1, 0, 0.3), explode_distance=0.45 * L, explode_order=2)
    comp = K.rounded_box(0.14 * L, 0.12 * L, 0.03 * L, 0.006 * L).translate(0.17 * L, 0, z_body + 0.04 * L)
    heat = [K.box(0.12 * L, 0.004 * L, 0.02 * L).translate(0.17 * L, y, z_body + 0.065 * L) for y in np.linspace(-0.05 * L, 0.05 * L, 9)]
    b.add("computer", "Máy tính nhúng", "Onboard computer", "electronics",
          [Shape(comp, "pcb", 35.0), Shape(K.Solid.union_all(heat), "aluminum", 35.0)], parent_id="chassis",
          aliases=["máy tính", "máy tính nhúng", "bo mạch", "computer", "bộ xử lý"],
          function="Xử lý dữ liệu LiDAR/camera, lập bản đồ và điều khiển động cơ.", position_tag="front",
          explode_dir=(0, 0, 1), explode_distance=0.16 * L, explode_order=2)

    z_top = z_shell + body_h
    # ---------- LiDAR ----------
    if p.get("lidar", True):
        lz = z_top - 0.01 * L
        lid = [Shape(sh.solid.translate(0.18 * L, 0, lz), sh.material, 40.0) for sh in C.lidar_puck(0.1 * L, 0.085 * L)]
        b.add("lidar", "LiDAR 360°", "LiDAR", "lidar", lid, parent_id="body_shell", required=True,
              aliases=["lidar", "li đa", "cảm biến laser", "máy quét laser", "ra đa laser"],
              function="Quét laser 360° đo khoảng cách để lập bản đồ và tránh vật cản.", position_tag="front",
              dimensions={"diameter": round(0.1 * L, 1), "height": round(0.085 * L, 1)},
              explode_dir=(0, 0, 1), explode_distance=0.2 * L, explode_order=1)
    # ---------- cột camera stereo ----------
    if p.get("camera", True):
        mast_h = 0.3 * L
        mx = -0.02 * L if p.get("lidar", True) else 0.18 * L
        mast = K.cylinder(0.014 * L, mast_h, segments=32).translate(mx, 0, z_top - 0.01 * L)
        mast_base = K.cylinder(0.035 * L, 0.02 * L, segments=40).translate(mx, 0, z_top - 0.01 * L)
        head = K.rounded_box(0.07 * L, 0.2 * L, 0.06 * L, 0.018 * L).translate(mx + 0.01 * L, 0, z_top + mast_h + 0.02 * L)
        lens_parts = []
        for side in (1, -1):
            barrel = K.cylinder(0.022 * L, 0.03 * L, segments=40).rotate(0, 90, 0).translate(mx + 0.035 * L, side * 0.06 * L, z_top + mast_h + 0.02 * L)
            glass = K.cylinder(0.017 * L, 0.004 * L, segments=40).rotate(0, 90, 0).translate(mx + 0.064 * L, side * 0.06 * L, z_top + mast_h + 0.02 * L)
            lens_parts.append((barrel, glass))
        mast_cable, _ = D.cable([(mx - 0.02 * L, 0.0, z_top), (mx - 0.02 * L, 0.004 * L, z_top + mast_h * 0.5),
                                 (mx - 0.018 * L, 0.0, z_top + mast_h - 0.005 * L)], 0.004 * L, connectors=False)
        base_screws = D.screws_at([(mx + 0.025 * L * math.cos(a), 0.025 * L * math.sin(a), z_top + 0.01 * L)
                                   for a in np.radians([45, 135, 225, 315])], (0, 0, 1), 0.006 * L)
        b.add("camera_mast", "Cột camera", "Camera mast", "mast",
              [Shape(mast + mast_base, "aluminum", 40.0), Shape(mast_cable, "rubber", 40.0),
               Shape(base_screws, "stainless", 40.0)], parent_id="body_shell",
              aliases=["cột camera", "cột", "mast", "trụ camera"], function="Nâng camera lên cao để quan sát xa.",
              position_tag="center", group="camera_assembly", explode_dir=(0, 0, 1), explode_distance=0.14 * L, explode_order=2)
        b.add("camera", "Camera stereo", "Stereo camera", "camera",
              [Shape(head, "plastic_black", 40.0)] + [Shape(bar, "aluminum_dark", 40.0) for bar, _ in lens_parts] +
              [Shape(gl, "lens", 40.0) for _, gl in lens_parts], parent_id="camera_mast", required=True,
              aliases=["camera", "máy quay", "camera stereo", "mắt", "cụm camera"],
              function="Cặp camera stereo đo chiều sâu và nhận dạng vật thể phía trước.", position_tag="front",
              group="camera_assembly", explode_dir=(0, 0, 1), explode_distance=0.12 * L, explode_order=3)
    if p.get("antenna", True):
        ant = [Shape(sh.solid.translate(-0.28 * L, 0.15 * L, z_top - 0.005 * L), sh.material, 40.0) for sh in C.antenna(0.22 * L, 0.006 * L)]
        b.add("antenna", "Ăng-ten", "Antenna", "antenna", ant, parent_id="body_shell",
              aliases=["ăng ten", "ăng-ten", "antenna"], function="Liên lạc vô tuyến với trạm điều khiển.",
              position_tag="rear_left", explode_dir=(0, 0, 1), explode_distance=0.12 * L, explode_order=2)
    if p.get("solar_panel", False):
        panel = K.rounded_box(0.34 * L, 0.3 * L, 0.012 * L, 0.004 * L).translate(-0.12 * L, 0, z_top + 0.006 * L)
        b.add("solar_panel", "Tấm pin mặt trời", "Solar panel", "solar", Shape(panel, "glass_tinted", 40.0), parent_id="body_shell",
              aliases=["pin mặt trời", "tấm pin", "solar"], function="Sạc bổ sung cho pin khi hoạt động ngoài trời.",
              position_tag="top", explode_dir=(0, 0, 1), explode_distance=0.1 * L, explode_order=1)

    # ---------- hệ treo + motor + bánh ----------
    layout = _wheel_layout(n, L)
    for side, side_tag, side_vi in ((1, "left", "trái"), (-1, "right", "phải")):
        susp_id = f"suspension_{side_tag}"
        yl = side * (body_w / 2 + 0.02 * L)
        links = []
        if rocker_bogie:
            pivot = np.array([0.05 * L, yl, z_body + 0.06 * L])
            bogie = np.array([-0.17 * L, yl, z_axle + 0.07 * L])
            front = np.array([layout[0][0], yl, z_axle + 0.02 * L])
            mid = np.array([layout[1][0], yl, z_axle + 0.02 * L])
            rear = np.array([layout[2][0], yl, z_axle + 0.02 * L])
            prof = P.rounded_rect(0.035 * L, 0.02 * L, 0.006 * L, 4)
            rocker = P.spline_through([front + [0, 0, 0.01 * L], (front + pivot) / 2 + [0, 0, 0.04 * L], pivot,
                                       (pivot + bogie) / 2 + [0, 0, 0.02 * L], bogie], 40)
            bog = P.spline_through([mid + [0, 0, 0.01 * L], (mid + bogie) / 2 + [0, 0, 0.03 * L], bogie,
                                    (bogie + rear) / 2 + [0, 0, 0.03 * L], rear + [0, 0, 0.01 * L]], 40)
            links = [K.sweep(prof, rocker, up=(0, 1, 0)), K.sweep(prof, bog, up=(0, 1, 0))]
            joints = [K.cylinder(0.022 * L, 0.05 * L, segments=32).rotate(90, 0, 0).translate(pivot[0], yl + side * 0.025 * L, pivot[2]),
                      K.cylinder(0.018 * L, 0.045 * L, segments=32).rotate(90, 0, 0).translate(bogie[0], yl + side * 0.022 * L, bogie[2])]
            links += joints
            # ốc trục khớp rocker/bogie (mặt ngoài)
            links.append(D.screws_at([(pivot[0], yl + side * 0.05 * L, pivot[2]), (bogie[0], yl + side * 0.045 * L, bogie[2])],
                                     (0, side, 0), 0.012 * L))
            wheel_mounts = [front, mid, rear]
        else:
            wheel_mounts = []
            for x, _, _ in layout:
                top_pt = np.array([x, yl, z_body + 0.06 * L])
                hub = np.array([x, yl + side * 0.03 * L, z_axle + 0.02 * L])
                for dz in (0.0, -0.035 * L):
                    arm_path = P.spline_through([top_pt + [0.03 * L, 0, dz], (top_pt + hub) / 2 + [0.01 * L, side * 0.01 * L, dz],
                                                 hub + [0.0, 0, dz * 0.4]], 20)
                    links.append(K.tube(arm_path, 0.009 * L, 14, rounded_ends=True))
                damper = K.tube(np.array([top_pt + [-0.03 * L, 0, 0.02 * L], hub + [-0.02 * L, 0, 0.01 * L]]), 0.012 * L, 18)
                links.append(damper)
                wheel_mounts.append(hub)
        b.add(susp_id, f"Hệ treo bên {side_vi}", f"{side_tag.title()} suspension", "suspension",
              [Shape(K.Solid.union_all(links), "aluminum", 40.0)], parent_id="chassis", required=True,
              aliases=["hệ treo", "giảm xóc", "rocker", "bogie", "treo", "suspension", "càng"],
              function=("Cơ cấu rocker-bogie giữ cả 6 bánh bám đất trên địa hình gồ ghề." if rocker_bogie else
                        "Treo độc lập kèm giảm chấn cho từng bánh."), position_tag=side_tag,
              explode_dir=(0, side, 0), explode_distance=0.12 * L, explode_order=3)
        for (x, suffix, pos_name), mount in zip(layout, wheel_mounts):
            tag = f"{suffix}_{side_tag}" if not suffix.isdigit() else f"{side_tag}_{suffix}"
            wy = side * track
            motor = K.revolve(P.fillet_polygon([(0, -0.035 * L), (R * 0.45, -0.035 * L), (R * 0.45, 0.035 * L), (0, 0.035 * L)],
                                               [0, 0.006 * L, 0.006 * L, 0], 4), segments=48).rotate(90, 0, 0)
            my = wy - side * (wheel_w * 0.5 + 0.02 * L)
            motor = motor.translate(x, my, z_axle)
            fins = D.cooling_fins(R * 0.45, 0.05 * L, 14, 0.012 * L, 0.004 * L).rotate(90, 0, 0).translate(x, my, z_axle)
            bracket = K.tube(np.array([mount, [x, my, z_axle]]), 0.012 * L, 16)
            # cáp nguồn động cơ đi về khung gầm (có đầu nối)
            cab, plug = D.cable([(x - side * 0.0, my - side * 0.03 * L, z_axle + R * 0.3),
                                 (x - 0.02 * L, my - side * 0.06 * L, z_axle + R * 0.55),
                                 (x * 0.8, side * (body_w / 2 + 0.004 * L), z_body + 0.035 * L)], 0.0045 * L)
            b.add(f"motor_{tag}", f"Động cơ bánh {pos_name} {side_vi}", f"Drive motor {suffix} {side_tag}", "motor",
                  [Shape(motor, "aluminum_dark", 40.0), Shape(fins, "aluminum", 40.0), Shape(bracket, "aluminum", 40.0),
                   Shape(cab, "rubber", 40.0), Shape(plug, "plastic_black", 40.0)], parent_id=susp_id, required=True,
                  aliases=["động cơ", "motor", "mô tơ", "động cơ bánh"], function="Động cơ điện dẫn động bánh xe qua hộp số.",
                  position_tag=f"{suffix}_{side_tag}" if suffix in ("front", "rear", "middle") else side_tag,
                  group=f"wheel_{tag}", joint_axis=(0, side, 0), explode_dir=(0, side, 0), explode_distance=0.06 * L,
                  explode_order=3)
            tire, rim = C.wheel(wheel_d, wheel_w, spokes=6)
            wshapes = [Shape(sh.solid.rotate(0, 0, 180 if side < 0 else 0).translate(x, wy, z_axle), sh.material, sh.sharp_angle)
                       for sh in tire + rim]
            b.add(f"wheel_{tag}", f"Bánh {pos_name} {side_vi}", f"Wheel {suffix} {side_tag}", "wheel", wshapes,
                  parent_id=f"motor_{tag}", required=True, aliases=["bánh", "bánh xe", "lốp", "wheel", "tire", "vỏ xe"],
                  function=f"Bánh xe Ø{wheel_d:.0f} mm, lốp gai chữ V bám địa hình.", position_tag=f"{suffix}_{side_tag}"
                  if suffix in ("front", "rear", "middle") else side_tag,
                  group=f"wheel_{tag}", joint_axis=(0, side, 0),
                  dimensions={"diameter": round(wheel_d, 1), "width": round(wheel_w, 1)},
                  explode_dir=(0, side, 0), explode_distance=0.22 * L, explode_order=2)
    b.note_stage(1, "Mở vỏ thân, nhấc LiDAR")
    b.note_stage(2, "Tháo bánh xe sang hai bên, rút pin ra sau, nhấc cột camera và máy tính")
    b.note_stage(3, "Tháo động cơ và hệ treo")
    b.metadata.update({"wheel_count": n, "wheel_diameter_mm": wheel_d, "ground_z_mm": 0.0,
                       "suspension": "rocker_bogie" if rocker_bogie else "independent"})
    return b.build()
