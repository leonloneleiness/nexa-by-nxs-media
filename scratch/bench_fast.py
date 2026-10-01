"""Chạy nhanh một nhóm benchmark: planner → dựng → chấm (không render, không GLB). In lỗi, thời gian, số tam giác."""
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def run(prompt: str) -> tuple:
    from nexa.three_d.generation.parametric import build_parametric
    from nexa.three_d.pipeline import ModelBuild
    from nexa.three_d.planner import Planner
    from nexa.three_d.quality import assess
    t0 = time.time()
    r = Planner(None).plan(prompt)
    if r.spec is None:
        return prompt, 0, 0, 0, ["NO SPEC " + "; ".join(r.questions)]
    try:
        asm = build_parametric(r.spec)
    except Exception as exc:
        return prompt, 0, 0, time.time() - t0, [f"BUILD ERROR {type(exc).__name__}: {exc}"]
    t1 = time.time()
    rep = assess(r.spec, ModelBuild.from_assembly(asm).part_data(), mode="parametric", metadata=asm.metadata)
    fails = [f"{c['name']}: {c['detail']}" for c in rep.checks if not c["ok"]]
    gates = [k for k, g in rep.gates.items() if not g["ok"] and k not in ("asset", "manifest")]
    return prompt, rep.total, asm.triangle_count, t1 - t0, fails + [f"GATE {g}" for g in gates]


def main() -> None:
    from nexa.three_d.benchmark import by_group
    groups = sys.argv[1:] or ["components"]
    prompts = [c.prompt for g in groups for c in by_group()[g]]
    with ProcessPoolExecutor(4) as ex:
        res = list(ex.map(run, prompts))
    bad = 0
    for prompt, score, tris, dt, fails in res:
        flag = score < 99 or fails or tris > 450_000 or dt > 5.0
        bad += bool(flag)
        if flag:
            print(f"{score:6.1f} {tris:7d} {dt:5.2f}s  {prompt}")
            for f in fails[:4]:
                print("        ", f)
    print(f"{len(res)} cases, {bad} flagged; max tris {max(r[2] for r in res)}, max build {max(r[3] for r in res):.2f}s")


if __name__ == "__main__":
    main()
