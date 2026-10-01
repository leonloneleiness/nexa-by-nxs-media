import sys; sys.path.insert(0,'.')
from tests.tech3d_helpers import build
for cat in ["fdm_printer","cnc_router","server_rack","electrical_enclosure","axial_fan","heatsink","dev_board"]:
    sp, asm, rep, dt = build(cat)
    names = [c["name"] for c in rep.checks if c.get("group", "") != "x"]
    print(cat, "|", " ; ".join(n for n in names if not n.startswith(("có ", "vật liệu", "lưới"))) [:1500])
