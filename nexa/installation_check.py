"""Read-only source/frozen installation smoke check, without starting devices or services."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path


def check_installation() -> dict:
    # Match the application's STA command executor. Importing WinRT and COM
    # SDKs in an arbitrary bulk-check order can otherwise select incompatible
    # apartments before pywinauto/comtypes initialize.
    sys.coinit_flags = 2  # COINIT_APARTMENTTHREADED, also honored by comtypes/pywinauto
    import pythoncom
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    import comtypes  # noqa: F401  # initialize before SDKs which use worker-thread WinRT
    import pywinauto  # noqa: F401
    from nexa.three_d.generation.templates import TECH_TEMPLATES, get_template
    from nexa.utils.config import QML_DIR, RESOURCE_ROOT, PROJECT_ROOT
    from nexa import __version__
    checked, errors, imported = [], [], []
    categories = sorted(set(TECH_TEMPLATES) | {'bolt', 'nut', 'washer', 'gear', 'flange', 'bracket',
                                              'uav', 'rover', 'humanoid', 'quadruped', 'helicopter', 'boat'})
    for category in categories:
        try:
            if not callable(get_template(category)):
                raise RuntimeError('missing build function')
            checked.append(category)
        except Exception as exc:
            errors.append(f'{category}: {type(exc).__name__}: {exc}')
    manifest = RESOURCE_ROOT / 'module-manifest.json'
    if getattr(sys, 'frozen', False):
        modules = json.loads(manifest.read_text(encoding='utf-8'))
    else:
        modules = sorted({'.'.join(p.relative_to(PROJECT_ROOT).with_suffix('').parts).removesuffix('.__init__')
                          for p in (PROJECT_ROOT / 'nexa').rglob('*.py')})
    dependencies = ('numpy', 'scipy.signal', 'sounddevice', 'miniaudio', 'faster_whisper', 'ctranslate2',
                    'onnxruntime', 'mediapipe', 'cv2', 'google.genai', 'openai', 'edge_tts',
                    'winrt.windows.media.control', 'winrt.windows.media.speechsynthesis',
                    'winrt.windows.storage.streams', 'win32com.client', 'pythoncom', 'win32serviceutil',
                    'pywinauto', 'pyautogui', 'pycaw.pycaw', 'comtypes', 'psutil', 'mss', 'PIL.Image',
                    'send2trash', 'yaml', 'dotenv', 'manifold3d', 'fast_simplification', 'gradio_client',
                    'pygments', 'pyflakes', 'PySide6.QtQuick3D', 'PySide6.QtWebEngineQuick')
    for name in (*modules, *dependencies):
        try:
            importlib.import_module(name)
            imported.append(name)
        except Exception as exc:
            errors.append(f'{name}: {type(exc).__name__}: {exc}')
    for name in ('Main.qml', 'ModelViewer.qml', 'ModelGenerationPanel.qml', 'GenerationProgress.qml', 'CodePanel.qml',
                 'EducationPanel.qml', 'EducationScene.qml', 'RuntimeDashboard.qml', 'HtmlPreview.qml'):
        if not (QML_DIR / name).is_file():
            errors.append(f'Missing QML: {name}')
    return {'ok': not errors, 'version': __version__, 'application_modules': len(modules),
            'imported_modules': imported, 'template_categories': checked, 'errors': errors}


def check_runtime() -> dict:
    """Exercise bundled native libraries/models offline, without opening devices.

    Synthetic images/audio intentionally avoid collecting user camera/mic data.
    Each check fails independently so the report lists all broken capabilities.
    """
    import numpy as np
    from nexa.utils.config import MODELS_DIR
    checks, errors = {}, []

    def run(name, fn):
        try:
            checks[name] = fn()
        except Exception as exc:
            errors.append(f'{name}: {type(exc).__name__}: {exc}')

    def speech():
        from faster_whisper import WhisperModel
        model = WhisperModel('small', device='cpu', compute_type='int8', cpu_threads=2,
                             download_root=str(MODELS_DIR / 'whisper'), local_files_only=True)
        # Run the encoder/decoder and separately exercise the packaged Silero VAD.
        samples = np.zeros(16000, dtype=np.float32)
        segments, _ = model.transcribe(samples, language='vi', beam_size=1, vad_filter=False)
        list(segments)
        segments, _ = model.transcribe(samples, language='en', beam_size=1, vad_filter=True)
        list(segments)
        return {'model': 'small', 'device': 'cpu', 'offline': True, 'inference_and_vad': True}

    def vision(kind):
        from nexa.vision.hand_tracker import HandTracker
        from nexa.vision.face_tracker import FaceTracker
        cls = HandTracker if kind == 'hand' else FaceTracker
        tracker = cls(MODELS_DIR / f'{kind}_landmarker.task')
        try:
            tracker.detect(np.zeros((128, 128, 3), dtype=np.uint8), 1)
        finally:
            tracker.close()
        return {'model_loaded': True, 'inference': True}

    def geometry():
        from nexa.three_d.geometry import kernel as k
        solid = k.box(20, 20, 20) - k.cylinder(3, 30)
        if not solid.status_ok or not 0 < solid.volume() < 8000:
            raise RuntimeError('CSG boolean calculation failed')
        return {'triangles': solid.to_mesh().triangle_count, 'volume': solid.volume()}

    def education():
        from nexa.education.simulations import EducationEngine
        engine = EducationEngine()
        lessons = []
        for lesson in engine.catalog():
            engine.select(lesson['id'])
            if not engine.run()['result']:
                raise RuntimeError(lesson['id'])
            lessons.append(lesson['id'])
        return lessons

    run('speech_cpu', speech)
    run('hand_tracking', lambda: vision('hand'))
    run('face_tracking', lambda: vision('face'))
    run('cad_geometry', geometry)
    run('education', education)
    return {'ok': not errors, 'checks': checks, 'errors': errors}


def main(report_path: str, runtime: bool = False) -> int:
    try:
        result = check_installation()
        if runtime:
            result['runtime'] = check_runtime()
            result['ok'] = result['ok'] and result['runtime']['ok']
    except Exception as exc:
        result = {'ok': False, 'errors': [f'{type(exc).__name__}: {exc}']}
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['ok'] else 1
