"""Chi tiết giao khối giữa hai bộ phận: python scratch/ov.py cat '{params}' partA partB → các mảnh giao (thể tích, hộp bao)"""
import sys, json; sys.path.insert(0, '.')
import numpy as np
from nexa.three_d.spec import normalize, validate_spec
from nexa.three_d.generation.parametric import build_parametric
cat, params, a, b = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3], sys.argv[4]
asm = build_parametric(normalize(validate_spec({"category": cat, "params": params})))
x = asm.part(a).solid & asm.part(b).solid
for c in ([] if x.is_empty else x.split_components()):
    lo, hi = c.bounds()
    print(round(abs(c.volume())), np.round(lo), np.round(hi))
