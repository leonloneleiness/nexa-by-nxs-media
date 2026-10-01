import sys; sys.path.insert(0,'.')
from nexa.three_d.spec import normalize, validate_spec
from nexa.three_d.generation.parametric import build_parametric
asm = build_parametric(normalize(validate_spec({"category": "train", "params": {"traction":"electric","wagons":0}})))
bp = asm.part("loco_body")
for m, mid in bp.meshes:
    print(mid, m.triangle_count)
g = [s for s in bp.meshes if s[1] == "glass_tinted"][0][0]
import numpy as np
v = g.vertices; print(v.min(0).round(0), v.max(0).round(0))
body = [s for s in bp.meshes if s[1] == "paint_primary"][0][0]
