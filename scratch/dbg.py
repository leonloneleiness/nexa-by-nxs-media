import sys; sys.path.insert(0,'.')
from nexa.three_d.spec import normalize, validate_spec
from nexa.three_d.generation.parametric import build_parametric
sp = normalize(validate_spec({"category":"spring","params":{"spring_type":"extension","free_length_mm":60,"wire_d_mm":1.5,"outer_d_mm":12}}))
asm = build_parametric(sp)
for bp in asm.parts:
    lo, hi = bp.solid.bounds(); print(bp.part.id, lo.round(2), hi.round(2))
