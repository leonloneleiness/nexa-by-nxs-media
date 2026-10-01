import sys; sys.path.insert(0,'.')
from nexa.three_d.spec import normalize, validate_spec
from nexa.three_d.generation.parametric import build_parametric
sp = normalize(validate_spec({"category":"linear_guide","params":{"series":"MGN9","length_mm":200}}))
asm = build_parametric(sp)
a = asm.part("rail_screws").solid; b = asm.part("carriage_1").solid
i = a & b
print(i.volume(), i.bounds())
print(asm.part("rail").solid.bounds(), b.bounds())
