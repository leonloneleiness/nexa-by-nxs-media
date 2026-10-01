p = 'nexa/three_d/benchmark.py'
s = open(p, encoding='utf-8').read()
s = s.replace('"vehicles", "energy"]', '"vehicles", "energy", "fabrication"]', 1)
fn = '''def _fabrication() -> list[BenchCase]:
    """Chế tạo & điện tử — 7 loại × 9 câu."""
    out: list[BenchCase] = []
    g = "fabrication"
    rows = [
        ("fdm_printer", [("Tạo máy in 3D", {}), ("Tạo máy in 3D CoreXY 300x300x350", {"kinematics": "corexy", "build_x_mm": 300.0, "build_y_mm": 300.0, "build_z_mm": 350.0}),
                         ("tao may in 3d kieu i3 vung in 250", {"kinematics": "bedslinger", "build_x_mm": 250.0, "build_y_mm": 250.0}),
                         ("Dựng máy in 3D kiểu Ender 3", {"kinematics": "bedslinger"}), ("Tạo máy in 3D Voron 350x350x340", {"kinematics": "corexy", "build_x_mm": 350.0}),
                         ("Thiết kế máy in 3D cao in 400 mm", {"build_z_mm": 400.0}), ("tạo mô hình máy in FDM hộp kín", {"kinematics": "corexy"}),
                         ("Tạo 3D printer 180x180x180", {"build_x_mm": 180.0, "build_y_mm": 180.0, "build_z_mm": 180.0}),
                         ("Tạo máy in nhựa 3D bàn trượt 220x220x250", {"kinematics": "bedslinger", "build_z_mm": 250.0})]),
        ("cnc_router", [("Tạo máy CNC", {}), ("Tạo máy CNC 6040", {"travel_x_mm": 600.0, "travel_y_mm": 400.0}),
                        ("tao may phay cnc 1200x800x200 truc chinh 4 kw", {"travel_x_mm": 1200.0, "travel_y_mm": 800.0, "travel_z_mm": 200.0, "spindle_kw": 4.0}),
                        ("Dựng máy khắc gỗ CNC 1325", {"travel_x_mm": 1300.0, "travel_y_mm": 1500.0}),
                        ("Tạo máy CNC router 800w hành trình Z 80", {"travel_z_mm": 80.0, "spindle_kw": 0.8}),
                        ("Thiết kế máy phay CNC 3040 trục chính 1,5 kW", {"travel_x_mm": 400.0, "travel_y_mm": 300.0, "spindle_kw": 1.5}),
                        ("tạo mô hình máy điêu khắc CNC 900x600", {"travel_x_mm": 900.0, "travel_y_mm": 600.0}),
                        ("Tạo CNC gia công gỗ 1500x1500x250 5,5 kW", {"travel_x_mm": 1500.0, "travel_y_mm": 1500.0, "travel_z_mm": 250.0, "spindle_kw": 5.5}),
                        ("Tạo máy CNC mini 2.2 kW", {"spindle_kw": 2.2})]),
        ("server_rack", [("Tạo tủ rack", {}), ("Tạo tủ rack 42U", {"rack_units": 42}), ("tao tu mang 12u sau 600", {"rack_units": 12, "depth_mm": 600.0}),
                         ("Dựng tủ server 27U sâu 800 mm", {"rack_units": 27, "depth_mm": 800.0}), ("Tạo tủ rack 19 inch 20U", {"rack_units": 20}),
                         ("Thiết kế tủ mạng 6U không thiết bị", {"rack_units": 6, "equipment": False}), ("tạo mô hình tủ rack có quạt", {}),
                         ("Tạo tủ máy chủ 48U sâu 1200", {"rack_units": 48, "depth_mm": 1200.0}), ("Tạo server rack 36U", {"rack_units": 36})]),
        ("electrical_enclosure", [("Tạo tủ điện", {}), ("Tạo tủ điện 600x800x250", {"width_mm": 600.0, "height_mm": 800.0, "depth_mm": 250.0}),
                                  ("tao tu dien 400x500x200 co cua kinh", {"width_mm": 400.0, "height_mm": 500.0, "depth_mm": 200.0, "window": True}),
                                  ("Dựng tủ điều khiển rộng 800 cao 1200 sâu 300", {"width_mm": 800.0, "height_mm": 1200.0, "depth_mm": 300.0}),
                                  ("Tạo hộp điện 300x400", {"width_mm": 300.0, "height_mm": 400.0}), ("Thiết kế tủ phân phối không ô kính", {"window": False}),
                                  ("tạo mô hình tủ điện có ô kính quan sát", {"window": True}), ("Tạo tủ aptomat 250x300x150", {"width_mm": 250.0, "height_mm": 300.0, "depth_mm": 150.0}),
                                  ("Tạo tủ điện 1000x1400x400", {"width_mm": 1000.0, "height_mm": 1400.0, "depth_mm": 400.0})]),
        ("axial_fan", [("Tạo quạt tản nhiệt", {}), ("Tạo quạt 120mm", {"size_mm": 120}), ("tao quat 80 mm 9 canh", {"size_mm": 80, "blades": 9}),
                       ("Dựng quạt máy tính 140 mm", {"size_mm": 140}), ("Tạo quạt 92mm không lưới", {"size_mm": 92, "guard": False}),
                       ("Thiết kế quạt 40 mm 5 cánh", {"size_mm": 40, "blades": 5}), ("tạo mô hình quạt case 12 cm", {"size_mm": 120}),
                       ("Tạo quạt 60mm có lưới bảo vệ", {"size_mm": 60, "guard": True}), ("Tạo quạt tản nhiệt 12V 11 cánh", {"blades": 11})]),
        ("heatsink", [("Tạo tản nhiệt CPU", {"heatsink_type": "tower"}), ("Tạo tản nhiệt CPU 6 ống đồng", {"heatsink_type": "tower", "heat_pipes": 6}),
                      ("tao tan nhiet nhom dun", {"heatsink_type": "extruded"}), ("Dựng tản nhiệt tháp không quạt", {"heatsink_type": "tower", "fan": False}),
                      ("Tạo tản nhiệt có quạt", {"fan": True}), ("Thiết kế heatsink 8 heat pipe", {"heat_pipes": 8}),
                      ("tạo mô hình tản nhiệt nhôm đùn không quạt", {"heatsink_type": "extruded", "fan": False}),
                      ("Tạo tản khí CPU 2 ống đồng", {"heat_pipes": 2}), ("Tạo tản nhiệt tháp 4 ống dẫn nhiệt", {"heatsink_type": "tower", "heat_pipes": 4})]),
        ("dev_board", [("Tạo bo mạch Arduino Uno", {"board": "arduino_uno"}), ("Tạo Raspberry Pi 4", {"board": "raspberry_pi"}),
                       ("tao mach arduino", {"board": "arduino_uno"}), ("Dựng bo mạch phát triển", {}), ("Tạo máy tính nhúng Raspberry Pi", {"board": "raspberry_pi"}),
                       ("Thiết kế kit Arduino Uno R3", {"board": "arduino_uno"}), ("tạo mô hình bo mạch vi điều khiển", {}),
                       ("Tạo RPi 4 model B", {"board": "raspberry_pi"}), ("Tạo board Arduino ATmega328", {"board": "arduino_uno"})]),
    ]
    for cat, items in rows:
        for txt, exp in items:
            _mk(g, out, txt, cat, **exp)
    return out


def cases() -> list[BenchCase]:'''
s = s.replace('def cases() -> list[BenchCase]:', fn, 1)
s = s.replace('_robotics() + _vehicles() + _energy())', '_robotics() + _vehicles() + _energy() + _fabrication())', 1)
open(p, 'w', encoding='utf-8').write(s)
print("ok")
