from pathlib import Path
import numpy as np
import pytest

from nexa.three_d.models import Bounds
from nexa.three_d.reference_import import import_mjcf


def test_import_preserves_world_units_and_joint_pose(tmp_path):
    pytest.importorskip("mujoco")
    # Tetrahedra make the authored transforms and metre-to-mm conversion measurable.
    source = tmp_path / "robot.xml"
    source.write_text('''<mujoco><asset><mesh name="tet" vertex="0 0 0  0.1 0 0  0 0.1 0  0 0 0.1"
        face="0 2 1 0 1 3 0 3 2 1 2 3"/></asset><worldbody>
        <body name="base"><geom type="mesh" mesh="tet" group="2"/>
        <body name="link" pos="0.2 0 0"><joint name="hinge" axis="0 1 0"/>
        <geom type="mesh" mesh="tet" group="2"/></body></body></worldbody></mujoco>''', encoding="utf-8")
    build = import_mjcf(source)
    assert len(build.parts) == 2
    bounds = Bounds.union([p.bounds for p in build.parts])
    assert sorted(bounds.size) == pytest.approx([100, 100, 300], abs=0.01)
    link = next(p for p in build.parts if p.id == "link")
    assert link.parent_id == "base"
    assert np.linalg.norm(link.joint_axis) == pytest.approx(1)
    for items in build.meshes.values():
        for mesh, _ in items:
            assert np.allclose(np.linalg.norm(mesh.normals, axis=1), 1)


def test_go2_reference_loads_when_available():
    pytest.importorskip("mujoco")
    source = Path(__file__).resolve().parents[1] / "data/reference_models/unitree_go2/go2.xml"
    if not source.exists():
        pytest.skip("Reference assets not downloaded")
    build = import_mjcf(source)
    assert len(build.parts) == 13
    assert sum(p.joint_axis is not None for p in build.parts) == 12
    size = Bounds.union([p.bounds for p in build.parts]).size
    assert 650 < size[2] < 800
    for items in build.meshes.values():
        for mesh, _ in items:
            assert np.allclose(np.linalg.norm(mesh.normals, axis=1), 1)
