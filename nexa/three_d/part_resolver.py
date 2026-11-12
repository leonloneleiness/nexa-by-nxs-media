"""Tìm bộ phận theo lời nói: tên/alias tiếng Việt–Anh + vị trí ("cánh trước bên trái", "motor phía sau bên phải",
"khớp đầu gối chân phải", "lá rotor số 2", "cụm camera", "bộ phận này").

Kết quả:
- ok: một bộ phận, hoặc cả một CỤM khi mọi ứng viên thuộc cùng cụm (vd. "rotor chính" = đầu rotor + các lá);
- ambiguous: nhiều bộ phận trùng tên ở các vị trí khác nhau → câu hỏi lại kèm các lựa chọn
  ("UAV có bốn cánh quạt. Anh muốn xem cánh trước trái, trước phải hay xem cả cụm?");
- not_found.
Lệnh số nhiều ("tất cả", "các", "cả cụm") hoặc thao tác ẩn/hiện chấp nhận nhiều bộ phận không cần hỏi lại.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from nexa.three_d.generation.assembly import POSITION_VI
from nexa.three_d.models import Part3D
from nexa.utils.text import fold

# Vị trí nhận trên chữ CÓ DẤU: "đuôi" (rotor đuôi) và "dưới" đều thành "duoi" khi bỏ dấu.
POS_WORDS = [  # (mẫu chữ thường có dấu, nhãn thành phần)
    (r"\b(phía |bên |mặt )?(trước|front|mũi)\b", "front"),
    (r"\b(phía |bên |mặt )?(sau|rear|back)\b", "rear"),
    (r"\b(phía |bên )?(trái|left)\b", "left"),
    (r"\b(phía |bên )?(phải|right)\b", "right"),
    (r"\b(phía |bên |mặt )?(trên|top|upper)\b", "top"),
    (r"\b(phía |bên |mặt )?(dưới|bottom|lower|bụng)\b", "bottom"),
    (r"\b(ở )?(giữa|center|middle)\b", "middle"),
]
# Câu gõ không dấu: nhận thêm bản bỏ dấu, trừ "duoi" đứng sau rotor/cánh/cần (= đuôi)
POS_WORDS_FOLDED = [(r"\b(phia |ben |mat )?(truoc)\b", "front"), (r"\b(phia |ben |mat )?(sau)\b", "rear"),
                    (r"\b(phia |ben )?(trai)\b", "left"), (r"\b(phia |ben )?(phai)\b", "right"),
                    (r"\b(phia |ben |mat )?(tren)\b", "top"),
                    (r"(?<!rotor )(?<!canh )(?<!can )\b(phia |ben |mat )?(duoi)\b", "bottom"),
                    (r"\b(o )?(giua)\b", "middle")]
GROUP_WORD = re.compile(r"\b(cum|ca cum)\b")
PLURAL = re.compile(r"\b(tat ca|toan bo|ca cum|cum|cac|nhung|het|all|ca bon|ca sau|ca hai|moi)\b")
DEICTIC = re.compile(r"\b(bo phan nay|chi tiet nay|cai nay|phan nay|linh kien nay|no|this)\b")
FILLER = re.compile(r"\b(xem|chi tiet|cho (toi|anh|em|minh)|phong to|zoom|focus|soi|nhin|hien thi|thong tin|bo phan|"
                    r"linh kien|phan|cai|chiec|con|cua|mo hinh|model|uav|drone|robot|xe|truc thang|may bay|cho|giup|"
                    r"hay|di|nhe|a|voi|ve|la gi|o dau|nao|bang|chuc nang|kich thuoc|tach rieng|chi xem|an|giau|hien)\b")
INDEX = re.compile(r"\b(?:so|thu|number|#)\s*(\d+)\b")


@dataclass
class ResolveResult:
    status: str                                    # ok | ambiguous | not_found
    part_ids: list[str] = field(default_factory=list)
    message: str = ""
    options: list[dict] = field(default_factory=list)
    group: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _positions(q: str) -> tuple[set[str], str]:
    """(vị trí, phần còn lại ĐÃ BỎ DẤU). q: chữ thường, có thể có dấu."""
    found: set[str] = set()
    rest = q
    accented = rest != fold(rest)
    for pat, tag in POS_WORDS:
        if re.search(pat, rest):
            found.add(tag)
            rest = re.sub(pat, " ", rest)
    rest = fold(rest)
    if not accented:
        for pat, tag in POS_WORDS_FOLDED:
            if re.search(pat, rest):
                found.add(tag)
                rest = re.sub(pat, " ", rest)
    return found, re.sub(r"\s+", " ", rest).strip()


def _tag_ok(tag: str, want: set[str]) -> bool:
    if not want:
        return True
    t = (tag or "").lower()
    parts = set(t.replace("-", "_").split("_"))
    if "middle" in want:
        want = (want - {"middle"}) | ({"middle"} if "middle" in parts else {"center"} if "center" in parts else {"middle"})
    return want <= parts or (want == {"center"} and t in ("center", "middle"))


def _score(part: Part3D, q: str) -> float:
    """Điểm khớp tên: alias khớp đúng cụm từ > tên chứa truy vấn > trùng từ."""
    if not q:
        return 0.0
    names = [part.name_vi.lower(), part.name_en.lower()] + [a.lower() for a in part.aliases]
    best = 0.0
    qw = set(q.split())
    for i, raw in enumerate(names):
        n = fold(raw)
        if not n:
            continue
        if n == q or _positions(raw)[1] == q:
            best = max(best, 20.0 if i else 18.0)
        elif re.search(rf"\b{re.escape(n)}\b", q):
            best = max(best, 4.0 + 2.5 * len(n.split()))
        elif re.search(rf"\b{re.escape(q)}\b", n):
            best = max(best, 3.0 + len(q.split()))
        else:
            common = qw & set(n.split())
            if common:
                best = max(best, 1.0 * len(common))
    return best


def resolve(parts: list[Part3D], query: str, *, selected: str | None = None, allow_multiple: bool = False,
            model_name: str = "") -> ResolveResult:
    qa = (query or "").lower()
    q = fold(query)
    if not parts:
        return ResolveResult("not_found", message="Chưa có mô hình nào đang mở.")
    # Capture-time selection binds an exact stable ID, never a fuzzy name.
    if any(p.id == query for p in parts):
        return ResolveResult("ok", [query])
    if DEICTIC.search(q) and not re.sub(DEICTIC, "", q).strip(" ,."):
        if selected and any(p.id == selected for p in parts):
            return ResolveResult("ok", [selected])
        return ResolveResult("not_found", message="Anh chưa chọn bộ phận nào. Anh nói tên bộ phận giúp em.")
    plural = bool(PLURAL.search(q)) or allow_multiple
    group_intent = bool(GROUP_WORD.search(q))
    idx_m = INDEX.search(q)
    index = int(idx_m.group(1)) if idx_m else None
    want, rest = _positions(qa)
    rest = INDEX.sub(" ", rest)
    rest = re.sub(r"\s+", " ", FILLER.sub(" ", PLURAL.sub(" ", rest))).strip()
    for w in fold(model_name).split():
        if len(w) > 2:
            rest = re.sub(rf"\b{re.escape(w)}\b", " ", rest)
    rest = re.sub(r"\s+", " ", rest).strip()
    scored = [(p, _score(p, rest)) for p in parts] if rest else [(p, 1.0) for p in parts]
    top = max((s for _, s in scored), default=0.0)
    if top <= 0:
        return ResolveResult("not_found", message=f"Em không thấy bộ phận nào tên '{query.strip()}' trong mô hình.")
    cands = [p for p, s in scored if s >= top - 1e-9]
    if want:
        filtered = [p for p in cands if _tag_ok(p.position_tag, want)]
        if not filtered and top >= 3:
            # vị trí có thể nằm trong tên (vỏ trên) thay vì position_tag
            filtered = [p for p in cands if all(POSITION_VI.get(w, w) in p.name_vi.lower() for w in want)]
        if not filtered:
            return ResolveResult("not_found", message=f"Không có {fold(query)} ở vị trí đó trong mô hình.")
        cands = filtered
    if index is not None:
        byi = [p for p in cands if re.search(rf"(?:_|\bso |\bthu ){index}\b", p.position_tag + " " + fold(p.name_vi))]
        if byi:
            cands = byi
    if group_intent and len({p.group for p in cands}) == 1 and cands[0].group:
        g = cands[0].group
        return ResolveResult("ok", [p.id for p in parts if p.group == g], group=g)
    if len(cands) == 1:
        return ResolveResult("ok", [cands[0].id])
    groups = {p.group for p in cands}
    if len(groups) == 1 and next(iter(groups)):
        # cùng một cụm (rotor chính = đầu rotor + lá): lấy nguyên cụm, kể cả bộ phận cùng cụm khớp tên
        g = next(iter(groups))
        return ResolveResult("ok", [p.id for p in cands], group=g)
    if plural:
        return ResolveResult("ok", [p.id for p in cands])
    kind = cands[0].name_vi.split(" ")[0].lower() if cands else "bộ phận"
    base = _common_prefix([p.name_vi for p in cands]) or kind
    labels = []
    for p in cands[:6]:
        pos = POSITION_VI.get(p.position_tag, "") or p.name_vi[len(base):].strip() or p.name_vi
        labels.append({"id": p.id, "label": pos or p.name_vi})
    count_vi = {2: "hai", 3: "ba", 4: "bốn", 5: "năm", 6: "sáu", 7: "bảy", 8: "tám"}.get(len(cands), str(len(cands)))
    choices = ", ".join(lbl["label"] for lbl in labels) + (", …" if len(cands) > len(labels) else "")
    subject = (model_name + " có ") if model_name else "Mô hình có "
    noun = base.strip().lower()
    msg = f"{subject}{count_vi} {noun}. Anh muốn xem {noun} {choices} hay xem cả cụm?"
    return ResolveResult("ambiguous", [p.id for p in cands], message=msg, options=labels)


def _common_prefix(names: list[str]) -> str:
    if not names:
        return ""
    words = [n.split() for n in names]
    out = []
    for i in range(min(len(w) for w in words)):
        if all(w[i].lower() == words[0][i].lower() for w in words):
            out.append(words[0][i])
        else:
            break
    return " ".join(out)
