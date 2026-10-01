"""Engineering questions for every supported category, not fabrication approval."""
from nexa.three_d.spec import CATEGORIES

# Each category names the interfaces/performance that its visual template cannot certify.
CHECKS = {
    "uav": "khối lượng cất cánh; lực đẩy motor/cánh/ESC/pin; bộ điều khiển bay; tâm khối lượng",
    "rover": "tải mỗi bánh; mô-men truyền động; bánh/trục/gá motor; nguồn và điều khiển",
    "humanoid": "tải và mô-men từng khớp; encoder/phanh; cân bằng; nguồn và điều khiển",
    "quadruped": "tải và mô-men từng khớp; chân/hộp số; cân bằng; nguồn và điều khiển",
    "helicopter": "động lực rotor; hệ điều khiển cánh; truyền động; cân bằng và kết cấu",
    "boat": "lượng chiếm nước; ổn định; độ kín; truyền động và lái",
    "bolt": "ren và dung sai; chiều dài kẹp; cấp bền; mô-men siết",
    "nut": "ren và dung sai; cấp bền; chiều cao ăn ren; cặp bu-lông tương thích",
    "washer": "đường kính lỗ/ngoài/độ dày; độ cứng; bề mặt tựa",
    "gear": "module/góc áp lực/số răng; khoảng cách trục; backlash; vật liệu và tải",
    "flange": "vòng chia và lỗ bu-lông; mặt ghép; gioăng; tải hoặc áp suất",
    "bracket": "vật liệu và chiều dày; tải; lỗ ghép; phương pháp gia công",
    "bearing": "mã/hậu tố hãng; dung sai lắp trục/vỏ; tải và tốc độ; bôi trơn",
    "stepper_motor": "mã motor; bản vẽ mặt bích/trục; dòng pha/driver; đường cong mô-men/tốc độ",
    "gearbox": "tỷ số truyền thực; tải/rpm; trục và then; ổ bi và bôi trơn",
    "cylinder": "áp suất; lực/hành trình; kiểu gá và cổng; van và giới hạn hành trình",
    "ball_valve": "DN và kiểu đầu nối; vật liệu/gioăng; môi chất/áp suất/nhiệt độ",
    "pipe_fitting": "DN/ren/tiêu chuẩn mặt bích; vật liệu; môi chất và áp suất",
    "belt_drive": "bước/biên dạng đai; puly và chiều rộng; khoảng cách trục; lực căng",
    "chain_drive": "cỡ xích; số răng; khoảng cách trục; tải và bôi trơn",
    "shaft_coupling": "hai đường kính trục; kiểu khóa; mô-men/rpm; sai lệch cho phép",
    "ball_screw": "mã vít/đai ốc; bước và chiều dài; gối đỡ; tải/tốc độ tới hạn",
    "linear_guide": "mã ray/con trượt; bước lỗ; tải/mô-men; độ phẳng bệ lắp",
    "spring": "vật liệu dây; độ cứng; hành trình làm việc; ứng suất và tuổi thọ",
    "robot_arm": "tải đầu công tác; mô-men khớp; hộp số/encoder/phanh; điều khiển",
    "robot_vacuum": "motor bánh/chổi/quạt; lưu lượng hút; pin/sạc; cảm biến và firmware",
    "agv": "tải và phanh; bánh/motor/hộp số; pin/sạc; cảm biến và dừng khẩn cấp",
    "fixed_wing": "khí động và kết cấu; tâm khối lượng; động lực/servo; điều khiển bay",
    "car": "khung và hệ treo; phanh/lái; truyền động; pin và điện công suất",
    "motorbike": "khung và hệ treo; phanh/lái; truyền động; pin và điện công suất",
    "excavator": "tải kết cấu; xi lanh/van/bơm; ổn định; mạch điều khiển",
    "forklift": "tải nâng và tâm tải; cột/xích/xi lanh; ổn định; phanh và điều khiển",
    "crane": "biểu đồ tải; cáp/puly/tời; kết cấu; ổn định và giới hạn hành trình",
    "train": "khổ đường và bộ bánh; bogie; phanh; kết cấu và truyền động",
    "cubesat": "giao diện cơ khí; ngân sách điện/nhiệt; liên lạc; thử rung và môi trường",
    "launch_vehicle": "hồ sơ thiết kế chuyên ngành; kết cấu; nhiệt và tải; quy trình thử được thẩm định",
    "wind_turbine": "tải gió; rotor/trục/ổ bi; máy phát/phanh; kết cấu tháp",
    "solar_array": "mã tấm pin; điện áp/dòng chuỗi; inverter/bảo vệ; tải gió và gá lắp",
    "generator_set": "động cơ/đầu phát; khớp nối; làm mát/xả; bảo vệ điện",
    "centrifugal_pump": "lưu lượng/cột áp; motor/trục; phớt/ổ bi; đường cong bơm",
    "storage_tank": "môi chất/áp suất; vật liệu và chiều dày; mối hàn; thử kín",
    "bridge": "tải trọng; vật liệu/tiết diện; liên kết/gối/móng; tính toán kết cấu",
    "steel_truss": "tải trọng; tiết diện; nút liên kết; ổn định và tính toán kết cấu",
    "lattice_tower": "tải gió; tiết diện; liên kết/móng; ổn định kết cấu",
    "fdm_printer": "hành trình và ray/đai/vít me; hotend/bed; driver/nguồn; dây điện và firmware",
    "cnc_router": "độ cứng khung; ray/vít me; spindle và lực cắt; driver/nguồn/giới hạn hành trình",
    "server_rack": "khoảng lỗ gá thiết bị; tải; thông gió; tiếp địa",
    "electrical_enclosure": "cấp bảo vệ/vật liệu; gá thiết bị; tản nhiệt; tiếp địa và sơ đồ điện",
    "axial_fan": "mã quạt/khoảng lỗ; điện áp/dòng; lưu lượng/áp tĩnh; chiều gió",
    "heatsink": "công suất nhiệt; điện trở nhiệt; mặt tiếp xúc và gá; luồng khí",
    "dev_board": "mã/revision bo; bản vẽ lỗ gá; điện áp và pinout; firmware",
    "generic": "xác định loại sản phẩm; chức năng từng cụm; bản vẽ và danh sách linh kiện thực",
}

PURCHASE_ASSEMBLIES = {"bearing", "stepper_motor", "gearbox", "cylinder", "ball_valve", "shaft_coupling",
                       "ball_screw", "linear_guide", "axial_fan", "dev_board"}

SOURCES = {
    "bearing": [{"title": "SKF 6204 — ví dụ catalogue, không tự gán cho mọi ổ bi",
                 "url": "https://www.emarketplace.in.skf.com/deep-groove-ball-bearing/6204"}],
    "stepper_motor": [{"title": "Pololu 2267 — ví dụ motor NEMA 17, cần đối chiếu đúng mã",
                       "url": "https://www.pololu.com/product/2267"}],
    "dev_board": [{"title": "Arduino UNO R3 — datasheet tham khảo, cần đúng loại/revision",
                   "url": "https://docs.arduino.cc/resources/datasheets/A000066-datasheet.pdf"}],
}


def requirements(category):
    return [x.strip() for x in CHECKS.get(category, CHECKS["generic"]).split(";")]


def coverage():
    return {c: c in CHECKS for c in CATEGORIES}
