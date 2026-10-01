"""Thư viện linh kiện chuẩn dùng chung cho các template (hệ kỹ thuật: X trước, Y trái, Z lên; mm).

Mỗi hàm trả danh sách Shape (khối + vật liệu) đặt tại gốc tọa độ, trục chính +Z (trừ khi ghi khác).
Tỷ lệ theo linh kiện thật phổ biến (motor outrunner 22xx, cánh quạt airfoil NACA xoắn theo bước, vít ISO 4762…).
"""
from __future__ import annotations

import math

import numpy as np

from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape


def screw(d: float = 3.0, length: float = 8.0, material: str = "steel_black_oxide") -> list[Shape]:
    """Vít đầu trụ lục giác chìm ISO 4762 (ren không mô hình hóa — linh kiện phụ). Đầu ở z ∈ [0, d], thân đi xuống."""
    from nexa.three_d.geometry.fasteners import socket_screw
    return [Shape(socket_screw(d, length), material, 35.0)]


def motor_outrunner(stator_d: float = 22.0, stator_h: float = 7.0, bell: str = "aluminum_anodized",
                    base: str = "aluminum_dark") -> list[Shape]:
    """Motor không chổi than kiểu outrunner (chuông quay bên ngoài). Đáy ở z=0, trục +Z."""
    r = stator_d / 2 + 2.6
    h_base = 0.28 * stator_h + 1.2
    h_bell = stator_h + 3.4
    # đế: đĩa có gân và lỗ bắt vít
    base_prof = P.fillet_polygon([(0, 0), (r * 0.98, 0), (r * 0.98, h_base * 0.55), (r * 0.72, h_base), (0, h_base)],
                                 [0, 0.5, 0.8, 0.6, 0], 4)
    base_s = K.revolve(base_prof, segments=72)
    holes = [K.cylinder(1.1, h_base + 1, segments=16).translate(r * 0.55 * math.cos(a), r * 0.55 * math.sin(a), -0.5)
             for a in np.radians([45, 135, 225, 315])]
    base_s = base_s.subtract_all(holes)
    # chuông: cốc có vai vát, lỗ thoát nhiệt trên nắp, rãnh làm mát
    z0 = h_base + 0.6
    bell_prof = P.fillet_polygon([(r * 0.55, z0), (r, z0), (r, z0 + h_bell * 0.82), (r * 0.82, z0 + h_bell),
                                  (2.2, z0 + h_bell), (2.2, z0 + h_bell - 1.2), (r - 1.2, z0 + h_bell - 1.4),
                                  (r - 1.2, z0 + 0.8), (r * 0.55, z0 + 0.8)], [0, 0.4, 1.2, 1.0, 0.3, 0, 0.2, 0.2, 0], 4)
    bell_s = K.revolve(bell_prof, segments=96)
    vents = []
    for k in range(6):
        a = 2 * math.pi * k / 6
        slot = K.rounded_box(r * 0.42, 2.6, 4, 1.2, segments=12).rotate(0, 0, math.degrees(a))
        vents.append(slot.translate(r * 0.55 * math.cos(a), r * 0.55 * math.sin(a), z0 + h_bell - 1))
    bell_s = bell_s.subtract_all(vents)
    # stator + cuộn dây đồng nhìn thấy qua khe
    stator = K.cylinder(stator_d / 2, stator_h, segments=48).translate(0, 0, z0 + 1.0)
    shaft = K.cylinder(1.5, h_bell + 5.5, segments=20).translate(0, 0, z0 + 0.5)
    nut = K.extrude(P.circle(3.3, 6), 3.2).translate(0, 0, z0 + h_bell + 0.2)
    nut = nut & K.cone(4.2, 3.2, 2.6, segments=24).translate(0, 0, z0 + h_bell + 0.2)
    return [Shape(bell_s, bell, 38.0), Shape(base_s, base, 38.0), Shape(stator, "copper", 38.0),
            Shape(shaft + nut, "steel", 38.0)]


def motor_height(stator_h: float = 7.0) -> float:
    return 0.28 * stator_h + 1.2 + 0.6 + stator_h + 3.4


def propeller(diameter: float = 127.0, blades: int = 3, pitch: float | None = None, hub_d: float | None = None,
              clockwise: bool = False, material: str = "prop_plastic", thickness_scale: float = 1.0,
              sections: int = 16) -> list[Shape]:
    """Cánh quạt nhiều lá: lá = loft các mặt cắt NACA 4412 dọc bán kính, góc xoắn β(r) = atan(P / 2πr), dây cung
    thuôn về đầu lá bo tròn. Mặt quay nằm trong XY tại z=0, trục +Z (lực đẩy hướng +Z).
    clockwise: chiều quay nhìn từ trên xuống (mặc định ngược chiều kim đồng hồ); lá được lật gương tương ứng."""
    R = diameter / 2
    pitch = pitch if pitch is not None else diameter * 0.85
    hub_r = (hub_d or max(10.0, diameter * 0.11)) / 2
    hub_h = max(6.0, diameter * 0.055)
    hub = K.revolve(P.fillet_polygon([(0, -hub_h / 2), (hub_r, -hub_h / 2), (hub_r, hub_h / 2), (hub_r * 0.55, hub_h / 2 + hub_r * 0.35),
                                      (0, hub_h / 2 + hub_r * 0.35)], [0, 0.6, 1.2, 1.0, 0], 4), segments=48)
    hub = hub - K.cylinder(2.6, hub_h * 3, segments=20).translate(0, 0, -hub_h * 1.5)
    base_af = P.naca4("4412", 1.0, 36)
    base_af[:, 0] -= 0.33                                # trục xoắn ở ~1/3 dây cung
    c_max = diameter * 0.12
    rs = np.linspace(hub_r * 0.75, R, sections)
    secs = []
    # Lá nằm dọc +Y. Quay ngược chiều kim đồng hồ: lá tại +Y đi về phía −X ⇒ mép trước ở phía −X và cao hơn
    # mép sau một góc β (đẩy khí xuống, lực đẩy +Z). Quay thuận chiều: lật gương qua mặt YZ.
    sgn = -1.0 if clockwise else 1.0
    for r in rs:
        t = (r - rs[0]) / (R - rs[0])
        chord = c_max * (0.72 + 1.1 * t - 1.25 * t ** 2) * (np.sqrt(max(0.0, 1 - t ** 8)) if t > 0.8 else 1.0)
        chord = max(chord, c_max * 0.12)
        beta = math.atan(pitch / (2 * math.pi * max(r, 1e-3)))
        thick = (1.6 - 0.9 * t) * thickness_scale        # gốc lá dày hơn (độ bền)
        cb, sb = math.cos(beta), math.sin(beta)
        chord_axis = np.array([sgn * cb, 0.0, -sb])       # mép trước → mép sau
        thick_axis = np.array([sgn * sb, 0.0, cb])        # phía mặt hút (lưng lá)
        pts = (base_af[:, :1] * chord) * chord_axis + (base_af[:, 1:] * chord * thick) * thick_axis + [0.0, r, 0.0]
        secs.append(pts)
    # đầu lá: thu về một điểm nhỏ
    tip = secs[-1].mean(axis=0) + [0, R * 0.012, 0]
    secs.append(np.repeat(tip[None], len(secs[-1]), axis=0))
    blade = K.loft(secs)
    blades_s = [blade.rotate(0, 0, 360.0 * k / blades) for k in range(blades)]
    body = K.Solid.union_all([hub] + blades_s)
    return [Shape(body, material, 50.0)]


def propeller_disc_radius(diameter: float) -> float:
    return diameter / 2


def battery_pack(length: float, width: float, height: float, wrap: str = "battery_wrap",
                 label: str = "paint_accent") -> list[Shape]:
    """Pin LiPo: hộp bo tròn + dải nhãn + dây nguồn/cân bằng. Tâm ở gốc, dài theo X."""
    body = K.rounded_box(length, width, height, min(width, height) * 0.18)
    band = K.rounded_box(length * 0.3, width + 0.4, height + 0.4, min(width, height) * 0.18).translate(-length * 0.18, 0, 0)
    band = band & K.box(length * 0.3, width * 2, height * 2).translate(-length * 0.18, 0, 0)
    lead = K.tube(P.spline_through([(-length / 2 + 2, width * 0.18, 0), (-length / 2 - 8, width * 0.2, 2),
                                    (-length / 2 - 14, width * 0.1, height * 0.4)], 16), 1.6, 10, rounded_ends=True)
    lead2 = K.tube(P.spline_through([(-length / 2 + 2, -width * 0.18, 0), (-length / 2 - 8, -width * 0.2, 2),
                                     (-length / 2 - 14, -width * 0.1, height * 0.4)], 16), 1.6, 10, rounded_ends=True)
    plug = K.rounded_box(8, width * 0.55, 6, 1.2).translate(-length / 2 - 16, 0, height * 0.4)
    return [Shape(body - band, wrap, 35.0), Shape(band, label, 35.0), Shape(lead, "led_red", 35.0),
            Shape(lead2, "plastic_black", 35.0), Shape(plug, "label_yellow", 35.0)]


def camera_gimbal(size: float = 30.0, gimbal: bool = True) -> tuple[list[Shape], list[Shape]]:
    """Camera nhìn +X. Trả (thân camera + ống kính, giá gimbal). Tâm camera ở gốc."""
    s = size
    body = K.rounded_box(s * 0.9, s, s * 0.85, s * 0.18)
    barrel = K.revolve(P.fillet_polygon([(0, 0), (s * 0.34, 0), (s * 0.34, s * 0.32), (s * 0.28, s * 0.4), (0, s * 0.4)],
                                        [0, 0, 1.0, 0.5, 0], 4), segments=64).rotate(0, 90, 0).translate(s * 0.35, 0, 0)
    ring = K.torus(s * 0.3, s * 0.04, segments=64, tube_segments=12).rotate(0, 90, 0).translate(s * 0.75, 0, 0)
    glass = K.revolve([(0, 0), (s * 0.26, 0), (s * 0.24, s * 0.05), (0, s * 0.08)], segments=64).rotate(0, 90, 0).translate(s * 0.74, 0, 0)
    cam = [Shape(body, "plastic_black", 40.0), Shape(barrel + ring, "aluminum_dark", 40.0), Shape(glass, "lens", 40.0)]
    mount: list[Shape] = []
    if gimbal:
        yoke_path = P.spline_through([(-s * 0.1, s * 0.62, 0), (-s * 0.2, s * 0.64, s * 0.5), (-s * 0.25, 0, s * 0.72),
                                      (-s * 0.2, -s * 0.64, s * 0.5), (-s * 0.1, -s * 0.62, 0)], 40)
        yoke = K.sweep(P.rounded_rect(s * 0.18, s * 0.08, s * 0.03, 3), yoke_path)
        motor_l = K.cylinder(s * 0.2, s * 0.14, segments=40).rotate(90, 0, 0).translate(-s * 0.05, s * 0.64, 0)
        motor_r = K.cylinder(s * 0.2, s * 0.14, segments=40).rotate(-90, 0, 0).translate(-s * 0.05, -s * 0.64, 0)
        pan = K.cylinder(s * 0.22, s * 0.2, segments=40).translate(-s * 0.25, 0, s * 0.68)
        mount = [Shape(K.Solid.union_all([yoke, motor_l, motor_r, pan]), "aluminum_dark", 40.0)]
    return cam, mount


def lidar_puck(diameter: float = 70.0, height: float = 60.0) -> list[Shape]:
    """LiDAR quay 360° kiểu puck: đế, cửa sổ quang học màu khói, nắp. Đáy ở z=0."""
    r = diameter / 2
    base = K.revolve(P.fillet_polygon([(0, 0), (r, 0), (r, height * 0.3), (0, height * 0.3)], [0, 1.5, 1.0, 0], 4), segments=96)
    window = K.revolve([(r * 0.93, height * 0.3), (r * 0.97, height * 0.3), (r * 0.97, height * 0.78), (r * 0.93, height * 0.78)],
                       segments=96)
    inner = K.cylinder(r * 0.93, height * 0.48, segments=96).translate(0, 0, height * 0.3)
    cap = K.revolve(P.fillet_polygon([(0, height * 0.78), (r, height * 0.78), (r, height * 0.9), (r * 0.85, height), (0, height)],
                                     [0, 0.8, 2.0, 1.5, 0], 4), segments=96)
    return [Shape(base + cap, "sensor_black", 40.0), Shape(inner, "plastic_black", 40.0), Shape(window, "glass_tinted", 40.0)]


def wheel(diameter: float, width: float, spokes: int = 5, rim_material: str = "aluminum",
          tire_material: str = "rubber", tread: bool = True) -> tuple[list[Shape], list[Shape]]:
    """Bánh xe có trục theo +Y (lăn theo X), tâm ở gốc. Trả (lốp, vành)."""
    R, w = diameter / 2, width
    r_rim = R * 0.64
    wall = w * 0.5
    tire_prof = P.fillet_polygon([(r_rim - 1, -wall * 0.88), (R * 0.93, -wall), (R, -wall * 0.55), (R, wall * 0.55),
                                  (R * 0.93, wall), (r_rim - 1, wall * 0.88)], [0, w * 0.18, w * 0.2, w * 0.2, w * 0.18, 0], 6)
    tire = K.revolve(tire_prof, segments=max(72, int(diameter * 0.8)) // 8 * 8)
    if tread:
        # rãnh gai chữ V so le hai bên (trong hệ revolve: trục bánh = Z, rãnh cắt vào mặt lăn tại bán kính R)
        n = max(18, int(diameter * 0.28))
        grooves = []
        for k in range(n):
            a = 360.0 * k / n
            for side in (1, -1):
                g = K.box(R * 0.08, R * 0.045, w * 0.44).rotate(side * 25, 0, 0).translate(R, 0, side * w * 0.24)
                grooves.append(g.rotate(0, 0, a + (180.0 / n if side < 0 else 0.0)))
        tire = tire.subtract_all(grooves)
    rim_prof = P.fillet_polygon([(R * 0.2, -w * 0.4), (r_rim, -w * 0.46), (r_rim, w * 0.46), (R * 0.2, w * 0.4)],
                                [0, 1.0, 1.0, 0], 4)
    rim_ring = K.revolve(rim_prof, segments=96) - K.cylinder(r_rim - w * 0.12, w * 2, segments=96).translate(0, 0, -w)
    hub = K.revolve(P.fillet_polygon([(0, -w * 0.42), (R * 0.2, -w * 0.42), (R * 0.2, w * 0.45), (R * 0.12, w * 0.55), (0, w * 0.55)],
                                     [0, 1, 1.5, 1, 0], 4), segments=64)
    spk = []
    for k in range(spokes):
        a = 360.0 * k / spokes
        sp = K.rounded_box(r_rim - R * 0.12, R * 0.12, w * 0.3, R * 0.04, segments=12).translate((r_rim + R * 0.12) / 2, 0, w * 0.1)
        spk.append(sp.rotate(0, 0, a))
    rim = K.Solid.union_all([rim_ring, hub] + spk)
    bolts = [K.cylinder(R * 0.025, w * 0.12, segments=12).translate(R * 0.12 * math.cos(a), R * 0.12 * math.sin(a), w * 0.53)
             for a in np.radians(np.arange(0, 360, 360 / 5))]
    # trục bánh theo +Y
    rot = lambda s: s.rotate(-90, 0, 0)  # noqa: E731
    return [Shape(rot(tire), tire_material, 45.0)], [Shape(rot(rim), rim_material, 40.0),
                                                     Shape(rot(K.Solid.union_all(bolts)), "steel", 40.0)]


def servo_actuator(diameter: float, length: float, housing: str = "aluminum_dark", cap: str = "paint_accent") -> list[Shape]:
    """Cụm khớp (động cơ + hộp số) hình trụ có gân tản nhiệt, trục +Z, tâm ở gốc."""
    r, h = diameter / 2, length
    body = K.revolve(P.fillet_polygon([(0, -h / 2), (r, -h / 2), (r, h / 2), (0, h / 2)], [0, r * 0.18, r * 0.18, 0], 5),
                     segments=72)
    fins = [K.box(r * 0.16, r * 0.06, h * 0.55).translate(r, 0, 0).rotate(0, 0, a) for a in range(0, 360, 30)]
    ring = K.cylinder(r * 1.02, h * 0.12, segments=72).translate(0, 0, h / 2 - h * 0.14)
    face = K.cylinder(r * 0.62, h * 0.08, segments=48).translate(0, 0, h / 2 - 0.01)
    # vòng ốc bắt mặt bích đầu ra + moay-ơ trục (chi tiết thật của khớp servo)
    from nexa.three_d.generation.templates import details as D
    top = h / 2 + h * 0.07 - 0.01
    bolts = D.screws_at([(r * 0.46 * math.cos(a), r * 0.46 * math.sin(a), top) for a in np.radians(np.arange(8) * 45 + 22.5)],
                        (0, 0, 1), r * 0.075)
    hub = K.cylinder(r * 0.2, h * 0.05, segments=32).translate(0, 0, top - h * 0.01)
    return [Shape(body.subtract_all(fins) if r > 8 else body, housing, 40.0), Shape(ring + face, cap, 40.0),
            Shape(bolts + hub, "steel", 40.0)]


def led(radius: float = 3.0, color: str = "led_green") -> list[Shape]:
    return [Shape(K.sphere(radius, 16).scale(1, 1, 0.6), color, 60.0)]


def antenna(height: float = 80.0, radius: float = 2.2) -> list[Shape]:
    base = K.revolve(P.fillet_polygon([(0, 0), (radius * 3, 0), (radius * 2.2, radius * 3), (0, radius * 3)], [0, 1, 1, 0], 3), segments=24)
    rod = K.capsule(radius, height).translate(0, 0, height / 2 + radius * 2)
    return [Shape(base, "plastic_black", 40.0), Shape(rod, "rubber", 40.0)]
