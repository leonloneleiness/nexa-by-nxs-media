# NEXA / SENTINEL

The September 2026 UI refresh uses graphite surfaces, silver typography and a restrained ice-cyan accent. Amber indicates attention; muted red indicates errors or stop actions. All application surfaces share `nexa/ui/qml/Theme.js`; `TacStyle.js` provides compatibility names for existing workspace components.

## Navigation and behavior

- The left rail opens Home, 3D, Code Studio, conversation history, gestures and settings. It disappears below 760 px; the dock and header retain access to those functions.
- A persistent command field accepts Enter. Ctrl+K focuses it, or opens the history command field while Code/3D occupies the workspace. Ctrl+H retains the history shortcut.
- The orbital core uses actual mic/output levels and existing controller state. Its continuous animation stops during standby and in minimal-effects mode. Full/reduced modes cap canvas updates at 30/18 per second.
- Opening a Code/3D workspace retains the existing adaptive layout and compact copilot. Emergency stop remains available in the home dock, workspace copilot and floating compact mode.
- Settings use a left category list on wider windows, and a category selector with a single-column form below 700 px. Existing settings values and save behavior are preserved.
- Shared frames, inputs and buttons apply to Code, 3D creation/viewer/parts, export/build dialogs, gesture controls, HUD and desktop overlays. Embedded HTML previews retain the colors authored by the user.

## Running and verification

Launch the updated source application with `start_windows.bat`. An already-running application must be closed and reopened to reload QML. The existing packaged executable in `dist` has not been rebuilt by this UI change.

Run the focused regression suite:

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_ui_command_center.py tests/test_three_d_ui.py tests/test_code.py tests/test_code_gestures.py -q
```

Render the UI and verify command delivery, shortcuts, settings navigation and compact mode without opening a mic/camera or calling AI:

```powershell
.venv/Scripts/python.exe -X utf8 scripts/preview_sentinel.py
```

Previews and `verification.json` are written to `results/sentinel_redesign`. The preview uses temporary settings and code history, with sample conversation content; CPU/RAM telemetry is sampled locally. Sizes cover 1600×900, 1320×820, 900×820, 600×640 and compact 230×230. The previous QML files are backed up in `results/sentinel_redesign/before`.

The native 3D verification used Direct3D 11 on Windows, a temporary local UAV model with 26 parts / 113,580 triangles, and the existing `scripts/smoke_3d_viewer.py --window --assembled` test. `viewer_3d_windows.png` is the verified 3D render. Software-only offscreen renders do not verify 3D geometry, and FPS from offscreen previews should not be treated as a product benchmark. No live voice recognition, camera gesture recognition or cloud generation was exercised by the UI preview.
