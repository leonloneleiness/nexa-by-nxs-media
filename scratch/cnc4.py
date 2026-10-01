import sys; sys.path.insert(0,'.')
from tests.tech3d_helpers import build, failed
for p in [{}, {"travel_x_mm":1200,"travel_y_mm":800,"travel_z_mm":200,"spindle_kw":4}, {"travel_x_mm":300,"travel_y_mm":300,"travel_z_mm":60,"spindle_kw":0.8},
          {"travel_x_mm":1500,"travel_y_mm":1500,"travel_z_mm":250,"spindle_kw":5.5}]:
    sp, asm, rep, dt = build("cnc_router", **p)
    print(p, sum(rep.scores.values()), failed(rep), f"{dt:.1f}s")
