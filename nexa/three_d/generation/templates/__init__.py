"""Template tham số theo nhóm hỗ trợ. Mỗi template nhận ModelSpec đã chuẩn hóa và trả BuiltAssembly."""
from __future__ import annotations

from typing import Callable

from nexa.three_d.generation.assembly import BuiltAssembly
from nexa.three_d.spec import ModelSpec


# mẫu kỹ thuật mở rộng: category → module trong templates/ (mỗi module có build(spec))
TECH_TEMPLATES = {
    "bearing": "bearing", "stepper_motor": "stepper", "gearbox": "gearbox", "cylinder": "cylinder",
    "ball_valve": "piping", "pipe_fitting": "piping", "belt_drive": "transmission", "chain_drive": "transmission",
    "shaft_coupling": "transmission", "ball_screw": "linear_motion", "linear_guide": "linear_motion", "spring": "spring",
    "robot_arm": "robot_arm", "robot_vacuum": "robot_vacuum", "agv": "agv",
    "fixed_wing": "fixed_wing", "car": "car", "motorbike": "motorbike", "excavator": "excavator", "forklift": "forklift",
    "crane": "crane", "train": "train", "cubesat": "cubesat", "launch_vehicle": "rocket",
    "wind_turbine": "wind_turbine", "solar_array": "solar", "generator_set": "genset", "centrifugal_pump": "pump",
    "storage_tank": "tank", "bridge": "bridge", "steel_truss": "truss", "lattice_tower": "tower",
    "fdm_printer": "printer3d", "cnc_router": "cnc", "server_rack": "rack", "electrical_enclosure": "enclosure", "axial_fan": "fan",
    "heatsink": "heatsink", "dev_board": "board",
}


def get_template(category: str) -> Callable[[ModelSpec], BuiltAssembly] | None:
    if category in TECH_TEMPLATES:
        import importlib
        return importlib.import_module(f"nexa.three_d.generation.templates.{TECH_TEMPLATES[category]}").build
    if category in ("bolt", "nut", "washer"):
        from nexa.three_d.generation.templates.fasteners import build
        return build
    if category in ("gear", "flange", "bracket"):
        from nexa.three_d.generation.templates.mechanical import build
        return build
    if category == "uav":
        from nexa.three_d.generation.templates.uav import build
        return build
    if category == "rover":
        from nexa.three_d.generation.templates.rover import build
        return build
    if category == "humanoid":
        from nexa.three_d.generation.templates.humanoid import build
        return build
    if category == "quadruped":
        from nexa.three_d.generation.templates.quadruped import build
        return build
    if category == "helicopter":
        from nexa.three_d.generation.templates.helicopter import build
        return build
    if category == "boat":
        from nexa.three_d.generation.templates.boat import build
        return build
    return None
