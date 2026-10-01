"""The mirrored core is a closed, outward-facing triangulated sphere."""
import os
from collections import Counter
from math import sqrt

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

def test_mirror_mesh_is_closed_and_outward_facing():
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QJSEngine
    from nexa.utils.config import QML_DIR
    app = QGuiApplication.instance() or QGuiApplication([])
    engine = QJSEngine()
    source = (QML_DIR / 'MirrorMesh.js').read_text(encoding='utf-8')
    result = engine.evaluate(source.replace('.pragma library', ''))
    assert not result.isError(), result.toString()
    mesh = engine.evaluate('mesh').toVariant()
    vertices, faces = mesh['vertices'], mesh['faces']
    assert len(faces) == 1280
    assert all(abs(sqrt(sum(c*c for c in p))-1) < 1e-9 for p in vertices)
    edges = Counter()
    for a, b, c in faces:
        p, q, r = vertices[a], vertices[b], vertices[c]
        u, v = [q[i]-p[i] for i in range(3)], [r[i]-p[i] for i in range(3)]
        normal = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
        assert sum(normal[i]*p[i] for i in range(3)) > 0
        edges.update(tuple(sorted(e)) for e in ((a,b), (b,c), (c,a)))
    assert set(edges.values()) == {2}
    assert len(vertices) - len(edges) + len(faces) == 2
