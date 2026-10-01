"""Dựng một mẫu, chấm điểm, quét giao khối, render 6 góc + 3/4 (ảnh PNG) để xem tận mắt.

    python scratch/ev.py <category> '{"param": value}' [out.png] [--exploded]
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexa.three_d import render as R  # noqa: E402
from nexa.three_d.generation.parametric import build_parametric  # noqa: E402
from nexa.three_d.pipeline import ModelBuild  # noqa: E402
from nexa.three_d.quality import assess  # noqa: E402
from nexa.three_d.spec import normalize, validate_spec  # noqa: E402


def main() -> None:
    cat = sys.argv[1]
    params = json.loads(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].startswith("{") else {}
    out = next((a for a in sys.argv[2:] if a.endswith(".png")), None)
    t0 = time.time()
    sp = normalize(validate_spec({"category": cat, "params": params}))
    asm = build_parametric(sp)
    t1 = time.time()
    mb = ModelBuild.from_assembly(asm)
    rep = assess(sp, mb.part_data(), mode="parametric", metadata=asm.metadata)
    t2 = time.time()
    fails = [c for c in rep.checks if not c["ok"]]
    print(f"{cat} {params}: build {t1 - t0:.2f}s assess {t2 - t1:.2f}s tris {asm.triangle_count} parts {len(asm.parts)} "
          f"score {rep.total:.1f} gates {[k for k, g in rep.gates.items() if not g['ok']]}")
    for c in fails:
        print("  FAIL", c["group"], c["name"], c["detail"])
    for c in rep.checks:
        if c["ok"] and c["group"] == "dimensions" and ("đo" in c["detail"] or "đếm" in c["detail"]):
            print("  ok  ", c["name"], c["detail"])
    print("  size", [round(x, 1) for x in asm.bounds.size], "steps", [(s.order, len(s.part_ids)) for s in asm.explosion_plan])
    if out:
        items = mb.render_items(exploded=1.0 if "--exploded" in sys.argv else 0.0)
        res = R.render_six(items, size=300, background="light")
        res["iso"] = R.render(items, "iso", 300, background="light", ssaa=2)
        Path(out).write_bytes(R.png_bytes(R.contact_sheet(res, cols=4)))
        print("  render", out, f"{time.time() - t2:.1f}s")


if __name__ == "__main__":
    main()
