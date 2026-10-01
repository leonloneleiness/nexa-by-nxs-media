import sys, math; sys.path.insert(0,'.')
import numpy as np
from nexa.three_d.planner import Planner
from nexa.three_d.generation.parametric import build_parametric
from nexa.three_d.motion import infer_motions
def disp(ch, t):
    d = np.zeros(3)
    for m in ch:
        if m["t"] == "slide":
            d += np.array(m["a"]) * (m["off"] + m["amp"] * math.sin(2*math.pi*t/m["per"] + m["ph"]))
    return d
for prompt, pairs, tipbed in [("tạo máy in 3D", [("y_carriages","y_rail"),("x_carriage","x_rail"),("z_carriage_l","z_rail_l"),("z_carriage_r","z_rail_r")], ("hotend","build_plate")),
                   ("tạo máy in 3D CoreXY", [("y_carriages","y_rails"),("x_carriage","x_rail"),("z_carriage_l","z_rail_l"),("z_carriage_r","z_rail_r")], ("hotend","build_plate")),
                   ("tạo máy CNC 6040", [("y_carriages","y_rails"),("x_carriages","x_rails"),("z_carriages","z_rails")], ("tool","table")),
                   ("tạo máy CNC 300x300x60 0.8 kW", [("y_carriages","y_rails"),("x_carriages","x_rails"),("z_carriages","z_rails")], ("tool","table"))]:
    spec = Planner(None, use_gemini=False).plan(prompt).spec
    parts = {p.part.id: p.part for p in build_parametric(spec).parts}
    ch, mode = infer_motions(spec.category, list(parts.values()))
    worst = {}; mingap = 1e9; ranges = {}
    for t in np.linspace(0, 60, 1201):
        for car, rail in pairs:
            c, r = parts[car], parts[rail]
            dc, dr = disp(ch[car], t), disp(ch[rail], t)
            lo = np.array(c.bounds.min) + dc - (np.array(r.bounds.min) + dr)
            hi = np.array(r.bounds.max) + dr - (np.array(c.bounds.max) + dc)
            i = int(np.argmax(np.abs(ch[car][0]["a"]))) if ch[car] else 1
            worst[car] = min(worst.get(car, 1e9), lo[i], hi[i])
        tip, bed = parts[tipbed[0]], parts[tipbed[1]]
        g = (tip.bounds.min[1] + disp(ch[tip.id], t)[1]) - (bed.bounds.max[1] + disp(ch[bed.id], t)[1])
        mingap = min(mingap, g)
    print(prompt, mode, {k: round(v,1) for k,v in worst.items()}, "min tip-bed gap", round(mingap,2))
    print("  nuts:", {k: [m["t"] for m in ch[k]] for k in parts if "nut" in k or "belt" in k or k in ("tool","collet_nut","x_screw","y_screws","corner_idlers","spindle")})
