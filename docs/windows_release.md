# Windows installer

The shared-key Windows release is built from the current working tree, including
uncommitted fixes. It is a single Inno Setup installer, not a single-file runtime.
It installs per user under `%LOCALAPPDATA%\Programs\NEXA`, includes Python and
native dependencies, and provides Desktop/Start Menu shortcuts and an uninstaller.
No elevation is requested by the installer.

## Build

Run from the repository root using the existing Python 3.11 environment:

```powershell
.venv\Scripts\python.exe scripts\export_app_icon.py
.venv\Scripts\python.exe scripts\build_exe.py --dist release\windows-portable
.venv\Scripts\python.exe -m PyInstaller --noconfirm --onefile --console --name NexaBridge --distpath release\bridge --workpath build\bridge --specpath build\bridge --paths . browser_bridge\native_host.py
New-Item -ItemType Directory -Force release\windows-portable\NEXA\browser_bridge
Copy-Item release\bridge\NexaBridge.exe release\windows-portable\NEXA\browser_bridge\NexaBridge.exe
.venv\Scripts\python.exe scripts\prepare_windows_release.py --include-shared-api
.venv\Scripts\python.exe scripts\verify_frozen_sources.py release\windows-portable\NEXA\NEXA.exe --report release\windows-source-check.json
& scratch\packaging-tools\InnoSetup\ISCC.exe /Qp installer\NEXA.iss
```

Use an installed Inno Setup 6 compiler if the local scratch compiler is absent.
Output: `release/NEXA-Setup.exe`. Only publish the completed installer, never the
developer source tree or a partially written compiler output.

Brand assets live in `assets/branding`: the editable SVG, transparent PNG, and
Windows ICO (16, 24, 32, 48, 64, 128, 256 px). The N monogram uses teal, orange,
violet and navy from NXS MEDIA's reference, with a rounded puzzle connector.
The application window, EXE, shortcuts, and installer use the same icon.

## Included configuration and models

The explicit `--include-shared-api` option copies an allowlist of configured API
values into the release `.env` without displaying them. These credentials are
recoverable by recipients; the distribution shares the publisher's API quota.
This is the shared-key distribution requested by the owner, not a server proxy.
Private user settings, conversation history, logs, and unlock credentials are not
copied. Existing `.env` is preserved on reinstall; model and application files update.

Both currently cached Whisper CPU/GPU models and the hand/face landmark models are
included. Changing to a different speech model may require an additional download.
Gemini, online TTS, and cloud generation still require Internet and available quota.
The optional Browser Bridge native host is bundled as `NexaBridge.exe`; advanced
browser integration still needs installation of the browser extension and native
host registration. Running generated programs requires their language runtimes
or compilers; this installer does not include every development toolchain.

## Verification

The application build runs `--nexa-check-install` to verify frozen modules,
template categories, and QML resources. `verify_frozen_sources.py` checks bytecode
against the working tree. `check_release_api.py` makes one minimal live Gemini
request without logging credentials.

For a disposable installation into `scratch/release-install-test`, run
`scripts/smoke_windows_release.py` to check installed modules, native-host origin
validation/EOF, UI startup/shutdown, screenshot rendering, and offline speech model
loading. It disables sleep/power remapping only in the disposable test configuration
and isolates user data; it does not alter release defaults. Reports live in
`release/verification`. A same-machine test is not a clean-machine certification.
