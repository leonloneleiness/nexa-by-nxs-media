"""Load only the bundled library. ctypes releases the GIL during computation."""
import ctypes
import os
from pathlib import Path
import sys
import numpy as np

_lib = None
if os.environ.get('NEXA_DISABLE_NATIVE') != '1':
    filename = 'nexa_geometry.dll' if sys.platform == 'win32' else 'libnexa_geometry.dylib' if sys.platform == 'darwin' else 'libnexa_geometry.so'
    try:
        candidate = ctypes.CDLL(str(Path(__file__).resolve().parent / filename))
        candidate.nexa_geometry_abi.restype = ctypes.c_int
        if candidate.nexa_geometry_abi() == 1:
            pointer = ctypes.POINTER(ctypes.c_double)
            candidate.nexa_frames.argtypes = [pointer, ctypes.c_size_t, pointer, pointer, pointer, pointer]
            candidate.nexa_frames.restype = ctypes.c_int
            _lib = candidate
    except (OSError, AttributeError):
        pass


def available():
    return _lib is not None


def frames(path, up):
    if _lib is None:
        return None
    p = np.ascontiguousarray(path, dtype=np.float64)
    u = np.ascontiguousarray(up, dtype=np.float64)
    if p.ndim != 2 or p.shape[1] != 3 or len(p) < 2 or u.shape != (3,):
        raise ValueError('Expected path (N, 3), N >= 2 and up (3,)')
    if not np.isfinite(p).all() or not np.isfinite(u).all():
        raise ValueError('Geometry coordinates must be finite')
    t, n, b = (np.empty_like(p) for _ in range(3))
    ptr = lambda a: a.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
    if _lib.nexa_frames(ptr(p), len(p), ptr(u), ptr(t), ptr(n), ptr(b)):
        raise RuntimeError('Native geometry rejected input')
    return t, n, b
