"""Bộ benchmark mô hình 3D: ≥ 60 câu yêu cầu cho MỖI nhóm hỗ trợ, kèm ground truth (loại + thông số kỳ vọng).

Câu được sinh xác định (không ngẫu nhiên) từ các cách nói tiếng Việt khác nhau × thông số khác nhau, để đo:
- tỷ lệ đạt quality gate = số mô hình vượt quality gate / tổng số yêu cầu (định nghĩa trong yêu cầu dự án);
- tỷ lệ hiểu đúng yêu cầu = số spec có loại + thông số khớp ground truth / tổng.
Chạy: .venv\\Scripts\\python scripts\\bench_3d_quality.py
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

GROUPS = ["uav", "rover", "humanoid", "quadruped", "helicopter", "boat", "mechanical", "components", "robotics", "vehicles", "energy", "fabrication"]
VI_NUM = {2: "hai", 3: "ba", 4: "bốn", 5: "năm", 6: "sáu", 7: "bảy", 8: "tám"}


@dataclass
class BenchCase:
    id: str
    group: str
    prompt: str
    category: str
    expect: dict = field(default_factory=dict)       # thông số phải khớp (sau chuẩn hóa)


def _uav() -> list[BenchCase]:
    verbs = ["Tạo", "Dựng cho anh", "Thiết kế", "Tạo mô hình 3D"]
    nouns = ["UAV", "drone", "flycam", "máy bay không người lái"]
    arms = [(4, "bốn cánh"), (6, "sáu cánh"), (8, "tám cánh"), (3, "ba cánh"), (4, "4 động cơ"), (6, "hexacopter")]
    extras = ["thân carbon màu đen, camera phía trước", "màu trắng, camera dưới bụng", "khung nhôm, không có camera",
              "cỡ lớn, màu cam, có gimbal", "mini, thân nhựa màu xanh", "khung 450 mm, camera phía trước",
              "chất lượng cao, vỏ carbon", "màu đỏ, càng đáp cao", "khung carbon 250 mm", "loại công nghiệp màu vàng"]
    out = []
    for i, (v, nn, (n, arm_txt), ex) in enumerate(itertools.islice(itertools.product(verbs, nouns, arms, extras), 0, None, 7)):
        if len(out) >= 60:
            break
        p = f"{v} {nn} {arm_txt}, {ex}"
        exp = {"arm_count": n}
        if "không có camera" in ex:
            exp["camera"] = "none"
        elif "dưới bụng" in ex:
            exp["camera"] = "bottom"
        elif "camera phía trước" in ex:
            exp["camera"] = "front"
        if "450 mm" in ex:
            exp["wheelbase_mm"] = 450.0
        if "250 mm" in ex:
            exp["wheelbase_mm"] = 250.0
        out.append(BenchCase(f"uav-{len(out) + 1:03d}", "uav", p, "uav", exp))
    return out


def _rover() -> list[BenchCase]:
    verbs = ["Tạo", "Dựng", "Thiết kế cho anh", "Tạo mô hình"]
    nouns = ["xe tự hành", "rover", "xe robot", "xe thám hiểm"]
    wheels = [(6, "sáu bánh"), (4, "bốn bánh"), (8, "tám bánh"), (6, "6 bánh"), (4, "4 bánh")]
    extras = ["có LiDAR và camera", "có camera", "dài 800 mm có LiDAR", "có pin mặt trời", "dài 1,2 m, màu trắng",
              "treo rocker bogie, có LiDAR", "màu cam, có ăng-ten", "dài 500 mm", "có LiDAR", "màu xám, có camera"]
    out = []
    for v, nn, (n, wt), ex in itertools.islice(itertools.product(verbs, nouns, wheels, extras), 0, None, 5):
        if len(out) >= 60:
            break
        exp = {"wheel_count": n}
        if "800 mm" in ex:
            exp["length_mm"] = 800.0
        if "1,2 m" in ex:
            exp["length_mm"] = 1200.0
        if "500 mm" in ex:
            exp["length_mm"] = 500.0
        if "lidar" in ex.lower():
            exp["lidar"] = True
        out.append(BenchCase(f"rover-{len(out) + 1:03d}", "rover", f"{v} {nn} {wt} {ex}", "rover", exp))
    return out


def _humanoid() -> list[BenchCase]:
    verbs = ["Tạo", "Dựng", "Thiết kế", "Tạo mô hình 3D", "Tạo cho anh"]
    nouns = ["robot hình người", "người máy", "humanoid", "robot dạng người"]
    extras = ["", "cao 1m8", "cao 1700 mm", "màu trắng", "tay kẹp", "kiểu công nghiệp", "cao 1,5 m, màu xanh",
              "có camera ở đầu", "màu đen, tay kẹp", "cao 1m6 màu bạc", "phong cách thể thao", "màu vàng"]
    out = []
    for v, nn, ex in itertools.product(verbs, nouns, extras):
        if len(out) >= 60:
            break
        exp: dict = {}
        if "1m8" in ex:
            exp["height_mm"] = 1800.0
        if "1700 mm" in ex:
            exp["height_mm"] = 1700.0
        if "1,5 m" in ex:
            exp["height_mm"] = 1500.0
        if "1m6" in ex:
            exp["height_mm"] = 1600.0
        if "tay kẹp" in ex:
            exp["hands"] = "gripper"
        out.append(BenchCase(f"humanoid-{len(out) + 1:03d}", "humanoid", f"{v} {nn} {ex}".strip(), "humanoid", exp))
    return out


def _quadruped() -> list[BenchCase]:
    verbs = ["Tạo", "Dựng", "Thiết kế", "Tạo mô hình", "Tạo giúp anh"]
    nouns = ["robot hình chó", "chó robot", "robot bốn chân", "robot 4 chân"]
    extras = ["mỗi chân có ba khớp", "mỗi chân có hai khớp", "có LiDAR", "dài 700 mm", "màu vàng, mỗi chân ba khớp",
              "có camera", "dài 1 m", "màu trắng", "3 khớp mỗi chân, có LiDAR và camera", "kiểu công nghiệp",
              "dài 500 mm, mỗi chân 2 khớp", "màu đen"]
    out = []
    for v, nn, ex in itertools.product(verbs, nouns, extras):
        if len(out) >= 60:
            break
        exp: dict = {}
        if "ba khớp" in ex or "3 khớp" in ex:
            exp["joints_per_leg"] = 3
        if "hai khớp" in ex or "2 khớp" in ex:
            exp["joints_per_leg"] = 2
        for txt, val in (("700 mm", 700.0), ("1 m", 1000.0), ("500 mm", 500.0)):
            if txt in ex:
                exp["length_mm"] = val
        out.append(BenchCase(f"quadruped-{len(out) + 1:03d}", "quadruped", f"{v} {nn} {ex}", "quadruped", exp))
    return out


def _helicopter() -> list[BenchCase]:
    verbs = ["Tạo", "Dựng", "Thiết kế", "Tạo mô hình 3D"]
    roles = [("rescue", "cứu hộ"), ("medical", "cứu thương"), ("civil", "dân sự"), ("utility", "vận tải"), ("rescue", "tìm kiếm cứu nạn")]
    extras = ["có rotor chính và rotor đuôi", "rotor chính 4 cánh", "rotor chính 5 cánh, rotor đuôi 2 cánh", "càng bánh xe",
              "dài 12 m", "màu đỏ trắng", "có tời cứu hộ", "rotor chính 2 lá", "dài 10 m, càng trượt", "màu xanh navy",
              "rotor chính 3 cánh"]
    out = []
    for v, (role, rtxt), ex in itertools.product(verbs, roles, extras):
        if len(out) >= 60:
            break
        exp: dict = {"role": role}
        for n in (2, 3, 4, 5):
            if f"rotor chính {n}" in ex:
                exp["main_blades"] = n
        if "rotor đuôi 2" in ex:
            exp["tail_rotor_blades"] = 2
        if "bánh" in ex:
            exp["landing"] = "wheels"
        if "12 m" in ex:
            exp["length_mm"] = 12000.0
        if "10 m" in ex:
            exp["length_mm"] = 10000.0
        out.append(BenchCase(f"helicopter-{len(out) + 1:03d}", "helicopter", f"{v} trực thăng {rtxt} {ex}", "helicopter", exp))
    return out


def _boat() -> list[BenchCase]:
    verbs = ["Tạo", "Dựng", "Thiết kế cho anh", "Tạo mô hình 3D"]
    kinds = [("speedboat", "ca nô cao tốc"), ("fishing", "tàu cá"), ("yacht", "du thuyền"), ("patrol", "tàu tuần tra"),
             ("speedboat", "xuồng máy"), ("patrol", "tàu cảnh sát biển")]
    extras = ["dài 6 m", "dài 12 m, máy trong", "hai máy gắn ngoài", "màu trắng xanh", "dài 8 m, không có lan can",
              "có cabin", "ba máy", "dài 15 m", "máy ngoài, màu đỏ", "không có cabin", "dài 4,5 m"]
    out = []
    for v, (kind, ktxt), ex in itertools.islice(itertools.product(verbs, kinds, extras), 0, None, 4):
        if len(out) >= 60:
            break
        exp: dict = {"boat_type": kind}
        for txt, mm in (("dài 6 m", 6000.0), ("dài 12 m", 12000.0), ("dài 8 m", 8000.0), ("dài 15 m", 15000.0), ("dài 4,5 m", 4500.0)):
            if txt in ex:
                exp["length_mm"] = mm
        if "máy trong" in ex:
            exp["propulsion"] = "inboard"
        if "máy gắn ngoài" in ex or "máy ngoài" in ex:
            exp["propulsion"] = "outboard"
        if "hai máy" in ex:
            exp["engines"] = 2
        if "ba máy" in ex:
            exp["engines"] = 3
        if "không có lan can" in ex:
            exp["railings"] = False
        if "không có cabin" in ex:
            exp["cabin"] = False
        out.append(BenchCase(f"boat-{len(out) + 1:03d}", "boat", f"{v} {ktxt} {ex}", "boat", exp))
    i = 0
    while len(out) < 60:                                 # bù đủ 60 câu bằng cách nói khác
        kind, ktxt = kinds[i % len(kinds)]
        out.append(BenchCase(f"boat-{len(out) + 1:03d}", "boat", f"Cho anh một chiếc {ktxt} dài {5 + i} m", "boat",
                             {"boat_type": kind, "length_mm": float((5 + i) * 1000)}))
        i += 1
    return out


def _mechanical() -> list[BenchCase]:
    out: list[BenchCase] = []
    bolts = [(3, 10, None), (4, 16, None), (5, 20, 0.8), (6, 25, 1.0), (8, 30, 1.25), (8, 40, None), (10, 35, 1.5),
             (10, 50, 1.25), (12, 60, 1.75), (12, 80, None), (16, 50, 2.0), (20, 80, 2.5), (6, 60, None), (8, 20, 1.0)]
    heads = ["", " đầu trụ lục giác chìm", " đầu côn", ""]
    for i, (d, L, p) in enumerate(bolts):
        head = heads[i % len(heads)]
        pitch = f", bước ren {str(p).replace('.', ',')} mm" if p else ""
        exp = {"diameter_mm": float(d), "length_mm": float(L)}
        if p:
            exp["pitch_mm"] = float(p)
        out.append(BenchCase(f"mech-{len(out) + 1:03d}", "mechanical", f"Tạo bu-lông M{d} dài {L} mm{pitch}{head}", "bolt", exp))
        out.append(BenchCase(f"mech-{len(out) + 1:03d}", "mechanical", f"tạo bulong M{d}x{L}" + (" inox kèm đai ốc" if i % 2 else ""),
                             "bolt", {"diameter_mm": float(d), "length_mm": float(L)}))
    for d in (4, 5, 6, 8, 10, 12, 16, 20, 24):
        out.append(BenchCase(f"mech-{len(out) + 1:03d}", "mechanical", f"Tạo đai ốc M{d}", "nut", {"diameter_mm": float(d)}))
    for d in (5, 6, 8, 10, 12, 16, 20):
        out.append(BenchCase(f"mech-{len(out) + 1:03d}", "mechanical", f"tạo vòng đệm M{d}", "washer", {"diameter_mm": float(d)}))
    for m, z in ((1, 20), (1.5, 24), (2, 32), (2, 40), (2.5, 18), (3, 30), (1, 60), (4, 22)):
        out.append(BenchCase(f"mech-{len(out) + 1:03d}", "mechanical", f"Tạo bánh răng module {str(m).replace('.', ',')} có {z} răng",
                             "gear", {"module_mm": float(m), "teeth": z}))
    for od, n in ((120, 4), (150, 6), (200, 8), (100, 4), (250, 8)):
        out.append(BenchCase(f"mech-{len(out) + 1:03d}", "mechanical", f"Tạo mặt bích đường kính {od} mm {n} lỗ", "flange",
                             {"outer_d_mm": float(od), "bolt_holes": n}))
    for w, h, dpt in ((40, 50, 50), (60, 80, 60), (30, 40, 40), (80, 100, 80)):
        out.append(BenchCase(f"mech-{len(out) + 1:03d}", "mechanical", f"Tạo giá đỡ chữ L {w}x{h}x{dpt} mm", "bracket",
                             {"width_mm": float(w), "height_mm": float(h), "depth_mm": float(dpt)}))
    return out


def _mk(group: str, out: list[BenchCase], prompt: str, cat: str, **exp) -> None:
    out.append(BenchCase(f"{group}-{len(out) + 1:03d}", group, prompt, cat, exp))


def _components() -> list[BenchCase]:
    """Linh kiện cơ khí tiêu chuẩn — 12 loại × 6 câu (có dấu / không dấu / cách gọi khác)."""
    out: list[BenchCase] = []
    g = "components"
    for txt, code, seal in (("Tạo ổ bi 6204", "6204", None), ("tạo vòng bi 6000", "6000", None),
                            ("Dựng bạc đạn 6305 2RS", "6305", "2RS"), ("tao o bi 6202 zz", "6202", "ZZ"),
                            ("Tạo mô hình ổ lăn 6010 kiểu hở", "6010", "open"), ("tạo bạc đạn 20x47x14", "6204", None)):
        exp = {"designation": code}
        if seal:
            exp["seal"] = seal
        _mk(g, out, txt, "bearing", **exp)
    for txt, size, L in (("Tạo động cơ bước NEMA 17", 17, None), ("tạo step motor nema 23", 23, None),
                         ("Dựng động cơ bước NEMA 34 thân dài 98 mm", 34, 98.0), ("tao dong co buoc nema 17 than dai 40 mm", 17, 40.0),
                         ("Tạo motor bước NEMA 23 thân dài 56 mm", 23, 56.0), ("Thiết kế động cơ bước nema 34", 34, None)):
        exp = {"frame_size": size}
        if L:
            exp["body_length_mm"] = L
        _mk(g, out, txt, "stepper_motor", **exp)
    for txt, st, ratio, m in (("Tạo hộp số 2 cấp tỉ số truyền 12", 2, 12.0, None), ("tạo hộp giảm tốc ba cấp tỷ số 80 module 1,5", 3, 80.0, 1.5),
                              ("Dựng hộp số bánh răng hai cấp tỉ số 20", 2, 20.0, None), ("tao hop so 3 cap ti so 60", 3, 60.0, None),
                              ("Tạo hộp giảm tốc 2 cấp i = 15 module 2,5", 2, 15.0, 2.5), ("Thiết kế gearbox hai cấp tỉ số 9", 2, 9.0, None)):
        exp = {"stages": st, "ratio": ratio}
        if m:
            exp["module_mm"] = m
        _mk(g, out, txt, "gearbox", **exp)
    for txt, kind, bore, stroke, state in (
            ("Tạo xi lanh khí nén phi 50 hành trình 200", "pneumatic", 50.0, 200.0, None),
            ("tạo xylanh khí nén 32x100", "pneumatic", 32.0, 100.0, None),
            ("Dựng xi lanh thủy lực nòng 80 hành trình 300 đang duỗi", "hydraulic", 80.0, 300.0, "extended"),
            ("tao xi lanh khi nen phi 63 hanh trinh 150 dang thu", "pneumatic", 63.0, 150.0, "retracted"),
            ("Tạo ben hơi phi 40 hành trình 50", "pneumatic", 40.0, 50.0, None),
            ("Tạo xi lanh thủy lực phi 100 hành trình 500 duỗi một nửa hành trình", "hydraulic", 100.0, 500.0, "mid")):
        exp = {"cylinder_type": kind, "bore_mm": bore, "stroke_mm": stroke}
        if state:
            exp["state"] = state
        _mk(g, out, txt, "cylinder", **exp)
    for txt, dn, state in (("Tạo van bi DN50", 50, None), ("tạo van bi tay gạt DN25 đang đóng", 25, "closed"),
                           ("Dựng van bi DN100 inox", 100, None), ("tao van bi dn15", 15, None),
                           ("Tạo van bi DN200 đang mở", 200, "open"), ("Thiết kế ball valve DN80", 80, None)):
        exp = {"dn": dn}
        if state:
            exp["state"] = state
        _mk(g, out, txt, "ball_valve", **exp)
    for txt, kind, dn in (("Tạo co 90 độ DN80", "elbow90", 80), ("tạo cút 45 DN100 inox", "elbow45", 100),
                          ("Tạo tê đều DN50", "tee", 50), ("tạo mặt bích nối ống DN65", "flange_joint", 65),
                          ("Dựng cút hàn 90 độ DN150", "elbow90", 150), ("tao te deu dn20", "tee", 20)):
        _mk(g, out, txt, "pipe_fitting", fitting=kind, dn=dn)
    for txt, belt, z1, z2 in (("Tạo bộ truyền đai GT2 puly 20 răng và 40 răng", "GT2", 20, 40),
                              ("tạo bộ truyền đai răng HTD puly 18 răng và 36 răng", "HTD5M", 18, 36),
                              ("Dựng bộ truyền đai GT2 16 răng dẫn 60 răng", "GT2", 16, 60),
                              ("tao bo truyen dai gt2 puly 20 rang va 20 rang", "GT2", 20, 20),
                              ("Tạo bộ truyền đai thang SPZ puly 100 và 200", "SPZ", None, None),
                              ("Tạo bộ truyền đai thang SPA puly 125 và 250", "SPA", None, None)):
        exp = {"belt": belt}
        if z1:
            exp.update(teeth_driver=z1, teeth_driven=z2)
        else:
            d1, d2 = (100.0, 200.0) if belt == "SPZ" else (125.0, 250.0)
            exp.update(pulley_d_mm=d1, pulley2_d_mm=d2)
        _mk(g, out, txt, "belt_drive", **exp)
    for txt, ch, z1, z2 in (("Tạo bộ truyền xích 08B đĩa 17 răng và 34 răng", "08B", 17, 34),
                            ("tạo bộ truyền xích 10B 19 răng và 38 răng", "10B", 19, 38),
                            ("Dựng bộ truyền xích con lăn 12B 21 răng và 42 răng", "12B", 21, 42),
                            ("tao bo truyen xich 06b 13 rang va 26 rang", "06B", 13, 26),
                            ("Tạo đĩa xích 16B 19 răng và 57 răng", "16B", 19, 57),
                            ("Thiết kế bộ truyền xích 08B 15 răng và 45 răng", "08B", 15, 45)):
        _mk(g, out, txt, "chain_drive", chain=ch, teeth_driver=z1, teeth_driven=z2)
    for txt, kind, b1, b2 in (("Tạo khớp nối mềm trục 14 sang 19", "jaw", 14.0, 19.0), ("tạo khớp nối cứng lỗ 8/10", "rigid", 8.0, 10.0),
                              ("Dựng khớp nối vấu trục 24 và 24", "jaw", 24.0, 24.0), ("tao khop noi mem truc 10 sang 12", "jaw", 10.0, 12.0),
                              ("Tạo khớp nối cứng trục 6 sang 8", "rigid", 6.0, 8.0), ("Tạo khớp nối đàn hồi trục 35 sang 28", "jaw", 35.0, 28.0)):
        _mk(g, out, txt, "shaft_coupling", coupling_type=kind, bore_mm=b1, bore2_mm=b2)
    for txt, d, ld, L in (("Tạo vít me bi SFU1605 dài 500 mm", 16.0, 5.0, 500.0), ("tạo vít me phi 20 bước 5 dài 800", 20.0, 5.0, 800.0),
                          ("Dựng vít me bi SFU2510 dài 1 m", 25.0, 10.0, 1000.0), ("tao vit me bi sfu1204 dai 300 mm", 12.0, 4.0, 300.0),
                          ("Tạo vít me bi SFU3205 dài 1200 mm", 32.0, 5.0, 1200.0), ("Tạo ball screw SFU1610 dài 400 mm", 16.0, 10.0, 400.0)):
        _mk(g, out, txt, "ball_screw", diameter_mm=d, lead_mm=ld, length_mm=L)
    for txt, ser, L, n in (("Tạo ray trượt HGR20 dài 600 mm hai con trượt", "HGR20", 600.0, 2), ("tạo ray MGN12 dài 300 mm", "MGN12", 300.0, None),
                           ("Dựng ray dẫn hướng HGR15 dài 400 mm một con trượt", "HGR15", 400.0, 1),
                           ("tao ray truot hgr25 dai 1 m 3 con truot", "HGR25", 1000.0, 3),
                           ("Tạo ray trượt tuyến tính MGN9 dài 200 mm", "MGN9", 200.0, None),
                           ("Tạo linear guide HGR30 dài 1500 mm bốn con trượt", "HGR30", 1500.0, 4)):
        exp = {"series": ser, "length_mm": L}
        if n:
            exp["carriages"] = n
        _mk(g, out, txt, "linear_guide", **exp)
    for txt, kind, d, od in (("Tạo lò xo nén dây 2 mm đường kính ngoài 20 mm 8 vòng", "compression", 2.0, 20.0),
                             ("tạo lò xo kéo dây 1,5 ngoài 12 dài 60", "extension", 1.5, 12.0),
                             ("Tạo lò xo xoắn dây 2 phi 16 6 vòng", "torsion", 2.0, 16.0),
                             ("tao lo xo nen day 3 ngoai 30 dai 80 mai phang", "compression", 3.0, 30.0),
                             ("Dựng lò xo nén dây 1 mm đường kính ngoài 10 mm 12 vòng khép kín", "compression", 1.0, 10.0),
                             ("Tạo lò xo kéo dây 2 mm đường kính ngoài 16 mm dài 90 mm", "extension", 2.0, 16.0)):
        _mk(g, out, txt, "spring", spring_type=kind, wire_d_mm=d, outer_d_mm=od)
    return out


def _robotics() -> list[BenchCase]:
    """Robot & tự động hóa — 3 loại × 20 câu."""
    out: list[BenchCase] = []
    g = "robotics"
    verbs = ["Tạo", "Dựng", "Thiết kế", "tạo mô hình", "Tạo giúp anh"]
    arm_nouns = ["cánh tay robot 6 trục", "cánh tay robot", "robot công nghiệp 6 trục", "cobot", "tay máy 6 bậc"]
    arm_extra = [("có tay kẹp", {"end_effector": "gripper"}), ("có giác hút", {"end_effector": "vacuum"}),
                 ("tầm với 850 mm", {"reach_mm": 850.0}), ("tầm với 1,3 m tải 10 kg", {"reach_mm": 1300.0, "payload_kg": 10.0}),
                 ("tư thế duỗi thẳng", {"pose": "reach"}), ("đang gắp hàng", {"pose": "pick"}),
                 ("kiểu công nghiệp sơn cam", {"style": "industrial"}), ("khớp 1 quay 45 độ", {"j1_deg": 45.0})]
    for i in range(20):
        v, nn = verbs[i % len(verbs)], arm_nouns[i % len(arm_nouns)]
        ex, exp = arm_extra[i % len(arm_extra)]
        exp = dict(exp)
        if "công nghiệp" in nn and "style" not in exp:
            exp["style"] = "industrial"
        if nn == "cobot":
            exp["style"] = "cobot"
        _mk(g, out, f"{v} {nn} {ex}", "robot_arm", **exp)
    vac_nouns = ["robot hút bụi", "robot hut bui", "robot lau nhà", "máy hút bụi robot", "robot hút bụi thông minh"]
    vac_extra = [("", {}), ("có lau nhà", {"mop": True}), ("hai chổi cạnh", {"side_brushes": 2}), ("đường kính 330 mm", {"diameter_mm": 330.0}),
                 ("không có lidar", {"lidar": False}), ("không có đế sạc", {"dock": False}), ("có lidar và lau nhà", {"lidar": True, "mop": True}),
                 ("đường kính 350 mm hai chổi cạnh", {"diameter_mm": 350.0, "side_brushes": 2})]
    for i in range(20):
        v, nn = verbs[i % len(verbs)], vac_nouns[i % len(vac_nouns)]
        ex, exp = vac_extra[i % len(vac_extra)]
        exp = dict(exp)
        if "lau nhà" in nn:
            exp["mop"] = True
        _mk(g, out, f"{v} {nn} {ex}".strip(), "robot_vacuum", **exp)
    agv_nouns = [("robot AGV", {}), ("AGV kho hàng", {}), ("robot giao hàng", {"top": "cargo"}), ("robot nâng kệ", {"top": "lift"}),
                 ("xe AGV", {})]
    agv_extra = [("bánh mecanum", {"drive": "mecanum"}), ("dẫn động vi sai", {"drive": "differential"}), ("dài 900 mm", {"length_mm": 900.0}),
                 ("có thùng hàng", {"top": "cargo"}), ("nâng kệ dài 1,2 m", {"top": "lift", "length_mm": 1200.0}),
                 ("không có lidar", {"lidar": False}), ("bánh mecanum dài 800 mm", {"drive": "mecanum", "length_mm": 800.0}), ("", {})]
    for i in range(20):
        v = verbs[i % len(verbs)]
        nn, e1 = agv_nouns[i % len(agv_nouns)]
        ex, e2 = agv_extra[i % len(agv_extra)]
        exp = {**e1, **e2}
        _mk(g, out, f"{v} {nn} {ex}".strip(), "agv", **exp)
    return out


def _vehicles() -> list[BenchCase]:
    """Phương tiện & hàng không vũ trụ — 9 loại × 7 câu (có dấu / không dấu / cách gọi khác)."""
    out: list[BenchCase] = []
    g = "vehicles"
    rows = [
        ("fixed_wing", [("Tạo máy bay", {}), ("Tạo máy bay hạng nhẹ 4 chỗ sải cánh 10 m", {"aircraft_type": "light", "wingspan_mm": 10000.0}),
                        ("tao uav canh co dinh", {"aircraft_type": "uav"}), ("Dựng máy bay VTOL 4 rotor nâng", {"aircraft_type": "vtol"}),
                        ("Tạo máy bay đuôi chữ T góc nhị diện 5 độ", {"tail": "t_tail", "dihedral_deg": 5.0}),
                        ("Thiết kế UAV cánh bằng đuôi chữ V sải cánh 2,4 m", {"aircraft_type": "uav", "tail": "v_tail", "wingspan_mm": 2400.0}),
                        ("tạo mô hình máy bay cánh quạt", {})]),
        ("car", [("Tạo ô tô điện", {}), ("Tạo xe hơi SUV", {"body_type": "suv"}), ("tao o to dien hatchback", {"body_type": "hatchback"}),
                 ("Dựng ô tô sedan dài 4,8 m", {"body_type": "sedan", "length_mm": 4800.0}),
                 ("Tạo xe điện VinFast VF 8 hai motor", {"body_type": "suv", "drive": "awd"}), ("Thiết kế xe 5 chỗ sedan cầu sau", {"drive": "rwd"}),
                 ("tạo mô hình ô tô SUV dẫn động 4 bánh", {"body_type": "suv", "drive": "awd"})]),
        ("motorbike", [("Tạo xe máy", {}), ("Tạo xe máy tay ga", {"bike_type": "scooter"}), ("tao xe dap dien", {"bike_type": "ebike"}),
                       ("Dựng mô tô côn tay", {"bike_type": "motorcycle"}), ("Tạo xe Honda SH", {"bike_type": "scooter"}),
                       ("Thiết kế xe đạp điện có baga", {"bike_type": "ebike"}), ("tạo mô hình xe mô tô phân khối lớn", {"bike_type": "motorcycle"})]),
        ("excavator", [("Tạo máy xúc", {}), ("Tạo máy xúc mini", {"size_class": "mini"}), ("tao may xuc 20 tan", {"size_class": "medium"}),
                       ("Dựng máy đào cỡ lớn tư thế vươn xa", {"size_class": "large", "pose": "reach"}),
                       ("Tạo máy xúc bánh xích quay 90 độ", {"swing_deg": 90.0}), ("Thiết kế máy xúc tư thế di chuyển", {"pose": "transport"}),
                       ("tạo mô hình máy cuốc 45 tấn đang đào", {"size_class": "large", "pose": "dig"})]),
        ("forklift", [("Tạo xe nâng", {}), ("Tạo xe nâng điện 2,5 tấn", {"capacity_kg": 2500.0, "power": "electric"}),
                      ("tao xe nang dau 3 tan", {"capacity_kg": 3000.0, "power": "diesel"}),
                      ("Dựng xe nâng hàng 1,5 tấn nâng cao 3 m", {"capacity_kg": 1500.0, "fork_height_mm": 3000.0}),
                      ("Tạo forklift 5 tấn chạy dầu", {"capacity_kg": 5000.0, "power": "diesel"}),
                      ("Thiết kế xe nâng điện nâng lên 4,5 m", {"fork_height_mm": 4500.0}), ("tạo mô hình xe nâng 2 tấn", {"capacity_kg": 2000.0})]),
        ("crane", [("Tạo xe cẩu", {}), ("Tạo xe cẩu cần dài 30 m", {"boom_length_mm": 30000.0}), ("tao xe cau 4 truc", {"axles": 4}),
                   ("Dựng cần cẩu ô tô góc nâng 60 độ", {"boom_angle_deg": 60.0}),
                   ("Tạo xe cẩu ống lồng cần dài 40 m góc nâng 75 độ", {"boom_length_mm": 40000.0, "boom_angle_deg": 75.0}),
                   ("Thiết kế cần trục ô tô 2 trục", {"axles": 2}), ("tạo mô hình xe cẩu thủy lực cần 12 m góc 30 độ", {"boom_length_mm": 12000.0, "boom_angle_deg": 30.0})]),
        ("train", [("Tạo tàu hỏa", {}), ("Tạo tàu điện 3 toa", {"traction": "electric", "wagons": 3}), ("tao dau may diesel", {"traction": "diesel", "wagons": 0}),
                   ("Dựng tàu hỏa chở hàng 4 toa", {"wagon_type": "freight", "wagons": 4}), ("Tạo đoàn tàu khổ 1435 hai toa", {"gauge": "standard", "wagons": 2}),
                   ("Thiết kế tàu khách một toa", {"wagon_type": "passenger", "wagons": 1}), ("tạo mô hình đầu máy tàu hỏa", {"wagons": 0})]),
        ("cubesat", [("Tạo vệ tinh CubeSat", {}), ("Tạo CubeSat 1U", {"units": 1}), ("tao ve tinh cubesat 6u", {"units": 6}),
                     ("Dựng vệ tinh nano 2U", {"units": 2}), ("Tạo CubeSat 12U có cánh pin", {"units": 12, "deployable_panels": True}),
                     ("Thiết kế CubeSat 3U không cánh pin", {"units": 3, "deployable_panels": False}), ("tạo mô hình vệ tinh 3U", {"units": 3})]),
        ("launch_vehicle", [("Tạo tên lửa", {}), ("Tạo tên lửa 3 tầng", {"stages": 3}), ("tao ten lua hai tang cao 50 m", {"stages": 2, "height_mm": 50000.0}),
                            ("Dựng tên lửa đẩy đường kính 3,7 m", {"diameter_mm": 3700.0}), ("Tạo rocket không cánh", {"fins": False}),
                            ("Thiết kế tên lửa phóng vệ tinh 3 tầng cao 60 m", {"stages": 3, "height_mm": 60000.0}),
                            ("tạo mô hình tên lửa kiểu Falcon 9", {})]),
    ]
    for cat, items in rows:
        for txt, exp in items:
            _mk(g, out, txt, cat, **exp)
    return out


def _energy() -> list[BenchCase]:
    """Năng lượng & công trình — 8 loại × 8 câu."""
    out: list[BenchCase] = []
    g = "energy"
    rows = [
        ("wind_turbine", [("Tạo tuabin gió", {}), ("Tạo tua bin gió rotor 120 m", {"rotor_diameter_mm": 120000.0}),
                          ("tao tuabin gio 2 canh", {"blades": 2}), ("Dựng tuabin gió cao 90 m", {"hub_height_mm": 90000.0}),
                          ("Tạo tuabin gió mở nắp nacelle", {"nacelle_open": True}), ("Thiết kế máy phát điện gió rotor 60 m cao 50 m",
                                                                                      {"rotor_diameter_mm": 60000.0, "hub_height_mm": 50000.0}),
                          ("tạo mô hình turbine gió 3 cánh", {"blades": 3}), ("Tạo cối xay gió phát điện", {})]),
        ("solar_array", [("Tạo hệ điện mặt trời", {}), ("Tạo hệ thống pin năng lượng mặt trời 20 tấm", {"panels": 20}),
                         ("tao he dien mat troi 8 tam 2 hang", {"panels": 8, "rows": 2}), ("Dựng tấm pin mặt trời nghiêng 20 độ", {"tilt_deg": 20.0}),
                         ("Tạo điện mặt trời 4 kWp", {"panels": 10}), ("Thiết kế hệ pin mặt trời 12 tấm không có biến tần", {"panels": 12, "inverter": False}),
                         ("tạo mô hình trang trại điện mặt trời 40 tấm 4 hàng", {"panels": 40, "rows": 4}), ("Tạo solar 6 tấm 1 hàng", {"panels": 6, "rows": 1})]),
        ("generator_set", [("Tạo máy phát điện", {}), ("Tạo máy phát điện 250 kVA", {"power_kva": 250.0}),
                           ("tao may phat dien 50 kva khung tran", {"power_kva": 50.0, "enclosure": "open"}),
                           ("Dựng máy phát điện diesel 500 kVA vỏ cách âm", {"power_kva": 500.0, "enclosure": "canopy"}),
                           ("Tạo genset 1000 kVA", {"power_kva": 1000.0}), ("Thiết kế tổ máy phát 20 kVA", {"power_kva": 20.0}),
                           ("tạo mô hình máy nổ phát điện khung trần", {"enclosure": "open"}), ("Tạo máy phát 100 kVA chống ồn", {"power_kva": 100.0, "enclosure": "canopy"})]),
        ("centrifugal_pump", [("Tạo máy bơm ly tâm", {}), ("Tạo máy bơm ly tâm 80-65-160", {"size": "80-65-160"}),
                              ("tao may bom nuoc 11 kw", {"motor_kw": 11.0}), ("Dựng bơm ly tâm 125-100-250", {"size": "125-100-250"}),
                              ("Tạo máy bơm DN50", {"size": "50-32-160"}), ("Thiết kế bơm nước 100-80-200 22 kW", {"size": "100-80-200", "motor_kw": 22.0}),
                              ("tạo mô hình máy bơm cấp nước 65-50-160", {"size": "65-50-160"}), ("Tạo pump ly tâm 4 kW", {"motor_kw": 4.0})]),
        ("storage_tank", [("Tạo bồn chứa", {}), ("Tạo bồn chứa 100 m3", {"capacity_m3": 100.0}),
                          ("tao bon nuoc nam ngang 5000 lit", {"orientation": "horizontal", "capacity_m3": 5.0}),
                          ("Dựng bồn dầu đứng 500 khối mái vòm", {"orientation": "vertical", "capacity_m3": 500.0, "roof": "dome"}),
                          ("Tạo bồn chứa 2000 m3 đường kính 16 m", {"capacity_m3": 2000.0, "diameter_mm": 16000.0}),
                          ("Thiết kế bể chứa nước 20 m3", {"capacity_m3": 20.0}), ("tạo mô hình bồn nằm 10 khối", {"orientation": "horizontal", "capacity_m3": 10.0}),
                          ("Tạo bồn xăng mái côn 50 m3", {"roof": "cone", "capacity_m3": 50.0})]),
        ("bridge", [("Tạo cây cầu", {}), ("Tạo cầu dây văng nhịp 80 m", {"bridge_type": "cable_stayed", "span_mm": 80000.0}),
                    ("tao cau vom nhip 100 m", {"bridge_type": "arch", "span_mm": 100000.0}), ("Dựng cầu giàn thép nhịp 60 m", {"bridge_type": "truss", "span_mm": 60000.0}),
                    ("Tạo cầu vòm rộng 12 m", {"bridge_type": "arch", "deck_width_mm": 12000.0}), ("Thiết kế cầu thép dài 40 m", {"span_mm": 40000.0}),
                    ("tạo mô hình cầu dây văng rộng 10 m", {"bridge_type": "cable_stayed", "deck_width_mm": 10000.0}), ("Tạo bridge truss 30 m", {"span_mm": 30000.0})]),
        ("steel_truss", [("Tạo giàn thép", {}), ("Tạo giàn thép kiểu Howe nhịp 18 m", {"truss_type": "howe", "span_mm": 18000.0}),
                         ("tao vi keo thep mai tam giac nhip 15 m", {"truss_type": "fink", "span_mm": 15000.0}),
                         ("Dựng giàn Warren nhịp 24 m cao 2,5 m", {"truss_type": "warren", "span_mm": 24000.0, "height_mm": 2500.0}),
                         ("Tạo giàn Pratt nhịp 12 m 6 khoang", {"truss_type": "pratt", "span_mm": 12000.0, "panels": 6}),
                         ("Thiết kế giàn mái thép nhịp 9 m", {"span_mm": 9000.0}), ("tạo mô hình kèo thép kiểu fink", {"truss_type": "fink"}),
                         ("Tạo truss thép nhịp 30 m", {"span_mm": 30000.0})]),
        ("lattice_tower", [("Tạo cột điện cao thế", {"tower_type": "power"}), ("Tạo tháp viễn thông", {"tower_type": "telecom"}),
                           ("tao cot dien cao the 40 m", {"tower_type": "power", "height_mm": 40000.0}),
                           ("Dựng tháp viễn thông 3 chân cao 45 m", {"tower_type": "telecom", "legs": 3, "height_mm": 45000.0}),
                           ("Tạo tháp BTS cao 30 m", {"tower_type": "telecom", "height_mm": 30000.0}), ("Thiết kế cột điện 110 kV", {"tower_type": "power"}),
                           ("tạo mô hình tháp thép cao 20 m", {"height_mm": 20000.0}), ("Tạo tháp anten 4 chân", {"tower_type": "telecom", "legs": 4})]),
    ]
    for cat, items in rows:
        for txt, exp in items:
            _mk(g, out, txt, cat, **exp)
    return out


def _fabrication() -> list[BenchCase]:
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
                        ("Thiết kế máy phay CNC 3040 trục chính 1,5 kW", {"travel_x_mm": 300.0, "travel_y_mm": 400.0, "spindle_kw": 1.5}),
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


def cases() -> list[BenchCase]:
    return (_uav() + _rover() + _humanoid() + _quadruped() + _helicopter() + _boat() + _mechanical() + _components() +
            _robotics() + _vehicles() + _energy() + _fabrication())


def by_group() -> dict[str, list[BenchCase]]:
    out: dict[str, list[BenchCase]] = {g: [] for g in GROUPS}
    for c in cases():
        out[c.group].append(c)
    return out


def spec_matches(case: BenchCase, spec) -> tuple[bool, list[str]]:
    """So spec với ground truth: loại + từng thông số kỳ vọng."""
    problems = []
    if spec is None:
        return False, ["không tạo được spec"]
    if spec.category != case.category:
        problems.append(f"loại {spec.category} ≠ {case.category}")
    for k, v in case.expect.items():
        got = spec.params.get(k)
        if isinstance(v, float):
            if got is None or abs(float(got) - v) > 1e-6:
                problems.append(f"{k}={got} ≠ {v}")
        elif got != v:
            problems.append(f"{k}={got} ≠ {v}")
    return not problems, problems
