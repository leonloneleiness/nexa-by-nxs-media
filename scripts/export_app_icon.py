"""Export the native SVG brand asset to PNG and a multi-resolution Windows ICO."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PIL import Image

root = Path(__file__).resolve().parents[1]
brand = root / 'assets/branding'
app = QGuiApplication([])
renderer = QSvgRenderer(str(brand / 'nexa-icon.svg'))
assert renderer.isValid()
canvas = QImage(1024, 1024, QImage.Format.Format_ARGB32)
canvas.fill(Qt.GlobalColor.transparent)
painter = QPainter(canvas)
renderer.render(painter)
painter.end()
assert canvas.save(str(brand / 'nexa-icon.png'))
with Image.open(brand / 'nexa-icon.png') as image:
    image.save(brand / 'nexa-icon.ico', sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
with Image.open(brand / 'nexa-icon.ico') as icon:
    assert len(icon.ico.sizes()) == 7
print('Exported SVG to PNG and seven Windows ICO sizes.')
