"""Tháp thép dàn: cột điện cao thế mạch kép (4 chân thép góc, thắt eo ở 0,62 H, 3 tầng xà mỗi bên + đỉnh chống sét, chuỗi
cách điện thủy tinh) hoặc tháp viễn thông (4 chân thép góc hoặc 3 chân ống, sàn công tác, ăng-ten, chảo viba, thang, đèn
báo không).

Khung tháp 4 chân: chân thép góc đều cạnh có cánh nằm đúng trên hai mặt tháp (lát từ loft hai mặt cắt → mặt cánh trùng mặt
phẳng tháp nghiêng); thanh giằng thép góc áp NGOÀI mặt cánh chân (chạm, không xuyên), giằng chéo chữ X xếp lớp + bản đệm ở
đầu thanh lớp 2, thanh ngang ở mọi nút; mỗi đầu thanh 1 bu-lông xuyên cánh chân (lỗ khoét cục bộ), đai ốc phía trong tháp
cách cánh còn lại của chân. Tháp 3 chân: ống thép hàn (mối hàn là tiếp xúc có chủ đích).
"""
from __future__ import annotations

import math

import manifold3d as m3d
import numpy as np

from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.generation.templates.structures import bake, light_bolt
from nexa.three_d.geometry import kernel as K
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec


def box_at(x0, x1, y0, y1, z0, z1) -> K.Solid:
    x0, x1 = sorted((x0, x1))
    y0, y1 = sorted((y0, y1))
    z0, z1 = sorted((z0, z1))
    return K.box(x1 - x0, y1 - y0, z1 - z0).translate((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)


class SquareTower:
    """Khung tháp 4 chân thép góc; bề rộng (khoảng cách hai đường gót chân) w(z) tuyến tính từng đoạn."""

    def __init__(self, levels: list[tuple[float, float]], leg: tuple[float, float], brace: tuple[float, float], bolt_d: float) -> None:
        self.lv = levels                                              # [(z, w)] tăng dần theo z (điểm gãy + nút)
        self.L, self.t = leg
        self.Lb, self.tb = brace
        self.d = bolt_d
        self.g = 0.55 * self.L                                        # đường tim bu-lông trên cánh chân, tính từ gót

    def w(self, z: float) -> float:
        zs = [a for a, _ in self.lv]
        ws = [b for _, b in self.lv]
        return float(np.interp(z, zs, ws))

    def legs(self) -> K.Solid:
        """4 chân: mỗi đoạn giữa hai điểm gãy là loft của mặt cắt chữ L ngang (mặt ngoài cánh nằm trên mặt tháp)."""
        L, t = self.L, self.t
        out = []
        breaks = [z for z, _ in self.lv]
        for sx in (1, -1):
            for sy in (1, -1):
                for z0, z1 in zip(breaks[:-1], breaks[1:]):
                    secs = []
                    for z in (z0, z1):
                        c = self.w(z) / 2
                        pts = [(0, 0), (-L, 0), (-L, -t), (-t, -t), (-t, -L), (0, -L)]   # gót ở góc, cánh vào trong theo −x, −y
                        secs.append(np.array([(sx * (c + px), sy * (c + py), z) for px, py in pts]))
                    out.append(K.loft(secs))
        return K.Solid.union_all(out)

    def _face_map(self, face: int, z0: float, z1: float) -> np.ndarray:
        """Ma trận affine (u, v, o) → thế giới cho mặt `face` (0:+x, 1:+y, 2:−x, 3:−y) trên đoạn [z0, z1]:
        u ngang dọc mặt, v = z, o ra ngoài mặt phẳng tháp."""
        a = (self.w(z1) - self.w(z0)) / (2 * (z1 - z0))
        c0 = self.w(z0) / 2 - a * z0
        base = np.array([[0.0, a, 1.0, c0], [1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])    # mặt +x (det = 1)
        R = np.array([[math.cos(face * math.pi / 2), -math.sin(face * math.pi / 2), 0], [math.sin(face * math.pi / 2), math.cos(face * math.pi / 2), 0],
                      [0, 0, 1.0]])
        return np.hstack([R @ base[:, :3], (R @ base[:, 3])[:, None]])

    def brace(self, face: int, p0: tuple[float, float], p1: tuple[float, float], layer: int, seg: tuple[float, float]) -> K.Solid:
        """Thanh giằng thép góc trong mặt `face`: đoạn (u, v) p0 → p1 trên đường tim bu-lông; cánh phẳng ở lớp `layer`
        (o ∈ [layer·tb, (layer+1)·tb]), cánh đứng ra ngoài ở mép dưới/trong."""
        Lb, tb = self.Lb, self.tb
        a, c = np.array(p0, float), np.array(p1, float)
        dvec = (c - a) / np.linalg.norm(c - a)
        nvec = np.array([-dvec[1], dvec[0]])
        ext = 0.9 * self.d
        a, c = a - dvec * ext, c + dvec * ext
        fp = np.array([a - nvec * Lb / 2, c - nvec * Lb / 2, c + nvec * Lb / 2, a + nvec * Lb / 2])
        flat = K.Solid(MC.cs(fp).extrude(tb)).translate(0, 0, layer * tb)
        strip = np.array([a - nvec * Lb / 2, c - nvec * Lb / 2, c - nvec * (Lb / 2 - tb), a - nvec * (Lb / 2 - tb)])
        stand = K.Solid(MC.cs(strip).extrude(Lb - tb)).translate(0, 0, (layer + 1) * tb)
        return (flat + stand).transform(self._face_map(face, *seg))

    def filler(self, face: int, p: tuple[float, float], seg: tuple[float, float]) -> K.Solid:
        s_ = 2.4 * self.d
        sq = np.array([(p[0] - s_ / 2, p[1] - s_ / 2), (p[0] + s_ / 2, p[1] - s_ / 2), (p[0] + s_ / 2, p[1] + s_ / 2), (p[0] - s_ / 2, p[1] + s_ / 2)])
        return K.Solid(MC.cs(sq).extrude(self.tb)).transform(self._face_map(face, *seg))

    def face_point(self, face: int, u: float, z: float, o: float, seg: tuple[float, float]) -> np.ndarray:
        M_ = self._face_map(face, *seg)
        return M_[:, :3] @ np.array([u, z, o]) + M_[:, 3]

    def face_normal(self, face: int, seg: tuple[float, float]) -> np.ndarray:
        """Pháp tuyến ngoài thật của mặt tháp nghiêng trên đoạn `seg` (mặt +x: x = a·z + c → n ∝ (1, 0, −a))."""
        z0, z1 = seg
        a = (self.w(z1) - self.w(z0)) / (2 * (z1 - z0))
        n = np.array([1.0, 0.0, -a]) / math.hypot(1.0, a)
        c, s_ = math.cos(face * math.pi / 2), math.sin(face * math.pi / 2)
        return np.array([c * n[0], s_ * n[0], n[2]])


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    kind = p.get("tower_type", "power")
    H = float(p.get("height_mm", 30000.0))
    legs_n = 4 if kind == "power" else int(p.get("legs", 4))
    mats = MC.tech_materials(spec, primary="#9aa3ab", secondary="#c1121f", accent="#f2f2f2")
    mats["galvanized"] = M.material("galvanized", "metal", "#aeb4ba", 0.85, 0.45, name="Thép mạ kẽm nhúng nóng")
    mats["concrete"] = M.material("concrete", "stone", "#a3a39b", 0.0, 0.85, name="Bê tông móng")
    mats["insulator_glass"] = M.material("insulator_glass", "glass", "#5f8f7a", 0.0, 0.08, alpha=0.85, name="Thủy tinh cách điện")
    mats["aluminum_cond"] = M.material("aluminum_cond", "metal", "#c9ccd0", 0.9, 0.35, name="Dây nhôm lõi thép")
    names = {"power": "Cột điện cao thế mạch kép", "telecom": "Tháp viễn thông"}
    b = AssemblyBuilder(spec.name or f"{names[kind]} cao {H / 1000:g} m", "lattice_tower", mats)
    if legs_n == 3:
        meta = _tubular3(b, H)
    else:
        meta = _square(b, H, kind)
    b.place_on_ground(center_xy=True)
    b.metadata.update({"tower_type": kind, "height_mm": H, "legs": legs_n, **meta, "strict_overlap": True})
    return b.build()


def _square(b: AssemblyBuilder, H: float, kind: str) -> dict:
    power = kind == "power"
    Bw = H / (5.5 if power else 8.0)
    Tw = max(1200.0, 0.22 * Bw) if power else max(1000.0, 0.3 * Bw)
    z_waist = 0.62 * H if power else H
    leg = (125.0, 10.0) if H >= 25000 else (100.0, 8.0)
    brace = (63.0, 6.0) if H >= 25000 else (50.0, 5.0)
    d = 16.0
    zp = 300.0                                                         # mặt bệ móng (chân tháp đặt tại z = zp)
    # nút: chia đều đến eo, rồi đều tới đỉnh
    n1 = max(4, round(z_waist / 3000.0))
    zs = list(np.linspace(0.0, z_waist, n1 + 1))
    if power and z_waist < H:
        n2 = max(3, round((H - z_waist) / 2500.0))
        zs += list(np.linspace(z_waist, H, n2 + 1))[1:]
    levels = [(0.0, Bw), (z_waist, Tw)] + ([(H, Tw)] if z_waist < H else [])
    T = SquareTower(levels, leg, brace, d)
    legs = T.legs().translate(0, 0, zp)
    braces, fillers, bolt_pts = [], [], []
    segs = [(a, c) for (a, _), (c, _) in zip(levels[:-1], levels[1:])]

    def seg_of(z0: float, z1: float) -> tuple[float, float]:
        return next(s for s in segs if s[0] - 1e-6 <= z0 and z1 <= s[1] + 1e-6)

    g = T.g
    dz = 3.2 * d                                                       # đầu chéo lệch khỏi nút: bu-lông cách nhau ≥ 3d
    z_first = 0.5 * brace[0] + 2.0 * d                                 # nút giằng thấp nhất (trên mặt móng)
    for face in range(4):
        for i, (za, zb) in enumerate(zip(zs[:-1], zs[1:])):
            sg = seg_of(za, zb)
            brk_off = (0.5 * brace[0] + 2.0) if any(abs(za - zb_) < 1e-6 for zb_, _w in levels[1:-1]) else 0.0   # nút gãy (eo)
            z0 = max(za, z_first) + (dz + brk_off if i > 0 else 0.0)
            z_top_node = zb - (0.5 * brace[0] + 2.0 if i == len(zs) - 2 else 0.0)    # nút đỉnh hạ xuống để thanh ngang không vượt đầu chân
            z1 = z_top_node - dz
            u0, u1 = T.w(z0) / 2 - g, T.w(z1) / 2 - g                   # đường tim bu-lông ở hai chân của mặt
            # chéo X: lớp 0 (trái dưới → phải trên), lớp 1 (phải dưới → trái trên) + bản đệm hai đầu
            braces.append(T.brace(face, (-u0, z0), (u1, z1), 0, sg))
            braces.append(T.brace(face, (u0, z0), (-u1, z1), 1, sg))
            fillers += [T.filler(face, (u0, z0), sg), T.filler(face, (-u1, z1), sg)]
            bolt_pts += [(face, (-u0, z0), 0, sg), (face, (u1, z1), 0, sg), (face, (u0, z0), 1, sg), (face, (-u1, z1), 1, sg)]
            if i > 0:                                                  # thanh ngang đúng tại nút (trừ chân tháp)
                zz = za
                if any(abs(za - zb_) < 1e-6 for zb_, _w in levels[1:-1]):
                    zz = za + 0.5 * brace[0] + 2.0                     # nút gãy (eo tháp): thanh ngang nằm trọn trên đoạn trên
                uu = T.w(zz) / 2 - g
                braces.append(T.brace(face, (-uu, zz), (uu, zz), 0, sg))
                bolt_pts += [(face, (-uu, zz), 0, sg), (face, (uu, zz), 0, sg)]
        # thanh ngang đỉnh
        zz = H - (0.5 * brace[0] + 2.0)
        uu = T.w(zz) / 2 - g
        braces.append(T.brace(face, (-uu, zz), (uu, zz), 0, segs[-1]))
        bolt_pts += [(face, (-uu, zz), 0, segs[-1]), (face, (uu, zz), 0, segs[-1])]
    # bu-lông: đầu ngoài mặt thanh giằng, đai ốc trong mặt cánh chân
    protos: dict[int, tuple] = {}
    bolts, nuts, cores = [], [], []
    for face, (u, z), layer, sg in bolt_pts:
        grip = T.t + (layer + 1) * T.tb
        if layer not in protos:
            protos[layer] = tuple(bake(x) for x in light_bolt(d, grip))
        head = T.face_point(face, u, z, (layer + 1) * T.tb, sg) + np.array([0, 0, zp])
        # mẫu dựng dọc +Y → trục bu-lông theo pháp tuyến THẬT của mặt tháp nghiêng (mặt tựa đầu áp đúng mặt thanh giằng)
        Mx = np.hstack([K.align_matrix([0.0, 1.0, 0.0], T.face_normal(face, sg)), head[:, None]])
        b_, n_, c_ = protos[layer]
        bolts.append(b_.transform(Mx).m)
        nuts.append(n_.transform(Mx).m)
        cores.append(c_.transform(Mx))
    brace_s = K.Solid.union_all([x.translate(0, 0, zp) for x in braces])
    fill_s = K.Solid.union_all([x.translate(0, 0, zp) for x in fillers])
    core_all = K.Solid.union_all(cores)
    legs = legs - core_all
    brace_s = brace_s - core_all
    fill_s = fill_s - core_all
    # móng
    pads = K.Solid.union_all([K.chamfer_box(1400.0, 1400.0, zp, 40.0).translate(sx * (Bw / 2 - 0.3 * leg[0]), sy * (Bw / 2 - 0.3 * leg[0]), zp / 2)
                              for sx in (1, -1) for sy in (1, -1)])
    b.add("foundation", "Móng bê tông (4 bệ)", "Foundations", "foundation", Shape(pads, "concrete", 35.0), required=True,
          aliases=["móng", "bệ móng", "móng tháp", "foundation"], function="Bệ móng bê tông cốt thép cho 4 chân tháp.", position_tag="bottom")
    b.add("legs", f"Chân tháp (4 × L{leg[0]:g}×{leg[1]:g})", "Tower legs", "tower_leg", Shape(legs, "galvanized", 35.0), parent_id="foundation",
          required=True, aliases=["chân tháp", "chân cột", "thép góc chân", "leg"], function=f"4 chân thép góc L{leg[0]:g}×{leg[1]:g} mạ kẽm, cánh nằm trên mặt tháp.",
          position_tag="center", explode_dir=(0, 0, 1), explode_distance=0.08 * H, explode_order=3, dimensions={"height": H, "base_width": Bw})
    b.add("bracing", f"Thanh giằng chéo X + ngang (L{brace[0]:g}×{brace[1]:g})", "Bracing", "bracing",
          [Shape(brace_s, "galvanized", 35.0), Shape(fill_s, "galvanized", 35.0)], parent_id="legs", required=True,
          aliases=["thanh giằng", "giằng chéo", "thanh ngang", "bracing", "bản đệm"], function="Giằng chéo chữ X hai lớp + bản đệm, thanh ngang tại mọi nút.",
          position_tag="center", explode_dir=(1, 0, 0), explode_distance=0.06 * H, explode_order=2)
    b.add("bolts", f"Bu-lông M{d:g} ({len(bolts)} bộ)", "Bolts", "bolt",
          [Shape(K.Solid(m3d.Manifold.compose(bolts)), "galvanized", 35.0, extra={"simplify": False}),
           Shape(K.Solid(m3d.Manifold.compose(nuts)), "galvanized", 35.0, extra={"simplify": False})], parent_id="legs", required=True,
          aliases=["bu lông", "bulong", "đai ốc", "bolt"], function=f"Bu-lông mạ kẽm M{d:g} cấp 6.8 xuyên cánh chân + thanh giằng.",
          position_tag="center", explode_dir=(0, 1, 0), explode_distance=0.05 * H, explode_order=1)
    contacts: list[list[str]] = []
    top_z = zp + H
    extra = {}
    if power:
        extra = _power_heads(b, T, zp, H, contacts)
    else:
        extra = _telecom_heads(b, zp + H, Tw, contacts, square=True)
    b.metadata["contacts"] = contacts
    b.note_stage(1, "Tháo thiết bị đầu tháp, bu-lông")
    b.note_stage(2, "Tháo thanh giằng")
    b.note_stage(3, "Tháo chân tháp khỏi móng")
    return {"base_width_mm": Bw, "top_width_mm": Tw, "leg_section": list(leg), "brace_section": list(brace), "panels": len(zs) - 1,
            "n_bolts": len(bolts), "top_z_mm": top_z, "foundation_top_mm": zp, "contacts": contacts, **extra,
            "standard": "Thép góc đều cạnh TCVN 1656 mạ kẽm; bu-lông 6.8; cột điện mạch kép tỷ lệ tuyến 110 kV (chưa kiểm toán TCVN 5575)"}


def _power_heads(b: AssemblyBuilder, T: SquareTower, zp: float, H: float, contacts: list) -> dict:
    """3 tầng xà mỗi bên (dọc ±Y) + đỉnh chống sét; chuỗi cách điện thủy tinh treo đầu xà, đoạn dây dẫn ngắn."""
    arms, strings, conds = [], [], []
    levels = [(0.66 * H, 0.14 * H), (0.78 * H, 0.17 * H), (0.9 * H, 0.14 * H)]
    L_ch = 90.0
    tips = []
    for z, La in levels:
        w = T.w(z)
        for sy in (1, -1):
            tip = np.array([0.0, sy * (w / 2 + La), zp + z])
            roots = [np.array([sx * (w / 2 - 0.2 * T.L), sy * (w / 2 - 0.2 * T.L), zp + z]) for sx in (1, -1)]
            top_root = np.array([0.0, sy * (w / 2 - 0.2 * T.L), zp + z + 0.35 * La])
            mems = [(r, tip) for r in roots] + [(top_root, tip)] + [(roots[0], roots[1])]
            k_n = 4
            for k in range(1, k_n):                                      # giằng tam giác trong xà
                f = k / k_n
                pa = roots[0] + (tip - roots[0]) * f
                pb = roots[1] + (tip - roots[1]) * f
                pc = top_root + (tip - top_root) * f
                mems += [(pa, pb), (pa, pc), (pb, pc)]
            for a_, c_ in mems:
                arms.append(K.tube(np.array([a_, c_]), 0.28 * L_ch, 8))
            # chuỗi cách điện: móc + 10 bát thủy tinh + khóa đỡ dây
            n_disc = 10
            top = tip - np.array([0, 0, 0.28 * L_ch])
            link = K.cylinder(14.0, 250.0, segments=12).translate(*(top - np.array([0, 0, 250.0])))
            discs = [K.revolve([(0, 0), (127.0, 20.0), (127.0, 30.0), (60.0, 55.0), (20.0, 146.0), (0, 146.0)], segments=32)
                     .translate(*(top - np.array([0, 0, 250.0 + 146.0 * (i + 1)]))) for i in range(n_disc)]
            z_clamp = top[2] - 250.0 - 146.0 * n_disc - 60.0
            clamp = box_at(tip[0] - 150.0, tip[0] + 150.0, tip[1] - 40.0, tip[1] + 40.0, z_clamp - 60.0, z_clamp + 60.0)
            strings.append((link + clamp, K.Solid.union_all(discs)))
            conds.append(K.cylinder(14.0, 5000.0, segments=16).rotate(0, 90, 0).translate(tip[0] - 2500.0, tip[1], z_clamp))
            tips.append(tip.tolist())
    # đỉnh chống sét: tháp nhọn nhỏ + dây chống sét
    wt = T.w(H)
    peak = [K.tube(np.array([[sx * (wt / 2 - 0.2 * T.L), sy * (wt / 2 - 0.2 * T.L), zp + H], [0, 0, zp + H + 3500.0]]), 0.28 * L_ch, 8)
            for sx in (1, -1) for sy in (1, -1)]
    ew = K.cylinder(9.0, 4000.0, segments=12).rotate(0, 90, 0).translate(-2000.0, 0, zp + H + 3500.0 + 9.0)
    b.add("crossarms", "Xà (6) + đỉnh chống sét", "Crossarms & earth peak", "crossarm", Shape(K.Solid.union_all(arms + peak), "galvanized", 35.0),
          parent_id="legs", required=True, aliases=["xà", "xà cột điện", "cánh xà", "đỉnh cột", "crossarm"],
          function="3 tầng xà dàn tam giác mỗi bên mang 6 pha (mạch kép), đỉnh mang dây chống sét.", position_tag="top",
          explode_dir=(0, 0, 1), explode_distance=0.1 * H, explode_order=2)
    b.add("insulators", "Chuỗi cách điện thủy tinh (6)", "Insulator strings", "insulator",
          [Shape(K.Solid.union_all([s[1] for s in strings]), "insulator_glass", 35.0), Shape(K.Solid.union_all([s[0] for s in strings]), "steel", 35.0)],
          parent_id="crossarms", required=True, aliases=["chuỗi cách điện", "sứ cách điện", "bát sứ", "insulator"],
          function="Chuỗi 10 bát thủy tinh U70 (tuyến 110 kV), khóa đỡ dây.", position_tag="top", explode_dir=(0, 0, -1), explode_distance=2500.0, explode_order=1)
    b.add("conductors", "Dây dẫn + dây chống sét (đoạn qua cột)", "Conductors", "conductor",
          [Shape(K.Solid.union_all(conds), "aluminum_cond", 35.0), Shape(ew, "steel", 35.0)], parent_id="insulators", required=True,
          aliases=["dây dẫn", "dây điện", "dây chống sét", "conductor"], function="Dây nhôm lõi thép ACSR, dây chống sét trên đỉnh.",
          position_tag="top", explode_dir=(1, 0, 0), explode_distance=3000.0, explode_order=1)
    contacts += [["crossarms", "bracing"], ["crossarms", "bolts"], ["conductors", "crossarms"]]
    return {"crossarm_levels": [z for z, _ in levels], "insulator_strings": 6, "tips": tips}


def _telecom_heads(b: AssemblyBuilder, z_top: float, Tw: float, contacts: list, square: bool) -> dict:
    """Sàn công tác + lan can, 3 hướng × 2 ăng-ten panel, 2 chảo viba, cột thu lôi + đèn báo không."""
    R = Tw / 2 + 700.0
    z_pf = z_top - 1500.0
    ring = K.cylinder(R, 60.0, segments=48) - K.cylinder(0.35 * Tw, 200.0, segments=32).translate(0, 0, -50.0)
    ring = ring.translate(0, 0, z_pf)
    rail = K.torus(R - 30.0, 25.0, segments=48, tube_segments=8).translate(0, 0, z_pf + 1100.0)
    posts = [K.cylinder(25.0, 1100.0, segments=10).translate((R - 30.0) * math.cos(a), (R - 30.0) * math.sin(a), z_pf + 60.0)
             for a in np.radians(np.arange(0, 360, 30))]
    brk = [box_at(-(Tw / 2 + 5.0) if s < 0 else Tw / 2 - 150.0, Tw / 2 + 5.0 if s > 0 else -(Tw / 2 - 150.0), -60.0, 60.0, z_pf - 400.0, z_pf)
           for s in (1, -1)]
    mounts, panels, dishes = [], [], []
    for k, a in enumerate(np.radians([90.0, 210.0, 330.0])):
        c = np.array([(R + 250.0) * math.cos(a), (R + 250.0) * math.sin(a)])
        mounts.append(K.cylinder(40.0, 3200.0, segments=16).translate(c[0], c[1], z_pf - 800.0))
        mounts.append(K.tube(np.array([[0.7 * R * math.cos(a), 0.7 * R * math.sin(a), z_pf + 30.0], [c[0], c[1], z_pf + 30.0]]), 35.0, 10))
        for j, off in enumerate((-350.0, 350.0)):
            t = np.array([-math.sin(a), math.cos(a)])
            pc = c + t * off + np.array([math.cos(a), math.sin(a)]) * 160.0
            pan = K.rounded_box(120.0, 300.0, 1400.0, 30.0, segments=6).rotate(0, 0, math.degrees(a)).translate(pc[0], pc[1], z_pf + 1000.0)
            clamp = K.tube(np.array([[c[0] + t[0] * off, c[1] + t[1] * off, z_pf + 1000.0], [pc[0], pc[1], z_pf + 1000.0]]), 25.0, 8)
            panels.append(pan)
            mounts.append(clamp)
    for a, zz in ((math.radians(30.0), z_pf - 2500.0), (math.radians(150.0), z_pf - 3800.0)):
        dv = np.array([math.cos(a), math.sin(a), 0.0])
        c0 = np.array([dv[0] * (Tw / 2 + 400.0), dv[1] * (Tw / 2 + 400.0), zz])
        dish = K.revolve([(0, 0), (600.0, 180.0), (620.0, 200.0), (600.0, 210.0), (0, 30.0)], segments=48)
        dishes.append(MC.orient(dish, c0 + dv * 120.0, dv))
        mounts.append(K.tube(np.array([dv * (0.5 * Tw - 60.0) + np.array([0, 0, zz]), c0 + dv * 130.0]), 45.0, 12))
    rod = K.cylinder(20.0, 3000.0, segments=12).translate(0, 0, z_top) + K.cylinder(80.0, 150.0, segments=16).translate(0, 0, z_top)
    lamp = K.sphere(90.0, segments=20).translate(0, 0, z_top + 3000.0 + 60.0)
    rod_base = (box_at(-Tw / 2 - 5.0, Tw / 2 + 5.0, -50.0, 50.0, z_top - 100.0, z_top) if square else
                K.cylinder(Tw / math.sqrt(3) + 60.0, 30.0, segments=36).translate(0, 0, z_top))   # tấm đỉnh phủ 3 đầu ống chân
    b.add("platform", "Sàn công tác + lan can", "Work platform", "platform", Shape(ring + rail + K.Solid.union_all(posts + brk), "galvanized", 35.0),
          parent_id="legs", required=True, aliases=["sàn công tác", "sàn tháp", "lan can", "platform"], function="Sàn lưới thép vòng quanh đỉnh tháp, lan can cao 1,1 m.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=2500.0, explode_order=2)
    b.add("antennas", "Ăng-ten panel 3 hướng (6) + giá đỡ", "Sector antennas", "antenna",
          [Shape(K.Solid.union_all(panels), "plastic_white", 35.0), Shape(K.Solid.union_all(mounts), "galvanized", 35.0)], parent_id="platform", required=True,
          aliases=["ăng-ten", "ăng ten", "anten", "ăng-ten panel", "antenna", "BTS"], function="3 hướng phủ sóng 120°, mỗi hướng 2 ăng-ten panel 1,4 m.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=2000.0, explode_order=1)
    b.add("dishes", "Chảo viba (2)", "Microwave dishes", "dish", Shape(K.Solid.union_all(dishes), "plastic_white", 35.0), parent_id="antennas",
          required=True, aliases=["chảo viba", "viba", "chảo", "microwave dish"], function="2 chảo viba Ø1,2 m truyền dẫn.",
          position_tag="top", explode_dir=(1, 0, 0), explode_distance=1500.0, explode_order=1)
    b.add("lightning_rod", "Kim thu sét + đèn báo không", "Lightning rod & aviation light", "rod",
          [Shape(rod + rod_base, "galvanized", 35.0), Shape(lamp, "led_red", 35.0)], parent_id="legs", required=True,
          aliases=["kim thu sét", "cột thu lôi", "đèn báo không", "đèn đỏ", "lightning rod"], function="Kim thu sét 3 m + đèn báo không LED đỏ.",
          position_tag="top", explode_dir=(0, 0, 1), explode_distance=2000.0, explode_order=1)
    contacts += [["antennas", "legs"], ["antennas", "bracing"], ["dishes", "legs"], ["dishes", "bracing"], ["antennas", "bolts"], ["dishes", "bolts"],
                 ["platform", "bracing"], ["platform", "bolts"], ["lightning_rod", "bracing"], ["lightning_rod", "bolts"]]
    return {"antennas": 6, "dishes": 2}


def _tubular3(b: AssemblyBuilder, H: float) -> dict:
    """Tháp viễn thông 3 chân ống: chân ống thuôn, giằng ống hàn (chéo + ngang), bệ móng."""
    Bw = H / 9.0
    Tw = max(900.0, 0.3 * Bw)
    zp = 300.0
    R0, R1 = Bw / math.sqrt(3), Tw / math.sqrt(3)                     # bán kính đường tròn ngoại tiếp tam giác chân
    ang = [math.radians(90.0 + 120.0 * k) for k in range(3)]
    r = lambda z: R0 + (R1 - R0) * z / H                               # noqa: E731
    leg_r0, leg_r1 = 80.0, 55.0
    legs = []
    for a in ang:
        path = np.array([[r(0) * math.cos(a), r(0) * math.sin(a), zp], [r(H) * math.cos(a), r(H) * math.sin(a), zp + H]])
        legs.append(K.tube(path, leg_r0, 24, scales=[1.0, leg_r1 / leg_r0]))
    n = max(6, round(H / 2500.0))
    zs = np.linspace(0.0, H, n + 1)
    br = []
    for k in range(3):
        a0, a1 = ang[k], ang[(k + 1) % 3]
        for i in range(n):
            z0, z1 = zs[i], zs[i + 1]
            p0 = np.array([r(z0) * math.cos(a0), r(z0) * math.sin(a0), zp + z0])
            p1 = np.array([r(z1) * math.cos(a1), r(z1) * math.sin(a1), zp + z1])
            q0 = np.array([r(z0) * math.cos(a1), r(z0) * math.sin(a1), zp + z0])
            q1 = np.array([r(z1) * math.cos(a0), r(z1) * math.sin(a0), zp + z1])
            br.append(K.tube(np.array([p0, p1]), 22.0, 10))
            br.append(K.tube(np.array([q0, q1]), 22.0, 10))
            if i > 0:
                br.append(K.tube(np.array([p0, q0]), 25.0, 10))
    pads = K.Solid.union_all([K.chamfer_box(1200.0, 1200.0, zp, 40.0).translate(R0 * math.cos(a), R0 * math.sin(a), zp / 2) for a in ang])
    b.add("foundation", "Móng bê tông (3 bệ)", "Foundations", "foundation", Shape(pads, "concrete", 35.0), required=True,
          aliases=["móng", "bệ móng", "foundation"], function="Bệ móng bê tông cho 3 chân tháp.", position_tag="bottom")
    b.add("legs", "Chân tháp ống thép (3)", "Tubular legs", "tower_leg", Shape(K.Solid.union_all(legs), "galvanized", 35.0), parent_id="foundation",
          required=True, aliases=["chân tháp", "ống chân", "leg"], function=f"3 chân ống thép mạ kẽm Ø{2 * leg_r0:g} → Ø{2 * leg_r1:g}.",
          position_tag="center", explode_dir=(0, 0, 1), explode_distance=0.08 * H, explode_order=3, dimensions={"height": H, "base_width": Bw})
    b.add("bracing", "Giằng ống hàn (chéo + ngang)", "Tubular bracing", "bracing", Shape(K.Solid.union_all(br), "galvanized", 35.0), parent_id="legs",
          required=True, aliases=["thanh giằng", "giằng chéo", "bracing"], function="Giằng ống Ø44 hàn vào chân tháp.", position_tag="center",
          explode_dir=(1, 0, 0), explode_distance=0.06 * H, explode_order=2)
    contacts = [["bracing", "legs"]]
    extra = _telecom_heads(b, zp + H, Tw, contacts, square=False)
    b.metadata["contacts"] = contacts
    b.note_stage(1, "Tháo thiết bị đầu tháp")
    b.note_stage(2, "Tháo giằng")
    b.note_stage(3, "Tháo chân tháp")
    return {"base_width_mm": Bw, "top_width_mm": Tw, "panels": n, "top_z_mm": zp + H, "foundation_top_mm": zp, "contacts": contacts, **extra,
            "standard": "Tháp viễn thông 3 chân ống thép hàn (tỷ lệ tháp 30–60 m); chưa kiểm toán tải gió (TCVN 2737)"}
