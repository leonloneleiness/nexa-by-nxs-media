import sys; sys.path.insert(0,'.')
from nexa.three_d.spec import normalize, validate_spec
from nexa.three_d.generation.parametric import build_parametric
from nexa.three_d.geometry import kernel as K
sp = normalize(validate_spec({"category":"cubesat","params":{"units":2}}))
asm = build_parametric(sp)
fr = asm.part("frame").solid
lo, hi = fr.bounds(); zc=(lo[2]+hi[2])/2
sec = fr & K.box(300, 300, 0.1).translate((lo[0]+hi[0])/2,(lo[1]+hi[1])/2, zc+7)
for c in sec.split_components(): print(c.bounds())
print(lo, hi)
comps = fr.split_components()
print(len(comps), [ (c.volume(), c.bounds()[0].round(1).tolist()) for c in comps if c.volume() < 1000])
