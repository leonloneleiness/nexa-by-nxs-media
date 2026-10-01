"""In thể tích giao + bbox các cặp contacts, và bbox các part chọn: python scratch/pairs.py cat '{params}' [part...]"""
import sys, json; sys.path.insert(0, '.')
import numpy as np
from nexa.three_d.spec import normalize, validate_spec
from nexa.three_d.generation.templates import get_template
cat = sys.argv[1]; params = json.loads(sys.argv[2])
sp = normalize(validate_spec({"category": cat, "params": params}))
from nexa.three_d.generation import templates as T
import importlib
asm = importlib.import_module("nexa.three_d.generation.templates." + T.TECH_TEMPLATES[cat]).build(sp)
S = {bp.part.id: bp.solid for bp in asm.parts}
def bb(s):
    lo, hi = s.bounds(); return f"[{lo[0]:.1f},{hi[0]:.1f}]x[{lo[1]:.1f},{hi[1]:.1f}]x[{lo[2]:.1f},{hi[2]:.1f}]"
for a, b in asm.metadata.get("contacts", []):
    v = S[a].intersection_volume(S[b])
    print(f"{a:>14} × {b:<14} ∩={v:9.2f}  {bb(S[a])}  {bb(S[b])}")
for pid in sys.argv[3:]:
    print(pid, bb(S[pid]))
