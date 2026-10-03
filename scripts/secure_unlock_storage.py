"""Apply the audited unlock ACL migration with elevation; never read secret bytes."""
from __future__ import annotations

import argparse
import ctypes
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    result = {'ok': False, 'checked': [], 'error': ''}
    try:
        if not ctypes.windll.shell32.IsUserAnAdmin():
            raise PermissionError('Administrator elevation is required to repair service storage.')
        from nexa.desktop.unlock import secure_secret_storage, secret_path
        import win32security
        secure_secret_storage()
        for path in (secret_path().parent, secret_path()):
            if not path.exists():
                continue
            sd = win32security.GetNamedSecurityInfo(str(path), win32security.SE_FILE_OBJECT,
                                                   win32security.DACL_SECURITY_INFORMATION)
            dacl = sd.GetSecurityDescriptorDacl()
            sids = [win32security.ConvertSidToStringSid(dacl.GetAce(i)[2]) for i in range(dacl.GetAceCount())]
            if set(sids) != {'S-1-5-18', 'S-1-5-32-544'}:
                raise RuntimeError('Unexpected principals in protected storage ACL.')
            result['checked'].append({'path': str(path), 'allowed_sids': sids})
        result['ok'] = True
    except Exception as exc:
        result['error'] = f'{type(exc).__name__}: {exc}'
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
