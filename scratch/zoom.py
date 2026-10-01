"""Ảnh cận cảnh một vùng: python scratch/zoom.py cat '{params}' part_or_* x,y,z half out.png [view]
Tọa độ kỹ thuật (sau đặt trên đất). Cắt từng shape theo hộp quanh điểm rồi render."""
import sys, json; sys.path.insert(0, '.')
import numpy as np
from nexa.three_d.spec import normalize, validate_spec
from nexa.three_d.generation.parametric import build_parametric
from nexa.three_d import render as R
from nexa.three_d.geometry import kernel as K
cat, params, sel = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3].split(",")
c = [float(v) for v in sys.argv[4].split(",")]
half, out = float(sys.argv[5]), sys.argv[6]
view = sys.argv[7] if len(sys.argv) > 7 else "iso"
asm = build_parametric(normalize(validate_spec({"category": cat, "params": params})))
box = K.box(2 * half, 2 * half, 2 * half).translate(*c)
items = []
for bp in asm.parts:
    if sel != ["*"] and bp.part.id not in sel:
        continue
    if bp.solid is None:
        continue
    cut = bp.solid & box
    if cut.is_empty:
        continue
    mm = cut.to_mesh(40.0)
    vm = mm.vertices
    mm.vertices = np.column_stack([vm[:, 1], vm[:, 2], vm[:, 0]])
    if getattr(mm, "normals", None) is not None:
        nm = mm.normals
        mm.normals = np.column_stack([nm[:, 1], nm[:, 2], nm[:, 0]])
    items.append((mm, asm.materials[bp.meshes[0][1]]))
res = R.render(items, view, 700, background="light", ssaa=2)
open(out, "wb").write(R.png_bytes(res.image))
print("items", len(items))
