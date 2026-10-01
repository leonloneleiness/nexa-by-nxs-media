"""Tạo bộ dữ liệu lệnh nói TỔNG HỢP bằng giọng đọc tiếng Việt (để phát triển/kiểm tra nhanh thí nghiệm ASR).

    .venv\\Scripts\\python scripts\\asr_synth.py                    # giọng WinRT offline (Microsoft An)
    .venv\\Scripts\\python scripts\\asr_synth.py --edge             # thêm giọng Edge HoaiMy + NamMinh (cần Internet)
    .venv\\Scripts\\python scripts\\asr_synth.py --rates 0,20       # thêm tốc độ đọc nhanh hơn 20%

Kết quả: data/asr_synth/<giọng>/<id>.wav (16 kHz mono) + data/asr_synth/manifest.jsonl.
CHẠY RIÊNG với asr_benchmark.py: tổng hợp WinRT và Whisper trong cùng một tiến trình từng làm Python bị crash.
Giọng TTS không thay được giọng người thật — xem docs/research_asr.md.
"""
from __future__ import annotations

import argparse
import sys
from math import gcd
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexa.research.corpus import SAMPLE_RATE, append_jsonl, write_wav  # noqa: E402
from nexa.research.templates import build_items  # noqa: E402


def to_16k(x: np.ndarray, sr: int) -> np.ndarray:
    if sr == SAMPLE_RATE:
        return x.astype(np.float32)
    from scipy.signal import resample_poly
    g = gcd(sr, SAMPLE_RATE)
    return resample_poly(x, SAMPLE_RATE // g, sr // g).astype(np.float32)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "data" / "asr_synth"))
    ap.add_argument("--edge", action="store_true", help="thêm giọng Edge (online)")
    ap.add_argument("--rates", default="0", help="tốc độ đọc, phần trăm, cách nhau dấu phẩy (vd 0,20)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--limit", type=int, default=0, help="chỉ tạo N câu đầu (thử nhanh)")
    args = ap.parse_args()

    from nexa.audio.tts import EdgeBackend, WinRTBackend, trim_silence
    voices: list[tuple[str, object]] = []
    rates = [int(r) for r in args.rates.split(",") if r.strip()]
    for rate in rates:
        winrt = WinRTBackend("", rate)
        ok, why = winrt.available()
        if ok:
            voices.append((f"winrt-an-r{rate}", winrt))
        else:
            print(f"Bỏ qua WinRT: {why}")
        if args.edge:
            for v in ("vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"):
                voices.append((f"edge-{v.split('-')[2].replace('Neural', '').lower()}-r{rate}", EdgeBackend(v, rate)))
    if not voices:
        print("Không có giọng đọc nào dùng được.")
        return 1

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / "manifest.jsonl"
    manifest.unlink(missing_ok=True)
    items = build_items(seed=args.seed)
    if args.limit:
        items = items[:args.limit]
    pad = np.zeros(int(0.3 * SAMPLE_RATE), np.float32)       # giống pre-roll/đuôi im lặng của VAD thật
    n = 0
    for vname, backend in voices:
        folder = out / vname
        folder.mkdir(exist_ok=True)
        for it in items:
            try:
                audio, sr = backend.synth(it["spoken"])
            except Exception as exc:
                print(f"  lỗi {vname} {it['id']}: {exc}")
                continue
            audio = trim_silence(to_16k(audio, sr), SAMPLE_RATE, lead_s=0.02, tail_s=0.05)
            wav = folder / f"{it['id']}.wav"
            write_wav(wav, np.concatenate([pad, audio, pad]))
            append_jsonl(manifest, {**it, "id": f"{vname}/{it['id']}", "speaker": vname,
                                    "audio": wav.relative_to(out).as_posix()})
            n += 1
        print(f"{vname}: xong")
    print(f"Đã tạo {n} câu → {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
