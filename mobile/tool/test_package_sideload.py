import plistlib
from pathlib import Path
import tempfile
import unittest
import zipfile
from package_sideload import package


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / 'Runner.app'
        self.app.mkdir()
        self.info = {'CFBundleSupportedPlatforms': ['iPhoneOS'],
                     'CFBundleExecutable': 'Runner', 'CFBundleIdentifier': 'test.nexa'}
        self.write_info()
        (self.app / 'Runner').write_bytes(b'\xcf\xfa\xed\xfe' + b'test fixture')
        framework = self.app / 'Frameworks/App.framework'
        framework.mkdir(parents=True)
        (framework / 'App').write_bytes(b'fixture')

    def write_info(self):
        (self.app / 'Info.plist').write_bytes(plistlib.dumps(self.info))

    def test_payload_layout_and_manifest(self):
        output = self.root / 'test.ipa'
        result = package(self.app, output)
        self.assertTrue(result['requires_resigning'])
        self.assertFalse(result['device_tested'])
        with zipfile.ZipFile(output) as archive:
            self.assertIn('Payload/Runner.app/Runner', archive.namelist())
            self.assertIsNone(archive.testzip())
        self.assertTrue(output.with_suffix('.ipa.sha256').exists())

    def test_rejects_simulator(self):
        self.info['CFBundleSupportedPlatforms'] = ['iPhoneSimulator']
        self.write_info()
        with self.assertRaises(ValueError):
            package(self.app, self.root / 'test.ipa')

    def test_rejects_uncompiled_source(self):
        (self.app / 'Runner').write_bytes(b'not compiled')
        with self.assertRaises(ValueError):
            package(self.app, self.root / 'test.ipa')

    def test_rejects_missing_framework(self):
        (self.app / 'Frameworks/App.framework/App').unlink()
        with self.assertRaises(ValueError):
            package(self.app, self.root / 'test.ipa')


if __name__ == '__main__':
    unittest.main()
