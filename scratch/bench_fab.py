import sys; sys.path.insert(0,'.')
from nexa.three_d.benchmark import by_group, spec_matches
from nexa.three_d.planner import Planner
cs = by_group()["fabrication"]; bad = 0
for c in cs:
    ok, why = spec_matches(c, Planner(None).plan(c.prompt).spec)
    if not ok:
        bad += 1; print("XX", c.prompt, why)
print(len(cs), "bad", bad)
