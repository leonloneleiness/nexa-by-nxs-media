"""Exercise the installed AI conversation path using a synthetic arithmetic question."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--installed', type=Path, required=True)
    parser.add_argument('--reports', type=Path, required=True)
    args = parser.parse_args()
    installed, reports = args.installed.resolve(), args.reports.resolve()
    if not installed.is_relative_to((ROOT / 'scratch').resolve()):
        raise SystemExit('Only disposable installations inside scratch/ are supported.')
    reports.mkdir(parents=True, exist_ok=True)
    test_user = reports / 'synthetic-user'
    env = {k:v for k,v in os.environ.items()
           if not k.startswith(('PYTHON', 'QT_', 'QML', 'NEXA_', 'GEMINI_', 'OPENAI_', 'HF_'))}
    windows = Path(env.get('SystemRoot', 'C:/Windows'))
    env.update(PATH=os.pathsep.join((str(windows / 'System32'), str(windows))),
        LOCALAPPDATA=str(test_user), APPDATA=str(test_user / 'Roaming'),
        HF_HUB_OFFLINE='1', QT_QPA_PLATFORM='offscreen', QT_QPA_FONTDIR=str(windows / 'Fonts'),
        NEXA_AUTOQUIT_SECONDS='45', NEXA_SMOKE_GRAB_AT='35',
        NEXA_SMOKE_GRAB=str(reports / 'ai-conversation.png'),
        NEXA_SMOKE_TEXT='Chỉ trả lời bằng chữ: 17 nhân 19 bằng bao nhiêu?')
    Path(env['APPDATA']).mkdir(parents=True, exist_ok=True)
    (installed / 'config/settings.yaml').write_text(
        'power:\n  clap_wake_guard: false\n  button_turns_off_display: false\n'
        '  auto_unlock: false\n  no_lock: false\n'
        'audio:\n  clap:\n    min_level_dbfs: 0\n'
        'tts:\n  backend: none\ngestures:\n  enabled_on_start: false\n'
        'stt:\n  model: small\n  device: cpu\nai:\n  persist_history: true\n', encoding='utf-8')
    with (reports / 'ai-stderr.txt').open('w', encoding='utf-8') as errors:
        run = subprocess.run([str(installed / 'NEXA.exe')], cwd=installed, env=env,
                             timeout=100, stderr=errors, creationflags=subprocess.CREATE_NO_WINDOW)
    history = test_user / 'NEXA/conversation_history.json'
    data = json.loads(history.read_text(encoding='utf-8')) if history.is_file() else {}
    answers = [m['text'] for m in data.get('messages', []) if m['role'] == 'model']
    report = {'ok': run.returncode == 0 and any('323' in text for text in answers),
              'exit_code': run.returncode, 'synthetic_test': '17 x 19 = 323',
              'received_answer': bool(answers), 'correct_answer': any('323' in text for text in answers)}
    (reports / 'ai-conversation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
