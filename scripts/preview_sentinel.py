"""Render Sentinel UI and exercise navigation without mic, camera or cloud calls."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace as NS

os.environ['QT_QPA_PLATFORM'] = 'offscreen:size=1920x1200'
os.environ['QT_QUICK_BACKEND'] = 'software'
os.environ['QT_QUICK_CONTROLS_STYLE'] = 'Basic'
os.environ['QT_QPA_FONTDIR'] = 'C:/Windows/Fonts'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QObject, Property, Signal, Slot, Qt, QMetaObject, Q_ARG
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest
from nexa.ui.bridge import UiBridge
from nexa.ui.code_bridge import CodeBridge
from nexa.code.service import CodeService
from nexa.code.models import CodeFile, CodeResult
from nexa.utils.config import Config, QML_DIR


class PreviewBridge(UiBridge):
    @Slot(result='QVariantList')
    def cameras(self): return []
    @Slot(result='QVariantList')
    def inputDevices(self): return ['Microphone (preview)']
    @Slot(result='QVariantList')
    def outputDevices(self): return ['Speakers (preview)']
    @Slot(result=str)
    def unlockServiceStatus(self): return '{"installed":false,"running":false}'


class Preview3D(QObject):
    changed = Signal()
    toast = Signal(str, bool)
    viewerOpen = Property(bool, lambda self: False, notify=changed)
    workspace = Property(bool, lambda self: False, lambda self, v: None, notify=changed)
    activeJob = Property('QVariantMap', lambda self: {}, notify=changed)
    providerStatus = Property('QVariantMap', lambda self: {}, notify=changed)


def main():
    out = ROOT / 'results/sentinel_redesign'
    out.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication([])
    app.setFont(QFont('Segoe UI', 10))
    temp = tempfile.TemporaryDirectory(prefix='nexa_sentinel_')
    d = Path(temp.name)
    cfg = Config(settings_path=d/'settings.yaml', gestures_path=d/'gestures.yaml', load_env=False)
    received = []
    ctrl = NS(config=cfg, gestures=NS(running=False, set_preview=lambda v: None),
              provider=NS(last_latency_ms=840.0),
              tts=NS(describe_backends=lambda: [], winrt_voices=lambda: []),
              monitors=NS(describe=lambda: []), media_targets=lambda: [],
              audio=NS(clap=NS(stats=lambda: {}, set_test=lambda v: None)),
              attention=NS(status=lambda: {}),
              submit_text=lambda text, source: received.append(text))
    ctrl.code = CodeService(None, history_dir=d/'code')
    ui = PreviewBridge(ctrl)
    code = CodeBridge(ctrl)
    f3 = Preview3D()
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda ws: warnings.extend(w.toString() for w in ws))
    for name, obj in [('nexa', ui), ('nexa3d', f3), ('nexaCode', code)]:
        engine.rootContext().setContextProperty(name, obj)
    engine.load(str(QML_DIR/'Main.qml'))
    assert engine.rootObjects(), warnings
    win = engine.rootObjects()[0]

    def pump(seconds=0.4):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            app.processEvents(); time.sleep(0.01)

    def capture(name, width=1320, height=820):
        win.setWidth(width); win.setHeight(height); pump()
        assert win.grabWindow().save(str(out/f'{name}.png'))

    ui._handle('status', {'mic': {'ok': True}, 'ai': {'ok': True},
                         'stt': {'ready': True, 'model': 'small'},
                         'tts': {'backend': 'edge'}, 'autonomy': 'standard'})
    ui._handle('state', {'state': 'STANDBY', 'label': 'Sẵn sàng', 'detail': ''})
    capture('home')
    # Verify both shortcut and Enter route to the existing controller exactly once.
    win.requestActivate(); pump()
    QTest.keyClick(win, Qt.Key_K, Qt.ControlModifier); pump()
    command = win.findChild(QQuickItem, 'commandInput')
    assert command.findChild(QQuickItem, 'sentinelInputField').hasActiveFocus()
    command.setProperty('text', '  mở Notepad  ')
    QTest.keyClick(win, Qt.Key_Return); pump()
    assert received == ['mở Notepad'] and command.property('text') == ''
    ui._handle('user_message', {'text': 'Mở Notepad rồi đặt âm lượng 30 phần trăm', 'source': 'voice'})
    for step, status, title in [('s1', 'done', 'Mở ứng dụng'), ('s2', 'running', 'Đặt âm lượng 30%')]:
        ui._handle('task', {'task_id': 'preview', 'step_id': step, 'tool': step, 'title': title,
                            'status': status, 'message': title, 'source': 'voice'})
    ui._handle('assistant_message', {'text': 'Dạ, em đã mở Notepad và đang chỉnh âm lượng về 30% ạ.'})
    ui._handle('state', {'state': 'LISTENING', 'label': 'Đang nghe', 'detail': ''})
    pump(1.4)
    capture('main')
    capture('wide', 1600, 900)
    capture('narrow', 900, 820)
    capture('minimum', 600, 640)
    win.setWidth(1320); win.setHeight(820)
    settings = win.findChild(QObject, 'settingsPopup')
    QMetaObject.invokeMethod(settings, 'open'); pump()
    capture('settings')
    nav = win.findChild(QQuickItem, 'settingsNavigation')
    assert nav is not None
    for index in range(9):
        nav.setProperty('currentIndex', index); pump(0.1)
    capture('settings_3d')
    capture('settings_minimum', 600, 640)
    QMetaObject.invokeMethod(settings, 'close'); pump()
    win.setWidth(1320); win.setHeight(820)
    gesture = win.findChild(QQuickItem, 'gesturePanel')
    gesture.setVisible(True); capture('gestures'); gesture.setVisible(False)

    result = CodeResult('sentinel-preview', 'Tạo hàm tính doanh thu', 'Phân tích doanh thu', 'python',
                        'Tổng hợp doanh thu theo tháng từ dữ liệu CSV.',
                        [CodeFile('revenue.py', 'python', 'from collections import defaultdict\n\ndef monthly_revenue(rows):\n    totals = defaultdict(float)\n    for row in rows:\n        totals[row["date"][:7]] += float(row["amount"])\n    return dict(sorted(totals.items()))\n')])
    ctrl.code._publish(result, announce=False)
    code.post('code_result', {'id': result.id})
    code.openPanel(); pump()
    # Auto-maximize is expected on opening a workspace; normalize for reproducible previews.
    win.showNormal(); capture('code_workspace', 1600, 900)
    QTest.keyClick(win, Qt.Key_K, Qt.ControlModifier); pump()
    assert win.property('historyOpen')
    capture('code_history', 1600, 900)
    win.setProperty('historyOpen', False)
    code.closePanel(); pump()
    QMetaObject.invokeMethod(win, 'enterCompact', Q_ARG('QVariant', True)); pump()
    assert ui.compact
    assert win.grabWindow().save(str(out/'compact.png'))
    QMetaObject.invokeMethod(win, 'enterCompact', Q_ARG('QVariant', False)); pump()
    assert not ui.compact
    win.close(); win.deleteLater(); app.processEvents()
    report = {'warnings': warnings, 'command_delivery': received,
              'settings_sections': 9, 'sizes': ['1600x900', '1320x820', '900x820', '600x640', '230x230'],
              'render_backend': 'Qt Quick software, offscreen'}
    (out/'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))
    assert not warnings, warnings
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
