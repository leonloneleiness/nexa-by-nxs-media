"""Download pinned, licensed robot source assets for the offline library updater."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1] / "data" / "reference_models"
PACKAGES = ("unitree_go2", "unitree_h1", "universal_robots_ur5e")
API = "https://api.github.com/repos/google-deepmind/mujoco_menagerie"


def main():
    r = requests.get(API + "/commits/main", timeout=40)
    r.raise_for_status()
    commit = r.json()["sha"]
    r = requests.get(API + "/git/trees/" + commit, params={"recursive": "1"}, timeout=60)
    r.raise_for_status()
    tree = r.json()
    if tree.get("truncated"):
        raise RuntimeError("GitHub tree truncated")
    files = [e for e in tree["tree"] if e["type"] == "blob" and e["path"].split("/")[0] in PACKAGES
             and ("/assets/" in e["path"] or Path(e["path"]).suffix in (".xml", ".md")
                  or Path(e["path"]).name == "LICENSE")]
    if sum(e.get("size", 0) for e in files) > 500_000_000:
        raise RuntimeError("Reference assets exceed download budget")
    ROOT.mkdir(parents=True, exist_ok=True)

    def fetch(entry):
        path = ROOT / entry["path"]
        path.resolve().relative_to(ROOT.resolve())
        url = "https://raw.githubusercontent.com/google-deepmind/mujoco_menagerie/" + commit + "/" + entry["path"]
        r = requests.get(url, timeout=90)
        r.raise_for_status()
        raw = r.content
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if blob != entry["sha"]:
            raise RuntimeError("Git blob mismatch: " + entry["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return {"path": entry["path"], "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

    with ThreadPoolExecutor(4) as pool:
        records = list(pool.map(fetch, files))
    (ROOT / "provenance.json").write_text(json.dumps({"repository": API, "commit": commit, "files": records}, indent=2), encoding="utf-8")
    print(json.dumps({"commit": commit, "files": len(records), "bytes": sum(x["bytes"] for x in records)}))


if __name__ == "__main__":
    main()
