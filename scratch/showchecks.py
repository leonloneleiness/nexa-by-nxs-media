"""In các check đo của một mẫu: python scratch/showchecks.py cat '{params}'"""
import sys, json; sys.path.insert(0, '.')
from nexa.three_d.spec import normalize, validate_spec
from nexa.three_d.generation.parametric import build_parametric
from nexa.three_d.pipeline import ModelBuild
from nexa.three_d.measure import run_checks
sp = normalize(validate_spec({"category": sys.argv[1], "params": json.loads(sys.argv[2] if len(sys.argv) > 2 else "{}")}))
asm = build_parametric(sp)
mb = ModelBuild.from_assembly(asm)
for c in run_checks(sp, mb.part_data(), asm.metadata):
    print("OK " if c.ok else "XX ", c.name, "|", c.detail)
print("parts:", [(q.part.id, q.part.category) for q in mb.part_data()])
