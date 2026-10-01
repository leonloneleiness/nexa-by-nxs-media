"""Deterministic offscreen animation preview of the actual QML living core."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['QT_QUICK_BACKEND']='software'
os.environ['QT_QPA_FONTDIR']='C:/Windows/Fonts'
import sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication,QColor,QFont
from PySide6.QtQuick import QQuickView
from PIL import Image
app=QGuiApplication([])
app.setFont(QFont("Segoe UI",10))
view=QQuickView()
view.setColor(QColor('#071925'))
view.setResizeMode(QQuickView.SizeRootObjectToView)
view.setSource(QUrl.fromLocalFile(str(ROOT/'nexa/ui/qml/TacticalCore.qml')))
assert view.rootObject(),view.errors()
view.resize(640,640)
core=view.rootObject()
view.show()
until=time.monotonic()+0.3
while time.monotonic()<until: app.processEvents();time.sleep(0.002)
assert core.property('phase')>0, 'Live frame animation must advance in standby'
core.setProperty('effects','minimal')
frozen=core.property('phase')
until=time.monotonic()+0.1
while time.monotonic()<until: app.processEvents();time.sleep(0.002)
assert core.property('phase')==frozen, 'Minimal effects must stop motion' 
out=ROOT/'results/mirror_hud'
frames=[]
for i in range(84):
    core.setProperty('phase',i/10)
    core.setProperty('orbitPhase',i/10*0.18)
    until=time.monotonic()+0.035
    while time.monotonic()<until: app.processEvents();time.sleep(0.002)
    img=view.grabWindow().convertToFormat(__import__('PySide6.QtGui',fromlist=['QImage']).QImage.Format_RGBA8888)
    frame=Image.frombytes('RGBA',(img.width(),img.height()),bytes(img.bits())).convert('RGB')
    frames.append(frame)
    if i in (0,28,56): frame.save(out/f'breathing_{i}.png')
frames[0].save(out/'living_core.gif',save_all=True,append_images=frames[1:],duration=100,loop=0,optimize=False)
assert frames[0].tobytes()!=frames[28].tobytes()
print('Rendered 84 QML frames: breathing, independent circular drift, and mirror flutter.')
view.close()
