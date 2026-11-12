"""Native/reference parity, degenerate paths, and fallback routing."""
import numpy as np
import pytest
from nexa.native import geometry
from nexa.three_d.geometry import kernel


@pytest.mark.skipif(not geometry.available(), reason='Build native kernel first')
@pytest.mark.parametrize('count', [2, 3, 100, 10000])
def test_native_matches_reference(count):
    path = np.random.default_rng(42).normal(size=(count, 3)).cumsum(axis=0)
    if count > 3:
        path[2] = path[1]
    for up in [(0, 0, 1), (1, 0, 0), (0, 0, 0)]:
        actual = geometry.frames(path, up)
        expected = kernel._rotation_minimizing_frames_python(path, up)
        for a, b in zip(actual, expected):
            np.testing.assert_allclose(a, b, atol=1e-9, rtol=1e-9)


@pytest.mark.skipif(not geometry.available(), reason='Build native kernel first')
def test_zero_and_noncontiguous_paths():
    for path in [np.zeros((8, 3)), np.arange(90.).reshape(30, 3)[::2]]:
        for a, b in zip(geometry.frames(path, (0, 0, 1)),
                        kernel._rotation_minimizing_frames_python(path)):
            np.testing.assert_allclose(a, b, atol=1e-9, rtol=1e-9)


def test_missing_library_falls_back(monkeypatch):
    monkeypatch.setattr(geometry, '_lib', None)
    path = np.array([[0., 0, 0], [1, 0, 0], [1, 1, 0]])
    for a, b in zip(kernel.rotation_minimizing_frames(path),
                    kernel._rotation_minimizing_frames_python(path)):
        np.testing.assert_array_equal(a, b)


@pytest.mark.skipif(not geometry.available(), reason='Build native kernel first')
@pytest.mark.parametrize('path', [np.zeros((1, 3)), np.zeros((3, 2)), np.full((2, 3), np.nan)])
def test_invalid_buffers_are_rejected(path):
    with pytest.raises(ValueError):
        geometry.frames(path, (0, 0, 1))
