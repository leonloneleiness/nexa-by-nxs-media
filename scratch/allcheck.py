"""Chạy nhiều biến thể một nhóm, in điểm/gate/thời gian: python scratch/allcheck.py cat '[{...},{...}]'"""
import sys, json, time; sys.path.insert(0, '.')
from nexa.three_d.spec import normalize, validate_spec
from nexa.three_d.generation.parametric import build_parametric
from nexa.three_d.pipeline import ModelBuild
from nexa.three_d.quality import assess
cat = sys.argv[1]
for params in json.loads(sys.argv[2]):
    t0 = time.time()
    sp = normalize(validate_spec({"category": cat, "params": params}))
    asm = build_parametric(sp)
    mb = ModelBuild.from_assembly(asm)
    rep = assess(sp, mb.part_data(), mode="parametric", metadata=asm.metadata)
    fails = [f"{c['name']}: {c['detail']}"[:150] for c in rep.checks if not c["ok"]]
    print(f"{cat} {params}: {rep.total:.1f} gates={[k for k, g in rep.gates.items() if not g['ok']]} tris={asm.triangle_count} {time.time() - t0:.1f}s", fails)
