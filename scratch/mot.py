import sys; sys.path.insert(0,'.')
from nexa.three_d.planner import Planner
from nexa.three_d.generation.parametric import build_parametric
from nexa.three_d.motion import infer_motions
import numpy as np
for prompt in sys.argv[1:]:
    spec = Planner(None, use_gemini=False).plan(prompt).spec
    parts = [p.part for p in build_parametric(spec).parts]
    ch, mode = infer_motions(spec.category, parts)
    print("==", spec.category, mode)
    for p in parts:
        lo, hi = np.round(p.bounds.min), np.round(p.bounds.max)
        own = [ (m["t"], m["a"], m.get("amp", m.get("s"))) for m in ch.get(p.id, [])]
        print(f"  {p.id:18s} {p.category:14s} par={p.parent_id} ax={p.joint_axis} lo={lo} hi={hi} {own}")
