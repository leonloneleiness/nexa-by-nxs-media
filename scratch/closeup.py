import sys, json; sys.path.insert(0,'.')
import numpy as np
from nexa.three_d.spec import normalize, validate_spec
from nexa.three_d.generation.parametric import build_parametric
from nexa.three_d.pipeline import ModelBuild
from nexa.three_d import render as R
cat, params, parts, out = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3].split(","), sys.argv[4]
view = sys.argv[5] if len(sys.argv) > 5 else "iso"
asm = build_parametric(normalize(validate_spec({"category": cat, "params": params})))
mb = ModelBuild.from_assembly(asm)
items = []
for p in mb.parts:
    if parts == ["*"] or p.id in parts:
        for m, mid in mb.meshes[p.id]:
            if len(sys.argv) > 6 and mid in sys.argv[6].split(","):
                continue
            items.append((m, mb.materials[mid]))
res = R.render(items, view, 700, background="light", ssaa=2)
open(out, "wb").write(R.png_bytes(res.image))
