"""Install the actual public installer into a disposable Unicode path, then verify file hashes."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--installer', type=Path, required=True)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--installed', type=Path, required=True)
    parser.add_argument('--reports', type=Path, required=True)
    args = parser.parse_args()
    installed = args.installed.resolve()
    if not installed.is_relative_to((ROOT / 'scratch').resolve()):
        raise SystemExit('Disposable target must be inside scratch/.')
    if installed.exists() and any(installed.iterdir()):
        raise SystemExit('Choose a fresh empty target for a genuine first-install test.')
    args.reports.mkdir(parents=True, exist_ok=True)
    log = (args.reports / 'installer.log').resolve()
    command = [str(args.installer.resolve()), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
               '/NOCLOSEAPPLICATIONS', '/NORESTARTAPPLICATIONS', '/NEXA_TEST_INSTALL=1',
               f'/DIR={installed}', f'/LOG={log}']
    result = subprocess.run(command, timeout=1200, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise SystemExit(f'Installer failed: {result.returncode}; inspect installer.log.')
    checked, errors = 0, []
    for source in args.payload.rglob('*'):
        if not source.is_file():
            continue
        relative = source.relative_to(args.payload)
        if relative.as_posix() in ('installation-check.json', 'release-payload-check.json', 'config/settings.yaml'):
            continue
        if relative.parts[0] == 'logs':
            continue
        target = installed / relative
        if not target.is_file() or digest(source) != digest(target):
            errors.append(relative.as_posix())
        checked += 1
    report = {'ok': not errors, 'installer_exit': result.returncode, 'checked_files': checked,
              'mismatches': errors, 'unicode_install_path': str(installed),
              'installer_sha256': digest(args.installer)}
    (args.reports / 'installed-integrity.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
