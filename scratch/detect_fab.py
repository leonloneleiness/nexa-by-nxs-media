import sys; sys.path.insert(0, '.')
from nexa.three_d.planner import LocalPlanner, detect_category
CASES = [
    ("tạo máy in 3D", "fdm_printer"), ("tạo máy in 3D CoreXY 300x300x350", "fdm_printer"), ("máy in 3d có ổ bi và vít me", "fdm_printer"),
    ("tạo máy in 3D kiểu Ender 3", "fdm_printer"), ("thiết kế 3d printer voron", "fdm_printer"),
    ("tạo máy CNC 6040", "cnc_router"), ("tạo máy phay CNC 1200x800x200 trục chính 4 kW", "cnc_router"), ("tạo máy khắc gỗ cnc", "cnc_router"),
    ("máy cnc có vít me bi và ray trượt", "cnc_router"), ("tạo máy CNC router 800w", "cnc_router"),
    ("tạo tủ rack 42U", "server_rack"), ("tủ rack có quạt", "server_rack"), ("tạo tủ mạng 12U sâu 600", "server_rack"),
    ("tạo tủ server", "server_rack"), ("tủ 19 inch 27U", "server_rack"),
    ("tạo tủ điện 600x800x250", "electrical_enclosure"), ("tạo tủ điện có cửa kính", "electrical_enclosure"), ("hộp điện 300x400", "electrical_enclosure"),
    ("tủ điện có quạt", "electrical_enclosure"), ("tạo tủ điều khiển", "electrical_enclosure"),
    ("tạo quạt 120mm", "axial_fan"), ("quạt tản nhiệt 80 mm 9 cánh", "axial_fan"), ("tạo quạt máy tính", "axial_fan"), ("quạt 92mm không lưới", "axial_fan"),
    ("tạo tản nhiệt CPU 6 ống đồng", "heatsink"), ("tản nhiệt có quạt", "heatsink"), ("tạo tản nhiệt nhôm đùn", "heatsink"),
    ("tản nhiệt tháp không quạt", "heatsink"), ("tản nhiệt cho raspberry pi", "heatsink"),
    ("tạo bo mạch Arduino Uno", "dev_board"), ("tạo Raspberry Pi 4", "dev_board"), ("bo mạch có tản nhiệt", "dev_board"), ("tạo mạch arduino", "dev_board"),
    # không được phá nhóm khác
    ("tạo máy bay cánh quạt", "fixed_wing"), ("tạo drone 4 cánh quạt", "uav"), ("tạo máy phát điện 100 kVA", "generator_set"),
    ("hệ pin mặt trời có tủ điện", "solar_array"), ("tạo tuabin gió", "wind_turbine"), ("tạo máy bay", "fixed_wing"),
    ("tạo vít me bi SFU1605", "ball_screw"), ("tạo ray trượt HGR20", "linear_guide"), ("tạo động cơ bước NEMA 23", "stepper_motor"),
    ("tạo bánh răng thanh răng rack", "gear"), ("tạo trực thăng", "helicopter"), ("tạo từ điển", "generic"),
]
bad = 0
for t, want in CASES:
    got = detect_category(t)
    if got != want:
        bad += 1
        print("XX", t, "->", got, "want", want)
print("detect bad", bad, "/", len(CASES))
PARSE = [
    "tạo máy in 3D CoreXY 300x300x350", "tạo máy in 3D kiểu i3 vùng in 250 cao in 300", "tạo máy CNC 6040", "tạo máy phay CNC 1200x800x200 trục chính 4 kW",
    "tạo máy CNC router 800w hành trình z 80", "tạo tủ mạng 12U sâu 600", "tủ rack 42U không thiết bị", "tạo tủ điện 600x800x250 có cửa kính",
    "tủ điện rộng 400 cao 500 sâu 200", "quạt tản nhiệt 80 mm 9 cánh", "quạt 92mm không lưới", "tạo tản nhiệt CPU 6 ống đồng", "tản nhiệt nhôm đùn không quạt",
    "tạo Raspberry Pi 4", "tạo bo mạch Arduino Uno",
]
for t in PARSE:
    raw = LocalPlanner().parse(t)
    print(raw["category"], raw["params"], "|", raw.get("name"))
