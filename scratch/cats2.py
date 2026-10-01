import sys; sys.path.insert(0,'.')
from tests.tech3d_helpers import build, failed
V = [("fdm_printer",{}),("fdm_printer",{"kinematics":"corexy","build_x_mm":300,"build_y_mm":300,"build_z_mm":350}),
 ("cnc_router",{}),("cnc_router",{"travel_x_mm":300,"travel_y_mm":300,"travel_z_mm":60,"spindle_kw":0.8}),
 ("server_rack",{}),("server_rack",{"rack_units":6,"depth_mm":450,"equipment":False}),
 ("electrical_enclosure",{}),("electrical_enclosure",{"width_mm":200,"height_mm":200,"depth_mm":120,"window":True}),
 ("axial_fan",{}),("axial_fan",{"size_mm":40,"blades":5,"guard":False}),("axial_fan",{"size_mm":140,"blades":11}),
 ("heatsink",{}),("heatsink",{"heatsink_type":"extruded","fan":False}),("heatsink",{"heat_pipes":0}),("heatsink",{"heat_pipes":8}),
 ("dev_board",{}),("dev_board",{"board":"raspberry_pi"})]
for cat,p in V:
    sp, asm, rep, dt = build(cat, **p)
    print(cat, p, round(sum(rep.scores.values()),1), rep.missing_parts, failed(rep)[:3], f"{dt:.1f}s")
