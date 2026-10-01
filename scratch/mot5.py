import sys; sys.path.insert(0,'.')
import numpy as np
from nexa.three_d.planner import Planner
from nexa.three_d.generation.parametric import build_parametric
from nexa.three_d.motion import infer_motions
for prompt in ["tạo tủ rack 42U", "tạo tủ điện có cửa kính", "tạo quạt 120mm", "tạo tản nhiệt CPU", "tạo Raspberry Pi 4", "tạo bo mạch Arduino"]:
    spec = Planner(None, use_gemini=False).plan(prompt).spec
    parts = [p.part for p in build_parametric(spec).parts]
    ch, mode = infer_motions(spec.category, parts)
    mv = {p.id: [(m["t"], m["a"], m["c"] if "c" in m else None) for m in ch[p.id]][:2] for p in parts if ch.get(p.id)}
    print(spec.category, mode, {k: v for k, v in list(mv.items())[:6]}, "n", len(mv))
    for p in parts:
        if p.category in ("rotor", "fan_frame", "door"):
            print("   ", p.id, p.category, "ax", p.joint_axis, "c", np.round((np.array(p.bounds.min)+np.array(p.bounds.max))/2), "size", np.round(np.array(p.bounds.max)-np.array(p.bounds.min)))
