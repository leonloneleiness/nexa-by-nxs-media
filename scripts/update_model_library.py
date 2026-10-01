"""Stage and publish a reversible update of an existing NEXA asset library.

Staging only reads the live library. --apply verifies input hashes, requires NEXA
to be closed, backs up every original, then swaps complete project directories.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import fields
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexa.three_d.generation.parametric import build_parametric, compile_dsl_parts
from nexa.three_d.manifest import load_manifest, save_manifest, validate_manifest
from nexa.three_d.models import Bounds, GENERATOR_VERSION
from nexa.three_d.pipeline import GenerationPipeline, ModelBuild
from nexa.three_d.spec import ModelSpec, normalize, validate_spec
from nexa.three_d import render as R
from nexa.three_d.geometry import materials as M
from nexa.three_d.geometry import gltf
from nexa.three_d.validator import validate_glb_bytes, Limits

REFERENCE_ROBOTS = {
    "quadruped": ("unitree_go2", "go2.xml", "Unitree Go2"),
    "humanoid": ("unitree_h1", "h1.xml", "Unitree H1"),
    "robot_arm": ("universal_robots_ur5e", "ur5e.xml", "Universal Robots UR5e"),
}
# Reviewed legacy classifications: two boat fallbacks and a humanoid AI sculpture.
CATEGORY_UPGRADES = {"20260925-213546-e9692a": "boat", "20260925-224829-f5622b": "boat",
                     "20260930-140856-c2dba5": "humanoid"}

REFERENCES = {
    "uav": "https://docs.holybro.com/company/user-manuals/drone-dev-kit",
    "rover": "https://github.com/nasa-jpl/open-source-rover",
    "helicopter": "https://shop.align.com.tw/partfinder.php?language=en",
    "boat": "https://traxxas.com/57076-4-spartan-brushless-36-boat-tsm",
    "robot_vacuum": "https://iroboteducation.github.io/create3_docs/hw/mechanical/",
    "agv": "https://emanual.robotis.com/docs/en/platform/turtlebot3/opensource/",
    "stepper_motor": "https://www.pololu.com/product/2267",
    "bearing": "https://www.emarketplace.in.skf.com/deep-groove-ball-bearing/6204",
    "train": "https://www.mobility.siemens.com/global/en/portfolio/rail/rolling-stock/commuter-and-regional-trains/mireo.html",
    "car": "https://service.tesla.com/docs/Model3/ServiceManual/en-us/",
    "launch_vehicle": "https://www.nasa.gov/humans-in-space/space-launch-system/resources-2/",
    "fixed_wing": "https://www.horizonhobby.com/on/demandware.static/Sites-horizon-us-Site/Sites-horizon-master/default/Manuals/EFL1045016_Manual.pdf",
    "cnc_router": "https://docs.sainsmart.com/article/b648ni5dr0-genmitsu-3018-prover-assembly-guide",
    "fdm_printer": "https://help.prusa3d.com/product/mk4/original-prusa-mk4-kit-assembly_1967",
    "dev_board": "https://docs.arduino.cc/resources/datasheets/A000066-datasheet.pdf",
}


def tree_hash(path):
    result = hashlib.sha256()
    for p in sorted(path.rglob("*")):
        if p.is_file():
            result.update(p.relative_to(path).as_posix().encode())
            result.update(hashlib.sha256(p.read_bytes()).digest())
    return result.hexdigest()


def geometry_hash(path):
    """Ignore container metadata/version changes when reporting geometry differences."""
    doc = gltf.read_glb(path.read_bytes())
    result = hashlib.sha256()
    for node in doc.nodes:
        result.update(node.name.encode())
        for primitive in node.primitives:
            result.update(primitive.mesh.vertices.round(6).tobytes())
            result.update(primitive.mesh.faces.tobytes())
    return result.hexdigest()


def stage_one(source, staging, original, product_redesign=False):
    from nexa.three_d.quality import assess
    pid = original.id
    src = source / "projects" / pid
    dest = staging / "projects" / pid
    if dest.exists():
        raise RuntimeError("Staging project already exists: " + pid)
    old_hash = tree_hash(src)
    shutil.copytree(src, dest)
    p = copy.deepcopy(original)
    valid_fields = {x.name for x in fields(ModelSpec)}
    spec = ModelSpec(**{k: v for k, v in p.spec.items() if k in valid_fields})
    if pid in CATEGORY_UPGRADES and p.category == "generic":
        spec = normalize(validate_spec({"category": CATEGORY_UPGRADES[pid], "params": {},
                                        "name": p.name}))
        spec.prompt = p.source_prompt
        p.category = spec.category
        p.spec = spec.to_dict()
        p.generation_mode = "parametric"
    build = None
    reference = REFERENCE_ROBOTS.get(p.category)
    kind = "preserved_external_geometry"
    info = {"previous_version": p.generator_version, "original_hash": old_hash,
            "original_spec": copy.deepcopy(original.spec), "date": "2026-09-30", "manufacturing_verified": False}
    product_builder = None
    if product_redesign and p.category == "generic":
        from nexa.three_d.generation.templates import catalog_products as products
        label = p.name.casefold()
        product_builder = (products.keyboard if "bàn phím" in label else
                           products.tracked_display if "xe tăng" in label else
                           products.hex_case if "lục giác" in label else None)
    if product_builder:
        build = ModelBuild.from_assembly(product_builder(spec))
        kind = "redesigned_product_study"
        p.generation_mode = "reference"
        p.provider = "nexa_product_study"
        info.update(evidence="original_product_study_not_manufacturer_cad",
                    reference_url=build.metadata.get("reference_url", ""))
    elif reference and not spec.explicit:
        from nexa.three_d.reference_import import import_mjcf
        package, file, label = reference
        folder = ROOT / "data/reference_models" / package
        build = import_mjcf(folder / file)
        provenance = json.loads((folder.parent / "provenance.json").read_text(encoding="utf-8"))
        lic = dest / "source/reference"
        lic.mkdir(parents=True, exist_ok=True)
        for name in ("LICENSE", "README.md", file):
            shutil.copy2(folder / name, lic / name)
        shutil.copy2(folder.parent / "provenance.json", lic / "provenance.json")
        info.update(reference_source=label, reference_url=f"https://github.com/google-deepmind/mujoco_menagerie/tree/{provenance['commit']}/{package}",
                    source_commit=provenance["commit"], evidence="source_visual_meshes_and_joint_transforms")
        p.name = original.name if original.name.endswith(" · " + label) else original.name + " · " + label
        p.generation_mode = "reference"
        p.provider = "mujoco_menagerie"
        kind = "replaced_with_source_geometry"
    elif p.generation_mode == "parametric":
        build = ModelBuild.from_assembly(build_parametric(spec))
        kind = "regenerated_parametric"
        info.update(reference_url=REFERENCES.get(p.category, ""), evidence="template_geometry_not_exact_product_replica")
    elif p.generation_mode == "dsl":
        dsl_file = src / "source/design.dsl.json"
        if dsl_file.exists():
            data = json.loads(dsl_file.read_text(encoding="utf-8"))
            dsl = compile_dsl_parts(spec, data["parts"])
            if dsl.errors or dsl.asm is None:
                raise ValueError("DSL errors: " + str(dsl.errors))
            build = ModelBuild.from_assembly(dsl.asm)
            kind = "recompiled_original_dsl"
    if build is not None:
        pipeline = GenerationPipeline(None, None, None)
        if product_redesign:
            from nexa.three_d.generation.templates.catalog_products import write_keyboard_texture
            write_keyboard_texture(build, dest)
        needed = set()
        for mat in build.materials.values():
            for rel in mat.textures.values():
                if "carbon" in rel:
                    needed.add("carbon")
                if "thread" in rel:
                    needed.add("thread")
                if Path(rel).stem in M.MICRO_TEXTURES:
                    needed.add(Path(rel).stem)
        if needed:
            M.write_textures(dest, needed)
        pipeline._write_glbs(build, dest)
        p.parts, p.materials = build.parts, list(build.materials.values())
        p.explosion_plan, p.has_assembly = build.explosion_plan, build.has_assembly
        p.bounds = Bounds.union([part.bounds for part in p.parts])
        p.metadata["build"] = build.metadata
        p.metadata["lods"] = {}
        if kind in ("replaced_with_source_geometry", "redesigned_product_study"):
            p.metadata.update(reference_source=info.get("reference_source", build.metadata.get("product_study")), conceptual=True,
                              assembly_confidence=0.5, manufacturing_unverified=True)
            p.quality_score = 0
            p.quality_report = {"status": "reference_asset" if kind == "replaced_with_source_geometry" else "product_study", "total": 0, "notes": build.warnings}
            p.status = "ready"
            p.spec["params"] = {}
            p.spec["notes"] = ("Reference MJCF: metric scale and source joint layout." if kind == "replaced_with_source_geometry" else
                                "Visual product study, not manufacturer CAD.") + " Original spec kept in library_update metadata."
        else:
            report = assess(spec, build.part_data(), mode=p.generation_mode, metadata=build.metadata)
            p.quality_report = report.to_dict()
            p.quality_score = round(report.total, 2)
            p.status = "ready" if report.status in ("passed", "best_effort") else "rejected"
            p.metadata.update(report.metadata)
        p.warnings = list(dict.fromkeys(p.warnings + build.warnings))
        items = build.render_items()
        (dest / "renders").mkdir(exist_ok=True)
        # Re-render previews for the actual geometry; no old preview survives the replacement.
        for view in ("front", "back", "left", "right", "top", "bottom", "iso"):
            rr = R.render(items, view, 512 if product_redesign and view == "iso" else 256,
                          ssaa=1, texture_root=dest, background="light" if product_redesign else "dark",
                          outline=not product_redesign)
            path = dest / ("thumbnail.png" if view == "iso" else f"renders/{view}.png")
            path.write_bytes(R.png_bytes(rr.image))
        p.thumbnail_path = "thumbnail.png"
        p.renders = {v: f"renders/{v}.png" for v in ("front", "back", "left", "right", "top", "bottom")}
        if build.has_assembly:
            (dest / "renders/exploded.png").write_bytes(R.png_bytes(R.render(build.render_items(1.0), "iso", 384 if product_redesign else 256,
                ssaa=1, texture_root=dest, background="light" if product_redesign else "dark", outline=not product_redesign).image))
            p.renders["exploded"] = "renders/exploded.png"
        p.generator_version = GENERATOR_VERSION + ":library-20260930"
    else:
        info["reason"] = "External AI mesh has no reproducible engineering source; preserved, not claimed rebuilt."
        if product_redesign:
            doc = gltf.read_glb((dest / p.asset_path).read_bytes())
            # Preserve embedded texture bindings when rendering an existing external asset.
            saved = {}
            for ti, tex in enumerate(doc.textures):
                data, mime = doc.images[tex["source"]]
                rel = f"textures/preview_{ti}." + ("png" if mime == "image/png" else "jpg")
                (dest / "textures").mkdir(exist_ok=True)
                (dest / rel).write_bytes(data)
                saved[ti] = rel
            materials = [gltf.material_from_gltf(i, m, saved) for i, m in enumerate(doc.materials)]
            items = [(pr.mesh, materials[pr.material]) for node in doc.nodes for pr in node.primitives if pr.material is not None]
            if not items:
                raise ValueError("External model has no renderable materials")
            for view in ("front", "back", "left", "right", "top", "bottom", "iso"):
                rel = "thumbnail.png" if view == "iso" else f"renders/{view}.png"
                (dest / rel).parent.mkdir(exist_ok=True)
                (dest / rel).write_bytes(R.png_bytes(R.render(items, view, 512 if view == "iso" else 256,
                    background="light", outline=False, ssaa=1, texture_root=dest).image))
            p.thumbnail_path = "thumbnail.png"
            p.renders = {v: f"renders/{v}.png" for v in ("front", "back", "left", "right", "top", "bottom")}
    if product_redesign:
        info["presentation"] = "studio_light_512"
        p.metadata["product_redesign"] = {"version": 1, "geometry": kind, "exact_replica": kind == "replaced_with_source_geometry"}
    p.cache_key = ""
    p.metadata["library_update"] = dict(info, kind=kind)
    p.metadata["manufacturing_unverified"] = True
    save_manifest(p, dest)
    checks = validate_manifest(p, dest, require_explosion=p.has_assembly)
    if not checks.ok:
        raise RuntimeError("Manifest: " + "; ".join(checks.errors))
    limits = Limits()
    for rel in {p.asset_path, *(part.asset for part in p.parts)}:
        result = validate_glb_bytes((dest / rel).read_bytes(), limits, rel)
        if not result.ok:
            raise RuntimeError("GLB: " + "; ".join(result.errors))
    old_glb = geometry_hash(src / original.asset_path)
    new_glb = geometry_hash(dest / p.asset_path)
    return {"id": pid, "name": p.name, "category": p.category, "kind": kind, "status": p.status,
            "geometry_changed": old_glb != new_glb, "parts": len(p.parts), "original_hash": old_hash,
            "staged_hash": tree_hash(dest), "reference": info.get("reference_url", "")}


def stage(source, staging, retry=(), product_redesign=False):
    staging.mkdir(parents=True, exist_ok=True)
    report_path = staging / "update_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {"source": str(source), "projects": [], "errors": []}
    if Path(report["source"]).resolve() != source.resolve():
        raise RuntimeError("Staging belongs to another source library")
    for pid in retry:
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", pid):
            raise ValueError("Invalid retry ID")
        previous = staging / "projects" / pid
        if previous.exists():
            archive = staging / "previous_attempts"
            archive.mkdir(exist_ok=True)
            previous.rename(archive / (pid + "-" + str(time.time_ns())))
        report["projects"] = [item for item in report["projects"] if item["id"] != pid]
    completed = {r["id"] for r in report["projects"]}
    report["errors"] = []
    for path in sorted((source / "projects").glob("*/manifest.json")):
        p = load_manifest(path.parent)
        if p.id in completed:
            continue
        print("BUILD", p.id, p.name, flush=True)
        try:
            item = stage_one(source, staging, p, product_redesign=product_redesign)
            report["projects"].append(item)
            print("OK", item["kind"], item["status"], flush=True)
        except Exception as exc:
            report["errors"].append({"id": p.id, "error": str(exc)})
            print("ERROR", p.id, str(exc), flush=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if report["errors"]:
        raise RuntimeError("Some projects could not be staged; live library was not changed.")


def publish(source, staging):
    import psutil
    # Avoid an open app overwriting our index from its old in-memory copy.
    for proc in psutil.process_iter(["pid", "name", "cmdline", "cwd"]):
        if proc.pid == os.getpid():
            continue
        name = (proc.info["name"] or "").lower()
        cmd = " ".join(proc.info["cmdline"] or []).lower()
        location = cmd + " " + (proc.info["cwd"] or "").lower()
        if name == "nexa.exe" or (name in ("python.exe", "pythonw.exe") and "main.py" in cmd and "nexa" in location):
            raise RuntimeError(f"NEXA đang chạy (PID {proc.pid}); đóng ứng dụng trước khi áp dụng.")
    report = json.loads((staging / "update_report.json").read_text(encoding="utf-8"))
    if report["errors"] or Path(report["source"]).resolve() != source.resolve():
        raise RuntimeError("Invalid staged report")
    ids = [item["id"] for item in report["projects"]]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", pid) for pid in ids):
        raise RuntimeError("Invalid project IDs in report")
    # Validate all inputs before touching any live project.
    for item in report["projects"]:
        if tree_hash(source / "projects" / item["id"]) != item["original_hash"]:
            raise RuntimeError("Original changed since staging: " + item["id"])
        if tree_hash(staging / "projects" / item["id"]) != item["staged_hash"]:
            raise RuntimeError("Staged project changed: " + item["id"])
    backup = source.parent / "3d_library_backups" / time.strftime("%Y%m%d-%H%M%S")
    backup.mkdir(parents=True, exist_ok=False)
    index_path = source / "index.json"
    shutil.copy2(index_path, backup / "index.json")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    done = []
    try:
        for item in report["projects"]:
            pid = item["id"]
            live = source / "projects" / pid
            prepared = source / "projects" / (pid + ".updating")
            if prepared.exists():
                raise RuntimeError("Pending directory already exists: " + str(prepared))
            shutil.copytree(staging / "projects" / pid, prepared)
            if tree_hash(prepared) != item["staged_hash"]:
                raise RuntimeError("Copy verification failed: " + pid)
            live.rename(backup / pid)
            done.append(pid)
            prepared.rename(live)
            p = load_manifest(live)
            old = index["projects"].get(pid, {})
            old.update(name=p.name, category=p.category, status=p.status, quality_score=p.quality_score,
                       cache_key="", thumbnail=p.thumbnail_path, bytes=sum(x.stat().st_size for x in live.rglob("*") if x.is_file()))
            index["projects"][pid] = old
        updated_ids = set(done)
        index["by_key"] = {k: v for k, v in index.get("by_key", {}).items() if v not in updated_ids}
        temporary = source / "index.library-update.json"
        temporary.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
        temporary.replace(index_path)
    except Exception:
        for pid in reversed(done):
            live = source / "projects" / pid
            if live.exists():
                live.rename(backup / (pid + ".failed-update"))
            (backup / pid).rename(live)
        shutil.copy2(backup / "index.json", index_path)
        raise
    shutil.copy2(staging / "update_report.json", backup / "update_report.json")
    (staging / "published.json").write_text(json.dumps({"backup": str(backup), "updated": done}, indent=2), encoding="utf-8")
    print("PUBLISHED", len(done), "BACKUP", backup)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(os.environ["LOCALAPPDATA"]) / "NEXA/3d_cache")
    parser.add_argument("--stage", type=Path, default=ROOT / "results/library_update_20260930")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--product-redesign", action="store_true", help="Rebuild legacy product studies and render the entire library in a light studio")
    parser.add_argument("--retry-project", action="append", default=[])
    args = parser.parse_args()
    source, staging = args.source.resolve(), args.stage.resolve()
    if source == staging or source in staging.parents or staging in source.parents:
        raise ValueError("Staging must be separate from the live library")
    if args.apply:
        publish(source, staging)
    else:
        stage(source, staging, args.retry_project, product_redesign=args.product_redesign)
