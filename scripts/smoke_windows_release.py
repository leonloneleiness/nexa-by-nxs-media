"""Smoke-test a disposable installed copy, with offline models and no power remapping."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
installed = (root / 'scratch/release-install-test').resolve()
reports = root / 'release/verification'
reports.mkdir(parents=True, exist_ok=True)
exe = installed / 'NEXA.exe'
env = dict(os.environ)
for k in list(env):
    if k.startswith(('PYTHON', 'QT_', 'QML', 'NEXA_', 'GEMINI_')):
        env.pop(k, None)
windows = os.environ.get('SystemRoot', r'C:\Windows')
env['PATH'] = os.pathsep.join((str(Path(windows) / 'System32'), windows))
env['HF_HUB_OFFLINE'] = '1'
env['NEXA_AUTOQUIT_SECONDS'] = '25'
env['NEXA_SMOKE_GRAB'] = str(reports / 'installed-app.png')
env['NEXA_SMOKE_GRAB_AT'] = '3'
env['LOCALAPPDATA'] = str(root / 'scratch/release-test-user')
env['APPDATA'] = str(root / 'scratch/release-test-user/Roaming')
Path(env['APPDATA']).mkdir(parents=True, exist_ok=True)
# This is ONLY the disposable installed copy, never the release payload.
(installed / 'config/settings.yaml').write_text(
    'power:\n  clap_wake_guard: false\n  button_turns_off_display: false\n'
    '  no_lock: false\n  auto_unlock: false\n'
    'tts:\n  backend: none\ngestures:\n  enabled_on_start: false\n'
    'stt:\n  device: cpu\n', encoding='utf-8')
report = reports / 'installed-modules.json'
check = subprocess.run([str(exe), '--nexa-check-install', str(report)], env=env, timeout=120)
assert check.returncode == 0 and json.loads(report.read_text(encoding='utf-8'))['ok']
bridge = installed / 'browser_bridge/NexaBridge.exe'
for origin, code in [('chrome-extension://ghkmpnijfoceebnoolnbhedljpelgnhp/', 0), ('invalid-origin', 1)]:
    p = subprocess.run([str(bridge), origin], input=b'', capture_output=True, env=env, timeout=30)
    assert p.returncode == code, 'Native host origin/EOF check failed'
with (reports / 'installed-stderr.txt').open('w', encoding='utf-8') as errors:
    logfile = installed / 'logs/nexa.log'
    log_offset = logfile.stat().st_size if logfile.exists() else 0
    try:
        ui = subprocess.run([str(exe)], env=env, cwd=installed, timeout=75, stderr=errors)
        exit_code = ui.returncode
    except subprocess.TimeoutExpired:
        exit_code = 'timeout'
log = logfile.read_bytes()[log_offset:].decode('utf-8', errors='replace')
summary = {'module_check': True, 'bridge_origin_and_eof': True, 'ui_exit': exit_code,
           'screenshot': (reports / 'installed-app.png').is_file(),
           'speech_model_loaded': 'Đã nạp faster-whisper' in log,
           'clean_shutdown': 'NEXA đã tắt' in log}
(reports / 'smoke.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary))
sys.exit(0 if exit_code == 0 and summary['screenshot'] and summary['speech_model_loaded'] else 1)
