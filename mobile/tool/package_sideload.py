"""Package a compiled iPhone .app for re-signing, never a simulator bundle.

This does not compile or sign an application. Run after Flutter's macOS build.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import stat
import tempfile
import zipfile


def package(app: Path, output: Path) -> dict:
    app = app.resolve()
    if not app.is_dir() or app.suffix != '.app':
        raise ValueError('Expected a compiled .app directory')
    info = plistlib.loads((app / 'Info.plist').read_bytes())
    if 'iPhoneOS' not in info.get('CFBundleSupportedPlatforms', []):
        raise ValueError('Only an iPhoneOS device build can be packaged')
    executable = info.get('CFBundleExecutable', '')
    if not executable or Path(executable).name != executable:
        raise ValueError('Invalid bundle executable')
    binary = app / executable
    if not binary.is_file() or binary.read_bytes()[:4] not in (
            b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'):
        raise ValueError('Missing Mach-O executable')
    if not (app / 'Frameworks/App.framework/App').is_file():
        raise ValueError('Missing compiled Flutter application framework')
    paths = sorted(app.rglob('*'))
    for path in paths:
        if path.is_symlink() and not path.resolve().is_relative_to(app):
            raise ValueError('Bundle symlink escapes application')
    output = output.resolve()
    if output.is_relative_to(app):
        raise ValueError('Output must be outside application')
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=output.parent, suffix='.tmp')
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in paths:
                name = f'Payload/{app.name}/{path.relative_to(app).as_posix()}'
                if path.is_symlink():
                    entry = zipfile.ZipInfo(name)
                    entry.create_system = 3
                    entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(entry, os.readlink(path).encode())
                elif path.is_file():
                    archive.write(path, name)
        with zipfile.ZipFile(tmp) as archive:
            if archive.testzip() is not None:
                raise ValueError('IPA checksum verification failed')
        os.replace(tmp, output)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    with output.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    report = {'bundle_id': info.get('CFBundleIdentifier'),
              'version': info.get('CFBundleShortVersionString'),
              'build': info.get('CFBundleVersion'), 'sha256': digest,
              'artifact': output.name, 'requires_resigning': True,
              'device_tested': False, 'app_store_uploadable': False}
    output.with_suffix('.ipa.sha256').write_text(f'{digest}  {output.name}\n')
    output.with_suffix('.ipa.json').write_text(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, default=Path('build/ios/iphoneos/Runner.app'))
    parser.add_argument('--output', type=Path, default=Path('build/sideload/NEXA-unsigned.ipa'))
    args = parser.parse_args()
    print(json.dumps(package(args.app, args.output), indent=2))
