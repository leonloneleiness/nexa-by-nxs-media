"""Prepare an existing PyInstaller build for the expressly authorized shared-key release.

Never prints secrets. Copies only selected API settings, never personal settings/history.
The resulting installer contains recoverable shared credentials; keep this script's
--include-shared-api flag explicit when rebuilding this distribution.
"""
from __future__ import annotations

import argparse
from importlib import metadata
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def copy_runtime_metadata(out: Path) -> None:
    """Preserve version/license metadata used by the in-app library dashboard."""
    from packaging.requirements import Requirement

    requirements = (ROOT / 'requirements.txt').read_text(encoding='utf-8').splitlines()
    # MediaPipe pulls OpenCV transitively; it is also shown in the dashboard.
    for line in [*requirements, 'opencv-contrib-python']:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        distribution = metadata.distribution(Requirement(line).name)
        entry = next(path for path in distribution.files or []
                     if path.name == 'METADATA' and path.parent.name.endswith('.dist-info'))
        source = Path(distribution.locate_file(entry)).parent
        shutil.copytree(source, out / '_internal' / source.name, dirs_exist_ok=True)


def shared_api_values(values: dict, provider_override: str | None = None) -> dict:
    """Return only release settings, requiring credentials for the chosen provider."""
    provider = provider_override or values.get('NEXA_AI_PROVIDER', 'gemini')
    required_key = 'OPENAI_API_KEY' if provider in ('openai', 'openai_compatible', 'compatible') else 'GEMINI_API_KEY'
    common = ('NEXA_AI_PROVIDER', 'NEXA_MAX_TOOL_STEPS', 'NEXA_CLOUD_SCREEN_VISION',
              'HF_TOKEN', 'TRIPO_API_KEY', 'MESHY_API_KEY', 'NEXA_3D_PROVIDER')
    provider_keys = (('GEMINI_API_KEY', 'GEMINI_MODEL', 'GEMINI_REQUEST_TIMEOUT_SECONDS')
                     if required_key == 'GEMINI_API_KEY' else
                     ('OPENAI_API_KEY', 'OPENAI_BASE_URL', 'OPENAI_MODEL', 'OPENAI_REQUEST_TIMEOUT_SECONDS'))
    allowed = common + provider_keys
    selected = {key: values[key] for key in allowed
                if values.get(key) and not values[key].startswith('YOUR_')}
    if not selected.get(required_key):
        raise ValueError(f'A configured {required_key} is required; no secrets printed.')
    selected['NEXA_AI_PROVIDER'] = provider
    return selected


def validate_payload(out: Path) -> dict:
    """Validate the complete installed tree before it is handed to Inno Setup.

    NEXA is intentionally a one-folder PyInstaller application.  A successful
    PyInstaller module check alone is not enough: it can pass while the release
    payload is missing the offline speech models or the QML/Qt runtime.
    """
    required_files = [
        out / "NEXA.exe",
        out / "_internal" / "PySide6" / "qml" / "QtQuick3D" / "qmldir",
        out / "config" / "settings.example.yaml",
        out / "config" / "gestures.yaml",
        out / ".env.example",
        out / "_internal" / "module-manifest.json",
        out / "browser_bridge" / "NexaBridge.exe",
    ]
    # PyInstaller --add-data places application resources under _internal;
    # models/config/browser_bridge are deliberately kept beside the exe.
    required_dirs = [out / "_internal", out / "_internal" / "assets", out / "models", out / "browser_bridge"]
    errors = [f"Thiếu tệp: {p.relative_to(out)}" for p in required_files if not p.is_file()]
    errors += [f"Thiếu thư mục: {p.relative_to(out)}" for p in required_dirs if not p.is_dir()]
    model_files = list((out / "models" / "whisper").rglob("*.bin")) if (out / "models" / "whisper").is_dir() else []
    if not model_files:
        errors.append("Thiếu model Whisper offline trong models/whisper")
    for repo in ('Systran--faster-whisper-small', 'mobiuslabsgmbh--faster-whisper-large-v3-turbo'):
        cache = out / 'models' / 'whisper' / f'models--{repo}'
        ref = cache / 'refs' / 'main'
        if not ref.is_file():
            errors.append(f'Thiếu cache index: {ref.relative_to(out)}')
            continue
        snapshot = cache / 'snapshots' / ref.read_text(encoding='utf-8').strip()
        for name in ('model.bin', 'config.json', 'tokenizer.json'):
            path = snapshot / name
            if not path.is_file() or path.stat().st_size == 0:
                errors.append(f'Thiếu dữ liệu model: {path.relative_to(out)}')
    for name in ("hand_landmarker.task", "face_landmarker.task"):
        if not (out / "models" / name).is_file():
            errors.append(f"Thiếu model MediaPipe: models/{name}")
    return {"ok": not errors, "errors": errors,
            "whisper_files": len(model_files),
            "payload": str(out)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--include-shared-api', action='store_true', required=True)
    parser.add_argument('--payload', type=Path, default=ROOT / 'release/windows-portable/NEXA')
    parser.add_argument('--provider', choices=('gemini', 'openai'), help='Explicit release-only provider override')
    args = parser.parse_args()
    out = args.payload.resolve()
    if not (out / 'NEXA.exe').is_file():
        raise SystemExit('Build NEXA.exe first.')
    result = json.loads((out / 'installation-check.json').read_text(encoding='utf-8'))
    if not result.get('ok'):
        raise SystemExit('Frozen installation check did not pass.')

    from dotenv import dotenv_values, set_key
    values = shared_api_values(dotenv_values(ROOT / '.env'), args.provider)
    env = out / '.env'
    env.write_text('# Shared API configuration for this NEXA distribution.\n', encoding='utf-8')
    for key, value in values.items():
        set_key(str(env), key, value)
    copy_runtime_metadata(out)

    def ignore_model_cache(directory: str, names: list[str]) -> list[str]:
        return [n for n in names if n in ('.locks', '__pycache__') or n.endswith(('.lock', '.incomplete'))]

    shutil.copytree(ROOT / 'models', out / 'models', dirs_exist_ok=True, ignore=ignore_model_cache)
    shutil.copytree(ROOT / 'browser_bridge', out / 'browser_bridge', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    bridge = out / 'browser_bridge'
    if not (bridge / 'NexaBridge.exe').is_file():
        raise SystemExit('Build the standalone NexaBridge.exe before preparing this release.')
    install = bridge / 'install_bridge.ps1'
    text = install.read_text(encoding='utf-8-sig')
    start = text.index('$HostBat =')
    end = text.index('New-Item -ItemType Directory', start)
    text = text[:start] + ('$HostBat = Join-Path $BridgeDir "NexaBridge.exe"\n'
                          'if (-not (Test-Path $HostBat)) { throw "Missing NexaBridge.exe" }\n\n') + text[end:]
    install.write_text(text, encoding='utf-8-sig')
    (bridge / 'native_host.bat').write_text('@echo off\r\n"%~dp0NexaBridge.exe" %*\r\n', encoding='utf-8')
    (out / 'HUONG-DAN.txt').write_text(
        'NEXA - NXS MEDIA\n\n'
        'Cai bang NEXA-Setup.exe va mo shortcut NEXA. Khong tach rieng NEXA.exe khoi thu muc cai dat.\n'
        'Khong can cai Python/thu vien hay nhap API key voi ban phat hanh da cau hinh.\n'
        'Can Windows 10/11 64-bit va Internet de dung AI/dich vu cloud.\n'
        'Model nhan dang giong noi CPU/GPU va nhan dien tay/mat da di kem.\n'
        'Cho phep micro/camera trong Windows khi su dung cac chuc nang tuong ung.\n'
        'Browser Bridge nang cao: cai extension trong browser_bridge/extension va chay\n'
        'browser_bridge/install_bridge.ps1. Native host da dong goi, khong can Python.\n'
        'Chay code sinh ra bang ngon ngu khac van can runtime/compiler cua ngon ngu do.\n'
        'AI dung quota chung cua nha phat hanh; phu thuoc key va dich vu con hoat dong.\n',
        encoding='utf-8')
    payload_report = validate_payload(out)
    (out / 'release-payload-check.json').write_text(
        json.dumps(payload_report, ensure_ascii=False, indent=2), encoding='utf-8')
    if not payload_report['ok']:
        raise SystemExit('Payload phát hành thiếu thành phần: ' + '; '.join(payload_report['errors']))
    print('Release payload prepared. Shared credentials included without displaying values.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
