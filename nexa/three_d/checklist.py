"""Checklist bộ phận bắt buộc theo nhóm — do MÃ tính từ ModelSpec, không lấy từ lời AI tự khai.

Mỗi mục: loại bộ phận (category trong Part3D) + số lượng tối thiểu + mô tả tiếng Việt. Quality gate đối chiếu
checklist với các bộ phận thật trong mô hình (đếm theo category), nên "thiếu cánh quạt" hay "3 motor thay vì 4"
bị phát hiện bất kể template/provider nào tạo ra mô hình.
"""
from __future__ import annotations

from dataclasses import dataclass

from nexa.three_d.spec import ModelSpec


@dataclass(frozen=True)
class ChecklistItem:
    category: str
    count: int
    label_vi: str
    required: bool = True


def canonical_checklist(spec: ModelSpec) -> list[ChecklistItem]:
    p = spec.params
    c = spec.category
    items: list[ChecklistItem] = []
    add = items.append
    if c == "uav":
        n = int(p.get("arm_count", 4))
        add(ChecklistItem("frame", 1, "khung/thân chính"))
        add(ChecklistItem("shell", 1, "vỏ"))
        add(ChecklistItem("arm", n, f"{n} tay đòn"))
        add(ChecklistItem("motor", n, f"{n} motor"))
        add(ChecklistItem("propeller", n, f"{n} cánh quạt"))
        add(ChecklistItem("battery", 1, "pin"))
        if p.get("camera", "front") != "none":
            add(ChecklistItem("camera", 1, "camera"))
        if p.get("landing_gear", True):
            add(ChecklistItem("landing_gear", 1, "càng đáp"))
    elif c == "rover":
        n = int(p.get("wheel_count", 6))
        add(ChecklistItem("frame", 1, "khung gầm"))
        add(ChecklistItem("shell", 1, "vỏ thân"))
        add(ChecklistItem("wheel", n, f"{n} bánh xe"))
        add(ChecklistItem("motor", n, f"{n} động cơ bánh"))
        add(ChecklistItem("suspension", 2, "hệ treo hai bên"))
        add(ChecklistItem("battery", 1, "pin"))
        if p.get("lidar", True):
            add(ChecklistItem("lidar", 1, "LiDAR"))
        if p.get("camera", True):
            add(ChecklistItem("camera", 1, "camera"))
    elif c == "humanoid":
        add(ChecklistItem("head", 1, "đầu"))
        add(ChecklistItem("torso", 1, "thân"))
        add(ChecklistItem("pelvis", 1, "hông"))
        add(ChecklistItem("hand", 2, "hai bàn tay"))
        add(ChecklistItem("foot", 2, "hai bàn chân"))
        add(ChecklistItem("arm_segment", 4, "hai cánh tay (tay trên + cẳng tay)"))
        add(ChecklistItem("leg_segment", 4, "hai chân (đùi + cẳng chân)"))
        add(ChecklistItem("joint", 12, "các khớp vai/khuỷu/hông/gối/cổ chân/cổ/eo"))
        add(ChecklistItem("battery", 1, "pin"))
    elif c == "quadruped":
        jpl = int(p.get("joints_per_leg", 3))
        add(ChecklistItem("frame", 1, "khung thân"))
        add(ChecklistItem("shell", 1, "vỏ"))
        add(ChecklistItem("head", 1, "đầu cảm biến"))
        add(ChecklistItem("leg_segment", 8, "4 chân × (đùi + cẳng chân)"))
        add(ChecklistItem("joint", 4 * jpl, f"4 chân × {jpl} khớp"))
        add(ChecklistItem("foot", 4, "4 bàn chân"))
        add(ChecklistItem("battery", 1, "pin"))
        if p.get("head_sensor", "both") in ("lidar", "both"):
            add(ChecklistItem("lidar", 1, "LiDAR"))
    elif c == "helicopter":
        add(ChecklistItem("fuselage", 1, "thân"))
        add(ChecklistItem("canopy", 1, "kính buồng lái"))
        add(ChecklistItem("tail_boom", 1, "cần đuôi"))
        add(ChecklistItem("stabilizer", 1, "cánh đuôi"))
        add(ChecklistItem("rotor_hub", 2, "đầu rotor chính + rotor đuôi"))
        nb, nt = int(p.get("main_blades", 4)), int(p.get("tail_rotor_blades", 4))
        add(ChecklistItem("rotor_blade", nb + nt, f"{nb} lá rotor chính + {nt} lá rotor đuôi"))
        add(ChecklistItem("landing_gear", 1, "càng đáp"))
        if p.get("role", "rescue") == "rescue" and p.get("hoist", True):
            add(ChecklistItem("hoist", 1, "tời cứu hộ"))
    elif c == "boat":
        n = int(p.get("engines", 1))
        inboard = (p.get("propulsion") or ("outboard" if p.get("boat_type", "speedboat") == "speedboat" else "inboard")) == "inboard"
        add(ChecklistItem("hull", 1, "thân tàu"))
        add(ChecklistItem("deck", 1, "boong"))
        add(ChecklistItem("propeller", n, f"{n} chân vịt"))
        add(ChecklistItem("motor", n, f"{n} máy/trục chân vịt"))
        if inboard:
            add(ChecklistItem("rudder", 1, "bánh lái"))
        if p.get("cabin", True):
            add(ChecklistItem("cabin", 1, "cabin/bàn lái"))
        if p.get("railings", True):
            add(ChecklistItem("railing", 1, "lan can"))
        add(ChecklistItem("fitting", 1, "cọc buộc dây + đèn hàng hải"))
    elif c == "bolt":
        add(ChecklistItem("bolt", 1, "bu-lông"))
        if p.get("include_nut"):
            add(ChecklistItem("nut", 1, "đai ốc"))
        if p.get("include_washer"):
            add(ChecklistItem("washer", 1, "vòng đệm"))
    elif c in ("nut", "washer", "gear", "flange", "bracket"):
        add(ChecklistItem(c, 1, {"nut": "đai ốc", "washer": "vòng đệm", "gear": "bánh răng", "flange": "mặt bích",
                                 "bracket": "giá đỡ"}[c]))
    else:
        items += tech_checklist(spec)
    return items


def tech_checklist(spec: ModelSpec) -> list[ChecklistItem]:
    """Bộ phận bắt buộc của các mẫu kỹ thuật mở rộng (linh kiện chuẩn, robot, phương tiện, công trình, máy chế tạo)."""
    from nexa.three_d import standards as S
    p, c = spec.params, spec.category
    out: list[ChecklistItem] = []
    add = out.append
    if c == "bearing":
        z = S.bearing_balls(p["designation"])[0] if p.get("designation") in S.BEARINGS else 1
        add(ChecklistItem("bearing_ring", 2, "vòng trong + vòng ngoài"))
        add(ChecklistItem("ball", z, f"{z} viên bi"))
        add(ChecklistItem("cage", 1, "vòng cách"))
        if p.get("seal", "open") in ("2RS", "ZZ"):
            add(ChecklistItem("seal", 2, "2 phớt/nắp chắn"))
    elif c == "stepper_motor":
        add(ChecklistItem("housing", 2, "nắp trước (mặt bích) + nắp sau"))
        add(ChecklistItem("stator", 1, "stator lá thép"))
        add(ChecklistItem("shaft", 1, "trục + rotor"))
        add(ChecklistItem("screw", 1, "vít xuyên thân"))
        add(ChecklistItem("connector", 1, "đầu cắm/ống luồn dây"))
        add(ChecklistItem("cable", 1, "dây pha"))
    elif c == "gearbox":
        n = int(p.get("stages", 2))
        add(ChecklistItem("housing", 2, "vỏ hộp hai nửa"))
        add(ChecklistItem("shaft", n + 1, f"{n + 1} trục"))
        add(ChecklistItem("gear", 2 * n, f"{2 * n} bánh răng ({n} cấp)"))
        add(ChecklistItem("bearing", 2 * (n + 1), f"{2 * (n + 1)} ổ bi"))
        add(ChecklistItem("seal", 2, "phớt trục vào/ra"))
        add(ChecklistItem("cover", 2 * (n + 1) + 1, "nắp ổ + nắp thăm"))
        add(ChecklistItem("fastener", 1, "bu-lông mặt ghép"))
        add(ChecklistItem("sight_glass", 1, "mắt thăm dầu"))
        add(ChecklistItem("plug", 1, "nút xả dầu"))
    elif c == "cylinder":
        add(ChecklistItem("cylinder_barrel", 1, "nòng"))
        add(ChecklistItem("housing", 2, "nắp trước + nắp sau"))
        add(ChecklistItem("piston", 1, "piston"))
        add(ChecklistItem("rod", 1, "cần piston"))
        add(ChecklistItem("tie_rod", 1, "thanh giằng"))
        add(ChecklistItem("nut", 1, "đai ốc thanh giằng"))
        add(ChecklistItem("fitting", 2, "2 cổng khí/dầu"))
    elif c == "ball_valve":
        add(ChecklistItem("valve_body", 2, "thân van + nắp đầu"))
        add(ChecklistItem("valve_ball", 1, "bi van"))
        add(ChecklistItem("seal", 2, "2 đệm PTFE"))
        add(ChecklistItem("shaft", 1, "trục van"))
        add(ChecklistItem("handle", 1, "tay gạt"))
        add(ChecklistItem("fastener", 1, "bu-lông ghép thân"))
        add(ChecklistItem("nut", 1, "nắp ép gioăng"))
    elif c == "pipe_fitting":
        kind = p.get("fitting", "elbow90")
        stubs = {"tee": 3}.get(kind, 2) if p.get("pipe_stubs", True) else 0
        if kind == "flange_joint":
            add(ChecklistItem("flange", 2, "2 mặt bích"))
            add(ChecklistItem("seal", 1, "gioăng"))
            add(ChecklistItem("fastener", 1, "bu-lông"))
            add(ChecklistItem("nut", 1, "đai ốc"))
        else:
            add(ChecklistItem("fitting", 1, "phụ kiện (co/tê)"))
        if stubs:
            add(ChecklistItem("pipe", stubs, f"{stubs} đoạn ống"))
    elif c == "belt_drive":
        add(ChecklistItem("belt", 1, "dây đai"))
        add(ChecklistItem("pulley", 2, "2 puly"))
        add(ChecklistItem("shaft", 2, "2 trục"))
        add(ChecklistItem("frame", 1, "tấm đỡ"))
        add(ChecklistItem("bearing", 1, "gối đỡ trục"))
        if p.get("belt", "GT2") in S.BELTS:
            add(ChecklistItem("motor", 1, "động cơ dẫn"))
    elif c == "chain_drive":
        add(ChecklistItem("chain", 1, "xích con lăn"))
        add(ChecklistItem("sprocket", 2, "2 đĩa xích"))
        add(ChecklistItem("shaft", 2, "2 trục"))
        add(ChecklistItem("bearing", 2, "2 gối đỡ"))
        add(ChecklistItem("frame", 1, "tấm đỡ"))
    elif c == "shaft_coupling":
        jaw = p.get("coupling_type", "jaw") == "jaw"
        add(ChecklistItem("coupling_hub", 2 if jaw else 1, "2 moay-ơ" if jaw else "ống kẹp"))
        if jaw:
            add(ChecklistItem("spider", 1, "đệm sao"))
        add(ChecklistItem("shaft", 2, "2 đầu trục"))
        add(ChecklistItem("screw", 1, "vít hãm/kẹp"))
    elif c == "ball_screw":
        add(ChecklistItem("shaft", 1, "trục vít me"))
        add(ChecklistItem("nut", 2, "đai ốc bi + đai ốc khóa"))
        add(ChecklistItem("bearing", 2, "gối BK + BF"))
    elif c == "linear_guide":
        n = int(p.get("carriages", 2))
        add(ChecklistItem("rail", 1, "ray"))
        add(ChecklistItem("carriage", n, f"{n} con trượt"))
        add(ChecklistItem("screw", 1, "vít lắp ray"))
    elif c == "spring":
        add(ChecklistItem("spring", 1, "lò xo (thân + móc/chân liền một dây)"))
    elif c == "robot_arm":
        add(ChecklistItem("base", 1, "đế robot"))
        add(ChecklistItem("joint", 5, "5 cụm khớp: vai (J1+J2), khuỷu (J3), cổ tay J4/J5/J6"))
        add(ChecklistItem("link", 2, "cánh tay trên + cẳng tay"))
        add(ChecklistItem("tool_flange", 1, "mặt bích dụng cụ ISO 9409-1"))
        add(ChecklistItem("cable", 2, "cáp dọc cánh tay"))
        if p.get("end_effector", "gripper") != "none":
            add(ChecklistItem("end_effector", 1, "dụng cụ (kẹp/giác hút)"))
    elif c == "robot_vacuum":
        add(ChecklistItem("chassis", 1, "khung gầm"))
        add(ChecklistItem("shell", 1, "nắp trên"))
        add(ChecklistItem("bumper", 1, "cản trước"))
        add(ChecklistItem("wheel", 2, "2 bánh chủ động"))
        add(ChecklistItem("caster", 1, "bánh xoay"))
        add(ChecklistItem("brush", 1 + int(p.get("side_brushes", 1)), "chổi chính + chổi cạnh"))
        add(ChecklistItem("dustbin", 1, "khay bụi"))
        add(ChecklistItem("button", 1, "nút điều khiển"))
        if p.get("lidar", True):
            add(ChecklistItem("lidar", 1, "tháp LiDAR"))
        if p.get("dock", True):
            add(ChecklistItem("dock", 1, "đế sạc"))
    elif c == "agv":
        mec = p.get("drive", "differential") == "mecanum"
        add(ChecklistItem("frame", 1, "khung gầm thép"))
        add(ChecklistItem("shell", 1, "vỏ thân"))
        add(ChecklistItem("wheel", 4 if mec else 2, "4 bánh mecanum" if mec else "2 bánh chủ động"))
        if not mec:
            add(ChecklistItem("caster", 4, "4 bánh xoay"))
        add(ChecklistItem("battery", 1, "pin"))
        add(ChecklistItem("bumper", 2, "cản trước/sau"))
        add(ChecklistItem("estop", 1, "nút dừng khẩn cấp"))
        add(ChecklistItem("light", 1, "đèn trạng thái"))
        add(ChecklistItem("camera", 1, "camera 3D"))
        if p.get("lidar", True):
            add(ChecklistItem("lidar", 2, "2 máy quét laser an toàn"))
        add(ChecklistItem("cargo" if p.get("top") == "cargo" else "lift", 1, "thùng hàng" if p.get("top") == "cargo" else "đầu nâng kệ"))
    elif c == "cubesat":
        add(ChecklistItem("frame", 1, "khung 4 ray góc"))
        add(ChecklistItem("pcb", 1, "chồng bo mạch"))
        add(ChecklistItem("antenna", 1, "ăng-ten"))
    elif c == "launch_vehicle":
        add(ChecklistItem("stage", int(p.get("stages", 2)), "các tầng"))
        add(ChecklistItem("engine", int(p.get("stages", 2)), "động cơ mỗi tầng"))
        add(ChecklistItem("interstage", 1 if int(p.get("stages", 2)) == 2 else 2, "vòng nối tầng"))
        add(ChecklistItem("fairing", 2, "2 nửa chóp mũi"))
        add(ChecklistItem("payload", 1, "vệ tinh tải trọng"))
        if p.get("fins", True):
            add(ChecklistItem("fin", 1, "cánh ổn định"))
    elif c == "train":
        n = 1 + int(p.get("wagons", 2))
        add(ChecklistItem("track", 1, "đường ray"))
        add(ChecklistItem("wheelset", 4 * n, "bộ trục bánh"))
        add(ChecklistItem("bogie", 2 * n, "giá chuyển hướng"))
        add(ChecklistItem("car_body", n, "thân xe"))
        add(ChecklistItem("coupler", 2 * n, "móc nối"))
        if p.get("traction", "diesel") == "electric":
            add(ChecklistItem("pantograph", 1, "cần lấy điện"))
            add(ChecklistItem("catenary", 1, "dây tiếp xúc"))
    elif c == "fixed_wing":
        add(ChecklistItem("fuselage", 1, "thân"))
        add(ChecklistItem("wing", 1, "cánh chính"))
        add(ChecklistItem("control_surface", 4 if p.get("tail", "conventional") != "v_tail" else 4, "cánh lái (aileron, elevator, rudder)"))
        add(ChecklistItem("tail", 2, "bộ đuôi"))
        add(ChecklistItem("propeller", 5 if p.get("aircraft_type") == "vtol" else 1, "cánh quạt"))
        add(ChecklistItem("landing_gear", 2, "càng đáp"))
        add(ChecklistItem("canopy", 1, "kính buồng lái"))
    elif c == "car":
        add(ChecklistItem("car_body", 1, "thân vỏ"))
        add(ChecklistItem("door", 4, "4 cửa"))
        add(ChecklistItem("wheel", 4, "4 bánh"))
        add(ChecklistItem("suspension", 4, "hệ treo + phanh"))
        add(ChecklistItem("battery", 1, "pin sàn"))
        add(ChecklistItem("motor", 2 if p.get("drive") == "awd" else 1, "motor điện"))
        add(ChecklistItem("hood", 1, "nắp capô"))
        add(ChecklistItem("trunk", 1, "nắp cốp / cửa hậu"))
        add(ChecklistItem("interior", 1, "nội thất"))
    elif c == "motorbike":
        t = p.get("bike_type", "motorcycle")
        add(ChecklistItem("frame", 1, "khung"))
        add(ChecklistItem("fork", 1, "phuộc trước"))
        add(ChecklistItem("wheel", 2, "2 bánh"))
        add(ChecklistItem("seat", 1, "yên"))
        if t == "motorcycle":
            add(ChecklistItem("engine", 1, "động cơ"))
            add(ChecklistItem("fuel_tank", 1, "bình xăng"))
            add(ChecklistItem("swingarm", 1, "càng sau"))
            add(ChecklistItem("chain", 1, "xích"))
        elif t == "scooter":
            add(ChecklistItem("engine", 1, "động cơ + CVT"))
            add(ChecklistItem("body_panel", 1, "vỏ nhựa"))
        else:
            add(ChecklistItem("battery", 1, "pin"))
            add(ChecklistItem("crankset", 1, "đùi đĩa"))
            add(ChecklistItem("chain", 1, "xích"))
    elif c == "excavator":
        add(ChecklistItem("undercarriage", 1, "gầm xích"))
        add(ChecklistItem("track", 2, "2 dải xích"))
        add(ChecklistItem("upper_structure", 1, "thân trên"))
        add(ChecklistItem("cab", 1, "cabin"))
        add(ChecklistItem("boom", 1, "cần"))
        add(ChecklistItem("stick", 1, "tay gầu"))
        add(ChecklistItem("bucket", 1, "gầu"))
        add(ChecklistItem("hydraulic_cylinder", 4, "4 xi lanh thủy lực"))
    elif c == "forklift":
        add(ChecklistItem("chassis", 1, "khung xe"))
        add(ChecklistItem("counterweight", 1, "đối trọng"))
        add(ChecklistItem("wheel", 4, "4 bánh"))
        add(ChecklistItem("mast", 2, "khung nâng (≥ 2 tầng)"))
        add(ChecklistItem("fork_carriage", 1, "giá càng"))
        add(ChecklistItem("fork", 2, "2 càng"))
        add(ChecklistItem("hydraulic_cylinder", 3, "xi lanh nâng + 2 xi lanh nghiêng"))
        add(ChecklistItem("frame", 1, "khung bảo vệ trên đầu"))
    elif c == "crane":
        add(ChecklistItem("carrier", 1, "xe cơ sở"))
        add(ChecklistItem("wheel", 2 * int(p.get("axles", 3)), "bánh xe"))
        add(ChecklistItem("outrigger", 4, "4 chân chống"))
        add(ChecklistItem("turntable", 1, "bàn quay"))
        add(ChecklistItem("boom", 4, "cần ống lồng (≥ 4 đoạn)"))
        add(ChecklistItem("hydraulic_cylinder", 1, "xi lanh nâng cần"))
        add(ChecklistItem("rope", 1, "cáp tời"))
        add(ChecklistItem("hook", 1, "móc cẩu"))
    elif c == "wind_turbine":
        add(ChecklistItem("foundation", 1, "móng"))
        add(ChecklistItem("tower", 1, "tháp"))
        add(ChecklistItem("yaw", 1, "hệ quay hướng"))
        add(ChecklistItem("nacelle", 1, "vỏ nacelle"))
        add(ChecklistItem("shaft", 1, "trục chính"))
        add(ChecklistItem("gearbox", 1, "hộp số"))
        add(ChecklistItem("generator", 1, "máy phát"))
        add(ChecklistItem("hub", 1, "moay-ơ"))
        add(ChecklistItem("blade", int(p.get("blades", 3)), "cánh"))
    elif c == "solar_array":
        add(ChecklistItem("solar_panel", int(p.get("panels", 12)), "tấm pin"))
        add(ChecklistItem("rack", 1, "giá đỡ"))
        add(ChecklistItem("clamp", 1, "kẹp tấm"))
        add(ChecklistItem("foundation", 1, "móng"))
        if p.get("inverter", True):
            add(ChecklistItem("inverter", 1, "biến tần"))
            add(ChecklistItem("cabinet", 1, "tủ điện"))
    elif c == "generator_set":
        add(ChecklistItem("base", 1, "khung đế + bồn dầu"))
        add(ChecklistItem("engine", 1, "động cơ"))
        add(ChecklistItem("alternator", 1, "đầu phát"))
        add(ChecklistItem("control_panel", 1, "tủ điều khiển"))
        add(ChecklistItem("isolator", 1, "đệm chống rung"))
        add(ChecklistItem("pipe", 1, "ống xả"))
        if p.get("enclosure", "canopy") == "canopy":
            add(ChecklistItem("canopy_frame", 1, "vỏ cách âm"))
            add(ChecklistItem("door", 4, "cửa hông"))
    elif c == "centrifugal_pump":
        add(ChecklistItem("pump_casing", 1, "vỏ xoắn"))
        add(ChecklistItem("impeller", 1, "cánh bơm"))
        add(ChecklistItem("shaft", 1, "trục"))
        add(ChecklistItem("coupling_hub", 1, "khớp nối"))
        add(ChecklistItem("motor", 1, "động cơ"))
        add(ChecklistItem("base", 1, "đế"))
    elif c == "storage_tank":
        add(ChecklistItem("tank_shell", 1, "thân bồn"))
        add(ChecklistItem("foundation", 1, "móng / bệ"))
        add(ChecklistItem("pipe", 1, "vòi"))
        add(ChecklistItem("valve_body", 1, "van"))
        if p.get("orientation", "vertical") == "vertical":
            add(ChecklistItem("tank_roof", 1, "mái"))
            add(ChecklistItem("ladder", 1, "thang"))
            add(ChecklistItem("manway", 1, "cửa người chui"))
        else:
            add(ChecklistItem("saddle", 1, "yên đỡ"))
    elif c == "bridge":
        t = p.get("bridge_type", "truss")
        add(ChecklistItem("abutment", 1, "mố cầu"))
        add(ChecklistItem("deck", 1, "mặt cầu"))
        if t == "truss":
            add(ChecklistItem("truss_member", 4, "thanh giàn"))
            add(ChecklistItem("gusset", 1, "bản mã"))
            add(ChecklistItem("bolt", 1, "bu-lông"))
            add(ChecklistItem("floor_beam", 1, "dầm ngang"))
        elif t == "cable_stayed":
            add(ChecklistItem("pylon", 2, "tháp cầu"))
            add(ChecklistItem("cable", 1, "dây văng"))
        else:
            add(ChecklistItem("arch", 1, "sườn vòm"))
            add(ChecklistItem("hanger", 1, "dây treo"))
    elif c == "steel_truss":
        add(ChecklistItem("truss_member", 3, "thanh cánh + thanh bụng"))
        add(ChecklistItem("gusset", 1, "bản mã"))
        add(ChecklistItem("bolt", 1, "bu-lông"))
        add(ChecklistItem("column", 1, "cột"))
        add(ChecklistItem("foundation", 1, "móng"))
    elif c == "lattice_tower":
        add(ChecklistItem("foundation", 1, "móng"))
        add(ChecklistItem("tower_leg", 1, "chân tháp"))
        add(ChecklistItem("bracing", 1, "thanh giằng"))
        if p.get("tower_type", "power") == "power":
            add(ChecklistItem("crossarm", 1, "xà"))
            add(ChecklistItem("insulator", 1, "chuỗi cách điện"))
        else:
            add(ChecklistItem("antenna", 1, "ăng-ten"))
            add(ChecklistItem("platform", 1, "sàn công tác"))
    elif c == "fdm_printer":
        add(ChecklistItem("frame", 1, "khung nhôm định hình"))
        add(ChecklistItem("rail", 2, "ray dẫn hướng"))
        add(ChecklistItem("carriage", 2, "con trượt"))
        add(ChecklistItem("bed", 1, "bàn nhiệt"))
        add(ChecklistItem("build_plate", 1, "tấm in"))
        add(ChecklistItem("belt", 2, "dây đai"))
        add(ChecklistItem("motor", 3, "động cơ bước"))
        add(ChecklistItem("pulley", 2, "puly"))
        add(ChecklistItem("shaft", 1, "vít me trục Z"))
        add(ChecklistItem("hotend", 1, "đầu phun"))
        add(ChecklistItem("power_supply", 1, "nguồn"))
        add(ChecklistItem("electronics", 1, "bo điều khiển"))
    elif c == "cnc_router":
        add(ChecklistItem("frame", 1, "khung + cầu gantry"))
        add(ChecklistItem("table", 1, "bàn rãnh T"))
        add(ChecklistItem("rail", 3, "ray trượt X/Y/Z"))
        add(ChecklistItem("carriage", 3, "con trượt"))
        add(ChecklistItem("shaft", 3, "vít me bi"))
        add(ChecklistItem("nut", 3, "đai ốc bi"))
        add(ChecklistItem("bearing", 3, "gối đỡ BK/BF"))
        add(ChecklistItem("motor", 3, "động cơ"))
        add(ChecklistItem("coupling", 3, "khớp nối"))
        add(ChecklistItem("spindle", 1, "trục chính"))
        add(ChecklistItem("tool", 1, "dao phay"))
        add(ChecklistItem("housing", 1, "hộp điều khiển"))
        add(ChecklistItem("estop", 1, "nút dừng khẩn"))
    elif c == "server_rack":
        add(ChecklistItem("frame", 1, "khung tủ"))
        add(ChecklistItem("rail", 1, "thanh ray 19 inch"))
        add(ChecklistItem("door", 2, "cửa trước + sau"))
        add(ChecklistItem("cover", 2, "vách hông"))
        add(ChecklistItem("fan_frame", 1, "quạt nóc"))
        add(ChecklistItem("caster", 1, "bánh xe"))
        if p.get("equipment", True):
            add(ChecklistItem("rack_device", 1, "thiết bị lắp tủ"))
    elif c == "electrical_enclosure":
        add(ChecklistItem("enclosure_body", 1, "vỏ tủ"))
        add(ChecklistItem("door", 1, "cửa"))
        add(ChecklistItem("mounting_plate", 1, "tấm lắp thiết bị"))
        add(ChecklistItem("din_rail", 1, "thanh ray DIN"))
        add(ChecklistItem("breaker", 1, "aptomat"))
        if float(p.get("width_mm", 600.0)) >= 400.0:                   # tủ nhỏ một hàng ray: không có máng cáp
            add(ChecklistItem("duct", 1, "máng cáp"))
        add(ChecklistItem("gland", 1, "ốc siết cáp"))
    elif c == "axial_fan":
        add(ChecklistItem("fan_frame", 1, "khung quạt"))
        add(ChecklistItem("rotor", 1, "cánh quạt"))
        add(ChecklistItem("cable", 1, "dây nguồn"))
        if p.get("guard", True):
            add(ChecklistItem("guard", 1, "lưới bảo vệ"))
    elif c == "heatsink":
        add(ChecklistItem("heatsink_base", 1, "đế tiếp xúc"))
        if p.get("heatsink_type", "tower") == "tower":                 # nhôm đùn: lá liền đế
            add(ChecklistItem("fins", 1, "lá tản nhiệt"))
            if int(p.get("heat_pipes", 4)) > 0:
                add(ChecklistItem("heat_pipe", 1, "ống đồng"))
        if p.get("fan", True):
            add(ChecklistItem("fan_frame", 1, "quạt"))
    elif c == "dev_board":
        add(ChecklistItem("pcb", 1, "bản mạch"))
        add(ChecklistItem("chip", 1, "vi điều khiển / SoC"))
        add(ChecklistItem("connector", 1, "chân cắm"))
        add(ChecklistItem("port", 1, "cổng giao tiếp"))
    return out


def evaluate(checklist: list[ChecklistItem], part_categories: list[str]) -> tuple[float, list[str]]:
    """(tỷ lệ đủ 0..1, danh sách thiếu tiếng Việt) — đếm theo category."""
    if not checklist:
        return 1.0, []
    counts: dict[str, int] = {}
    for cat in part_categories:
        counts[cat] = counts.get(cat, 0) + 1
    got, need, missing = 0.0, 0.0, []
    for item in checklist:
        have = counts.get(item.category, 0)
        need += item.count
        got += min(have, item.count)
        if have < item.count and item.required:
            missing.append(f"{item.label_vi} (có {have}/{item.count})")
    return (got / need if need else 1.0), missing
