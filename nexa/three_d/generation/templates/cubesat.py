"""Vệ tinh CubeSat 1U / 2U / 3U / 6U / 12U theo CubeSat Design Specification rev. 14.1 (Cal Poly).

Kích thước ngoài (standards.CUBESAT): 1U 100 × 100 × 113,5 mm; 3U 100 × 100 × 340,5; 6U 100 × 226,3 × 366; 12U
226,3 × 226,3 × 366. Khung nhôm 7075/6061 với 4 ray góc 8,5 mm (mặt tiếp xúc ≥ 6,5 mm, bo cạnh R1) chạy suốt chiều Z,
khung đầu, tấm hông lùi vào trong mặt ray; pin mặt trời dán thân + cánh pin gập mở (từ 2U), mô-đun ăng-ten UHF 4 dải
thước dây mở, chồng bo mạch PC/104 (OBC, EPS, pin 18650, radio, ADCS có bánh đà), camera tải trọng mặt −Z có loa che
sáng, lò xo tách + công tắc ngắt ở chân ray, cảm biến Mặt Trời. Ray đứng thẳng (trục Z).

Tháo: cánh pin → ăng-ten → tấm hông → chồng bo mạch rút theo trục Z → khung.
"""
from __future__ import annotations

import numpy as np

from nexa.three_d import standards as S
from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec


def _cells(w: float, h: float, t: float, nx: int, ny: int) -> tuple[K.Solid, K.Solid]:
    """Mảng pin mặt trời trên tấm (mặt phẳng XY, dày theo +Z): (đế PCB, các ô pin kính xanh đen)."""
    base = K.rounded_box(w, h, t, min(1.0, t * 0.4)).translate(0, 0, t / 2)
    cw, ch = (w - 3.0) / nx, (h - 3.0) / ny
    cells = []
    for i in range(nx):
        for j in range(ny):
            cells.append(K.box(cw - 0.8, ch - 0.8, 0.3).translate(-w / 2 + 1.5 + cw * (i + 0.5), -h / 2 + 1.5 + ch * (j + 0.5), t + 0.15))
    return base, K.Solid.union_all(cells)


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    U = int(p.get("units", 3))
    X, Y, Z = S.CUBESAT[U]
    r = S.CUBESAT_RAIL
    rw = r["width"]
    mats = MC.tech_materials(spec)
    mats["cell"] = M.material("cell", "glass", "#0b1030", 0.2, 0.12, name="Pin mặt trời GaAs ba lớp")
    b = AssemblyBuilder(spec.name or f"Vệ tinh CubeSat {U}U", "cubesat", mats)
    # ---------- khung + 4 ray góc ----------
    rails = []
    for sx in (1, -1):
        for sy in (1, -1):
            rail = K.rounded_box(rw, rw, Z, r["edge_radius"]).translate(sx * (X / 2 - rw / 2), sy * (Y / 2 - rw / 2), Z / 2)
            rails.append(rail)
    ends = []
    for zc in (2.0, Z - 2.0):
        ring = K.box(X - 0.2, Y - 0.2, 4.0) - K.box(X - 2 * rw, Y - 2 * rw, 6.0)
        ends.append(ring.translate(0, 0, zc))
    n_mid = {1: 0, 2: 1, 3: 2, 6: 2, 12: 2}[U]
    for k in range(n_mid):
        zc = Z * (k + 1) / (n_mid + 1)
        ends.append((K.box(X - 0.2, Y - 0.2, 3.0) - K.box(X - 2 * rw, Y - 2 * rw, 5.0)).translate(0, 0, zc))
    deck = K.box(X - 2 * rw + 0.6, Y - 2 * rw + 0.6, 2.0).translate(0, 0, 5.0)   # sàn đỡ chồng bo mạch + camera (ăn vào ray)
    frame_extra = [deck]
    frame = K.Solid.union_all(rails + ends + frame_extra)
    # chân ray: lò xo tách (+Z) + công tắc ngắt (−Z)
    plungers, switches = [], []
    for sx in (1, -1):
        for sy in (1, -1):
            cx, cy = sx * (X / 2 - rw / 2), sy * (Y / 2 - rw / 2)
            if sx > 0:
                plungers.append(K.cylinder(1.6, 3.0, segments=16).translate(cx, cy, Z - 0.01))
                frame = frame - K.cylinder(1.6, 3.02, segments=16).translate(cx, cy, Z - 3.0)
            else:
                switches.append(K.cylinder(1.8, 1.8, segments=16).translate(cx, cy, -1.8 + 0.01))
                frame = frame - K.cylinder(1.8, 1.82, segments=16).translate(cx, cy, 0.0 - 0.01)
    b.add("frame", "Khung + 4 ray góc", "Structure & rails", "frame",
          [Shape(frame, "aluminum", 30.0), Shape(K.Solid.union_all(plungers), "stainless", 30.0), Shape(K.Solid.union_all(switches), "steel", 30.0)],
          required=True, aliases=["khung", "ray", "ray góc", "rail", "khung nhôm", "lò xo tách", "công tắc ngắt"],
          function=f"Khung nhôm {U}U: 4 ray {rw:g} mm trượt trong ống phóng P-POD, lò xo tách + công tắc ngắt ở chân ray.",
          position_tag="center", dimensions={"x": X, "y": Y, "z": Z})
    # ---------- tấm hông + pin dán thân ----------
    inset = 1.2
    t_panel = 1.6
    faces = [("px", np.array([1.0, 0, 0]), Y - 2 * rw, X), ("nx", np.array([-1.0, 0, 0]), Y - 2 * rw, X),
             ("py", np.array([0, 1.0, 0]), X - 2 * rw, Y), ("ny", np.array([0, -1.0, 0]), X - 2 * rw, Y)]
    panel_shapes, cell_shapes = [], []
    for tag, nrm, width, depth_dim in faces:
        h = Z - 10.0
        nx_c, ny_c = max(1, int(width // 38)), max(1, int(h // 70))
        base, cells = _cells(width, h, t_panel, nx_c, ny_c)
        # tấm nằm trong mặt vuông góc pháp tuyến, mặt ngoài lùi vào so với mặt ray
        off = depth_dim / 2 - inset - t_panel - 0.3
        up = np.array([0, 0, 1.0])
        side = np.cross(up, nrm)
        m = K.affine(np.column_stack([side, up, nrm]), nrm * off + np.array([0, 0, Z / 2]))
        panel_shapes.append(base.transform(m))
        cell_shapes.append(cells.transform(m))
    b.add("side_panels", "Tấm hông + pin mặt trời dán thân", "Side panels & body cells", "solar_panel",
          [Shape(K.Solid.union_all(panel_shapes), "pcb", 30.0), Shape(K.Solid.union_all(cell_shapes), "cell", 30.0)], parent_id="frame",
          required=True, aliases=["tấm hông", "pin mặt trời", "tấm pin", "solar panel", "tấm pin dán thân"],
          function="Tấm PCB pin mặt trời GaAs ba lớp (hiệu suất ~29 %) dán 4 mặt hông.", position_tag="side",
          explode_dir=(1, 1, 0), explode_distance=0.9 * max(X, Y), explode_order=3)
    # tấm hông cần chạm khung: đặt mép tấm tựa vào ray (khoảng cách tấm–ray = 0)
    # ---------- cánh pin mở (từ 2U) ----------
    contacts = [["side_panels", "frame"]]
    if U >= 2 and p.get("deployable_panels", True):
        wing_w, wing_h = (Y - 4.0), Z - 8.0
        for sx, tag in ((1, "px"), (-1, "nx")):
            base, cells = _cells(wing_h, wing_w, t_panel, max(1, int(wing_h // 40)), max(1, int(wing_w // 38)))
            # cánh mở ra ngang (vuông góc mặt), bản lề ở mép trên mặt ±X
            m = K.affine(np.column_stack([np.array([sx, 0, 0.0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])]),
                         np.array([sx * (X / 2 + wing_h / 2 + 2.0), 0.0, 2.0 - t_panel / 2]))
            hinge = K.cylinder(1.6, Y - 2.0, segments=16).rotate(90, 0, 0).translate(sx * (X / 2 + 1.2), (Y - 2.0) / 2, 2.0)
            arm = K.box(4.0, wing_w * 0.9, 1.2).translate(sx * (X / 2 + 1.8), 0, 2.0)
            b.add(f"wing_{tag}", f"Cánh pin mở {'+X' if sx > 0 else '−X'}", "Deployable solar wing", "solar_panel",
                  [Shape(base.transform(m), "pcb", 30.0), Shape(cells.transform(m), "cell", 30.0), Shape(hinge + arm, "stainless", 30.0)],
                  parent_id="frame", required=True, aliases=["cánh pin", "tấm pin mở", "solar wing", "cánh pin mặt trời"],
                  function="Cánh pin gập bằng dây nylon + dao nhiệt, bản lề ở mép dưới, mở 90° khi vào quỹ đạo.", position_tag="bottom",
                  joint_axis=(0, 1, 0), explode_dir=(sx, 0, 0.3), explode_distance=0.5 * X + 40, explode_order=1)
            contacts.append([f"wing_{tag}", "frame"])
    # ---------- mô-đun ăng-ten UHF ----------
    ant_base = K.box(X - 2 * rw, Y - 2 * rw, 6.0).translate(0, 0, Z - 0.5 - 3.0)
    tapes = []
    L_ant = 170.0
    for k, (dx, dy) in enumerate(((1, 0), (0, 1), (-1, 0), (0, -1))):
        start = np.array([dx * (X / 2 - rw - 6.0), dy * (Y / 2 - rw - 6.0), Z - 4.4])
        d = np.array([dx, dy, 0.0])
        tape = K.box(L_ant, 2.5, 0.2).transform(K.affine(K.align_matrix((1, 0, 0), d), start + d * (L_ant / 2)))
        tapes.append(tape)
    b.add("antenna", "Ăng-ten UHF (4 dải thước dây)", "UHF antenna module", "antenna",
          [Shape(ant_base, "pcb", 30.0), Shape(K.Solid.union_all(tapes), "stainless", 30.0)], parent_id="frame", required=True,
          aliases=["ăng ten", "ăng-ten", "antenna", "uhf", "dải thước dây"],
          function="Mô-đun ăng-ten UHF 435 MHz: 4 dải thép lò xo mở hình chữ thập.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=0.6 * Z + 40, explode_order=2)
    contacts.append(["antenna", "frame"])
    # ---------- chồng bo mạch PC/104 ----------
    bw, bd, bt = min(90.2, X - 2 * rw - 2), min(95.9, Y - 2 * rw - 2), 1.6
    n_units = {1: 1, 2: 2, 3: 3, 6: 3, 12: 3}[U]
    stacks_xy = [(0.0, 0.0)] if U <= 3 else ([(0.0, -Y / 4 + 1), (0.0, Y / 4 - 1)] if U == 6 else [(sx * (X / 4 - 0.5), sy * (Y / 4 - 0.5)) for sx in (1, -1) for sy in (1, -1)])
    if U > 3:
        bw, bd = min(90.2, X / (2 if U == 12 else 1) - 2 * rw - 4) - (6.0 if U == 12 else 0.0), min(95.9, Y / 2 - rw - 6)
    boards, chips, rods, cells18650 = [], [], [], []
    names = ["OBC", "EPS", "Pin", "Radio", "ADCS", "Tải trọng"]
    z0, z1 = 22.0, Z - 16.0
    for cx, cy in stacks_xy:
        n_b = max(3, 3 * n_units)
        zs = np.linspace(z0, z1, n_b)
        for k, zb in enumerate(zs):
            boards.append(K.box(bw, bd, bt).translate(cx, cy, zb))
            chips.append(K.box(14, 14, 1.2).translate(cx - bw * 0.2, cy + bd * 0.15, zb + bt / 2 + 0.6))
            chips.append(K.box(9, 20, 1.0).translate(cx + bw * 0.22, cy - bd * 0.1, zb + bt / 2 + 0.5))
            if names[k % len(names)] == "Pin" and zb + 20 < z1:
                for j in range(2):
                    cells18650.append(K.cylinder(9.25, 65.0, segments=24).rotate(0, 90, 0).translate(cx - 32.5, cy + (j - 0.5) * 20.0, zb + bt / 2 + 9.26))
        for sx in (1, -1):
            for sy in (1, -1):
                rods.append(K.cylinder(1.6, z1 + 2 - 6.0, segments=12).translate(cx + sx * (bw / 2 - 4), cy + sy * (bd / 2 - 4), 6.0))
    rod_s = K.Solid.union_all(rods)
    board_s = K.Solid.union_all(boards) - rod_s
    b.add("pcb_stack", "Chồng bo mạch PC/104", "Avionics stack", "pcb",
          [Shape(board_s, "pcb", 30.0), Shape(K.Solid.union_all(chips), "plastic_black", 30.0), Shape(rod_s, "brass", 30.0)] +
          ([Shape(K.Solid.union_all(cells18650), "battery_wrap", 30.0)] if cells18650 else []), parent_id="frame", required=True,
          aliases=["bo mạch", "máy tính trên khoang", "obc", "eps", "pcb", "chồng bo mạch", "pin 18650"],
          function="Chồng bo PC/104: máy tính OBC, nguồn EPS + pin Li-ion 18650, radio, điều khiển tư thế ADCS.",
          position_tag="center", explode_dir=(0, 0, 1), explode_distance=1.2 * Z + 60, explode_order=4)
    contacts.append(["pcb_stack", "frame"])
    # ---------- camera tải trọng mặt −Z ----------
    cam_r = min(18.0 if U < 12 else 13.0, X / 2 - rw - 8)
    body = K.cylinder(cam_r, 10.0, segments=48).translate(0, 0, 6.0)
    baffle = K.cylinder(cam_r * 0.9, 5.0, segments=48) - K.cylinder(cam_r * 0.75, 7.0, segments=48).translate(0, 0, -1)
    baffle = baffle.translate(0, 0, 1.0 + 0.01)
    lens = K.cylinder(cam_r * 0.75, 0.8, segments=48).translate(0, 0, 5.2)
    cam_hole = K.cylinder(cam_r * 0.9, 3.0, segments=48).translate(0, 0, 3.5)
    b.cut("frame", cam_hole)
    b.add("camera", "Camera tải trọng", "Payload camera", "camera",
          [Shape(body + baffle, "aluminum_dark", 30.0), Shape(lens, "lens", 30.0)], parent_id="frame", required=True,
          aliases=["camera", "tải trọng", "ống kính", "payload", "loa che sáng"],
          function="Camera quan sát Trái Đất (ống kính + loa che sáng) nhìn qua mặt −Z.", position_tag="bottom",
          explode_dir=(0, 0, -1), explode_distance=0.5 * Z + 40, explode_order=2)
    contacts.append(["camera", "frame"])
    b.note_stage(1, "Gập cánh pin")
    b.note_stage(2, "Tháo mô-đun ăng-ten, camera")
    b.note_stage(3, "Tháo tấm hông pin mặt trời")
    b.note_stage(4, "Rút chồng bo mạch khỏi khung")
    b.place_on_ground(center_xy=True)
    b.metadata.update({"units": U, "envelope_mm": [X, Y, Z], "rail_mm": rw, "standard": "CubeSat Design Specification rev. 14.1",
                       "strict_overlap": True, "contacts": contacts})
    return b.build()

