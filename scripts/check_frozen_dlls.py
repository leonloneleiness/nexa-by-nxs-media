"""Check direct PE imports against bundled DLLs and Windows System32 (no developer PATH)."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pefile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('payload', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    root = args.payload.resolve()
    files = [p for p in root.rglob('*') if p.suffix.lower() in ('.dll', '.pyd', '.exe')]
    bundled = {p.name.lower() for p in files}
    system = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32'
    missing, checked, inactive = {}, 0, []
    for path in files:
        # PyOpenGL ships alternate 32-bit / Python 2.x / Python 3.3 builds
        # alongside the active Python 3.11 x64 vc14 binaries. win32.py selects
        # only *64.vc14.dll here; legacy variants are never loaded by NEXA.
        if path.parent.name == 'DLLS' and path.parent.parent.name == 'OpenGL' and path.name.endswith(
                ('32.vc9.dll', '64.vc9.dll', '32.vc10.dll', '64.vc10.dll', '32.vc14.dll')):
            inactive.append(path.relative_to(root).as_posix())
            continue
        pe = pefile.PE(str(path), fast_load=True)
        try:
            pe.parse_data_directories(directories=[1])
            for entry in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
                name = entry.dll.decode('ascii', errors='replace').lower()
                if name.startswith(('api-ms-', 'ext-ms-')) or name in bundled or (system / name).is_file():
                    continue
                missing.setdefault(name, []).append(path.relative_to(root).as_posix())
            checked += 1
        finally:
            pe.close()
    report = {'ok': not missing, 'checked_pe_files': checked, 'missing_direct_imports': missing,
              'inactive_opengl_variants': inactive,
              'scope': 'Direct imports against payload/System32 on the build OS; runtime and other OS versions require smoke tests.'}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
