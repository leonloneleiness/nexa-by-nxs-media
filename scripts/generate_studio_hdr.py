"""Sinh assets/3d/studio.hdr — môi trường ánh sáng studio (equirectangular, Radiance RGBE, RLE) cho viewer 3D.

Nền tối kiểu NEXA + softbox lớn trên đầu, dải đèn chính trước-trái, đèn viền sau-phải, sàn tối: kim loại PBR có
phản xạ đẹp mà không cần tải ảnh HDR bên ngoài.
    .venv\\Scripts\\python scripts\\generate_studio_hdr.py
"""
from __future__ import annotations

import math
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def studio(width: int = 1024, height: int = 512) -> np.ndarray:
    v, u = np.mgrid[0:height, 0:width]
    lon = (u + 0.5) / width * 2 * math.pi - math.pi          # −π..π
    lat = math.pi / 2 - (v + 0.5) / height * math.pi         # π/2 (trên) .. −π/2 (dưới)
    dx, dy, dz = np.cos(lat) * np.sin(lon), np.sin(lat), np.cos(lat) * np.cos(lon)
    img = np.zeros((height, width, 3))
    sky = np.clip(dy, 0, 1)
    img += (np.array([0.018, 0.024, 0.04]) * (0.4 + 0.6 * sky)[..., None])
    img[dy < 0] = np.array([0.012, 0.013, 0.016]) * (1 + dy[dy < 0, None])            # sàn tối

    def softbox(direction, size, power, color=(1.0, 1.0, 1.0), soft=0.35):
        d = np.asarray(direction, float)
        d /= np.linalg.norm(d)
        cosang = dx * d[0] + dy * d[1] + dz * d[2]
        ang = np.arccos(np.clip(cosang, -1, 1))
        w = np.clip(1 - (ang - size) / (size * soft), 0, 1) * (ang < size * (1 + soft))
        return w[..., None] * np.asarray(color) * power

    img += softbox((0.0, 1.0, 0.1), 0.55, 5.0, (1.0, 0.98, 0.95))        # softbox trên đầu
    img += softbox((-0.7, 0.45, 0.6), 0.22, 7.0, (1.0, 0.97, 0.92))      # đèn chính trước-trái
    img += softbox((0.8, 0.3, -0.5), 0.16, 4.0, (0.75, 0.9, 1.0))        # đèn viền sau-phải (hơi xanh)
    img += softbox((0.9, 0.15, 0.4), 0.12, 1.5, (0.4, 0.85, 1.0))        # điểm nhấn cyan NEXA
    return img.astype(np.float32)


def to_rgbe(img: np.ndarray) -> np.ndarray:
    m = img.max(axis=2)
    out = np.zeros(img.shape[:2] + (4,), np.uint8)
    nz = m > 1e-32
    mant, exp = np.frexp(m[nz])
    scale = mant * 256.0 / m[nz]
    out[nz, 0:3] = np.clip(img[nz] * scale[:, None], 0, 255).astype(np.uint8)
    out[nz, 3] = (exp + 128).astype(np.uint8)
    return out


def write_hdr(path: Path, img: np.ndarray) -> None:
    h, w, _ = img.shape
    rgbe = to_rgbe(img)
    buf = bytearray(f"#?RADIANCE\nFORMAT=32-bit_rle_rgbe\n\n-Y {h} +X {w}\n".encode("ascii"))
    for y in range(h):
        buf += struct.pack("BBBB", 2, 2, (w >> 8) & 0xFF, w & 0xFF)       # RLE kiểu mới
        for c in range(4):
            row = rgbe[y, :, c]
            i = 0
            while i < w:
                # gói lặp khi ≥ 4 byte giống nhau, không thì gói thường ≤ 128 byte
                run = 1
                while i + run < w and run < 127 and row[i + run] == row[i]:
                    run += 1
                if run >= 4:
                    buf += bytes([128 + run, int(row[i])])
                    i += run
                    continue
                j = i
                while j < w and j - i < 128:
                    r2 = 1
                    while j + r2 < w and r2 < 4 and row[j + r2] == row[j]:
                        r2 += 1
                    if r2 >= 4:
                        break
                    j += 1
                buf += bytes([j - i]) + row[i:j].tobytes()
                i = j
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(buf))


def main() -> int:
    out = ROOT / "assets" / "3d" / "studio.hdr"
    write_hdr(out, studio())
    print(f"Đã ghi {out} ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
