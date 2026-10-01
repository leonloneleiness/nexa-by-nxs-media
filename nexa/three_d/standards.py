"""Bảng số liệu tiêu chuẩn cho các mẫu CAD kỹ thuật (mm). Mỗi bảng ghi rõ nguồn.

Chỉ dùng số liệu công bố trong tiêu chuẩn/catalogue phổ biến; chỗ nào là ƯỚC LƯỢNG theo tỷ lệ thiết kế thì ghi rõ
(ví dụ số bi và đường kính bi của ổ lăn — mỗi hãng khác nhau, tiêu chuẩn ISO 15 không quy định).
Quality gate (measure.py) đo lại trên khối thật và so với các bảng này.
"""
from __future__ import annotations

import math

# ------------------------------------------------------------------ ổ bi rãnh sâu — ISO 15:2017 (kích thước biên)
# mã → (d lỗ, D ngoài, B rộng, r_s min vát). Dãy đường kính 0 (60xx), 2 (62xx), 3 (63xx), dãy chiều rộng 1/0.
# Nguồn: ISO 15:2017 bảng kích thước biên; khớp catalogue SKF/NSK "Deep groove ball bearings".
BEARINGS: dict[str, tuple[float, float, float, float]] = {
    "6000": (10, 26, 8, 0.3), "6001": (12, 28, 8, 0.3), "6002": (15, 32, 9, 0.3), "6003": (17, 35, 10, 0.3),
    "6004": (20, 42, 12, 0.6), "6005": (25, 47, 12, 0.6), "6006": (30, 55, 13, 1.0), "6007": (35, 62, 14, 1.0),
    "6008": (40, 68, 15, 1.0), "6009": (45, 75, 16, 1.0), "6010": (50, 80, 16, 1.0), "6011": (55, 90, 18, 1.1),
    "6012": (60, 95, 18, 1.1),
    "6200": (10, 30, 9, 0.6), "6201": (12, 32, 10, 0.6), "6202": (15, 35, 11, 0.6), "6203": (17, 40, 12, 0.6),
    "6204": (20, 47, 14, 1.0), "6205": (25, 52, 15, 1.0), "6206": (30, 62, 16, 1.0), "6207": (35, 72, 17, 1.1),
    "6208": (40, 80, 18, 1.1), "6209": (45, 85, 19, 1.1), "6210": (50, 90, 20, 1.1), "6211": (55, 100, 21, 1.5),
    "6212": (60, 110, 22, 1.5),
    "6300": (10, 35, 11, 0.6), "6301": (12, 37, 12, 1.0), "6302": (15, 42, 13, 1.0), "6303": (17, 47, 14, 1.0),
    "6304": (20, 52, 15, 1.1), "6305": (25, 62, 17, 1.1), "6306": (30, 72, 19, 1.1), "6307": (35, 80, 21, 1.5),
    "6308": (40, 90, 23, 1.5), "6309": (45, 100, 25, 1.5), "6310": (50, 110, 27, 2.0), "6311": (55, 120, 29, 2.0),
    "6312": (60, 130, 31, 2.1),
}
# Đường kính bi tiêu chuẩn ISO 3290-1 (inch đổi mm + cỡ mét) dùng để làm tròn đường kính bi ước lượng.
BALL_SIZES = [2.0, 2.381, 2.5, 3.0, 3.175, 3.5, 3.969, 4.0, 4.5, 4.762, 5.0, 5.556, 5.953, 6.0, 6.35, 6.747, 7.0, 7.144,
              7.5, 7.938, 8.0, 8.5, 8.731, 9.0, 9.525, 10.0, 10.319, 11.0, 11.112, 11.5, 11.906, 12.0, 12.303, 12.7, 13.494,
              14.0, 14.288, 15.081, 15.875, 16.669, 17.462, 19.05, 20.638, 22.225, 23.812]


def bearing_balls(code: str) -> tuple[int, float, float]:
    """(số bi Z, đường kính bi Dw, đường kính vòng tâm bi dm) — ƯỚC LƯỢNG theo tỷ lệ thiết kế ổ bi rãnh sâu
    (Harris & Kotzalas, Rolling Bearing Analysis: Dw ≈ 0,30·(D−d) dãy 62, 0,27 dãy 60, 0,34 dãy 63; góc chiếm của
    vòng cách ~ 190–200° Conrad), làm tròn theo cỡ bi ISO 3290. Catalogue hãng có thể khác ±1 bi."""
    d, D, _B, _r = BEARINGS[code]
    k = {"0": 0.27, "2": 0.30, "3": 0.34}[code[1]]
    dm = (d + D) / 2
    raw = k * (D - d)
    dw = min(BALL_SIZES, key=lambda s: abs(s - raw))
    # lắp kiểu Conrad: tổng góc chiếm của bi ≤ ~ 186° + 2·asin… → Z ≈ floor(π·dm·0,58/Dw)+1
    z = int(math.floor(math.pi * dm * 0.56 / dw)) + 1
    return max(6, min(z, 16)), dw, dm


# ------------------------------------------------------------------ động cơ bước — NEMA ICS 16-2001
# cỡ → (cạnh mặt bích, khoảng cách tâm lỗ (vuông), Ø lỗ/ren, Ø gờ định tâm, cao gờ, Ø trục, dài trục, chiều dài thân gợi ý)
# Nguồn: NEMA ICS 16 (khung 17/23/34: gờ 0,866"/1,500"/2,875"; khoảng lỗ 1,220"/1,856"/2,740"; trục 5 mm/0,25"/0,5").
NEMA: dict[int, dict] = {
    17: dict(flange=42.3, hole_spacing=31.0, hole_d=3.0, hole_kind="M3", pilot_d=22.0, pilot_h=2.0, shaft_d=5.0,
             shaft_len=24.0, lengths=(34.0, 40.0, 48.0, 60.0), flat=0.5),
    23: dict(flange=56.4, hole_spacing=47.14, hole_d=5.1, hole_kind="Ø5,1", pilot_d=38.1, pilot_h=1.6, shaft_d=6.35,
             shaft_len=20.6, lengths=(41.0, 56.0, 76.0, 100.0), flat=0.5),
    34: dict(flange=86.0, hole_spacing=69.6, hole_d=5.5, hole_kind="Ø5,5", pilot_d=73.0, pilot_h=2.0, shaft_d=12.7,
             shaft_len=31.8, lengths=(66.0, 80.0, 98.0, 114.0), flat=1.2),
}

# ------------------------------------------------------------------ xi lanh khí nén — ISO 15552:2018
# bore → (Ø cần, ren cần KK, khoảng tâm thanh giằng TG, cạnh nắp E, cổng khí)
# Nguồn: ISO 15552 bảng kích thước lắp lẫn (TG, KK, Ø cần); cạnh nắp E theo catalogue Festo DSBC/SMC CP96.
ISO15552: dict[int, dict] = {
    32: dict(rod=12, kk="M10×1,25", kk_d=10, tg=32.5, e=45, port="G1/8"),
    40: dict(rod=16, kk="M12×1,25", kk_d=12, tg=38.0, e=52, port="G1/4"),
    50: dict(rod=20, kk="M16×1,5", kk_d=16, tg=46.5, e=65, port="G1/4"),
    63: dict(rod=20, kk="M16×1,5", kk_d=16, tg=56.5, e=75, port="G3/8"),
    80: dict(rod=25, kk="M20×1,5", kk_d=20, tg=72.0, e=95, port="G3/8"),
    100: dict(rod=25, kk="M20×1,5", kk_d=20, tg=89.0, e=115, port="G1/2"),
    125: dict(rod=32, kk="M27×2", kk_d=27, tg=110.0, e=140, port="G1/2"),
}

# ------------------------------------------------------------------ đường ống — DN, OD, mặt bích, phụ kiện hàn
# OD ống: EN 10220 / ISO 4200 dãy 1 (trùng ASME B36.10M). NPS tương ứng.
PIPE_OD: dict[int, float] = {15: 21.3, 20: 26.9, 25: 33.7, 32: 42.4, 40: 48.3, 50: 60.3, 65: 76.1, 80: 88.9, 100: 114.3,
                             125: 139.7, 150: 168.3, 200: 219.1}
PIPE_WALL: dict[int, float] = {15: 2.77, 20: 2.87, 25: 3.38, 32: 3.56, 40: 3.68, 50: 3.91, 65: 5.16, 80: 5.49, 100: 6.02,
                               125: 6.55, 150: 7.11, 200: 8.18}      # ASME B36.10M SCH 40
NPS: dict[int, float] = {15: 0.5, 20: 0.75, 25: 1.0, 32: 1.25, 40: 1.5, 50: 2.0, 65: 2.5, 80: 3.0, 100: 4.0, 125: 5.0,
                         150: 6.0, 200: 8.0}
# Mặt bích EN 1092-1 PN16 (kiểu 11 cổ hàn): DN → (D ngoài, K vòng tâm lỗ, Ø lỗ L, số lỗ, ren bu-lông, dày C2)
FLANGE_PN16: dict[int, tuple[float, float, float, int, int, float]] = {
    15: (95, 65, 14, 4, 12, 16), 20: (105, 75, 14, 4, 12, 18), 25: (115, 85, 14, 4, 12, 18), 32: (140, 100, 18, 4, 16, 18),
    40: (150, 110, 18, 4, 16, 18), 50: (165, 125, 18, 4, 16, 18), 65: (185, 145, 18, 8, 16, 18), 80: (200, 160, 18, 8, 16, 20),
    100: (220, 180, 18, 8, 16, 20), 125: (250, 210, 18, 8, 16, 22), 150: (285, 240, 22, 8, 20, 22), 200: (340, 295, 22, 12, 20, 24),
}
# Đường kính mặt gờ nổi d1 (EN 1092-1 PN16, gờ cao f1 = 2 mm).
FLANGE_RF: dict[int, float] = {15: 45, 20: 58, 25: 68, 32: 78, 40: 88, 50: 102, 65: 122, 80: 138, 100: 158, 125: 188,
                               150: 212, 200: 268}
# Phụ kiện hàn đối đầu ASME B16.9: co 90° bán kính dài A = 1,5·NPS (in), co 45° B, tê đều C (mm).
ELBOW45_B: dict[int, float] = {15: 16, 20: 19, 25: 22, 32: 25, 40: 29, 50: 35, 65: 44, 80: 51, 100: 64, 125: 79, 150: 95, 200: 127}
TEE_C: dict[int, float] = {15: 25, 20: 29, 25: 38, 32: 48, 40: 57, 50: 64, 65: 76, 80: 86, 100: 105, 125: 124, 150: 143, 200: 178}
# Van bi: chiều dài mặt–mặt ASME B16.10 Class 150 kiểu ngắn (short pattern).
VALVE_FTF: dict[int, float] = {15: 108, 20: 117, 25: 127, 32: 140, 40: 165, 50: 178, 65: 190, 80: 203, 100: 229, 125: 356,
                               150: 394, 200: 457}


def elbow90_a(dn: int) -> float:
    """ASME B16.9 co 90° bán kính dài: A = 1,5 × NPS × 25,4 (NPS ≥ 3/4); NPS 1/2 = 38 mm."""
    return 38.0 if dn == 15 else 1.5 * NPS[dn] * 25.4


# ------------------------------------------------------------------ truyền động đai / xích / khớp nối
# Đai răng: bước p, chiều cao răng ht, tổng dày hs, bề rộng thường dùng. Nguồn: Gates PowerGrip GT2/GT3 & HTD catalogue.
BELTS: dict[str, dict] = {
    "GT2": dict(pitch=2.0, tooth_h=0.75, total_h=1.38, widths=(6.0, 9.0, 10.0), pld=0.254),
    "HTD5M": dict(pitch=5.0, tooth_h=2.06, total_h=3.8, widths=(9.0, 15.0, 25.0), pld=0.5715),
}
# Đai thang hẹp ISO 4184 / DIN 7753: bề rộng đỉnh b, chiều cao h, góc rãnh 38°, bề rộng chuẩn lp.
VBELTS: dict[str, dict] = {"SPZ": dict(top=9.7, height=8.0, lp=8.5), "SPA": dict(top=12.7, height=10.0, lp=11.0),
                           "SPB": dict(top=16.3, height=13.0, lp=14.0)}
# Xích con lăn ISO 606 dãy B (châu Âu): bước p, Ø con lăn d1, rộng trong b1, Ø chốt d2, cao má h2.
CHAINS: dict[str, dict] = {
    "06B": dict(pitch=9.525, roller=6.35, inner_w=5.72, pin=3.28, plate_h=8.2, plate_t=1.3),
    "08B": dict(pitch=12.7, roller=8.51, inner_w=7.75, pin=4.45, plate_h=11.8, plate_t=1.6),
    "10B": dict(pitch=15.875, roller=10.16, inner_w=9.65, pin=5.08, plate_h=14.7, plate_t=1.7),
    "12B": dict(pitch=19.05, roller=12.07, inner_w=11.68, pin=5.72, plate_h=16.1, plate_t=1.85),
    "16B": dict(pitch=25.4, roller=15.88, inner_w=17.02, pin=8.28, plate_h=21.0, plate_t=4.0),
}
# Khớp nối vấu (jaw) kiểu ROTEX/Lovejoy: cỡ → (Ø ngoài, tổng dài, Ø lỗ tối đa). Nguồn: catalogue KTR ROTEX.
JAW_COUPLINGS: dict[int, tuple[float, float, float]] = {14: (30, 35, 16), 19: (40, 66, 24), 24: (55, 78, 28),
                                                       28: (65, 90, 38), 38: (80, 114, 45), 42: (95, 126, 55)}

# ------------------------------------------------------------------ vít me bi, ray trượt
# Vít me bi cán SFU (kiểu DIN 69051 mặt bích): (d, bước) → Ø bi, Ø thân đai ốc, Ø mặt bích, dày bích, dài đai ốc,
# Ø vòng lỗ, số lỗ, Ø lỗ. Nguồn: catalogue TBI Motion SFU/SFI.
BALL_SCREWS: dict[str, dict] = {
    "1204": dict(d=12, lead=4, ball=2.5, nut_d=24, flange_d=40, flange_t=8, nut_l=35, pcd=32, holes=6, hole_d=4.5),
    "1605": dict(d=16, lead=5, ball=3.175, nut_d=28, flange_d=48, flange_t=10, nut_l=42, pcd=38, holes=6, hole_d=5.5),
    "1610": dict(d=16, lead=10, ball=3.175, nut_d=28, flange_d=48, flange_t=10, nut_l=57, pcd=38, holes=6, hole_d=5.5),
    "2005": dict(d=20, lead=5, ball=3.175, nut_d=36, flange_d=58, flange_t=10, nut_l=42, pcd=47, holes=6, hole_d=6.6),
    "2505": dict(d=25, lead=5, ball=3.175, nut_d=40, flange_d=62, flange_t=10, nut_l=42, pcd=51, holes=6, hole_d=6.6),
    "2510": dict(d=25, lead=10, ball=4.762, nut_d=40, flange_d=62, flange_t=12, nut_l=62, pcd=51, holes=6, hole_d=6.6),
    "3205": dict(d=32, lead=5, ball=3.175, nut_d=50, flange_d=80, flange_t=12, nut_l=55, pcd=65, holes=6, hole_d=9.0),
    "3210": dict(d=32, lead=10, ball=6.35, nut_d=50, flange_d=80, flange_t=12, nut_l=90, pcd=65, holes=6, hole_d=9.0),
}
# Ray dẫn hướng tuyến tính. HIWIN HG (HGR ray + HGH..CA con trượt) và MGN (miniature).
# (rộng ray W_R, cao ray H_R, bước lỗ P, Ø lỗ đi qua d, Ø lỗ bậc D, sâu bậc h, rộng con trượt W, dài L, cao tổng H,
#  khoảng ốc con trượt B×C, ren ốc). Nguồn: catalogue HIWIN Linear Guideway (HG, MG series).
LINEAR_GUIDES: dict[str, dict] = {
    "HGR15": dict(rail_w=15, rail_h=15, pitch=60, hole_d=4.5, cb_d=7.5, cb_h=5.3, car_w=34, car_l=61.4, h=28, b=26, c=26, m=4, e=20),
    "HGR20": dict(rail_w=20, rail_h=17.5, pitch=60, hole_d=6.0, cb_d=9.5, cb_h=8.5, car_w=44, car_l=77.5, h=30, b=32, c=36, m=5, e=20),
    "HGR25": dict(rail_w=23, rail_h=22, pitch=60, hole_d=7.0, cb_d=11.0, cb_h=9.0, car_w=48, car_l=84.0, h=40, b=35, c=35, m=6, e=20),
    "HGR30": dict(rail_w=28, rail_h=26, pitch=80, hole_d=9.0, cb_d=14.0, cb_h=12.0, car_w=60, car_l=97.4, h=45, b=40, c=40, m=8, e=20),
    "MGN7": dict(rail_w=7, rail_h=4.8, pitch=15, hole_d=2.4, cb_d=4.2, cb_h=2.3, car_w=17, car_l=22.5, h=8, b=12, c=8, m=2, e=5),
    "MGN9": dict(rail_w=9, rail_h=6.5, pitch=20, hole_d=3.5, cb_d=6.0, cb_h=3.5, car_w=20, car_l=28.9, h=10, b=15, c=10, m=3, e=7.5),
    "MGN12": dict(rail_w=12, rail_h=8, pitch=25, hole_d=3.5, cb_d=6.0, cb_h=4.5, car_w=27, car_l=34.7, h=13, b=20, c=15, m=3, e=10),
    "MGN15": dict(rail_w=15, rail_h=10, pitch=40, hole_d=3.5, cb_d=6.0, cb_h=5.0, car_w=32, car_l=42.1, h=16, b=25, c=20, m=3, e=15),
}
# Gối đỡ vít me BK (cố định) theo Ø ngõng trục. Nguồn: catalogue THK/HIWIN support unit BK/BF.
SCREW_SUPPORTS: dict[int, dict] = {
    12: dict(bk="BK10", w=60, h=39, l=25, center_h=22, journal=10),
    16: dict(bk="BK12", w=60, h=43, l=25, center_h=25, journal=12),
    20: dict(bk="BK15", w=70, h=48, l=27, center_h=28, journal=15),
    25: dict(bk="BK20", w=88, h=60, l=35, center_h=34, journal=20),
    32: dict(bk="BK25", w=106, h=80, l=42, center_h=48, journal=25),
}


# ------------------------------------------------------------------ robot
# Mặt bích dụng cụ ISO 9409-1: ký hiệu → (Ø vòng lỗ d1, số lỗ, ren, Ø lỗ định tâm d3 (H7), Ø ngoài bích, lỗ chốt Ø).
ISO9409: dict[str, dict] = {
    "31.5-4-M5": dict(pcd=31.5, n=4, thread=5.0, pilot=20.0, d=40.0, pin=5.0),
    "40-4-M6": dict(pcd=40.0, n=4, thread=6.0, pilot=25.0, d=50.0, pin=6.0),
    "50-4-M6": dict(pcd=50.0, n=4, thread=6.0, pilot=31.5, d=63.0, pin=6.0),
    "63-4-M6": dict(pcd=63.0, n=4, thread=6.0, pilot=40.0, d=80.0, pin=6.0),
    "80-6-M8": dict(pcd=80.0, n=6, thread=8.0, pilot=50.0, d=100.0, pin=8.0),
    "100-6-M8": dict(pcd=100.0, n=6, thread=8.0, pilot=63.0, d=125.0, pin=8.0),
    "125-6-M10": dict(pcd=125.0, n=6, thread=10.0, pilot=80.0, d=160.0, pin=10.0),
}
# Tỷ lệ động học cánh tay 6 trục kiểu UR (Universal Robots UR5 DH: d1 89,2; a2 425; a3 392; d4 109,3; d5 94,75;
# d6 82,5 mm; tầm với 850 mm) — dùng để co giãn theo tầm với yêu cầu.
UR_RATIOS = dict(d1=0.105, a2=0.5, a3=0.461, y_shoulder=0.16, elbow_back=0.141, d4=0.111, d5=0.1115, d6=0.097)


# ------------------------------------------------------------------ không gian
# CubeSat Design Specification rev. 14.1 (Cal Poly, 2022): kích thước ngoài (X × Y × Z, mm), Z dọc ray.
CUBESAT: dict[int, tuple[float, float, float]] = {1: (100.0, 100.0, 113.5), 2: (100.0, 100.0, 227.0), 3: (100.0, 100.0, 340.5),
                                                  6: (100.0, 226.3, 366.0), 12: (226.3, 226.3, 366.0)}
CUBESAT_RAIL = dict(width=8.5, min_contact=6.5, standoff=6.5, edge_radius=1.0)   # ray góc, mặt tiếp xúc ≥ 6,5 mm
# Khổ đường ray (khoảng cách mép trong hai ray, mm): khổ mét (đường sắt Việt Nam) và khổ tiêu chuẩn UIC/AREMA.
RAIL_GAUGE: dict[str, float] = {"meter": 1000.0, "standard": 1435.0}
RAIL_PROFILE: dict[str, dict] = {                                                  # ray P43 (khổ mét VN) / UIC 60
    "meter": dict(height=140.0, head=70.0, foot=114.0, web=14.5), "standard": dict(height=172.0, head=72.0, foot=150.0, web=16.5)}


# ------------------------------------------------------------------ chế tạo / điện tử
# Tủ rack 19" EIA-310-E / IEC 60297: bề rộng tấm mặt 482,6 mm, khoảng tâm lỗ ray 465,1 mm, lòng ray 450 mm (≥ 17,72"),
# 1U = 44,45 mm; mỗi U 3 lỗ cách mép U 6,35 / 22,225 / 38,1 mm (bước 15,875 – 15,875 – 12,7).
RACK = dict(panel_width=482.6, hole_spacing=465.1, opening=450.0, u=44.45, hole_offsets=(6.35, 22.225, 38.1), square_hole=9.5)
# Quạt hướng trục thông dụng (cạnh khung, dày, khoảng tâm lỗ vít): 40/60/80/92/120/140 mm.
FANS: dict[int, tuple[float, float, float]] = {40: (40.0, 10.0, 32.0), 60: (60.0, 15.0, 50.0), 80: (80.0, 25.0, 71.5),
                                              92: (92.0, 25.0, 82.5), 120: (120.0, 25.0, 105.0), 140: (140.0, 25.0, 124.5)}
# Nhôm định hình V-slot/T-slot 20 mm: rãnh 6 mm, lỗ tâm Ø4,2 (ren M5), 2040 = hai ô 2020.
EXTRUSION_20 = dict(size=20.0, slot=6.0, slot_depth=6.0, core=4.2, wall=1.8)
# Vít me T8 (máy in 3D): Ø8, bước 2 mm, 4 đầu mối → bước dẫn 8 mm; đai ốc đồng mặt bích Ø22.
T8 = dict(d=8.0, pitch=2.0, lead=8.0, nut_flange=22.0, nut_len=15.0)
# Bo mạch: Arduino Uno R3 (68,58 × 53,34 mm; lỗ bắt Ø3,2 theo tọa độ bản vẽ Arduino) và Raspberry Pi 4 B (85 × 56 mm;
# 4 lỗ M2,5 lưới 58 × 49 mm cách mép 3,5 mm; GPIO 2 × 20 bước 2,54 mm).
BOARDS: dict[str, dict] = {
    "arduino_uno": dict(w=68.58, h=53.34, t=1.6, holes=[(13.97, 2.54), (15.24, 50.8), (66.04, 7.62), (66.04, 35.56)], hole_d=3.2, pitch=2.54),
    "raspberry_pi": dict(w=85.0, h=56.0, t=1.4, holes=[(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)], hole_d=2.75, pitch=2.54),
}
# Aptomat tép (MCB) theo mô-đun DIN 43880: rộng 17,5–18 mm/cực, thanh ray DIN EN 60715 TH35-7,5.
DIN_MODULE, DIN_RAIL = 18.0, dict(w=35.0, h=7.5, t=1.0)


def tool_flange_for(payload_kg: float) -> str:
    """Chọn cỡ mặt bích ISO 9409-1 theo tải (quy ước phổ biến của hãng: UR3–UR16 dùng 50-4-M6)."""
    if payload_kg <= 16:
        return "50-4-M6"
    if payload_kg <= 30:
        return "63-4-M6"
    if payload_kg <= 120:
        return "100-6-M8"
    return "125-6-M10"


def nearest_key(table: dict, value: float):
    return min(table, key=lambda k: abs(float(k) - float(value)))
