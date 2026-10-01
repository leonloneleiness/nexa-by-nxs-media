"""Tạo các âm thanh hiệu ứng procedural của NEXA vào assets/sounds/*.wav."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexa.audio import sfx  # noqa: E402


def main() -> int:
    out = ROOT / "assets" / "sounds"
    out.mkdir(parents=True, exist_ok=True)
    for name in ("wake", "sleep", "confirm", "error", "listen"):
        path = out / f"{name}.wav"
        sfx.write_wav(path, sfx.synth(name))
        print(f"Đã tạo {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
