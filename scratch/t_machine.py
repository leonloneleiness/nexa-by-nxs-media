import time, numpy as np
from nexa.three_d.generation.templates import machine as MC
from nexa.three_d import standards as S
def chk(name, s):
    print(name, s.status_ok, not s.is_empty, s.triangle_count, np.round(np.array(s.bounds()),2).tolist())
t=time.time()
b = MC.bearing_solids("6204", seal="2RS")
chk("outer", b["outer"]); chk("inner", b["inner"]); chk("cage", b["cage"]); chk("seal", b["seals"][0])
print("balls", b["z"], b["dw"], [round(x.intersection_volume(b["outer"]),4) for x in b["balls"][:2]], round(b["balls"][0].intersection_volume(b["inner"]),4), round(b["cage"].intersection_volume(b["balls"][0]),4))
print("ball-inner gap", b["balls"][0].m.min_gap(b["inner"].m, 1.0), b["balls"][0].m.min_gap(b["outer"].m, 1.0), b["cage"].m.min_gap(b["balls"][0].m,1))
g = MC.spur_gear(2, 17, 20, 12); chk("gear", g)
n = MC.nema_stepper(17, 48); [chk(k, n[k]) for k in ("front","stack","rear","screws","shaft")]
p = MC.timing_pulley(20, "GT2", 6, 5, 7); chk("pulley", p)
s, R = MC.sprocket(17, "08B", 20); chk("sprocket", s); print(R)
C = MC.chain_center(R, MC.sprocket(34,"08B",25)[1], 450, 12.7)
pts = MC.chain_rollers(R, MC.sprocket(34,"08B",25)[1], C, 12.7)
d = [np.linalg.norm(pts[i]-pts[(i+1)%len(pts)]) for i in range(len(pts))]
print("chain", len(pts), round(min(d),4), round(max(d),4), C)
pl, rl = MC.roller_chain(pts, "08B"); chk("plates", pl); chk("rollers", rl)
g2 = S.LINEAR_GUIDES["HGR20"]; r = MC.linear_rail(g2, 400); chk("rail", r); c = MC.carriage(g2); chk("car", c["body"]); chk("caps", c["caps"])
print("car-rail", c["body"].intersection_volume(r), c["body"].m.min_gap(r.m, 1), c["seals"].intersection_volume(r))
bs = MC.ball_screw_rod(16, 5, 3.175, 300); chk("bs", bs)
e = MC.bend(60.3, 3.91, 76.2, 90); chk("elbow", e)
f, info = MC.weld_neck_flange(50); chk("flange", f)
print("time", time.time()-t)
