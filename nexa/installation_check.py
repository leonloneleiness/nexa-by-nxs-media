"""Read-only source/frozen installation smoke check, without starting devices or services."""
from __future__ import annotations

import importlib
import json
from pathlib import Path


def check_installation() -> dict:
    from nexa.three_d.generation.templates import TECH_TEMPLATES, get_template
    from nexa.utils.config import QML_DIR
    checked, errors = [], []
    categories = sorted(set(TECH_TEMPLATES) | {'bolt', 'nut', 'washer', 'gear', 'flange', 'bracket',
                                              'uav', 'rover', 'humanoid', 'quadruped', 'helicopter', 'boat'})
    for category in categories:
        try:
            if not callable(get_template(category)):
                raise RuntimeError('missing build function')
            checked.append(category)
        except Exception as exc:
            errors.append(f'{category}: {type(exc).__name__}: {exc}')
    for name in ('manifold3d', 'fast_simplification', 'PySide6.QtQuick3D', 'nexa.code.runners',
                 'nexa.code.live_run', 'nexa.three_d.generation.hf_provider'):
        try:
            importlib.import_module(name)
        except Exception as exc:
            errors.append(f'{name}: {type(exc).__name__}: {exc}')
    for name in ('Main.qml', 'ModelViewer.qml', 'ModelGenerationPanel.qml', 'GenerationProgress.qml', 'CodePanel.qml'):
        if not (QML_DIR / name).is_file():
            errors.append(f'Missing QML: {name}')
    return {'ok': not errors, 'template_categories': checked, 'errors': errors}


def main(report_path: str) -> int:
    try:
        result = check_installation()
    except Exception as exc:
        result = {'ok': False, 'errors': [f'{type(exc).__name__}: {exc}']}
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['ok'] else 1
