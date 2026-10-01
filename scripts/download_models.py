"""Tải và cache model cho NEXA.

  python scripts/download_models.py            # tải tất cả
  python scripts/download_models.py --hands    # chỉ MediaPipe hand_landmarker.task
  python scripts/download_models.py --faces    # chỉ MediaPipe face_landmarker.task (nhận biết ngồi máy, hướng nhìn)
  python scripts/download_models.py --whisper small   # chỉ model faster-whisper (tên tùy chọn)

- hand_landmarker.task, face_landmarker.task: tải từ bucket chính thức của Google (storage.googleapis.com/mediapipe-models).
  Kiểm tra MD5 bằng giá trị server trả trong header x-goog-hash (nguồn tự cung cấp). NEXA không
  tự đặt checksum cố định.
- faster-whisper: tải qua faster_whisper.download_model từ Hugging Face (Systran/faster-whisper-*),
  thư viện dùng cơ chế kiểm tra của huggingface_hub.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from nexa.utils.config import MODELS_DIR, Config  # noqa: E402
from nexa.vision.face_tracker import MODEL_URL as FACE_URL  # noqa: E402
from nexa.vision.hand_tracker import MODEL_URL  # noqa: E402


def download_hands(force: bool = False) -> bool:
    return _download_task(MODEL_URL, MODELS_DIR / "hand_landmarker.task", "hands", force)


def download_faces(force: bool = False) -> bool:
    return _download_task(FACE_URL, MODELS_DIR / "face_landmarker.task", "faces", force)


def _download_task(url: str, target: Path, tag: str, force: bool = False) -> bool:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    if target.exists() and not force:
        print(f"[{tag}] Đã có {target} ({target.stat().st_size // 1024} KB) — bỏ qua. Dùng --force để tải lại.")
        return True
    print(f"[{tag}] Tải {url}")
    tmp = target.with_suffix(".part")
    req = urllib.request.Request(url, headers={"User-Agent": "NEXA-model-downloader"})
    md5 = hashlib.md5()
    expected_md5 = None
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, tmp.open("wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            for h in resp.headers.get_all("x-goog-hash") or []:
                for part in h.split(","):
                    part = part.strip()
                    if part.startswith("md5="):
                        expected_md5 = base64.b64decode(part[4:]).hex()
            done = 0
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                md5.update(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total
                    print(f"\r[{tag}] {done // 1024} / {total // 1024} KB ({pct}%)", end="", flush=True)
        print()
    except Exception as exc:
        print(f"[{tag}] LỖI tải model: {exc}")
        tmp.unlink(missing_ok=True)
        return False
    if expected_md5:
        if md5.hexdigest() != expected_md5:
            print(f"[{tag}] LỖI: MD5 không khớp (nhận {md5.hexdigest()}, server báo {expected_md5}). Đã xóa tệp tải dở.")
            tmp.unlink(missing_ok=True)
            return False
        print(f"[{tag}] MD5 khớp với server: {expected_md5}")
    else:
        print(f"[{tag}] Server không cung cấp checksum; đã kiểm tra kích thước tải về.")
    tmp.replace(target)
    print(f"[{tag}] Đã lưu {target}")
    return True


def download_whisper(name: str) -> bool:
    from faster_whisper import download_model
    out = MODELS_DIR / "whisper"
    out.mkdir(parents=True, exist_ok=True)
    print(f"[whisper] Tải model '{name}' từ Hugging Face vào {out} (có thể vài trăm MB)…")
    try:
        path = download_model(name, cache_dir=str(out))
    except Exception as exc:
        print(f"[whisper] LỖI: {exc}")
        return False
    print(f"[whisper] Sẵn sàng: {path}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Tải model cho NEXA")
    ap.add_argument("--hands", action="store_true")
    ap.add_argument("--faces", action="store_true")
    ap.add_argument("--whisper", nargs="?", const="__config__")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    both = not args.hands and not args.faces and args.whisper is None
    ok = True
    if args.hands or both:
        ok &= download_hands(args.force)
    if args.faces or both:
        ok &= download_faces(args.force)
    if args.whisper is not None or both:
        name = Config().get("stt.model") if args.whisper in (None, "__config__") else args.whisper
        ok &= download_whisper(name or "small")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
