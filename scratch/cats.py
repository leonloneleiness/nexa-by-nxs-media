import sys, collections; sys.path.insert(0,'.')
from tests.tech3d_helpers import build
from nexa.three_d.pipeline import ModelBuild
for cat in ["fdm_printer","cnc_router","server_rack","electrical_enclosure","axial_fan","heatsink","dev_board"]:
    sp, asm, rep, dt = build(cat)
    pd = ModelBuild.from_assembly(asm).part_data()
    c = collections.Counter(p.part.category for p in pd)
    print(cat, rep.scores, dict(c), "missing:", rep.missing_parts)
