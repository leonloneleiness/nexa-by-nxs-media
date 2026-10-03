"""Compare bundled NEXA bytecode with source, ignoring build-dependent filenames/line tables."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import CodeType

from PyInstaller.archive.readers import CArchiveReader

ROOT = Path(__file__).resolve().parents[1]


def signature(value):
    if isinstance(value, CodeType):
        return (value.co_code, tuple(signature(v) for v in value.co_consts), value.co_names,
                value.co_varnames, value.co_freevars, value.co_cellvars, value.co_argcount,
                value.co_posonlyargcount, value.co_kwonlyargcount, value.co_flags)
    if isinstance(value, tuple):
        return tuple(signature(v) for v in value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('exe', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    archive = CArchiveReader(str(args.exe))
    pyz = archive.open_embedded_archive(next(name for name in archive.toc if name.endswith('.pyz')))
    checked, mismatched = [], []
    for name in sorted(pyz.toc):
        if name != 'nexa' and not name.startswith('nexa.'):
            continue
        path = ROOT.joinpath(*name.split('.')).with_suffix('.py')
        if not path.exists():
            path = ROOT.joinpath(*name.split('.')) / '__init__.py'
        bundled = pyz.extract(name)
        if not path.exists() and bundled is None:
            continue  # implicit namespace package has no source/bytecode
        source = compile(path.read_text(encoding='utf-8-sig'), str(path), 'exec', dont_inherit=True)
        if signature(source) != signature(bundled):
            mismatched.append(name)
        checked.append(name)
    report = {'ok': bool(checked) and not mismatched, 'checked_modules': len(checked), 'mismatched': mismatched}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
