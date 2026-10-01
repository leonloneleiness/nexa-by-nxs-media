"""Ổ bi rãnh sâu một dãy 60xx / 62xx / 63xx (ISO 15:2017 kích thước biên d × D × B).

Vòng trong + vòng ngoài có rãnh lăn (độ ôm 52 %), bi chạm đáy rãnh hai vòng, vòng cách thép dập (hai nửa tán đinh)
hoặc nhựa PA66 kiểu gài, tùy chọn hai phớt cao su 2RS (môi chạm vòng trong) hoặc hai nắp thép ZZ (có khe hở), ngàm
vào rãnh vòng ngoài. Số bi/đường kính bi: ƯỚC LƯỢNG theo tỷ lệ thiết kế (standards.bearing_balls), làm tròn theo cỡ
bi ISO 3290 — mỗi hãng có thể khác ±1 bi. Ổ nằm ngang, trục thẳng đứng, đáy ở z = 0.

Thứ tự tháo thật: tháo phớt/nắp → tháo vòng cách → dồn bi → rút vòng trong.
"""
from __future__ import annotations

import math

from nexa.three_d import standards as S
from nexa.three_d.generation.assembly import AssemblyBuilder, BuiltAssembly
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d.geometry.kernel import Shape
from nexa.three_d.spec import ModelSpec


def build(spec: ModelSpec) -> BuiltAssembly:
    p = spec.params
    code = p["designation"]
    seal = p.get("seal", "open")
    b = MC.bearing_solids(code, seal=seal, cage=p.get("cage", "steel"))
    d, D, B = b["d"], b["D"], b["B"]
    mats = MC.tech_materials(spec)
    ring_mat = "stainless" if p.get("material") == "stainless" else "bearing_steel"
    name = f"Ổ bi {code}" + (f"-{seal}" if seal != "open" else "")
    asm = AssemblyBuilder(spec.name or name, "bearing", mats)
    asm.add("outer_ring", "Vòng ngoài", "Outer ring", "bearing_ring", Shape(b["outer"], ring_mat, 30.0), required=True,
            aliases=["vòng ngoài", "vỏ ổ bi", "outer ring", "vòng bi ngoài", "rãnh lăn ngoài"],
            function=f"Vòng ngoài D = {D:g} mm lắp vào gối/ổ đỡ; có rãnh lăn cho bi.", position_tag="center",
            dimensions={"outer_diameter": D, "width": B})
    asm.add("inner_ring", "Vòng trong", "Inner ring", "bearing_ring", Shape(b["inner"], ring_mat, 30.0), parent_id="outer_ring",
            required=True, aliases=["vòng trong", "vòng bi trong", "inner ring", "lỗ ổ bi"],
            function=f"Vòng trong d = {d:g} mm lắp chặt lên trục, quay cùng trục.", position_tag="center",
            explode_dir=(0, 0, -1), explode_distance=B * 2.2, explode_order=4, joint_axis=(0, 0, 1),
            dimensions={"bore": d, "width": B})
    for k, (ball, a) in enumerate(zip(b["balls"], b["angles"])):
        asm.add(f"ball_{k + 1}", f"Bi số {k + 1}", f"Ball {k + 1}", "ball", Shape(ball, ring_mat, 30.0), parent_id="inner_ring",
                aliases=["bi", "viên bi", "bi thép", "ball"] + ([f"bi {k + 1}"] if k < 9 else []),
                function=f"Bi thép Ø{b['dw']:g} mm lăn giữa hai rãnh, truyền tải hướng kính.", position_tag="center",
                explode_dir=(math.cos(a), math.sin(a), 0), explode_distance=b["dw"] * 1.6 + D * 0.12, explode_order=3,
                dimensions={"diameter": b["dw"]})
    asm.add("cage", "Vòng cách", "Cage", "cage", Shape(b["cage"], "plastic_black" if p.get("cage") == "polyamide" else "cage_steel", 35.0),
            parent_id="outer_ring", aliases=["vòng cách", "vòng giữ bi", "cage", "rế bi"],
            function="Giữ các bi cách đều nhau, không cọ vào nhau.", position_tag="center",
            explode_dir=(0, 0, 1), explode_distance=B * 2.0, explode_order=2)
    contacts = [("ball_*", "outer_ring"), ("inner_ring", "ball_*"), ("cage", "ball_*")]
    for k, s_ in enumerate(b["seals"]):
        top = k == 0
        pid = "seal_top" if top else "seal_bottom"
        asm.add(pid, ("Phớt" if seal == "2RS" else "Nắp chắn") + (" trên" if top else " dưới"),
                ("Seal" if seal == "2RS" else "Shield") + (" top" if top else " bottom"), "seal",
                Shape(s_, "nbr" if seal == "2RS" else "stainless", 35.0), parent_id="outer_ring",
                aliases=["phớt", "phốt", "nắp chắn", "seal", "shield", "2rs", "zz"],
                function="Chắn bụi/nước và giữ mỡ bôi trơn bên trong ổ.", position_tag="top" if top else "bottom",
                explode_dir=(0, 0, 1 if top else -1), explode_distance=B * (3.4 if top else 4.2), explode_order=1)
        asm.cut("outer_ring", s_)                                   # rãnh ngàm phớt trên vòng ngoài
        if seal == "2RS":
            contacts.append((pid, "inner_ring"))                    # môi phớt tì lên vòng trong
    asm.note_stage(1, "Tháo phớt/nắp chắn")
    asm.note_stage(2, "Tháo vòng cách")
    asm.note_stage(3, "Dồn bi ra ngoài")
    asm.note_stage(4, "Rút vòng trong")
    asm.place_on_ground()
    z, dw, dm = S.bearing_balls(code)
    asm.metadata.update({"designation": code, "d_mm": d, "D_mm": D, "B_mm": B, "balls": z, "ball_d_mm": dw,
                         "pitch_d_mm": dm, "seal": seal, "standard": "ISO 15:2017; số/đường kính bi ước lượng (ISO 3290)",
                         "strict_overlap": True, "contacts": [list(c) for c in contacts]})
    return asm.build()
