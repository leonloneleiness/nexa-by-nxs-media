import sys,time,tempfile,json
from pathlib import Path
sys.path.insert(0,"."); sys.path.insert(0,"scripts")
from smoke_3d_viewer import PROMPTS
from nexa.three_d.asset_store import AssetStore
from nexa.three_d.service import ThreeDService
from nexa.utils.config import Config
d=Path(tempfile.mkdtemp()); cfg=Config(settings_path=d/"s.yaml",gestures_path=d/"g.yaml",load_env=False); cfg.set("three_d.ai_review",False)
st=AssetStore(d/"c"); svc=ThreeDService(cfg,notify=lambda k,v:None,store=st,provider_factory=lambda:None)
for k in sys.argv[1:] or PROMPTS:
    j=svc.submit(PROMPTS[k],open_when_ready=False)
    while not j.terminal: time.sleep(.05)
    if not j.project_id: print(k,"FAIL",getattr(j,"error","")); continue
    pr=st.load(j.project_id); q=pr.quality_report or {}
    print(f"{k:16s} {pr.status:9s} {pr.quality_score} {q.get('status')}")
    if q.get("status")!="passed" and len(sys.argv)>1:
        print([ (c.get("group"),c.get("name"),c.get("detail")) for c in q.get("checks",[]) if not c.get("ok")], {kk:v for kk,v in q.items() if kk not in ("checks","metrics")})
svc.shutdown()
