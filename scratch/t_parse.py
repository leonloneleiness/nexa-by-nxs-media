import sys; sys.path.insert(0, '.')
from nexa.three_d.planner import LocalPlanner
P = LocalPlanner()
for t in sys.argv[1:]:
    r = P.parse(t)
    print(f"{t!r:60} -> {r['category']:15} {r['params']}")
