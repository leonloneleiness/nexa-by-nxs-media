"""Quản lý bộ dữ liệu giọng thật do NEXA thu (research.record_corpus: true).

    .venv\\Scripts\\python scripts\\asr_corpus.py stats
    .venv\\Scripts\\python scripts\\asr_corpus.py export labels.csv     # mở bằng Excel, sửa cột reference
    .venv\\Scripts\\python scripts\\asr_corpus.py import labels.csv     # ghi manifest.jsonl cho asr_benchmark.py

Gán nhãn: nghe file WAV (cột audio_path), sửa cột "reference" thành ĐÚNG câu đã nói, viết đúng chính tả tên riêng
("mở VS Code", không phải "mở vi ét cốt"). Cột "skip" = 1 để loại câu (không phải lệnh, nói chen, nhạc…).
Ô reference được điền sẵn bằng chữ NEXA nghe được để sửa cho nhanh — câu chưa được sửa/duyệt vẫn giữ "checked" trống
và KHÔNG được nhập (tránh lấy chính kết quả nhận dạng làm đáp án).
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexa.research.corpus import append_jsonl, read_jsonl  # noqa: E402

FIELDS = ["id", "speaker", "time", "duration_s", "route", "hyp", "reference", "checked", "skip", "context",
          "audio_path"]


def corpus_root() -> Path:
    from nexa.utils.config import LOCAL_DATA_DIR, Config
    cfg = Config(load_env=False)
    custom = str(cfg.get("research.corpus_dir") or "").strip()
    return Path(custom) if custom else LOCAL_DATA_DIR / "asr_corpus"


def cmd_stats(root: Path) -> int:
    rows = read_jsonl(root / "utterances.jsonl")
    ok = [r for r in rows if r.get("ok")]
    print(f"Thư mục: {root}")
    print(f"Tổng {len(rows)} câu, {len(ok)} nhận dạng được, {sum(r['duration_s'] for r in rows) / 60:.1f} phút âm thanh")
    print("Theo người nói:", dict(Counter(r.get("speaker", "") for r in rows)))
    print("Theo loại lệnh:", dict(Counter(r.get("route", "") for r in ok).most_common(10)))
    print("Theo chế độ gợi ý:", dict(Counter(r.get("bias_mode", "") for r in rows)))
    print(f"Đã gán nhãn: {sum(1 for r in rows if r.get('reference'))}")
    return 0


def cmd_export(root: Path, csv_path: Path) -> int:
    rows = read_jsonl(root / "utterances.jsonl")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({"id": r["id"], "speaker": r.get("speaker", ""), "time": r.get("time", ""),
                        "duration_s": r.get("duration_s", ""), "route": r.get("route", ""), "hyp": r.get("hyp", ""),
                        "reference": r.get("reference") or r.get("hyp", ""), "checked": "1" if r.get("reference") else "",
                        "skip": "", "context": "|".join(r.get("context") or []),
                        "audio_path": str((root / r["audio"]).resolve())})
    print(f"Đã xuất {len(rows)} câu → {csv_path}. Sửa reference, đặt checked=1 cho câu đã duyệt.")
    return 0


def cmd_import(root: Path, csv_path: Path) -> int:
    by_id = {r["id"]: r for r in read_jsonl(root / "utterances.jsonl")}
    labelled = 0
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            item = by_id.get(row.get("id", ""))
            if item is None or row.get("skip", "").strip() == "1" or row.get("checked", "").strip() != "1":
                continue
            ref = row.get("reference", "").strip()
            if ref:
                item["reference"] = ref
                labelled += 1
    manifest = root / "manifest.jsonl"
    tmp = manifest.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    for item in by_id.values():
        if item.get("reference"):
            append_jsonl(tmp, {"id": item["id"], "audio": item["audio"], "reference": item["reference"],
                               "context": item.get("context") or [], "speaker": item.get("speaker", ""),
                               "group": item.get("route", ""), "style": "real"})
    if tmp.exists():
        tmp.replace(manifest)
    print(f"Đã nhận {labelled} nhãn; manifest: {manifest}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["stats", "export", "import"])
    ap.add_argument("csv", nargs="?")
    ap.add_argument("--root", default="")
    args = ap.parse_args()
    root = Path(args.root) if args.root else corpus_root()
    if not (root / "utterances.jsonl").exists():
        print(f"Chưa có dữ liệu ở {root}. Bật research.record_corpus trong config/settings.yaml rồi dùng NEXA.")
        return 1
    if args.action == "stats":
        return cmd_stats(root)
    if not args.csv:
        ap.error("cần đường dẫn file CSV")
    return (cmd_export if args.action == "export" else cmd_import)(root, Path(args.csv))


if __name__ == "__main__":
    raise SystemExit(main())
