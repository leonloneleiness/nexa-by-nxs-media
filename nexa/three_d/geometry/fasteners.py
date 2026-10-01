"""Nominal socket-head geometry shared by assemblies. Smooth shanks are not thread CAD.

ISO 4762 nominal envelope uses the project's ISO_METRIC table. Unsupported diameters
remain explicitly custom geometry for legacy templates, never catalogue parts.
"""
from __future__ import annotations

import math

from nexa.three_d.geometry import kernel as K, profiles as P
from nexa.three_d.spec import iso_row


def socket_dimensions(diameter: float) -> dict:
    if not math.isfinite(diameter) or diameter <= 0:
        raise ValueError("Đường kính vít phải dương và hữu hạn.")
    row = iso_row(diameter)
    # iso_row rounds to 0.1 mm: do not classify e.g. 3.04 as nominal M3.
    if row and abs(diameter - round(diameter, 1)) < 1e-9:
        return {"diameter": diameter, "head_diameter": row["dk"], "head_height": row["kc"],
                "socket_af": row["sk"], "pitch": row["p"], "standard": "ISO 4762 nominal"}
    return {"diameter": diameter, "head_diameter": 1.75 * diameter + 0.25,
            "head_height": diameter, "socket_af": 0.8 * diameter, "pitch": None, "standard": "custom"}


def socket_screw(diameter: float, length: float) -> K.Solid:
    """Head bearing plane z=0; smooth shank -length..0, exact nominal head envelope.

Socket depth and edge chamfers are illustrative; not a manufacturing drawing.
"""
    if not math.isfinite(length) or length <= 0:
        raise ValueError("Chiều dài vít phải dương và hữu hạn.")
    dims = socket_dimensions(diameter)
    radius, height = dims["head_diameter"] / 2, dims["head_height"]
    bevel = min(0.08 * diameter, height / 5)
    head = K.revolve([(0, 0), (radius, 0), (radius, height - bevel),
                      (radius - bevel, height), (0, height)], segments=48)
    socket = K.extrude(P.circle(dims["socket_af"] / (2 * math.cos(math.pi / 6)), 6), height).translate(0, 0, height * 0.4)
    tip = min(0.12 * diameter, length / 4)
    shank = K.revolve([(0, -length), (diameter / 2 - tip, -length), (diameter / 2, -length + tip),
                       (diameter / 2, 0.01), (0, 0.01)], segments=32)
    return (head - socket) + shank


def through_holes(points, diameter: float, z_min: float, z_max: float) -> K.Solid:
    """A single shared cutter for aligned mating plates. Diameter is specified by caller."""
    if not all(math.isfinite(v) for v in (diameter, z_min, z_max)) or diameter <= 0 or z_max <= z_min:
        raise ValueError("Thông số lỗ xuyên không hợp lệ.")
    return K.Solid.union_all([K.cylinder(diameter / 2, z_max - z_min + 0.02, segments=32)
                              .translate(float(x), float(y), z_min - 0.01) for x, y in points])
