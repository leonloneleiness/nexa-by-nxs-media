"""Schema tham số cho các nhóm CAD kỹ thuật mở rộng (linh kiện chuẩn, robot, phương tiện, năng lượng/công trình,
máy chế tạo/điện tử). spec.py gộp các bảng này vào SUPPORTED_GROUPS/CATEGORY_GROUP/PARAM_SCHEMAS.

Module này KHÔNG import spec.py (tránh vòng lặp); các hàm kiểm tra nhận ModelSpec dạng duck-typing.
Tham số bắt buộc chỉ khi không thể chọn mặc định hợp lý (vd mã ổ bi); còn lại có mặc định và được ghi chú.
"""
from __future__ import annotations

from typing import Any

from nexa.three_d import standards as S


def _num(lo: float, hi: float, desc: str = "", **kw) -> dict:
    return {"type": "number", "minimum": lo, "maximum": hi, "description": desc, **kw}


def _int(lo: int, hi: int, desc: str = "", **kw) -> dict:
    return {"type": "integer", "minimum": lo, "maximum": hi, "description": desc, **kw}


def _enum(values: list, desc: str = "", **kw) -> dict:
    return {"type": "string", "enum": values, "description": desc, **kw}


def _bool(desc: str = "", **kw) -> dict:
    return {"type": "boolean", "description": desc, **kw}


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or [], "additionalProperties": False}


TECH_GROUPS: dict[str, str] = {
    "components": "Linh kiện cơ khí tiêu chuẩn (ổ bi, động cơ bước, hộp số, xi lanh, van/ống, truyền động, ray, lò xo)",
    "robotics": "Robot và tự động hóa (cánh tay robot 6 trục, robot hút bụi, AGV/robot giao hàng)",
    "vehicles": "Phương tiện (máy bay cánh bằng/VTOL, ô tô điện, xe máy/xe đạp điện, máy xúc, xe nâng, xe cẩu, tàu hỏa, "
                "CubeSat, tên lửa nhiều tầng)",
    "energy": "Năng lượng & công trình (tuabin gió, hệ pin mặt trời, máy phát điện, máy bơm ly tâm, bồn chứa, cầu, giàn thép, "
              "tháp thép)",
    "fabrication": "Máy chế tạo & điện tử (máy in 3D FDM, máy CNC 3 trục, tủ rack 19\", tủ điện, quạt, tản nhiệt, bo mạch)",
}
TECH_CATEGORY_GROUP: dict[str, str] = {
    "bearing": "components", "stepper_motor": "components", "gearbox": "components", "cylinder": "components",
    "ball_valve": "components", "pipe_fitting": "components", "belt_drive": "components", "chain_drive": "components",
    "shaft_coupling": "components", "ball_screw": "components", "linear_guide": "components", "spring": "components",
    "robot_arm": "robotics", "robot_vacuum": "robotics", "agv": "robotics",
    "fixed_wing": "vehicles", "car": "vehicles", "motorbike": "vehicles", "excavator": "vehicles", "forklift": "vehicles",
    "crane": "vehicles", "train": "vehicles", "cubesat": "vehicles", "launch_vehicle": "vehicles",
    "wind_turbine": "energy", "solar_array": "energy", "generator_set": "energy", "centrifugal_pump": "energy",
    "storage_tank": "energy", "bridge": "energy", "steel_truss": "energy", "lattice_tower": "energy",
    "fdm_printer": "fabrication", "cnc_router": "fabrication", "server_rack": "fabrication", "electrical_enclosure": "fabrication",
    "axial_fan": "fabrication", "heatsink": "fabrication", "dev_board": "fabrication",
}
TECH_CATEGORY_VI: dict[str, str] = {
    "bearing": "ổ bi", "stepper_motor": "động cơ bước", "gearbox": "hộp số", "cylinder": "xi lanh",
    "ball_valve": "van bi", "pipe_fitting": "phụ kiện đường ống", "belt_drive": "bộ truyền đai",
    "chain_drive": "bộ truyền xích", "shaft_coupling": "khớp nối trục", "ball_screw": "vít me bi",
    "linear_guide": "ray trượt tuyến tính", "spring": "lò xo",
    "robot_arm": "cánh tay robot", "robot_vacuum": "robot hút bụi", "agv": "robot AGV",
    "fixed_wing": "máy bay cánh bằng", "car": "ô tô điện", "motorbike": "xe máy", "excavator": "máy xúc", "forklift": "xe nâng",
    "crane": "xe cẩu", "train": "tàu hỏa", "cubesat": "vệ tinh CubeSat", "launch_vehicle": "tên lửa",
    "wind_turbine": "tuabin gió", "solar_array": "hệ pin mặt trời", "generator_set": "máy phát điện", "centrifugal_pump": "máy bơm ly tâm",
    "storage_tank": "bồn chứa", "bridge": "cầu", "steel_truss": "giàn thép", "lattice_tower": "tháp thép",
    "fdm_printer": "máy in 3D", "cnc_router": "máy CNC", "server_rack": "tủ rack", "electrical_enclosure": "tủ điện", "axial_fan": "quạt",
    "heatsink": "tản nhiệt", "dev_board": "bo mạch",
}
# nhóm cần cảnh báo an toàn (phương tiện, robot, cần cẩu, tên lửa…) — bổ sung theo từng đợt
TECH_SAFETY: set[str] = {"robot_arm", "robot_vacuum", "agv", "fixed_wing", "car", "motorbike", "excavator", "forklift", "crane",
                         "train", "cubesat", "launch_vehicle",
                         # công trình / thiết bị năng lượng: chưa tính kết cấu, móng, tải gió/động đất
                         "wind_turbine", "solar_array", "generator_set", "storage_tank", "bridge", "steel_truss", "lattice_tower",
                         # máy chế tạo (chuyển động, nhiệt, điện áp nguồn)
                         "fdm_printer", "cnc_router", "electrical_enclosure"}

DNS = sorted(S.PIPE_OD)
TECH_SCHEMAS: dict[str, dict] = {
    "bearing": _obj({
        "designation": _enum(sorted(S.BEARINGS), "Mã ổ bi rãnh sâu ISO 15, ví dụ 6204 (d=20, D=47, B=14)"),
        "seal": _enum(["open", "2RS", "ZZ"], "open = hở, 2RS = hai phớt cao su, ZZ = hai nắp thép", default="open"),
        "cage": _enum(["steel", "polyamide"], "Vòng cách thép dập hoặc nhựa PA66", default="steel"),
        "material": _enum(["chrome_steel", "stainless"], "Thép ổ lăn 100Cr6 hoặc inox 440C", default="chrome_steel"),
    }, ["designation"]),
    "stepper_motor": _obj({
        "frame_size": _int(17, 34, "Cỡ khung NEMA: 17, 23 hoặc 34", default=17),
        "body_length_mm": _num(20, 200, "Chiều dài thân (không kể trục)"),
        "shaft": _enum(["single", "double"], "Trục một đầu hay hai đầu", default="single"),
    }, []),
    "gearbox": _obj({
        "stages": _int(2, 3, "Số cấp bánh răng", default=2),
        "ratio": _num(4, 150, "Tỷ số truyền tổng mong muốn", default=12.0),
        "module_mm": _num(1, 6, "Module cấp đầu (cấp sau tăng dần)", default=2.0),
        "housing": _enum(["cast_iron", "aluminum"], "Vỏ gang sơn hoặc nhôm đúc", default="cast_iron"),
    }, []),
    "cylinder": _obj({
        "cylinder_type": _enum(["pneumatic", "hydraulic"], "Khí nén (ISO 15552) hoặc thủy lực", default="pneumatic"),
        "bore_mm": _num(20, 250, "Đường kính nòng (khí nén ISO 15552: 32, 40, 50, 63, 80, 100, 125)", default=50.0),
        "stroke_mm": _num(10, 2000, "Hành trình", default=100.0),
        "state": _enum(["retracted", "extended", "mid"], "Trạng thái cần: thu / duỗi / giữa", default="retracted"),
    }, []),
    "ball_valve": _obj({
        "dn": _int(15, 200, "Cỡ danh nghĩa DN15–DN200", default=50),
        "state": _enum(["open", "closed"], "Tay gạt dọc ống = mở, vuông góc = đóng", default="open"),
        "material": _enum(["carbon_steel", "stainless"], default="carbon_steel"),
    }, []),
    "pipe_fitting": _obj({
        "fitting": _enum(["flange_joint", "elbow90", "elbow45", "tee"], "Mặt bích nối ống, co 90°, co 45° hoặc tê đều",
                         default="elbow90"),
        "dn": _int(15, 200, "Cỡ danh nghĩa DN15–DN200", default=50),
        "material": _enum(["carbon_steel", "stainless"], default="carbon_steel"),
        "pipe_stubs": _bool("Kèm đoạn ống hàn hai đầu", default=True),
    }, []),
    "belt_drive": _obj({
        "belt": _enum(["GT2", "HTD5M", "SPZ", "SPA"], "Đai răng GT2/HTD 5M hoặc đai thang hẹp SPZ/SPA", default="GT2"),
        "teeth_driver": _int(10, 120, "Số răng puly dẫn (đai răng)", default=20),
        "teeth_driven": _int(10, 150, "Số răng puly bị dẫn (đai răng)", default=40),
        "pulley_d_mm": _num(40, 400, "Đường kính chuẩn puly dẫn (đai thang)"),
        "pulley2_d_mm": _num(40, 800, "Đường kính chuẩn puly bị dẫn (đai thang)"),
        "center_distance_mm": _num(30, 3000, "Khoảng cách tâm hai trục"),
        "width_mm": _num(3, 60, "Bề rộng đai (đai răng)"),
    }, []),
    "chain_drive": _obj({
        "chain": _enum(sorted(S.CHAINS), "Xích con lăn ISO 606 (dãy B)", default="08B"),
        "teeth_driver": _int(9, 60, "Số răng đĩa xích dẫn", default=17),
        "teeth_driven": _int(9, 100, "Số răng đĩa xích bị dẫn", default=34),
        "center_distance_mm": _num(50, 3000, "Khoảng cách tâm gần đúng (hiệu chỉnh theo số mắt xích nguyên)"),
    }, []),
    "shaft_coupling": _obj({
        "coupling_type": _enum(["jaw", "rigid"], "Khớp nối mềm vấu (có đệm sao) hoặc khớp nối cứng ống kẹp", default="jaw"),
        "bore_mm": _num(5, 55, "Đường kính lỗ trục 1", default=14.0),
        "bore2_mm": _num(5, 55, "Đường kính lỗ trục 2 (bỏ trống = bằng trục 1)"),
    }, []),
    "ball_screw": _obj({
        "diameter_mm": _num(12, 32, "Đường kính danh nghĩa vít (12, 16, 20, 25, 32)", default=16.0),
        "lead_mm": _num(4, 10, "Bước vít (4, 5, 10)", default=5.0),
        "length_mm": _num(100, 3000, "Tổng chiều dài trục vít", default=500.0),
        "supports": _bool("Kèm gối đỡ BK/BF hai đầu", default=True),
    }, []),
    "linear_guide": _obj({
        "series": _enum(sorted(S.LINEAR_GUIDES), "Cỡ ray: HGR15–30 hoặc MGN7–15", default="HGR20"),
        "length_mm": _num(60, 4000, "Chiều dài ray", default=400.0),
        "carriages": _int(1, 4, "Số con trượt", default=2),
    }, []),
    "spring": _obj({
        "spring_type": _enum(["compression", "extension", "torsion"], "Lò xo nén / kéo / xoắn", default="compression"),
        "wire_d_mm": _num(0.3, 30, "Đường kính dây", default=2.0),
        "outer_d_mm": _num(2, 300, "Đường kính ngoài", default=20.0),
        "free_length_mm": _num(5, 1500, "Chiều dài tự do (lò xo nén/kéo, kéo tính cả móc)"),
        "active_coils": _num(1.5, 60, "Số vòng làm việc", default=8.0),
        "ends": _enum(["ground", "closed", "open"], "Đầu lò xo nén: mài phẳng / khép kín / hở", default="ground"),
        "material": _enum(["spring_steel", "stainless"], default="spring_steel"),
    }, []),
    # ---------------------------------------------------------------- robot
    "robot_arm": _obj({
        "reach_mm": _num(300, 3200, "Tầm với (tâm J1 → mặt bích dụng cụ khi duỗi)", default=850.0),
        "payload_kg": _num(0.5, 500, "Tải định mức", default=5.0),
        "style": _enum(["cobot", "industrial"], "Cobot (kiểu UR) hay robot công nghiệp (khâu đúc kiểu KUKA)", default="cobot"),
        "end_effector": _enum(["gripper", "vacuum", "none"], "Tay kẹp hai ngón / giác hút / không", default="gripper"),
        "pose": _enum(["ready", "upright", "reach", "pick"], "Tư thế", default="ready"),
        **{f"j{i}_deg": _num(-360, 360, f"Góc khớp J{i} (độ)") for i in range(1, 7)},
    }, []),
    "robot_vacuum": _obj({
        "diameter_mm": _num(250, 420, "Đường kính thân", default=350.0),
        "lidar": _bool("Tháp LiDAR trên nóc", default=True),
        "side_brushes": _int(1, 2, "Số chổi cạnh", default=1),
        "mop": _bool("Có tấm lau nhà", default=False),
        "dock": _bool("Kèm đế sạc", default=True),
    }, []),
    "agv": _obj({
        "drive": _enum(["differential", "mecanum"], "Vi sai (2 bánh chủ động + bánh xoay) hay 4 bánh mecanum", default="differential"),
        "top": _enum(["lift", "cargo"], "Nâng kệ (kiểu Kiva) hay thùng chở hàng có nắp", default="lift"),
        "length_mm": _num(400, 2500, "Chiều dài thân", default=900.0),
        "lidar": _bool("Có LiDAR an toàn", default=True),
    }, []),
    # ---------------------------------------------------------------- phương tiện
    "fixed_wing": _obj({
        "aircraft_type": _enum(["light", "uav", "vtol"], "Máy bay hạng nhẹ 4 chỗ / UAV cánh cố định / UAV VTOL 4 rotor nâng",
                               default="light"),
        "wingspan_mm": _num(800, 40000, "Sải cánh (đầu cánh tới đầu cánh)"),
        "dihedral_deg": _num(0, 10, "Góc nhị diện cánh", default=3.0),
        "tail": _enum(["conventional", "v_tail", "t_tail"], "Kiểu đuôi", default="conventional"),
    }, []),
    "car": _obj({
        "body_type": _enum(["sedan", "suv", "hatchback"], "Kiểu thân", default="sedan"),
        "length_mm": _num(3000, 6000, "Chiều dài toàn bộ"),
        "drive": _enum(["rwd", "awd"], "Cầu sau (1 motor) hay hai cầu (2 motor)", default="rwd"),
    }, []),
    "motorbike": _obj({
        "bike_type": _enum(["motorcycle", "scooter", "ebike"], "Mô tô côn tay / xe tay ga / xe đạp điện", default="motorcycle"),
    }, []),
    "excavator": _obj({
        "size_class": _enum(["mini", "medium", "large"], "Cỡ máy: mini (~3 t), trung (~20 t), lớn (~45 t)", default="medium"),
        "pose": _enum(["dig", "transport", "reach"], "Tư thế cần: đào / di chuyển / vươn xa", default="dig"),
        "swing_deg": _num(-180, 180, "Góc quay toa (độ)", default=0.0),
    }, []),
    "forklift": _obj({
        "capacity_kg": _num(1000, 5000, "Tải nâng định mức", default=2500.0),
        "power": _enum(["electric", "diesel"], "Xe nâng điện (ắc quy) hay dầu", default="electric"),
        "fork_height_mm": _num(0, 4500, "Chiều cao mặt càng nâng", default=150.0),
    }, []),
    "crane": _obj({
        "boom_length_mm": _num(9000, 40000, "Chiều dài cần hiện tại (đã ra ống)", default=18000.0),
        "boom_angle_deg": _num(0, 80, "Góc nâng cần", default=45.0),
        "axles": _int(2, 4, "Số trục xe", default=3),
    }, []),
    "train": _obj({
        "traction": _enum(["diesel", "electric"], "Đầu máy diesel hay tàu điện (cần lấy điện)", default="diesel"),
        "wagons": _int(0, 4, "Số toa kéo theo", default=2),
        "wagon_type": _enum(["passenger", "freight"], "Toa khách hay toa hàng", default="passenger"),
        "gauge": _enum(["meter", "standard"], "Khổ ray 1000 mm (Việt Nam) hay 1435 mm", default="meter"),
    }, []),
    "cubesat": _obj({
        "units": _int(1, 12, "Kích thước CubeSat: 1, 2, 3, 6 hoặc 12U", default=3),
        "deployable_panels": _bool("Cánh pin mở (từ 2U)", default=True),
    }, []),
    "launch_vehicle": _obj({
        "stages": _int(2, 3, "Số tầng", default=2),
        "height_mm": _num(10000, 120000, "Chiều cao toàn bộ", default=70000.0),
        "diameter_mm": _num(1000, 10000, "Đường kính thân", default=3700.0),
        "fins": _bool("Cánh ổn định ở đuôi tầng 1", default=True),
    }, []),
    # ---------------------------------------------------------------- năng lượng & công trình
    "wind_turbine": _obj({
        "rotor_diameter_mm": _num(20000, 120000, "Đường kính rotor", default=90000.0),
        "hub_height_mm": _num(20000, 90000, "Chiều cao tâm rotor so với mặt đất"),
        "blades": _int(2, 3, "Số cánh", default=3),
        "nacelle_open": _bool("Mở nắp vỏ máy (nacelle) để thấy trục chính, hộp số, máy phát", default=False),
    }, []),
    "solar_array": _obj({
        "panels": _int(1, 40, "Số tấm pin", default=12),
        "rows": _int(1, 4, "Số hàng giá đỡ", default=2),
        "tilt_deg": _num(0, 45, "Góc nghiêng tấm pin (Việt Nam 10–20°)", default=15.0),
        "inverter": _bool("Kèm biến tần + tủ điện", default=True),
    }, []),
    "generator_set": _obj({
        "power_kva": _num(10, 1000, "Công suất định mức (kVA)", default=100.0),
        "enclosure": _enum(["open", "canopy"], "Khung trần hay vỏ cách âm", default="canopy"),
    }, []),
    "centrifugal_pump": _obj({
        "size": _enum(["50-32-160", "65-50-160", "80-65-160", "100-80-200", "125-100-250"],
                      "Cỡ EN 733: DN hút – DN đẩy – Ø cánh bơm danh nghĩa", default="65-50-160"),
        "motor_kw": _num(0.75, 90, "Công suất động cơ (kW)"),
    }, []),
    "storage_tank": _obj({
        "orientation": _enum(["vertical", "horizontal"], "Bồn đứng hay bồn nằm", default="vertical"),
        "capacity_m3": _num(1, 2000, "Dung tích (m³)", default=50.0),
        "diameter_mm": _num(800, 20000, "Đường kính bồn"),
        "roof": _enum(["cone", "dome"], "Mái côn hay mái vòm (bồn đứng)", default="cone"),
    }, []),
    "bridge": _obj({
        "bridge_type": _enum(["truss", "cable_stayed", "arch"], "Cầu giàn thép / cầu dây văng / cầu vòm", default="truss"),
        "span_mm": _num(20000, 120000, "Chiều dài nhịp chính", default=60000.0),
        "deck_width_mm": _num(4000, 20000, "Bề rộng mặt cầu", default=8000.0),
    }, []),
    "steel_truss": _obj({
        "truss_type": _enum(["pratt", "howe", "warren", "fink"], "Kiểu giàn", default="pratt"),
        "span_mm": _num(6000, 30000, "Nhịp giàn", default=12000.0),
        "height_mm": _num(800, 6000, "Chiều cao giàn ở giữa nhịp"),
        "panels": _int(4, 12, "Số khoang (chẵn)"),
    }, []),
    "lattice_tower": _obj({
        "tower_type": _enum(["power", "telecom"], "Cột điện cao thế hay tháp viễn thông", default="power"),
        "height_mm": _num(10000, 60000, "Chiều cao tháp", default=30000.0),
        "legs": _int(3, 4, "Số chân (tháp viễn thông có thể 3 chân)", default=4),
    }, []),
    # ---------------------------------------------------------------- chế tạo & điện tử
    "fdm_printer": _obj({
        "kinematics": _enum(["bedslinger", "corexy"], "Kiểu i3 (bàn trượt Y) hay CoreXY (hộp kín)", default="bedslinger"),
        "build_x_mm": _num(100, 400, "Vùng in X", default=220.0),
        "build_y_mm": _num(100, 400, "Vùng in Y", default=220.0),
        "build_z_mm": _num(100, 450, "Vùng in Z", default=250.0),
    }, []),
    "cnc_router": _obj({
        "travel_x_mm": _num(300, 1500, "Hành trình X", default=600.0),
        "travel_y_mm": _num(300, 1500, "Hành trình Y", default=400.0),
        "travel_z_mm": _num(60, 250, "Hành trình Z", default=100.0),
        "spindle_kw": _num(0.5, 5.5, "Công suất trục chính (kW)", default=2.2),
    }, []),
    "server_rack": _obj({
        "rack_units": _int(6, 48, "Chiều cao tủ tính theo U (1U = 44,45 mm)", default=42),
        "depth_mm": _num(450, 1200, "Chiều sâu tủ", default=1000.0),
        "equipment": _bool("Lắp thiết bị mẫu (máy chủ, switch, patch panel, PDU)", default=True),
    }, []),
    "electrical_enclosure": _obj({
        "width_mm": _num(200, 1200, "Bề rộng tủ", default=600.0),
        "height_mm": _num(200, 1400, "Chiều cao tủ", default=800.0),
        "depth_mm": _num(120, 400, "Chiều sâu tủ", default=250.0),
        "window": _bool("Cửa có ô kính quan sát", default=False),
    }, []),
    "axial_fan": _obj({
        "size_mm": _int(40, 140, "Cỡ quạt: 40, 60, 80, 92, 120, 140 mm", default=120),
        "blades": _int(5, 11, "Số cánh", default=7),
        "guard": _bool("Lưới bảo vệ", default=True),
    }, []),
    "heatsink": _obj({
        "heatsink_type": _enum(["tower", "extruded"], "Tản tháp ống đồng (CPU) hay tản nhôm đùn", default="tower"),
        "heat_pipes": _int(0, 8, "Số ống dẫn nhiệt (tản tháp)", default=4),
        "fan": _bool("Kèm quạt", default=True),
    }, []),
    "dev_board": _obj({
        "board": _enum(["arduino_uno", "raspberry_pi"], "Arduino Uno R3 hay Raspberry Pi 4 B", default="arduino_uno"),
    }, []),
}


# khoảng cách tâm tối thiểu để lắp động cơ (NEMA 17/23) cạnh gối đỡ trục bị dẫn trên cùng tấm đỡ
MIN_CENTER = {"GT2": 60.0, "HTD5M": 75.0}


class TechSpecError(ValueError):
    pass


def semantic_checks(spec: Any) -> None:
    """Kiểm tra liên hệ giữa tham số (ném TechSpecError, spec.py đổi thành SpecError)."""
    p, c = spec.params, spec.category
    if c == "gearbox":
        if p.get("stages", 2) == 2 and p.get("ratio", 12.0) > 60:
            raise TechSpecError("hộp 2 cấp chỉ hợp lý tới tỷ số 60 — tỷ số lớn hơn cần hộp 3 cấp")
    elif c == "stepper_motor":
        if p["frame_size"] not in S.NEMA:
            raise TechSpecError("động cơ bước hỗ trợ NEMA 17, 23 hoặc 34")
    elif c == "cylinder":
        if p.get("cylinder_type") == "pneumatic" and int(round(p["bore_mm"])) not in S.ISO15552:
            raise TechSpecError("xi lanh khí nén ISO 15552 chỉ có nòng " + ", ".join(str(b) for b in S.ISO15552) + " mm")
    elif c == "ball_screw":
        key = f"{int(round(p['diameter_mm'])):02d}{int(round(p['lead_mm'])):02d}"
        if key not in S.BALL_SCREWS:
            raise TechSpecError("vít me bi hỗ trợ SFU " + ", ".join(S.BALL_SCREWS) + " (đường kính + bước)")
        if p["length_mm"] < S.BALL_SCREWS[key]["nut_l"] * 2.5:
            raise TechSpecError("trục vít quá ngắn so với đai ốc bi")
    elif c == "linear_guide":
        g = S.LINEAR_GUIDES[p["series"]]
        if p["length_mm"] < g["car_l"] * p.get("carriages", 1) + 2 * g["e"]:
            raise TechSpecError("ray quá ngắn cho số con trượt")
    elif c == "spring":
        d, D = p["wire_d_mm"], p["outer_d_mm"]
        idx = (D - d) / d
        if not 3.0 <= idx <= 20.0:
            raise TechSpecError(f"chỉ số lò xo D/d = {idx:.1f} ngoài khoảng chế tạo được 3–20")
        if p.get("spring_type", "compression") == "compression" and p.get("free_length_mm"):
            n_total = p.get("active_coils", 8.0) + 2
            if p["free_length_mm"] <= n_total * d * 1.05:
                raise TechSpecError("chiều dài tự do nhỏ hơn chiều dài nén khít (số vòng × đường kính dây)")
    elif c == "belt_drive":
        belt = p.get("belt", "GT2")
        if belt in S.BELTS:
            r_sum = (p.get("teeth_driver", 20) + p.get("teeth_driven", 40)) * S.BELTS[belt]["pitch"] / 3.14159265 / 2
        else:
            d1 = p.get("pulley_d_mm", 100.0)
            r_sum = (d1 + p.get("pulley2_d_mm", 2 * d1)) / 2
        if p.get("center_distance_mm") and p["center_distance_mm"] < max(r_sum + 8, MIN_CENTER.get(belt, 0.0)):
            raise TechSpecError(f"khoảng cách tâm tối thiểu {max(r_sum + 8, MIN_CENTER.get(belt, 0.0)):.0f} mm "
                                "(tổng bán kính puly, chỗ lắp động cơ và gối đỡ)")
    elif c == "cubesat":
        if p.get("units", 3) not in S.CUBESAT:
            raise TechSpecError("CubeSat hỗ trợ 1U, 2U, 3U, 6U, 12U (CubeSat Design Specification)")
    elif c == "launch_vehicle":
        if p.get("height_mm", 70000.0) < 8 * p.get("diameter_mm", 3700.0):
            raise TechSpecError("tên lửa quá mập: chiều cao nên ≥ 8 lần đường kính")
    elif c in ("ball_valve", "pipe_fitting"):
        if p["dn"] not in S.PIPE_OD:
            raise TechSpecError("cỡ DN hỗ trợ: " + ", ".join(f"DN{d}" for d in DNS))
    elif c == "chain_drive":
        if p.get("teeth_driven", 34) < p.get("teeth_driver", 17):
            raise TechSpecError("đĩa bị dẫn nên có số răng ≥ đĩa dẫn (bộ giảm tốc)")
    elif c == "wind_turbine":
        D = p.get("rotor_diameter_mm", 90000.0)
        if p.get("hub_height_mm") and p["hub_height_mm"] < D / 2 + 10000.0:
            raise TechSpecError(f"tâm rotor phải cao ≥ {D / 2 + 10000:.0f} mm (đầu cánh cách đất ≥ 10 m)")
        if p.get("hub_height_mm", 0) + D / 2 > 150000.0:
            raise TechSpecError("tổng chiều cao (tâm rotor + bán kính) vượt 150 m")
    elif c == "solar_array":
        if p.get("panels", 12) < p.get("rows", 2):
            raise TechSpecError("số tấm pin phải ≥ số hàng giá đỡ")
    elif c == "bridge":
        if p.get("bridge_type") == "cable_stayed" and p.get("span_mm", 60000.0) * 1.8 > 150000.0:
            raise TechSpecError("cầu dây văng: nhịp chính tối đa 83 m trong mô hình (tổng dài với 2 nhịp biên ≤ 150 m)")
    elif c == "axial_fan":
        if p.get("size_mm", 120) not in S.FANS:
            raise TechSpecError("cỡ quạt hỗ trợ: " + ", ".join(f"{k} mm" for k in S.FANS))
    elif c == "server_rack":
        if p.get("equipment", True) and p.get("rack_units", 42) < 8:
            raise TechSpecError("tủ dưới 8U không đủ chỗ cho bộ thiết bị mẫu — chọn không lắp thiết bị hoặc tủ ≥ 8U")
    elif c == "steel_truss":
        if p.get("panels") and p["panels"] % 2:
            raise TechSpecError("số khoang giàn phải chẵn (đối xứng qua giữa nhịp)")


def normalize(spec: Any) -> None:
    p, c, used = spec.params, spec.category, spec.defaults_used
    if c == "stepper_motor":
        if "body_length_mm" not in p:
            p["body_length_mm"] = S.NEMA[p["frame_size"]]["lengths"][2]
            used.append(f"thân NEMA {p['frame_size']} dài {p['body_length_mm']:g} mm (cỡ phổ biến)")
    elif c == "cylinder":
        if p.get("cylinder_type") == "hydraulic" and "bore_mm" not in spec.explicit:
            used.append("nòng thủy lực mặc định 50 mm")
    elif c == "belt_drive":
        belt = p.get("belt", "GT2")
        if belt in S.BELTS:
            p.setdefault("width_mm", S.BELTS[belt]["widths"][0 if belt == "GT2" else 1])
            pd1 = p["teeth_driver"] * S.BELTS[belt]["pitch"] / 3.14159265
            pd2 = p["teeth_driven"] * S.BELTS[belt]["pitch"] / 3.14159265
        else:
            if "pulley_d_mm" not in p:
                p["pulley_d_mm"] = 100.0
                used.append("puly dẫn đường kính chuẩn 100 mm")
            p.setdefault("pulley2_d_mm", round(p["pulley_d_mm"] * 2, 1))
            pd1, pd2 = p["pulley_d_mm"], p["pulley2_d_mm"]
        if "center_distance_mm" not in p:
            p["center_distance_mm"] = round(max(1.2 * (pd1 + pd2), pd2 + 0.6 * pd1, MIN_CENTER.get(belt, 0.0) + 20), 1)
            used.append(f"khoảng cách tâm {p['center_distance_mm']:g} mm")
    elif c == "chain_drive":
        ch = S.CHAINS[p.get("chain", "08B")]
        if "center_distance_mm" not in p:
            p["center_distance_mm"] = round(35 * ch["pitch"], 1)
            used.append("khoảng cách tâm ≈ 35 bước xích (khuyến nghị 30–50 bước)")
    elif c == "shaft_coupling":
        p.setdefault("bore2_mm", p["bore_mm"])
    elif c == "fixed_wing":
        if "wingspan_mm" not in p:
            p["wingspan_mm"] = {"light": 11000.0, "uav": 2000.0, "vtol": 2400.0}[p.get("aircraft_type", "light")]
            used.append(f"sải cánh {p['wingspan_mm']:g} mm theo loại máy bay")
    elif c == "wind_turbine":
        if "hub_height_mm" not in p:
            D = p.get("rotor_diameter_mm", 90000.0)
            p["hub_height_mm"] = min(max(0.9 * D, D / 2 + 15000.0), 150000.0 - D / 2)
            used.append(f"tâm rotor cao {p['hub_height_mm'] / 1000:g} m (≈ 0,9 × đường kính rotor)")
    elif c == "centrifugal_pump":
        if "motor_kw" not in p:
            p["motor_kw"] = {"50-32-160": 4.0, "65-50-160": 7.5, "80-65-160": 11.0, "100-80-200": 22.0, "125-100-250": 45.0}[p.get("size", "65-50-160")]
            used.append(f"động cơ {p['motor_kw']:g} kW theo cỡ bơm")
    elif c == "steel_truss":
        span = p.get("span_mm", 12000.0)
        if "height_mm" not in p:
            p["height_mm"] = round(span / (4.0 if p.get("truss_type") == "fink" else 6.0), -1)
            used.append(f"cao giàn {p['height_mm']:g} mm (≈ nhịp/{4 if p.get('truss_type') == 'fink' else 6})")
        if "panels" not in p:
            p["panels"] = max(4, min(12, 2 * round(span / 3000.0)))
            used.append(f"{p['panels']} khoang")
    elif c == "car":
        if "length_mm" not in p:
            p["length_mm"] = {"sedan": 4700.0, "suv": 4600.0, "hatchback": 4100.0}[p.get("body_type", "sedan")]
            used.append(f"dài {p['length_mm']:g} mm theo kiểu thân")
    elif c == "spring":
        t = p.get("spring_type", "compression")
        d = p["wire_d_mm"]
        if "free_length_mm" not in p:
            n = p.get("active_coils", 8.0)
            if t == "compression":
                p["free_length_mm"] = round((n + 2) * d + n * 0.45 * (p["outer_d_mm"] - d), 1)
            elif t == "extension":
                p["free_length_mm"] = round((n + 1) * d + 2 * (p["outer_d_mm"] - d), 1)
            else:
                p["free_length_mm"] = round((n + 1) * d * 1.1, 1)
            used.append(f"chiều dài tự do {p['free_length_mm']:g} mm theo số vòng")


def questions(spec: Any) -> list[dict[str, str]]:
    if spec.category == "bearing" and "designation" not in spec.params:
        return [{"field": "designation", "question": "Anh cần ổ bi cỡ nào ạ (ví dụ 6204, 6000, 6305)?"}]
    return []
