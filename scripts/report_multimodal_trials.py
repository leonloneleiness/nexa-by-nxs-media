"""Summarize manually labelled VI/EN/mixed hardware trials; never fabricate measurements.

Input CSV columns: language,noise,mode,expected_action,actual_action,expected_target,
actual_target,false_activation,response_ms. One row per trial, including negative trials.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["language"], row["noise"], row["mode"])].append(row)
    output = []
    for (language, noise, mode), samples in sorted(groups.items()):
        labelled = [r for r in samples if r.get("expected_action")]
        targets = [r for r in labelled if r.get("expected_target")]
        latencies = sorted(float(r["response_ms"]) for r in samples if r.get("response_ms", "").strip())
        if any(t < 0 for t in latencies):
            raise ValueError("response_ms must be nonnegative")
        import math
        output.append({"language": language, "noise": noise, "mode": mode, "trials": len(samples),
                       "task_accuracy": (mean(r["expected_action"] == r.get("actual_action") and
                                              (not r.get("expected_target") or r["expected_target"] == r.get("actual_target"))
                                              for r in labelled) if labelled else None),
                       "target_accuracy": mean(r["expected_target"] == r.get("actual_target") for r in targets) if targets else None,
                       "false_activations": sum(r.get("false_activation", "").lower() in ("1", "true", "yes") for r in samples),
                       "latency_samples": len(latencies), "mean_response_ms": mean(latencies) if latencies else None,
                       "p95_response_ms": latencies[math.ceil(len(latencies)*0.95)-1] if latencies else None})
    return {"scope": "User-labelled hardware trials; blank metrics mean no measurements.", "groups": output}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.csv.open(encoding="utf-8-sig", newline="") as stream:
        result = summarize(list(csv.DictReader(stream)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
