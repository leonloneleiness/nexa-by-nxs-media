"""Audit public tool routes and classify every user-facing bridge slot.

No device access, cloud calls, real settings or credentials are used.
Run: python scripts/audit_bilingual_commands.py --output docs/bilingual_catalog.json
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Existing bridge buttons already have equivalent registered tools.
EXISTING = {
    "main": {
        "toggleGestures":"set_gesture_mode", "toggleAirMouse":"set_air_mouse",
        "setPresence":"set_presence_lock", "setHeadTarget":"set_head_target", "calibrateHead":"calibrate_head",
        "saveSettings":"set_nexa_setting",
    },
    "code": {
        "openPanel":"open_code_panel", "closePanel":"close_code_panel", "setView":"code_set_view",
        "generate":"generate_code", "refine":"refine_code", "cancel":"cancel_code_job", "runTests":"run_code_tests",
    },
    "3d": {
        "generate":"generate_3d_model", "cancelJob":"cancel_3d_job", "openModel":"open_3d_model",
        "closeViewer":"close_3d_viewer", "partAction":"hide_3d_part", "showAll":"show_all_3d_parts",
        "explode":"explode_3d_assembly", "collapse":"collapse_3d_assembly", "toggleMotion":"set_3d_motion",
        "resetView":"reset_3d_view", "setRenderMode":"set_3d_render_mode", "orbit":"rotate_3d_view",
        "zoomBy":"zoom_3d_view", "exportModel":"export_3d_model",
    },
    "edu": {"close":"close_nexa_panel"},
}
INTERNAL = {
    "main": {"wake":"wake entry point", "pushToTalk":"microphone entry point", "sendText":"text entry point",
             "stop":"router stop", "cancelTask":"router cancel", "sleep":"router sleep",
             "confirm":"router confirm", "deny":"router deny", "clearConversation":"router clear_history"},
    "code": {"webConsole":"web preview telemetry"}, "3d":{"reportFps":"render telemetry",
        "selectPointedPart":"camera capture-time hit-test input; not a spoken command"}, "edu":{},
}
PROTECTED = {"main":{"setApiKey":"Credential entry stays in Settings; do not log keys in transcripts.",
                       "setUnlockPassword":"Windows secret entry stays in Settings; not voice authentication."}}


def audit():
    from nexa.ai.bilingual import catalog_route
    from nexa.ai.intent_router import IntentRouter
    from nexa.ai.tool_registry import build_registry
    from nexa.ai.ui_commands import COMMANDS
    from nexa.utils.config import Config
    with tempfile.TemporaryDirectory(prefix="nexa-command-audit-") as folder:
        cfg = Config(settings_path=Path(folder)/"settings.yaml", gestures_path=Path(folder)/"gestures.yaml", load_env=False)
        registry = build_registry(cfg)
        tools = []
        for name in registry.names():
            spec = registry.get(name)
            tools.append({"name":name, "vi":"lệnh " + spec.title, "en":"command " + name.replace("_", " "),
                          "parameters":spec.ai_schema(), "needs_control":spec.needs_control,
                          "always_confirm":spec.always_confirm})
        slots = []
        for target, filename, classname in (("main","bridge.py","UiBridge"), ("code","code_bridge.py","CodeBridge"),
                                            ("3d","three_d_bridge.py","ThreeDBridge"), ("edu","education_bridge.py","EducationBridge")):
            tree = ast.parse((ROOT/"nexa"/"ui"/filename).read_text(encoding="utf-8-sig"))
            cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == classname)
            for node in cls.body:
                if not isinstance(node, ast.FunctionDef) or node.name.startswith("_"):
                    continue
                if not any(isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "Slot" for d in node.decorator_list):
                    continue
                command = next((c.name for c in COMMANDS if c.target == target and c.method == node.name), None)
                command = command or EXISTING.get(target, {}).get(node.name)
                if command:
                    status = "registered" if registry.get(command) else "missing_tool"
                    reason = command
                elif node.name in INTERNAL.get(target, {}):
                    status, reason = "entry_or_internal", INTERNAL[target][node.name]
                elif node.name in PROTECTED.get(target, {}):
                    status, reason = "protected_input", PROTECTED[target][node.name]
                else:
                    status, reason = "uncovered", "No command classification"
                slots.append({"bridge":target,"method":node.name,"status":status,"route":reason})
        return {"scope":"Public registry routes and Qt bridge slots; not arbitrary speech recognition or hardware certification.",
                "tool_count":len(tools), "tools":tools, "ui_slots":slots,
                "uncovered":[s for s in slots if s["status"] in ("uncovered","missing_tool")]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"tools":report["tool_count"], "ui_slots":len(report["ui_slots"]), "uncovered":report["uncovered"]}, ensure_ascii=False))
    sys.exit(1 if report["uncovered"] else 0)
