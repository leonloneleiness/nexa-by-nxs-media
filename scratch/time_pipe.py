import sys, time, tempfile
from pathlib import Path
sys.path.insert(0, '.')
from nexa.three_d.asset_store import AssetStore
from nexa.three_d.job_manager import JobManager
from nexa.three_d.pipeline import GenerationPipeline
from nexa.three_d.planner import Planner
from nexa.utils.config import Config
tmp = Path(tempfile.mkdtemp())
cfg = Config(settings_path=tmp / "s.yaml", gestures_path=tmp / "g.yaml", load_env=False)
cfg.set("three_d.ai_review", False)
store = AssetStore(tmp / "cache", cache_size_mb=100000)
pipe = GenerationPipeline(cfg, store, Planner(None), None, provider_factory=lambda: None)
jm = JobManager(pipe.run, timeout_s=600)
for prompt in sys.argv[1:]:
    t0 = time.monotonic()
    job = jm.submit(prompt)
    stages = []
    last = None
    while not job.terminal:
        if job.message != last:
            stages.append((round(time.monotonic() - t0, 2), job.message[:60])); last = job.message
        time.sleep(0.02)
    print(f"{time.monotonic()-t0:6.2f}s {job.state.value} {job.quality_score} {prompt}")
    for s in stages: print("   ", s)
jm.shutdown()
