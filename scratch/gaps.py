"""In khe hở/xuyên giữa các cặp bộ phận của template: python scratch/gaps.py <kind> a:b a:b ..."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from smoke_3d_viewer import PROMPTS  # noqa: E402

from nexa.three_d.generation.parametric import build_parametric  # noqa: E402
from nexa.three_d.planner import Planner  # noqa: E402

spec = Planner(None, use_gemini=False).plan(PROMPTS[sys.argv[1]])
spec = spec.spec if hasattr(spec, "spec") else spec
built = build_parametric(spec)
by = {pd.part.id: pd for pd in built.parts}
for pair in sys.argv[2:]:
    a, b = pair.split(":")
    sa, sb = by[a].solid, by[b].solid
    print(pair, "gap", round(sa.m.min_gap(sb.m, 50.0), 3), "overlap", round(sa.intersection_volume(sb), 2))
