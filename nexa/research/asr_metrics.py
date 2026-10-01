"""Chỉ số đánh giá nhận dạng lệnh nói lẫn Việt–Anh.

- WER/CER: tỷ lệ lỗi từ/ký tự sau chuẩn hóa nhẹ (chữ thường, NFC, bỏ dấu câu). GIỮ dấu thanh: "mở" ≠ "mơ".
- Lỗi tên riêng (entity error rate): tên ứng dụng/dịch vụ/từ tiếng Anh trong câu chuẩn có được ghi ĐÚNG trong câu
  nhận dạng không. "VS Code" và "Visual Studio Code" cùng một thực thể; "VS Của" là sai.
- Lệnh đúng (command success): IntentRouter cho ra CÙNG hành động (loại + công cụ + tham số) với câu nhận dạng
  và câu chuẩn. Câu chuẩn rơi vào Gemini ("ai") không đo được cục bộ nên bị loại khỏi mẫu số.
- Kiểm định: bootstrap ghép cặp cho chênh lệch WER, McNemar chính xác cho chênh lệch tỷ lệ lệnh đúng.
"""
from __future__ import annotations

import json
import math
import random
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable, Sequence

from nexa.utils.text import fold, nfc

_PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE = re.compile(r"\s+")
UNSCORABLE_ROUTES = {"ai", "clarify"}


def normalize(text: str) -> str:
    return _SPACE.sub(" ", _PUNCT.sub(" ", nfc(text or "").lower())).strip()


def edit_distance(ref: Sequence[str], hyp: Sequence[str]) -> int:
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1]


def word_errors(ref: str, hyp: str) -> tuple[int, int]:
    """(số lỗi, số từ câu chuẩn)."""
    r, h = normalize(ref).split(), normalize(hyp).split()
    return edit_distance(r, h), len(r)


def char_errors(ref: str, hyp: str) -> tuple[int, int]:
    r, h = normalize(ref).replace(" ", ""), normalize(hyp).replace(" ", "")
    return edit_distance(list(r), list(h)), len(r)


# ----- thực thể (tên riêng / từ tiếng Anh) -----
@lru_cache(maxsize=4)
def _entity_patterns(extra: tuple[str, ...] = ()) -> tuple[tuple[str, re.Pattern], ...]:
    from nexa.ai.english_terms import TERMS
    from nexa.audio.context_bias import PROCESS_TERMS
    from nexa.desktop.app_aliases import KNOWN_APPS
    surfaces: dict[str, str] = {}                      # dạng viết (fold) → mã thực thể
    for app in KNOWN_APPS:
        for form in (app.name, *app.hint):
            surfaces.setdefault(fold(form), app.name)
    for canon, _ in TERMS:
        surfaces.setdefault(fold(canon), canon)
    for names in PROCESS_TERMS.values():                # ứng dụng ngoài KNOWN_APPS mà gợi ý ngữ cảnh nhận ra
        for name in names:
            surfaces.setdefault(fold(name), name)
    for word in extra:
        if word.strip():
            surfaces.setdefault(fold(word), word.strip())
    ordered = sorted(surfaces.items(), key=lambda kv: len(kv[0]), reverse=True)
    return tuple((eid, re.compile(r"(?<![\w])" + r"[\s-]*".join(map(re.escape, form.replace("-", " ").split()))
                                  + r"(?![\w])")) for form, eid in ordered)


def entities(text: str, extra: Iterable[str] = ()) -> list[str]:
    """Mã các thực thể có trong câu (theo thứ tự xuất hiện; khớp dài nhất trước, không chồng lấn)."""
    folded = fold(nfc(text or ""))
    found: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []
    for eid, pat in _entity_patterns(tuple(extra)):
        for m in pat.finditer(folded):
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), eid))
    return [eid for _, eid in sorted(found)]


def entity_hits(ref: str, hyp: str, extra: Iterable[str] = ()) -> tuple[int, int]:
    """(số thực thể của câu chuẩn được ghi đúng, tổng số thực thể của câu chuẩn)."""
    extra = tuple(extra)
    want = entities(ref, extra)
    have = entities(hyp, extra)
    hits = 0
    for eid in want:
        if eid in have:
            have.remove(eid)
            hits += 1
    return hits, len(want)


# ----- lệnh -----
def command_signature(router: Any, text: str) -> str:
    route = router.route(text)
    calls = [[name, args] for name, args in route.calls]
    return json.dumps({"kind": route.kind, "calls": calls, "action": route.action}, ensure_ascii=False,
                      sort_keys=True, default=str)


def command_match(router: Any, ref: str, hyp: str) -> bool | None:
    """True/False; None nếu câu chuẩn không phải lệnh cục bộ (rơi vào Gemini) — không tính."""
    ref_route = router.route(ref)
    if ref_route.kind in UNSCORABLE_ROUTES:
        return None
    return command_signature(router, ref) == command_signature(router, hyp)


# ----- tổng hợp -----
@dataclass
class Score:
    word_err: int
    words: int
    char_err: int
    chars: int
    ent_hit: int
    ents: int
    command_ok: bool | None
    latency_s: float


def score(router: Any, ref: str, hyp: str, latency_s: float = 0.0, extra: Iterable[str] = ()) -> Score:
    we, wn = word_errors(ref, hyp)
    ce, cn = char_errors(ref, hyp)
    eh, en = entity_hits(ref, hyp, extra)
    return Score(we, wn, ce, cn, eh, en, command_match(router, ref, hyp), latency_s)


def _pct(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def summarize(scores: Sequence[Score]) -> dict[str, float]:
    words = sum(s.words for s in scores) or 1
    chars = sum(s.chars for s in scores) or 1
    ents = sum(s.ents for s in scores)
    cmd = [s.command_ok for s in scores if s.command_ok is not None]
    lat = [s.latency_s for s in scores]
    return {
        "n": len(scores),
        "wer": sum(s.word_err for s in scores) / words,
        "cer": sum(s.char_err for s in scores) / chars,
        "entity_error_rate": (1 - sum(s.ent_hit for s in scores) / ents) if ents else 0.0,
        "entities": ents,
        "command_success": (sum(cmd) / len(cmd)) if cmd else 0.0,
        "commands": len(cmd),
        "latency_mean_s": (sum(lat) / len(lat)) if lat else 0.0,
        "latency_p90_s": _pct(lat, 0.9),
    }


def paired_bootstrap_wer(a: Sequence[Score], b: Sequence[Score], n: int = 2000,
                         seed: int = 0) -> dict[str, float]:
    """Chênh lệch WER (b − a) với khoảng tin cậy 95% và p hai phía, lấy mẫu lại theo CÂU (ghép cặp)."""
    assert len(a) == len(b), "hai hệ thống phải chấm trên cùng tập câu"
    if not a:
        return {"delta": 0.0, "ci_low": 0.0, "ci_high": 0.0, "p": 1.0}
    rng = random.Random(seed)
    idx = range(len(a))

    def wer(scores: Sequence[Score], sample: Sequence[int]) -> float:
        return sum(scores[i].word_err for i in sample) / (sum(scores[i].words for i in sample) or 1)

    delta = wer(b, idx) - wer(a, idx)
    deltas = []
    for _ in range(n):
        sample = [rng.randrange(len(a)) for _ in idx]
        deltas.append(wer(b, sample) - wer(a, sample))
    deltas.sort()
    worse = sum(1 for d in deltas if d >= 0)
    better = sum(1 for d in deltas if d <= 0)
    return {"delta": delta, "ci_low": _pct(deltas, 0.025), "ci_high": _pct(deltas, 0.975),
            "p": min(1.0, 2 * min(worse, better) / n)}


def mcnemar_exact(a: Sequence[bool | None], b: Sequence[bool | None]) -> dict[str, float]:
    """Kiểm định McNemar chính xác cho hai hệ thống trên cùng câu (bỏ câu không chấm được)."""
    b_only = sum(1 for x, y in zip(a, b) if x is False and y is True)
    a_only = sum(1 for x, y in zip(a, b) if x is True and y is False)
    n = a_only + b_only
    if n == 0:
        return {"a_only": 0, "b_only": 0, "p": 1.0}
    k = min(a_only, b_only)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return {"a_only": a_only, "b_only": b_only, "p": min(1.0, 2 * p)}
