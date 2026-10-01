"""Gỡ lỗi tâm khớp: dựng mô hình gen theo kind, in tâm chuyển động vs tâm hộp bao/trọng tâm/tâm tiếp xúc cho các part."""
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from smoke_3d_viewer import PROMPTS  # noqa: E402

from nexa.three_d.asset_store import AssetStore  # noqa: E402
from nexa.three_d.motion import _Builder  # noqa: E402
from nexa.three_d.service import ThreeDService  # noqa: E402
from nexa.three_d.viewer_controller import ViewerController  # noqa: E402
from nexa.utils.config import Config  # noqa: E402

kind, ids = sys.argv[1], sys.argv[2:]
d = Path(tempfile.mkdtemp())
cfg = Config(settings_path=d / "s.yaml", gestures_path=d / "g.yaml", load_env=False)
cfg.set("three_d.ai_review", False)
store = AssetStore(d / "c")
svc = ThreeDService(cfg, notify=lambda k, v: None, store=store, provider_factory=lambda: None)
job = svc.submit(PROMPTS[kind], open_when_ready=False)
while not job.terminal:
    time.sleep(0.05)
pr = store.load(job.project_id)
geom = ViewerController.mesh_geom(pr, str(store.project_dir(job.project_id)))
b = _Builder(pr.category, pr.parts, geom)
b.build()
np.set_printoptions(precision=1, suppress=True)
for p in pr.parts:
    if ids and p.id not in ids:
        continue
    q = b.by[p.id]
    m = b.own.get(p.id)
    par = b.parent(q)
    ct = geom.contact(p.id, par.id, float(min(np.max(q.size), np.max(par.size)))) if par else None
    print(p.id, q.cat, "parent", q.parent, "axis", q.axis, "size", q.size)
    print("   bbox c", q.c, "pivot", q.pivot, "centroid", geom.centroid(p.id), "contact", ct)
    if m:
        print("   motion", m["t"], "a", m["a"], "c", m.get("c"), "amp", m.get("amp"))
svc.shutdown()
