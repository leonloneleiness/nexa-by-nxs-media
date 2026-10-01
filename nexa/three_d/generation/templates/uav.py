"""UAV đa rotor (3/4/6/8 tay đòn): khung carbon kẹp tay đòn, vỏ trên/dưới cong liền mạch, motor outrunner,
cánh quạt airfoil xoắn (chiều quay xen kẽ), pin tháo phía sau, camera gimbal phía trước, càng đáp dạng ống.

Cây lắp ráp: khung → vỏ/pin/bo mạch/camera/càng đáp/tay đòn; tay đòn → motor → cánh quạt; tay đòn → ốc liên kết.
Tách (exploded view) theo thứ tự tháo: cánh quạt theo trục motor, vỏ trên mở lên, pin rút ra sau, ốc nhấc lên,
tay đòn trượt theo phương bán kính, motor nhấc khỏi tay đòn.
"""
from __future__ import annotations

import math
import re

import numpy as np

from nexa.three_d.generation.assembly import POSITION_VI, AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import components as C
from nexa.three_d.generation.templates import details as D
from nexa.three_d.generation.templates.machine import hex_nut, flat_washer
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry import profiles as P
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.geometry.fasteners import through_holes
from nexa.three_d.spec import ModelSpec

ARM_LAYOUT: dict[int, list[tuple[float, str]]] = {
    3: [(60, "front_left"), (180, "rear"), (300, "front_right")],
    4: [(45, "front_left"), (135, "rear_left"), (225, "rear_right"), (315, "front_right")],
    6: [(30, "front_left"), (90, "left"), (150, "rear_left"), (210, "rear_right"), (270, "right"), (330, "front_right")],
    8: [(22.5, "front_left"), (67.5, "left_front"), (112.5, "left_rear"), (157.5, "rear_left"), (202.5, "rear_right"),
        (247.5, "right_rear"), (292.5, "right_front"), (337.5, "front_right")],
}
EXTRA_POS_VI = {"left_front": "trái phía trước", "left_rear": "trái phía sau", "right_front": "phải phía trước",
                "right_rear": "phải phía sau"}


def pos_vi(tag: str) -> str:
    return POSITION_VI.get(tag, EXTRA_POS_VI.get(tag, tag))


def _dome(length: float, width: float, height: float, x_rear: float, z_base: float, down: bool = False,
          hollow: float = 0.0, samples: int = 26, ring: int = 56, rear_cap: float = 0.8) -> K.Solid:
    """Vỏ cong liền mạch: loft các mặt cắt siêu elip dọc trục X, mũi thu nhọn phía trước, đáy phẳng tại z_base."""
    secs = []
    for t in np.linspace(0, 1, samples):
        w = width * (max(0.0, 1 - t ** 3)) ** 0.5 * (rear_cap + (1 - rear_cap) * math.sin(math.pi * min(1.0, t * 1.6)))
        h = height * (max(0.0, 1 - t ** 2.6)) ** 0.5
        x = x_rear + t * length
        if t >= 1.0:
            secs.append(np.repeat([[x, 0.0, z_base]], ring, axis=0))
            continue
        prof = P.superellipse(max(w, 1e-3), max(2 * h, 1e-3), 2.6, ring)
        secs.append(np.column_stack([np.full(ring, x), prof[:, 0], z_base + prof[:, 1]]))
    body = K.loft(secs)
    big = max(length, width, height) * 4
    half = K.box(big, big, big).translate(x_rear + length / 2, 0, z_base + (-big / 2 if down else big / 2))
    body = body & half
    if hollow > 0:
        inner = body.scale(1 - hollow, 1 - hollow * 1.6, 1 - hollow * 1.6)
        c0 = np.array([x_rear + length * 0.45, 0.0, z_base])
        inner = inner.translate(*(c0 - c0 * np.array([1 - hollow, 1 - hollow * 1.6, 1 - hollow * 1.6])))
        body = body - inner.translate(0, 0, -height * 0.02 if not down else height * 0.02)
    return body


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    n = int(p.get("arm_count", 4))
    W = float(p["wheelbase_mm"])
    s = W / 250.0
    style = spec.style or {}
    primary = M.color_from_name(style.get("primary_color"), "#adb4b8")
    secondary = M.color_from_name(style.get("secondary_color"), "#23262b")
    accent = M.color_from_name(style.get("accent_color"), "#d17b42")
    mats = M.library(primary, secondary, accent)
    frame_mat = {"carbon": "carbon", "plastic": "plastic_black", "aluminum": "aluminum_dark"}[p.get("frame_material", "carbon")]
    # "thân màu trắng" mà không nói vật liệu khung → sơn cả khung/tay đòn theo màu chính (carbon chỉ là mặc định)
    said_material = re.search(r"carbon|cacbon|các.?bon|nhựa|plastic|nhôm|alu", (spec.prompt or "").lower())
    if style.get("primary_color") and primary != "#141518" and not said_material:
        frame_mat = "paint_primary"
    shell_mat = "carbon" if (style.get("finish") == "carbon" or (p.get("frame_material", "carbon") == "carbon" and
                                                                 style.get("finish") != "glossy" and
                                                                 primary == "#141518")) \
        else "paint_primary"
    name = spec.name or f"UAV {n} cánh"
    b = AssemblyBuilder(name, "uav", mats)

    t_plate = 3.0 * s
    arm_t = 5.5 * s
    z_arm0, z_arm1 = 0.0, arm_t
    z_top_plate = z_arm1 + t_plate
    Rm = W / 2
    adj = 2 * Rm * math.sin(math.pi / n)
    prop_d = min(0.51 * W, 0.86 * adj)
    blades = int(p.get("prop_blades", 3))
    stator_d, stator_h = 22.0 * s, 7.0 * s
    motor_h = C.motor_height(stator_h)

    # ---------- khung trung tâm: tấm dưới + tấm trên (carbon, có lỗ giảm trọng lượng) + trụ đỡ ----------
    plate_l, plate_w = 0.46 * W, 0.26 * W
    outline = P.rounded_rect(plate_l, plate_w, 0.06 * W, 8)
    slots = [P.rounded_rect(0.1 * W, 0.035 * W, 0.017 * W, 6, center=(x, y))
             for x in (-0.11 * W, 0.0, 0.11 * W) for y in (-0.06 * W, 0.06 * W)]
    bottom = K.extrude([outline] + slots, t_plate).translate(0, 0, -t_plate)
    nose = K.extrude(P.rounded_rect(0.12 * W, 0.1 * W, 0.03 * W, 6, center=(0.25 * W, 0)), t_plate).translate(0, 0, -t_plate)
    top = K.extrude([P.rounded_rect(plate_l * 0.86, plate_w * 0.92, 0.05 * W, 8)] + slots[2:4], t_plate).translate(0, 0, z_arm1)
    # M3 fasteners keep their physical size when wheelbase changes. Reinforce the
    # mating lands so a screw is not suspended in a lightening slot.
    clamp_points = {}
    for angle, tag in ARM_LAYOUT[n]:
        a = math.radians(angle)
        radial = np.array([math.cos(a), math.sin(a)])
        tangent = np.array([-radial[1], radial[0]])
        clamp_points[tag] = [0.12 * W * radial + sign * 0.02 * W * tangent for sign in (-1, 1)]
    all_clamps = [xy for pair in clamp_points.values() for xy in pair]
    bottom = bottom + K.Solid.union_all([K.cylinder(4.0, t_plate, segments=32).translate(x, y, -t_plate) for x, y in all_clamps])
    top = top + K.Solid.union_all([K.cylinder(4.0, t_plate, segments=32).translate(x, y, z_arm1) for x, y in all_clamps])
    clamp_cutter = through_holes(all_clamps, 3.4, -t_plate, z_top_plate)
    bottom, top = bottom - clamp_cutter, top - clamp_cutter
    standoffs = [K.cylinder(2.6 * s, arm_t, segments=20).translate(x, y, 0)
                 for x in (-0.17 * W, 0.17 * W) for y in (-0.095 * W, 0.095 * W)]
    # ốc đầu tròn bắt tấm trên vào trụ đỡ
    plate_screws = D.screws_at([(x, y, z_top_plate) for x in (-0.17 * W, 0.17 * W) for y in (-0.095 * W, 0.095 * W)], (0, 0, 1), 2.4 * s)
    frame_shapes = [Shape(K.Solid.union_all([bottom, nose, top]), frame_mat, 35.0, uv_scale=22.0 * s),
                    Shape(K.Solid.union_all(standoffs), "aluminum_anodized", 35.0), Shape(plate_screws, "steel_black_oxide", 35.0)]
    b.add("frame", "Khung trung tâm", "Center frame", "frame", frame_shapes, required=True,
          aliases=["khung", "thân chính", "thân", "khung sườn", "frame", "body", "thân máy"],
          function="Kết cấu chịu lực trung tâm, kẹp các tay đòn và mang toàn bộ thiết bị.", position_tag="center",
          dimensions={"wheelbase": round(W, 1), "plate_length": round(plate_l, 1), "plate_width": round(plate_w, 1),
                      "plate_thickness": round(t_plate, 2)}, explode_distance=0.0)

    # ---------- bo mạch điều khiển bay ----------
    FC_X = 0.06 * W                                   # dưới vỏ trên, không chạm thành vỏ (đã đo giao khối)
    fc = K.rounded_box(36 * s, 36 * s, 1.6 * s, 3 * s).translate(FC_X, 0, z_top_plate + 7 * s)
    chips = [K.box(9 * s, 9 * s, 1.4 * s).translate(FC_X, 0, z_top_plate + 8.4 * s),
             K.box(6 * s, 4 * s, 1.2 * s).translate(FC_X + 10 * s, 9 * s, z_top_plate + 8.3 * s)]
    fc_standoffs = [K.cylinder(1.4 * s, 6.2 * s, segments=12).translate(FC_X + x, y, z_top_plate)
                    for x in (-15.2 * s, 15.2 * s) for y in (-15.2 * s, 15.2 * s)]
    b.add("flight_controller", "Bo mạch điều khiển bay", "Flight controller", "electronics",
          [Shape(fc, "pcb", 35.0), Shape(K.Solid.union_all(chips), "sensor_black", 35.0),
           Shape(K.Solid.union_all(fc_standoffs), "aluminum", 35.0)], parent_id="frame",
          aliases=["bo mạch", "mạch điều khiển", "flight controller", "fc", "bộ điều khiển bay"],
          function="Tính toán cân bằng, điều khiển tốc độ các motor theo cảm biến IMU và lệnh điều khiển.",
          position_tag="center", explode_dir=(0, 0, 1), explode_distance=0.16 * W, explode_order=2,
          no_clash_with=["shell_top"])

    # ---------- vỏ trên (canopy) và vỏ dưới ----------
    canopy = _dome(0.4 * W, 0.2 * W, 0.075 * W, -0.06 * W, z_top_plate, hollow=0.08)
    # khe hút gió làm mát ở mũi vỏ + đèn trạng thái trên nóc
    canopy = canopy - D.vent_cutter((0.1 * W, 0.0, z_top_plate + 0.05 * W), (1, 0, 0.6), (0, 1, 0), 0.08 * W, 0.012 * W, 5,
                                    0.015 * W)
    status_led = K.rounded_box(0.03 * W, 0.006 * W, 0.004 * W, 0.002 * W).translate(-0.04 * W, 0, z_top_plate + 0.074 * W)
    # Service hatch seams follow the actual curved shell instead of floating decals.
    canopy = canopy - D.panel_lines(canopy, [("x", -0.10 * W), ("x", 0.12 * W)],
                                    width=0.45 * s, depth=0.30 * s)
    b.add("shell_top", "Vỏ trên", "Top shell", "shell", [Shape(canopy, shell_mat, 40.0, uv_scale=22.0 * s),
                                                        Shape(status_led, "led_green", 40.0)],
          parent_id="frame", required=True, aliases=["vỏ trên", "nắp trên", "vỏ", "lớp vỏ", "canopy", "top shell", "vỏ bọc"],
          function="Che chắn bo mạch, giảm cản gió và bảo vệ khỏi bụi/nước nhẹ.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=0.3 * W, explode_order=1)
    # ---------- cột GPS/la bàn: trên nóc vỏ (pin sau/dưới) hoặc đuôi tấm khung (pin đặt trên) ----------
    on_canopy = p.get("battery", "rear") != "top"
    gps_x = 0.02 * W if on_canopy else -0.29 * W
    boom = None
    if on_canopy:                                       # đo cao độ nóc vỏ tại chỗ đặt cột (không đoán)
        probe = canopy & K.box(2 * s, 2 * s, 0.5 * W).translate(gps_x, 0, z_top_plate + 0.2 * W)
        z0 = float(probe.bounds()[1][2]) - 1.0 * s if not probe.is_empty else z_top_plate + 0.07 * W
    else:                                               # pin nằm trên: cột GPS trên cần carbon nhô ra đuôi khung
        z0 = z_top_plate
        boom = K.rounded_box(0.13 * W, 0.03 * W, t_plate, 0.01 * W).translate(-0.24 * W, 0, z_top_plate - t_plate / 2)
    mast_h = 0.09 * W
    gps_mast = K.cylinder(1.6 * s, mast_h, segments=16).translate(gps_x, 0, z0)
    if boom is not None:
        gps_mast = gps_mast + boom
    gps_base = K.cylinder(4.5 * s, 2.0 * s, segments=24).translate(gps_x, 0, z0)
    gps_puck = K.revolve(P.fillet_polygon([(0, 0), (0.05 * W, 0), (0.05 * W, 0.018 * W), (0, 0.022 * W)],
                                          [0, 1.0 * s, 3.0 * s, 0], 4), segments=48).translate(gps_x, 0, z0 + mast_h)
    b.add("gps", "GPS / la bàn", "GPS module", "sensor",
          [Shape(gps_mast + gps_base, "carbon", 35.0, uv_scale=22.0 * s), Shape(gps_puck, "plastic_white", 35.0)],
          parent_id="shell_top" if on_canopy else "frame", aliases=["gps", "la bàn", "định vị", "compass"],
          function="Thu tín hiệu vệ tinh định vị và la bàn số để giữ vị trí, bay theo điểm.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=0.12 * W, explode_order=1, no_clash_with=["battery", "antenna"])
    belly = _dome(0.34 * W, 0.18 * W, 0.045 * W, -0.16 * W, -t_plate, down=True, hollow=0.1, rear_cap=0.9)
    b.add("shell_bottom", "Vỏ dưới", "Bottom shell", "shell", Shape(belly, "paint_secondary", 40.0), parent_id="frame",
          aliases=["vỏ dưới", "bụng", "lớp vỏ", "vỏ", "bottom shell"], function="Bảo vệ mặt dưới khung và dây điện.",
          position_tag="bottom", explode_dir=(0, 0, -1), explode_distance=0.22 * W, explode_order=2)

    # ---------- pin (tháo ra phía sau) ----------
    bl, bw, bh = 0.3 * W, 0.13 * W, 0.1 * W
    batt_mode = p.get("battery", "rear")
    if batt_mode == "bottom" and p.get("camera", "front") == "bottom":
        batt_mode = "rear"                            # camera dưới bụng chiếm chỗ → pin ra sau (báo rõ, không âm thầm)
        b.warnings.append("Camera đặt dưới bụng nên pin được chuyển ra phía sau (hai bộ phận không thể cùng chỗ).")
    batt_parent = "frame"
    if batt_mode == "top":                              # nằm sát nóc vỏ trên (đo cao độ thật, không để hở)
        pr = canopy & K.box(bl * 0.6, bw * 0.6, 0.5 * W).translate(-0.02 * W, 0, z_top_plate + 0.2 * W)
        z_c = float(pr.bounds()[1][2]) if not pr.is_empty else z_top_plate + 0.075 * W
        batt_pos, batt_parent = (-0.02 * W, 0, z_c + bh / 2 + 0.2 * s), "shell_top"
    elif batt_mode == "bottom":                         # treo sát đáy vỏ dưới
        pr = belly & K.box(bl * 0.6, bw * 0.6, 0.5 * W).translate(0.0, 0, -t_plate - 0.2 * W)
        z_b = float(pr.bounds()[0][2]) if not pr.is_empty else -t_plate - 0.045 * W
        bx = -0.14 * W if p.get("camera", "front") == "bottom" else 0.0   # nhường chỗ camera dưới bụng
        pr = belly & K.box(bl * 0.6, bw * 0.6, 0.5 * W).translate(bx, 0, -t_plate - 0.2 * W)
        z_b = float(pr.bounds()[0][2]) if not pr.is_empty else z_b
        batt_pos, batt_parent = (bx, 0.0, z_b - bh / 2 - 0.2 * s), "shell_bottom"
    else:
        batt_pos = (-0.22 * W, 0.0, z_top_plate + bh / 2 + 0.5 * s)     # lùi sau vỏ trên (không lấn vỏ)
    batt_dir = {"rear": (-1, 0, 0.25), "top": (0, 0, 1), "bottom": (0, 0, -1)}[batt_mode]
    batt = [Shape(sh.solid.translate(*batt_pos), sh.material, 35.0) for sh in C.battery_pack(bl, bw, bh)]
    strap = K.box(0.03 * W, bw + 2.4 * s, 1.2 * s).translate(batt_pos[0] + 0.05 * W, 0, batt_pos[2] + bh / 2 + 0.6 * s)
    batt.append(Shape(strap, "rubber_gray", 35.0))
    b.add("battery", "Pin LiPo", "LiPo battery", "battery", batt, parent_id=batt_parent, required=True,
          aliases=["pin", "ắc quy", "battery", "khối pin", "nguồn"],
          function="Cấp điện cho motor và thiết bị điện tử (LiPo nhiều cell).", position_tag=batt_mode,
          dimensions={"length": round(bl, 1), "width": round(bw, 1), "height": round(bh, 1)},
          explode_dir=batt_dir, explode_distance=0.32 * W, explode_order=1,
          no_clash_with=["shell_top", "flight_controller", "antenna", "camera", "gimbal", "gps"])

    # ---------- camera + gimbal ----------
    cam_mode = p.get("camera", "front")
    if cam_mode != "none":
        cs = 0.12 * W
        cam_shapes, mount_shapes = C.camera_gimbal(cs, bool(p.get("gimbal", True)))
        if cam_mode == "front":
            c_pos = np.array([0.27 * W, 0.0, -t_plate - 0.92 * cs])
            rot = lambda sol: sol  # noqa: E731
        else:
            c_pos = np.array([0.02 * W, 0.0, -t_plate - 0.045 * W - 0.95 * cs])
            rot = lambda sol: sol.rotate(0, 55, 0)  # noqa: E731
        gimbal_part = None
        if mount_shapes:
            mshape = [Shape(rot(sh.solid).translate(*c_pos), sh.material, 40.0) for sh in mount_shapes]
            post_z0 = c_pos[2] + 0.86 * cs                 # đỉnh motor pan → mặt dưới khung
            post = K.cylinder(3 * s, max(1.0, -t_plate - post_z0 + 0.5 * s), segments=20)
            mshape.append(Shape(post.translate(c_pos[0] - 0.25 * cs, 0, post_z0), "aluminum_dark", 40.0))
            b.add("gimbal", "Gimbal chống rung", "Camera gimbal", "gimbal", mshape, parent_id="frame",
                  aliases=["gimbal", "giá camera", "cụm camera", "bộ chống rung"],
                  function="Giữ camera ổn định theo 2 trục, bù rung và nghiêng của thân.", position_tag=cam_mode,
                  group="camera_assembly", explode_dir=(1, 0, -0.6), explode_distance=0.18 * W, explode_order=2)
            gimbal_part = "gimbal"
            b.cut("shell_bottom", K.Solid.union_all([sh.solid for sh in mshape]))   # lỗ cho trụ gimbal xuyên vỏ dưới
        b.add("camera", "Camera", "Camera", "camera", [Shape(rot(sh.solid).translate(*c_pos), sh.material, 40.0)
                                                         for sh in cam_shapes],
              parent_id=gimbal_part or "frame", required=True,
              aliases=["camera", "máy quay", "ống kính", "cam", "cụm camera"],
              function="Quay phim/chụp ảnh và truyền hình ảnh về bộ điều khiển.", position_tag=cam_mode,
              group="camera_assembly", dimensions={"size": round(cs, 1)},
              explode_dir=(1, 0, 0) if cam_mode == "front" else (0, 0, -1), explode_distance=0.14 * W, explode_order=3)

    # ---------- càng đáp ----------
    if p.get("landing_gear", True):
        z_skid = -0.2 * W
        gear = []
        for side in (1, -1):
            skid_path = P.spline_through([(-0.17 * W, side * 0.13 * W, z_skid + 0.012 * W), (-0.12 * W, side * 0.13 * W, z_skid),
                                          (0.12 * W, side * 0.13 * W, z_skid), (0.17 * W, side * 0.13 * W, z_skid + 0.012 * W)], 30)
            gear.append(K.tube(skid_path, 3.2 * s, 16, rounded_ends=True))
            for x in (-0.09 * W, 0.09 * W):
                strut = P.spline_through([(x, side * 0.07 * W, -t_plate + 0.5), (x, side * 0.1 * W, -0.1 * W),
                                          (x, side * 0.13 * W, z_skid)], 24)
                gear.append(K.tube(strut, 2.6 * s, 14))
        feet = [K.capsule(4.2 * s, 0.08 * W).rotate(0, 90, 0).translate(0, side * 0.13 * W, z_skid - 0.2 * s)
                for side in (1, -1)]
        b.add("landing_gear", "Càng đáp", "Landing gear", "landing_gear",
              [Shape(K.Solid.union_all(gear), "aluminum_dark" if frame_mat != "carbon" else "carbon", 40.0, uv_scale=18 * s),
               Shape(K.Solid.union_all(feet), "rubber", 40.0)], parent_id="frame", required=True,
              aliases=["càng đáp", "chân đáp", "càng", "chân", "landing gear", "skid"],
              function="Đỡ máy khi cất/hạ cánh, giữ camera và cánh quạt cách mặt đất.", position_tag="bottom",
              explode_dir=(0, 0, -1), explode_distance=0.2 * W, explode_order=2)
        # vỏ dưới được khoét lỗ cho chân càng đi xuyên lên khung (như vỏ thật)
        b.cut("shell_bottom", K.Solid.union_all(gear))

    # ---------- ăng-ten ----------
    # gắn dưới hai tay đòn sau, chĩa xuống–ra ngoài (không vướng pin, GPS, càng đáp hay tay đòn khác)
    rear = sorted(ARM_LAYOUT[n], key=lambda at: math.cos(math.radians(at[0])))[:2]
    ants = []
    for ang_r, _tag in rear:
        dr = np.array([math.cos(math.radians(ang_r)), math.sin(math.radians(ang_r)), 0.0])
        base = dr * (0.62 * Rm) + np.array([0, 0, 0.3 * s])
        aim = np.array([0, 0, -1.0]) + 0.35 * dr
        for sh in C.antenna(0.13 * W, 1.6 * s):
            ants.append(Shape(sh.solid.align_z(aim / np.linalg.norm(aim), base), sh.material, 40.0))
    b.add("antenna", "Ăng-ten", "Antennas", "antenna", ants, parent_id=f"arm_{rear[0][1]}",
          aliases=["ăng ten", "ăng-ten", "antenna", "anten"], function="Thu phát tín hiệu điều khiển và video.",
          position_tag="rear", explode_dir=(0, 0, 1), explode_distance=0.12 * W, explode_order=2)

    # ---------- tay đòn, ốc, motor, cánh quạt ----------
    disks = []
    for idx, (ang, tag) in enumerate(ARM_LAYOUT[n]):
        a = math.radians(ang)
        d = np.array([math.cos(a), math.sin(a), 0.0])
        r0 = 0.08 * W
        tip = Rm
        secs = []
        for t in np.linspace(0, 1, 14):
            r = r0 + (tip - r0) * t
            wdt = ((0.085 if n <= 6 else 0.06) - 0.03 * t) * W      # 8 cánh: gốc hẹp hơn để các tay không chồng nhau
            thk = arm_t * (1.0 - 0.12 * t)
            prof = P.rounded_rect(wdt, thk, thk * 0.42, 4)
            y_axis = np.array([-d[1], d[0], 0.0])
            pts = r * d + prof[:, :1] * y_axis + (z_arm0 + thk / 2 + prof[:, 1:2]) * np.array([0, 0, 1.0])   # đáy phẳng z=0
            secs.append(pts)
        arm = K.loft(secs)
        pad = K.cylinder(0.075 * W, arm_t, segments=64).translate(*(tip * d)).translate(0, 0, z_arm0)
        ring = K.torus(0.075 * W, arm_t * 0.5, segments=64, tube_segments=12).translate(*(tip * d)).translate(0, 0, arm_t / 2)
        arm_solid = K.Solid.union_all([arm, pad, ring])
        arm_solid = arm_solid - K.cylinder(2.2 * s, arm_t * 3, segments=16).translate(*(tip * d)).translate(0, 0, -arm_t)
        arm_solid = arm_solid - through_holes(clamp_points[tag], 3.4, -t_plate, z_top_plate)
        led_mat = "led_red" if math.cos(a) > 0.1 else ("led_green" if math.cos(a) < -0.1 else "led_white")
        led_pos = (tip - 0.08 * W) * d
        led_s = K.sphere(2.4 * s, 16).scale(1, 1, 0.6).translate(led_pos[0], led_pos[1], z_arm0 - 0.4 * s)
        arm_id = f"arm_{tag}"
        vi = pos_vi(tag)
        # mạch điều tốc (ESC) bọc co nhiệt trên tay đòn + bó dây 3 pha chạy dọc tay tới motor
        esc_c = (r0 + 0.3 * (tip - r0)) * d
        esc = K.rounded_box(0.07 * W, 0.035 * W, 0.012 * W, 0.005 * W).rotate(0, 0, ang).translate(esc_c[0], esc_c[1],
                                                                                                    arm_t + 0.006 * W)
        wire_pts = [esc_c + d * 0.035 * W + np.array([0, 0, arm_t + 0.004 * W]),
                    (tip - 0.2 * (tip - r0)) * d + np.array([0, 0, arm_t + 0.0035 * W]),
                    (tip - 0.05 * W) * d + np.array([0, 0, arm_t + 0.004 * W])]
        wires, _ = D.cable(wire_pts, 1.3 * s, connectors=False)
        b.add(arm_id, f"Tay đòn {vi}", f"Arm {tag.replace('_', ' ')}", "arm",
              [Shape(arm_solid, frame_mat, 40.0, uv_scale=22.0 * s), Shape(led_s, led_mat, 60.0),
               Shape(esc, "plastic_black", 40.0), Shape(wires, "rubber", 40.0)], parent_id="frame",
              required=True, aliases=["tay đòn", "cánh tay đòn", "tay", "arm", "boom"],
              function="Đỡ motor ở khoảng cách tính toán, truyền lực nâng về khung trung tâm.", position_tag=tag,
              group=f"arm_{tag}", dimensions={"length": round(tip - r0, 1)},
              explode_dir=tuple(d), explode_distance=0.3 * W, explode_order=3)
        # ốc liên kết tay đòn – khung (2 vít M3 đi xuyên tấm trên)
        screw_shapes = []
        grip = arm_t + 2 * t_plate
        screw_length = next((v for v in (8, 10, 12, 16, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 100)
                             if v >= grip + 0.5 + 2.4 + 1.0), None)
        if screw_length is None:
            raise ValueError("Chồng tấm quá dày cho liên kết M3 hiện có; cần thiết kế lại liên kết.")
        for pos in clamp_points[tag]:
            for sh in C.screw(3.0, screw_length):
                screw_shapes.append(Shape(sh.solid.translate(pos[0], pos[1], z_top_plate), sh.material, 35.0))
            screw_shapes.append(Shape(flat_washer(3.0).translate(pos[0], pos[1], -t_plate - 0.5), "steel", 35.0))
            screw_shapes.append(Shape(hex_nut(3.0).translate(pos[0], pos[1], -t_plate - 0.5 - 2.4), "steel", 35.0))
        b.add(f"screws_{tag}", f"Ốc liên kết tay đòn {vi}", f"Arm screws {tag.replace('_', ' ')}", "screw", screw_shapes,
              parent_id=arm_id, aliases=["ốc", "vít", "ốc liên kết", "bu lông", "screw"],
              function="Hai vít M3 kẹp tay đòn giữa tấm trên và tấm dưới của khung.", position_tag=tag,
              group=f"arm_{tag}", dimensions={"diameter": 3.0, "length": screw_length, "clearance_hole": 3.4},
              explode_dir=(0, 0, 1), explode_distance=0.1 * W, explode_order=2)
        # motor
        mpos = tip * d + np.array([0, 0, z_arm1])
        motor = [Shape(sh.solid.translate(*mpos), sh.material, sh.sharp_angle) for sh in C.motor_outrunner(stator_d, stator_h)]
        b.add(f"motor_{tag}", f"Motor {vi}", f"Motor {tag.replace('_', ' ')}", "motor", motor, parent_id=arm_id,
              required=True, aliases=["motor", "động cơ", "mô tơ", "mo to"],
              function=f"Motor không chổi than {stator_d / s:.0f}{stator_h / s:02.0f} quay cánh quạt tạo lực nâng.",
              position_tag=tag, group=f"arm_{tag}", joint_axis=(0, 0, 1),
              dimensions={"stator_diameter": round(stator_d, 1), "stator_height": round(stator_h, 1)},
              explode_dir=(0, 0, 1), explode_distance=0.14 * W, explode_order=4)
        # cánh quạt: chiều quay xen kẽ (cặp chéo cùng chiều)
        clockwise = (idx % 2 == 1)
        hub_h = max(6.0, prop_d * 0.055)
        ppos = mpos + np.array([0, 0, motor_h + hub_h / 2 + 0.6 * s])
        prop = [Shape(sh.solid.rotate(0, 0, ang + 15).translate(*ppos), sh.material, 50.0)
                for sh in C.propeller(prop_d, blades, clockwise=clockwise)]
        b.add(f"propeller_{tag}", f"Cánh quạt {vi}", f"Propeller {tag.replace('_', ' ')}", "propeller", prop,
              parent_id=f"motor_{tag}", required=True,
              aliases=["cánh quạt", "cánh", "propeller", "prop", "rotor", "chong chóng"],
              function=f"Tạo lực nâng khi quay ({'thuận' if clockwise else 'ngược'} chiều kim đồng hồ nhìn từ trên), "
                       f"{blades} lá, đường kính {prop_d / 25.4:.1f} inch.",
              position_tag=tag, group=f"arm_{tag}", joint_axis=(0, 0, 1),
              dimensions={"diameter": round(prop_d, 1), "blades": blades, "pitch": round(prop_d * 0.85, 1)},
              explode_dir=(0, 0, 1), explode_distance=0.16 * W, explode_order=1,
              no_clash_with=["frame", "shell_top", "battery", "antenna"])
        disks.append({"part": f"propeller_{tag}", "center": [float(x) for x in ppos], "radius": prop_d / 2})
    b.note_stage(1, "Tháo cánh quạt theo trục motor, mở vỏ trên, rút pin ra phía sau")
    b.note_stage(2, "Nhấc ốc liên kết, tháo vỏ dưới, camera/gimbal, càng đáp, bo mạch")
    b.note_stage(3, "Rút các tay đòn theo phương bán kính")
    b.note_stage(4, "Nhấc motor khỏi đế tay đòn")
    b.metadata.update({"prop_disks": disks, "wheelbase_mm": W, "arm_count": n, "prop_diameter_mm": prop_d})
    b.metadata["arm_clamps"] = {"screw": "M3", "clearance_mm": 3.4, "frame_grip_mm": grip,
                                "screw_length_mm": screw_length, "quantity": 2 * n,
                                "thread_geometry": "simplified", "load_verified": False,
                                "points_ros_mm": {k: [list(map(float, p)) for p in v] for k, v in clamp_points.items()}}
    return b.build()
