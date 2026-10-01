"""Bộ đo chuẩn nhận dạng lệnh nói lẫn Việt–Anh (thí nghiệm của docs/research_asr.md).

    .venv\\Scripts\\python scripts\\asr_benchmark.py --manifest data\\asr_synth\\manifest.jsonl
    .venv\\Scripts\\python scripts\\asr_benchmark.py --manifest <bộ người thật>.jsonl --models small,large-v3-turbo ^
        --bias none,static,context --snr clean,10

Mỗi dòng manifest (JSONL): {"id", "audio" (đường dẫn tương đối so với file manifest), "reference",
"context" (tên đang mở trên máy lúc nói, tùy chọn), "group"/"style"/"speaker" (tùy chọn, để chia nhóm)}.

Biến thí nghiệm:
  model × thiết bị      — stt.model / stt.device
  gợi ý (--bias)        — none: không gợi ý | static: câu mẫu + tên cố định | context: thêm tên trong "context"
  nhiễu (--snr)         — clean hoặc SNR dB (nhiễu trắng, hạt giống cố định theo id câu)
  hậu xử lý             — raw: chữ Whisper | norm: sau bảng sửa phiên âm của NEXA (apply_stt_fixes)
Kết quả trong results/asr/<thời điểm>/: utterances.csv, summary.json, report.md.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import tempfile
import time
import zlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexa.research import asr_metrics as M  # noqa: E402
from nexa.research.corpus import read_jsonl, read_wav  # noqa: E402


def add_noise(x: np.ndarray, snr_db: float, key: str) -> np.ndarray:
    voiced = x[np.abs(x) > 0.01]
    power = float(np.mean(voiced ** 2)) if voiced.size else float(np.mean(x ** 2) or 1e-6)
    rng = np.random.default_rng(zlib.crc32(key.encode("utf-8")))
    noise = rng.standard_normal(x.size).astype(np.float32) * np.sqrt(power / 10 ** (snr_db / 10))
    return np.clip(x + noise, -1.0, 1.0).astype(np.float32)


def load_items(paths: list[str], limit: int, groups: set[str]) -> list[dict]:
    items = []
    for p in paths:
        base = Path(p).resolve().parent
        for row in read_jsonl(Path(p)):
            if not str(row.get("reference", "")).strip():
                continue                       # câu chưa gán nhãn
            if groups and row.get("group") not in groups:
                continue
            row["_audio"] = (base / row["audio"]).resolve()
            items.append(row)
    return items[:limit] if limit else items


def fmt(x: float, pct: bool = True) -> str:
    return f"{x * 100:.1f}%" if pct else f"{x:.2f}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", action="append", required=True)
    ap.add_argument("--models", default="auto")
    ap.add_argument("--device", default="auto")
    ap.add_argument("--beam", type=int, default=3)
    ap.add_argument("--bias", default="none,static,context")
    ap.add_argument("--snr", default="clean")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--groups", default="", help="chỉ chạy các nhóm câu này (vd open,close)")
    ap.add_argument("--user-settings", action="store_true",
                    help="dùng config/settings.yaml (hotwords/ứng dụng riêng của anh) thay vì mặc định")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    from nexa.ai.intent_router import IntentRouter, apply_stt_fixes
    from nexa.audio.stt import SpeechRecognizer
    from nexa.utils.config import CONFIG_DIR, Config

    items = load_items(args.manifest, args.limit, {g for g in args.groups.split(",") if g})
    if not items:
        print("Manifest không có câu nào đã gán nhãn.")
        return 1
    audio_cache = {it["id"]: read_wav(it["_audio"]) for it in items}
    ref_norm = {it["id"]: apply_stt_fixes(it["reference"]) for it in items}
    tmp = Path(tempfile.mkdtemp(prefix="nexa-asr-"))
    settings = CONFIG_DIR / "settings.yaml" if args.user_settings else tmp / "settings.yaml"
    cfg = Config(settings_path=settings, gestures_path=tmp / "gestures.yaml", load_env=False)
    cfg.set("stt.device", args.device)
    cfg.set("stt.beam_size", args.beam)
    router = IntentRouter()
    out = Path(args.out) if args.out else ROOT / "results" / "asr" / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)

    biases = [b for b in args.bias.split(",") if b]
    snrs = [s for s in args.snr.split(",") if s]
    rows: list[dict] = []
    scores: dict[tuple, list[M.Score]] = {}
    meta = {"manifests": [str(Path(m).resolve()) for m in args.manifest], "items": len(items),
            "manifest_sha1": [hashlib.sha1(Path(m).read_bytes()).hexdigest() for m in args.manifest],
            "beam": args.beam, "user_settings": args.user_settings, "runs": []}
    try:
        import faster_whisper
        meta["faster_whisper"] = faster_whisper.__version__
    except Exception:
        pass

    for model in [m for m in args.models.split(",") if m]:
        cfg.set("stt.model", model)
        rec = SpeechRecognizer(cfg, ROOT / "models")
        if not rec.load(on_status=print):
            print(rec.error)
            continue
        label = f"{rec._model_name}@{rec.device}"
        meta["runs"].append({"model": rec._model_name, "device": rec.device})
        first = audio_cache[items[0]["id"]][0]
        rec.transcribe(first)                      # chạy nháp: không tính độ trễ khởi tạo
        for bias in biases:
            cfg.set("stt.bias_mode", bias)
            for snr in snrs:
                key = (label, bias, snr)
                raw_scores, norm_scores = [], []
                t0 = time.monotonic()
                for it in items:
                    audio, sr = audio_cache[it["id"]]
                    if snr != "clean":
                        audio = add_noise(audio, float(snr), it["id"])
                    ctx = (it.get("context") or []) if bias == "context" else None
                    res = rec.transcribe(audio, sr, context=ctx)
                    hyp = res.text if res.ok else ""
                    norm = apply_stt_fixes(hyp) if hyp else ""
                    s_raw = M.score(router, it["reference"], hyp, res.elapsed_s)
                    # Hậu xử lý đổi "folder" → "thư mục", "file" → "tệp"…: chấm với câu chuẩn đã qua CÙNG phép đổi,
                    # nếu không WER "norm" bị phạt oan.
                    s_norm = M.score(router, ref_norm[it["id"]], norm, res.elapsed_s)
                    raw_scores.append(s_raw)
                    norm_scores.append(s_norm)
                    rows.append({"model": label, "bias": bias, "snr": snr, "id": it["id"],
                                 "group": it.get("group", ""), "style": it.get("style", ""),
                                 "speaker": it.get("speaker", ""), "reference": it["reference"], "hyp": hyp,
                                 "hyp_norm": norm, "rejected": "" if res.ok else res.reason,
                                 "wer_raw": s_raw.word_err / max(1, s_raw.words),
                                 "wer_norm": s_norm.word_err / max(1, s_norm.words),
                                 "entities": s_raw.ents, "ent_hit_raw": s_raw.ent_hit, "ent_hit_norm": s_norm.ent_hit,
                                 "command_ok": "" if s_raw.command_ok is None else int(s_raw.command_ok),
                                 "avg_logprob": round(res.avg_logprob, 3), "latency_s": round(res.elapsed_s, 3),
                                 "context": "|".join(res.context_terms)})
                scores[key + ("raw",)] = raw_scores
                scores[key + ("norm",)] = norm_scores
                s = M.summarize(raw_scores)
                print(f"{label:28} bias={bias:8} snr={snr:6} WER {fmt(s['wer'])}  lỗi tên {fmt(s['entity_error_rate'])}"
                      f"  lệnh đúng {fmt(s['command_success'])}  {time.monotonic() - t0:.0f}s")
        rec.unload()

    with open(out / "utterances.csv", "w", newline="", encoding="utf-8-sig") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)

    summary = {"meta": meta, "systems": [], "by_group": [], "tests": []}
    for (label, bias, snr, post), sc in scores.items():
        summary["systems"].append({"model": label, "bias": bias, "snr": snr, "post": post, **M.summarize(sc)})
        if post == "raw":
            for group in sorted({it.get("group", "") for it in items}):
                idx = [i for i, it in enumerate(items) if it.get("group", "") == group]
                summary["by_group"].append({"model": label, "bias": bias, "snr": snr, "group": group,
                                            **M.summarize([sc[i] for i in idx])})
    # Kiểm định ghép cặp: mỗi chế độ gợi ý so với chế độ đứng trước nó (none → static → context).
    for (label, bias, snr, post), sc in scores.items():
        if post != "raw" or bias not in biases or biases.index(bias) == 0:
            continue
        base_bias = biases[biases.index(bias) - 1]
        base = scores.get((label, base_bias, snr, "raw"))
        if base is None:
            continue
        summary["tests"].append({"model": label, "snr": snr, "a": base_bias, "b": bias,
                                 "wer": M.paired_bootstrap_wer(base, sc),
                                 "command": M.mcnemar_exact([s.command_ok for s in base], [s.command_ok for s in sc])})
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [f"# Kết quả đo nhận dạng — {time.strftime('%Y-%m-%d %H:%M')}", "",
          f"{len(items)} câu · beam {args.beam} · manifest: {', '.join(Path(m).name for m in args.manifest)}", "",
          "| Model | Gợi ý | SNR | Hậu xử lý | WER | CER | Lỗi tên riêng | Lệnh đúng | Trễ TB (s) | Trễ p90 (s) |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in summary["systems"]:
        md.append(f"| {r['model']} | {r['bias']} | {r['snr']} | {r['post']} | {fmt(r['wer'])} | {fmt(r['cer'])} | "
                  f"{fmt(r['entity_error_rate'])} ({r['entities']}) | {fmt(r['command_success'])} ({r['commands']}) | "
                  f"{r['latency_mean_s']:.2f} | {r['latency_p90_s']:.2f} |")
    if summary["tests"]:
        md += ["", "## Kiểm định ghép cặp (b so với a, hậu xử lý raw)", "",
               "| Model | SNR | a → b | ΔWER [KTC 95%] | p (bootstrap) | Lệnh: chỉ a đúng / chỉ b đúng | p (McNemar) |",
               "|---|---|---|---|---|---|---|"]
        for t in summary["tests"]:
            w, c = t["wer"], t["command"]
            md.append(f"| {t['model']} | {t['snr']} | {t['a']} → {t['b']} | {w['delta'] * 100:+.1f} điểm "
                      f"[{w['ci_low'] * 100:+.1f}; {w['ci_high'] * 100:+.1f}] | {w['p']:.3f} | "
                      f"{c['a_only']} / {c['b_only']} | {c['p']:.3f} |")
    md += ["", "## Theo nhóm câu (raw)", "", "| Model | Gợi ý | SNR | Nhóm | n | WER | Lỗi tên riêng | Lệnh đúng |",
           "|---|---|---|---|---|---|---|---|"]
    for r in summary["by_group"]:
        md.append(f"| {r['model']} | {r['bias']} | {r['snr']} | {r['group']} | {r['n']} | {fmt(r['wer'])} | "
                  f"{fmt(r['entity_error_rate'])} | {fmt(r['command_success'])} |")
    (out / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Kết quả: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
