"""Smoke-test a disposable installed copy, with offline models and no power remapping."""
from __future__ import annotations

import json
import argparse
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--installed', type=Path, default=root / 'scratch/release-install-test')
parser.add_argument('--reports', type=Path, default=root / 'release/verification')
parser.add_argument('--panels', nargs='+', default=['main', 'settings', 'gestures', '3d', 'code', 'edu'])
parser.add_argument('--device', choices=('cpu', 'auto'), default='cpu')
parser.add_argument('--offscreen', action='store_true', help='Render without opening visible desktop windows')
args = parser.parse_args()
installed = args.installed.resolve()
# Never overwrite a normal user's configuration or the public release payload.
if not installed.is_relative_to((root / 'scratch').resolve()):
    raise SystemExit('Smoke UI requires a disposable installation inside scratch/.')
reports = args.reports.resolve()
reports.mkdir(parents=True, exist_ok=True)
exe = installed / 'NEXA.exe'
env = dict(os.environ)
for k in list(env):
    if k.startswith(('PYTHON', 'QT_', 'QML', 'NEXA_', 'GEMINI_', 'OPENAI_', 'HF_')):
        env.pop(k, None)
windows = os.environ.get('SystemRoot', r'C:\Windows')
env['PATH'] = os.pathsep.join((str(Path(windows) / 'System32'), windows))
env['HF_HUB_OFFLINE'] = '1'
if args.offscreen:
    env['QT_QPA_PLATFORM'] = 'offscreen'
    env['QT_QPA_FONTDIR'] = str(Path(windows) / 'Fonts')
env['NEXA_AUTOQUIT_SECONDS'] = '25' if args.device == 'auto' else '16'
env['NEXA_SMOKE_GRAB_AT'] = '8'
env['LOCALAPPDATA'] = str(installed.parent / 'test-user')
env['APPDATA'] = str(installed.parent / 'test-user/Roaming')
Path(env['APPDATA']).mkdir(parents=True, exist_ok=True)
# This is ONLY the disposable installed copy, never the release payload.
(installed / 'config/settings.yaml').write_text(
    'power:\n  clap_wake_guard: false\n  button_turns_off_display: false\n'
    '  no_lock: false\n  auto_unlock: false\n'
    'tts:\n  backend: none\ngestures:\n  enabled_on_start: false\n'
    f'stt:\n  model: {"auto" if args.device == "auto" else "small"}\n  device: {args.device}\n'
    '  compute_type: auto\n', encoding='utf-8')
report = reports / 'installed-modules.json'
check = subprocess.run([str(exe), '--nexa-check-runtime', str(report)], env=env, cwd=installed,
                       timeout=180, creationflags=subprocess.CREATE_NO_WINDOW)
assert check.returncode == 0 and json.loads(report.read_text(encoding='utf-8'))['ok']
bridge = installed / 'browser_bridge/NexaBridge.exe'
for origin, code in [('chrome-extension://ghkmpnijfoceebnoolnbhedljpelgnhp/', 0), ('invalid-origin', 1)]:
    p = subprocess.run([str(bridge), origin], input=b'', capture_output=True, env=env, timeout=30,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    assert p.returncode == code, 'Native host origin/EOF check failed'
panels = {}
for panel in args.panels:
    png = reports / f'installed-{panel}.png'
    # A stale screenshot must never count as a successful run.
    png.unlink(missing_ok=True)
    env['NEXA_SMOKE_OPEN'] = '' if panel == 'main' else panel
    env['NEXA_SMOKE_GRAB'] = str(png)
    with (reports / f'installed-{panel}-stderr.txt').open('w', encoding='utf-8') as errors:
        logfile = installed / 'logs/nexa.log'
        log_offset = logfile.stat().st_size if logfile.exists() else 0
        try:
            ui = subprocess.run([str(exe)], env=env, cwd=installed, timeout=75, stderr=errors,
                                creationflags=subprocess.CREATE_NO_WINDOW)
            exit_code = ui.returncode
        except subprocess.TimeoutExpired:
            exit_code = 'timeout'
    log = logfile.read_bytes()[log_offset:].decode('utf-8', errors='replace') if logfile.exists() else ''
    stderr = (reports / f'installed-{panel}-stderr.txt').read_text(encoding='utf-8', errors='replace')
    failures = [line for line in (log + '\n' + stderr).splitlines()
                if any(marker in line for marker in ('Traceback (most recent call last)', 'ModuleNotFoundError',
                    'ImportError:', 'DLL load failed', 'QML:', 'ReferenceError:', 'TypeError:', 'is not installed'))]
    panels[panel] = {'ui_exit': exit_code, 'screenshot': png.is_file() and png.stat().st_size > 10000,
                     'speech_model_loaded': 'Đã nạp faster-whisper' in log,
                     'clean_shutdown': 'NEXA đã tắt' in log, 'errors': failures}
    panels[panel]['ok'] = (exit_code == 0 and panels[panel]['screenshot']
                           and panels[panel]['speech_model_loaded'] and panels[panel]['clean_shutdown']
                           and not failures)
    print(json.dumps({'panel': panel, **{k:v for k,v in panels[panel].items() if k != 'errors'},
                      'error_count': len(failures), 'first_errors': failures[:3]}), flush=True)
summary = {'module_check': True, 'offline_runtime_check': True, 'bridge_origin_and_eof': True,
           'panels': panels, 'ok': bool(panels) and all(p['ok'] for p in panels.values())}
(reports / 'smoke.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps({'ok': summary['ok'], 'panels_checked': list(panels)}))
sys.exit(0 if summary['ok'] else 1)
