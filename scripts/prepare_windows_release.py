"""Prepare an existing PyInstaller build for the expressly authorized shared-key release.

Never prints secrets. Copies only selected API settings, never personal settings/history.
The resulting installer contains recoverable shared credentials; keep this script's
--include-shared-api flag explicit when rebuilding this distribution.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--include-shared-api', action='store_true', required=True)
    parser.add_argument('--payload', type=Path, default=ROOT / 'release/windows-portable/NEXA')
    args = parser.parse_args()
    out = args.payload.resolve()
    if not (out / 'NEXA.exe').is_file():
        raise SystemExit('Build NEXA.exe first.')
    result = json.loads((out / 'installation-check.json').read_text(encoding='utf-8'))
    if not result.get('ok'):
        raise SystemExit('Frozen installation check did not pass.')

    from dotenv import dotenv_values, set_key
    values = dotenv_values(ROOT / '.env')
    if not values.get('GEMINI_API_KEY') or values['GEMINI_API_KEY'].startswith('YOUR_'):
        raise SystemExit('A configured Gemini API key is required; no secrets printed.')
    allowed = ('NEXA_AI_PROVIDER', 'GEMINI_API_KEY', 'GEMINI_MODEL',
               'GEMINI_REQUEST_TIMEOUT_SECONDS', 'NEXA_MAX_TOOL_STEPS',
               'NEXA_CLOUD_SCREEN_VISION', 'HF_TOKEN', 'TRIPO_API_KEY', 'MESHY_API_KEY')
    env = out / '.env'
    env.write_text('# Shared API configuration for this NEXA distribution.\n', encoding='utf-8')
    for key in allowed:
        if values.get(key):
            set_key(str(env), key, values[key])

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
        'Mo NEXA.exe hoac shortcut NEXA. Khong can cai Python/thu vien hay nhap API key.\n'
        'Can Windows 10/11 64-bit va Internet de dung Gemini/dich vu cloud.\n'
        'Model nhan dang giong noi CPU/GPU va nhan dien tay/mat da di kem.\n'
        'Cho phep micro/camera trong Windows khi su dung cac chuc nang tuong ung.\n'
        'Browser Bridge nang cao: cai extension trong browser_bridge/extension va chay\n'
        'browser_bridge/install_bridge.ps1. Native host da dong goi, khong can Python.\n'
        'Chay code sinh ra bang ngon ngu khac van can runtime/compiler cua ngon ngu do.\n'
        'AI dung quota chung cua nha phat hanh; phu thuoc key va dich vu con hoat dong.\n',
        encoding='utf-8')
    print('Release payload prepared. Shared credentials included without displaying values.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
