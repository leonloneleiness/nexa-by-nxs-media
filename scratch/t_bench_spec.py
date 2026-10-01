import sys, collections; sys.path.insert(0,'.')
from nexa.three_d.benchmark import by_group, spec_matches
from nexa.three_d.planner import Planner
pl = Planner(None)
g = sys.argv[1] if len(sys.argv) > 1 else "components"
cs = by_group()[g]
bad = 0
cnt = collections.Counter(c.category for c in cs)
for c in cs:
    r = pl.plan(c.prompt)
    ok, pr = spec_matches(c, r.spec)
    if not ok:
        bad += 1; print("BAD", c.prompt, pr, r.questions)
print(len(cs), "cases", bad, "bad", dict(cnt))
