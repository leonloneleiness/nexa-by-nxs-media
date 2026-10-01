import sys, json, time; sys.path.insert(0,'.')
from nexa.three_d.spec import normalize, validate_spec
from nexa.three_d.generation.parametric import build_parametric
cat = sys.argv[1]; params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
t=time.time(); asm = build_parametric(normalize(validate_spec({"category":cat,"params":params}))); print("build", round(time.time()-t,2))
for bp in sorted(asm.parts, key=lambda b: -b.part.triangles)[:12]:
    print(bp.part.id, bp.part.triangles, [(mid, m.triangle_count) for m, mid in bp.meshes])
