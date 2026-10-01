"""Gemini viết code theo yêu cầu → chuẩn hóa → kiểm tra tĩnh → (có lỗi) gửi lỗi lại cho Gemini sửa, tối đa N lượt.

JSON Gemini trả chỉ là DỮ LIỆU: đường dẫn tệp được làm sạch (không tuyệt đối/không '..'), không có gì được chạy ở đây.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Callable

from nexa.code import checks
from nexa.code.models import LANG_LABEL, CodeFile, CodeResult, FileCheck, lang_for_path, norm_lang, safe_rel_path
from nexa.utils.logging import get_logger

log = get_logger("code.generator")

MAX_FILES = 12
MAX_FILE_CHARS = 120_000

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Tên ngắn gọn của bản code, tiếng Việt, ≤ 60 ký tự"},
        "language": {"type": "string", "description": "Ngôn ngữ chính, ví dụ python, javascript, typescript, java, csharp, sql"},
        "summary": {"type": "string", "description": "2–4 câu tiếng Việt: code làm gì, thiết kế chính"},
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Đường dẫn tương đối, ví dụ src/app.py"},
                    "language": {"type": "string"},
                    "content": {"type": "string", "description": "Toàn bộ nội dung tệp"},
                },
                "required": ["path", "language", "content"],
            },
        },
        "entry": {"type": "string", "description": "Tệp chạy chính (nếu có)"},
        "run_instructions": {"type": "string", "description": "Cách cài và chạy trên Windows, tiếng Việt, kèm lệnh"},
        "dependencies": {"type": "array", "items": {"type": "string"}, "description": "Thư viện ngoài cần cài (tên gói)"},
        "notes": {"type": "array", "items": {"type": "string"}, "description": "Giả định/giới hạn đáng chú ý, tiếng Việt"},
    },
    "required": ["title", "language", "summary", "files", "run_instructions"],
}

SYSTEM_BASE = """Bạn là kỹ sư phần mềm cấp cao viết code cho một đồng nghiệp người Việt trên Windows 11.
Trả về DUY NHẤT một JSON đúng schema. Mỗi tệp đặt trọn nội dung trong "content" (không bọc ```).

Yêu cầu chất lượng — code phải DÙNG ĐƯỢC NGAY:
- Hoàn chỉnh, chạy được, không TODO/placeholder/"..."/"phần còn lại tương tự". Không bịa API hay thư viện không tồn tại.
- Ưu tiên thư viện chuẩn; chỉ dùng thư viện ngoài khi thật cần và liệt kê trong "dependencies".
- Xử lý lỗi và trường hợp biên hợp lý; không nuốt lỗi im lặng; không hard-code mật khẩu/khóa (đọc từ biến môi trường).
- Định dạng đẹp theo chuẩn cộng đồng: Python theo PEP 8 (4 dấu cách, type hints, docstring, dòng ≤ 100 ký tự);
  JavaScript/TypeScript/HTML/CSS/JSON/YAML thụt 2 dấu cách; Java/C#/C++/Go theo quy ước chuẩn của ngôn ngữ (Go như gofmt).
- Tên biến/hàm/lớp bằng tiếng Anh, rõ nghĩa. {comment_rule}
- Tách tệp hợp lý nếu lớn; bản nhỏ thì 1 tệp chính là đủ. Không tạo tệp nhị phân.
- Nếu là chương trình chạy được: có hàm main và `if __name__ == "__main__":` (Python) hoặc tệp entry rõ ràng.
{test_rule}
- "run_instructions": lệnh cài/chạy cho Windows (PowerShell hoặc cmd), ngắn gọn.
- Nếu yêu cầu mơ hồ, chọn giả định hợp lý nhất và ghi vào "notes".
"""

TEST_RULE = """- KÈM kiểm thử tự động nhỏ nhưng thực chất cho phần logic chính (trừ khi yêu cầu chỉ là SQL/cấu hình/HTML tĩnh):
  Python: tệp test_<tên>.py dùng hàm test_* với assert thuần (không fixture pytest, không mạng, không tệp ngoài);
  JavaScript: tệp <tên>.test.js dùng node:test + node:assert/strict (CommonJS hoặc ESM nhất quán với code).
  Kiểm thử phải chạy nhanh (< 5 giây), không cần nhập liệu, không mở cửa sổ, không gọi mạng."""


def build_system(comment_language: str = "vi", with_tests: bool = True) -> str:
    comment_rule = ("Chú thích và docstring viết bằng tiếng Việt, ngắn gọn, chỉ ở chỗ cần giải thích."
                    if comment_language.lower().startswith("vi") else
                    "Comments and docstrings in English, concise, only where they add value.")
    return SYSTEM_BASE.format(comment_rule=comment_rule, test_rule=TEST_RULE if with_tests else
                              "- Không cần viết kiểm thử trừ khi được yêu cầu.")


class CodeGenError(Exception):
    pass


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + "\n…(lược bớt)"


def files_block(files: list[CodeFile], limit: int = 90_000) -> str:
    out, used = [], 0
    for f in files:
        chunk = f"=== {f.path} ({f.language}) ===\n{f.content}"
        if used + len(chunk) > limit:
            chunk = _clip(chunk, max(2000, limit - used))
        out.append(chunk)
        used += len(chunk)
        if used >= limit:
            break
    return "\n\n".join(out)


def errors_block(result_checks: list[FileCheck], only_errors: bool = True) -> str:
    lines = []
    for c in result_checks:
        if c.status == "error" or (not only_errors and c.status == "warning"):
            lines.append(f"- {c.path} [{c.tool}]:")
            lines.extend(f"    {m}" for m in c.messages[:8])
    return "\n".join(lines)


class CodeGenerator:
    """Không giữ trạng thái giữa các lần gọi (trừ last_model) — an toàn khi chạy trên luồng nền."""

    def __init__(self, gemini: Any, config: Any = None) -> None:
        self.gemini = gemini
        self.config = config
        self.last_model = ""

    def cfg(self, key: str, default: Any) -> Any:
        v = self.config.get(f"code.{key}") if self.config is not None else None
        return default if v is None else v

    def ready(self) -> tuple[bool, str]:
        if self.gemini is None or not hasattr(self.gemini, "generate_json"):
            return False, "Chưa có Gemini."
        try:
            ok, why = self.gemini.status()[:2]
            return bool(ok), str(why or "")
        except Exception:
            return True, ""

    @property
    def models(self) -> list[str]:
        ms = [str(m).strip() for m in (self.cfg("models", None) or []) if str(m).strip()]
        base = getattr(self.gemini, "model", None)
        if isinstance(base, str) and base and base not in ms:
            ms.append(base)
        return ms

    # ---------------------------------------------------------------- Gemini
    def _ask(self, prompt: str, token: Any) -> dict:
        system = build_system(str(self.cfg("comment_language", "vi")), bool(self.cfg("with_tests", True)))
        kwargs: dict[str, Any] = {"system": system, "max_tokens": int(self.cfg("max_tokens", 32000)),
                                  "temperature": float(self.cfg("temperature", 0.2))}
        try:
            data = self.gemini.generate_json(prompt, SCHEMA, token, models=self.models or None,
                                             timeout_s=float(self.cfg("timeout_s", 180)),
                                             thinking=str(self.cfg("thinking", "medium")), **kwargs)
        except TypeError:           # provider giả lập/kiểu cũ không có tham số tác vụ dài
            data = self.gemini.generate_json(prompt, SCHEMA, token, **kwargs)
        self.last_model = str(getattr(self.gemini, "last_model", "") or "") or self.last_model
        if not isinstance(data, dict):
            raise CodeGenError("Gemini không trả JSON đúng dạng.")
        return data

    # ---------------------------------------------------------------- dữ liệu → CodeResult
    def parse(self, data: dict, prompt: str, want_lang: str = "") -> CodeResult:
        main_lang = norm_lang(str(data.get("language") or want_lang or ""))
        files: list[CodeFile] = []
        seen: set[str] = set()
        for i, raw in enumerate(data.get("files") or []):
            if not isinstance(raw, dict) or len(files) >= MAX_FILES:
                continue
            content = str(raw.get("content") or "")
            if not content.strip():
                continue
            path = safe_rel_path(str(raw.get("path") or ""), i)
            base, n = path, 2
            while path.lower() in seen:
                stem, dot, ext = base.rpartition(".")
                path = f"{stem}_{n}.{ext}" if dot else f"{base}_{n}"
                n += 1
            seen.add(path.lower())
            lang = lang_for_path(path, str(raw.get("language") or main_lang))
            if lang == "text" and norm_lang(str(raw.get("language") or "")) in LANG_LABEL:
                lang = norm_lang(str(raw.get("language")))
            files.append(CodeFile(path, lang, checks.normalize(content[:MAX_FILE_CHARS], lang)))
        if not files:
            raise CodeGenError("Gemini không trả tệp code nào.")
        if not main_lang or main_lang not in LANG_LABEL:
            main_lang = files[0].language
        entry = safe_rel_path(str(data.get("entry") or ""), 0) if data.get("entry") else ""
        if entry:                   # tệp chạy chính lên đầu, kiểm thử xuống cuối
            files.sort(key=lambda f: (f.path != entry, checks._is_test(f.path)))
        else:
            files.sort(key=lambda f: checks._is_test(f.path))
        str_list = lambda v: [str(x).strip() for x in (v or []) if str(x).strip()][:20]   # noqa: E731
        return CodeResult(
            id=time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6], prompt=prompt,
            title=str(data.get("title") or "Bản code").strip()[:80], language=main_lang,
            summary=str(data.get("summary") or "").strip()[:2000], files=files,
            run_instructions=str(data.get("run_instructions") or "").strip()[:3000],
            dependencies=str_list(data.get("dependencies")), notes=str_list(data.get("notes")),
            created=time.time(), model=self.last_model)

    # ---------------------------------------------------------------- quy trình
    def _finish(self, res: CodeResult, prompt_for_repair: Callable[[CodeResult], str], token: Any,
                progress: Callable[[str, float], None], want_lang: str) -> CodeResult:
        """Kiểm tra; còn lỗi thì nhờ Gemini sửa (tối đa code.repair_rounds lượt)."""
        rounds = int(self.cfg("repair_rounds", 2))
        res.checks = checks.check_files(res.files)
        for i in range(rounds):
            if res.check_status != "error":
                break
            token.raise_if_cancelled()
            progress(f"Phát hiện lỗi cú pháp — nhờ Gemini sửa (lượt {i + 1}/{rounds})…", 0.55 + 0.15 * i)
            try:
                fixed = self.parse(self._ask(prompt_for_repair(res), token), res.prompt, want_lang)
            except CodeGenError as exc:
                log.warning("Lượt sửa lỗi hỏng: %s", exc)
                break
            fixed.id, fixed.parent, fixed.rounds = res.id, res.parent, res.rounds + 1
            fixed.checks = checks.check_files(fixed.files)
            if fixed.check_status == "error" and _n_errors(fixed.checks) >= _n_errors(res.checks):
                res.rounds = fixed.rounds  # sửa không tốt hơn → giữ bản cũ
                continue
            res = fixed
        progress("Kiểm tra thư viện cần cài…", 0.9)
        res.missing_packages = checks.missing_packages(res.files)
        return res

    def generate(self, request: str, language: str, token: Any,
                 progress: Callable[[str, float], None] = lambda s, p: None) -> CodeResult:
        want = norm_lang(language)
        lang_line = (f"Ngôn ngữ bắt buộc: {LANG_LABEL.get(want, want)}." if want else
                     "Ngôn ngữ: tự chọn phù hợp nhất với yêu cầu (mặc định Python nếu không rõ).")
        prompt = f"{lang_line}\n\nYêu cầu của anh:\n{request.strip()}"
        progress("Gemini đang viết code…", 0.15)
        res = self.parse(self._ask(prompt, token), request, want)
        progress("Đang kiểm tra cú pháp và lỗi…", 0.5)

        def repair(cur: CodeResult) -> str:
            return (f"{prompt}\n\nBản trước của bạn có lỗi do trình kiểm tra phát hiện:\n{errors_block(cur.checks)}\n\n"
                    f"Code hiện tại:\n{files_block(cur.files)}\n\n"
                    "Hãy trả lại TOÀN BỘ các tệp (kể cả tệp không đổi) đã sửa hết lỗi, giữ nguyên chức năng.")
        return self._finish(res, repair, token, progress, want)

    def refine(self, base: CodeResult, instruction: str, token: Any, run_output: str = "",
               progress: Callable[[str, float], None] = lambda s, p: None) -> CodeResult:
        """Chỉnh sửa theo yêu cầu mới của anh (hoặc sửa theo kết quả chạy thử bị lỗi)."""
        extra = ""
        if run_output:
            extra = f"\n\nKết quả chạy thử (lệnh chạy trong thư mục chứa các tệp):\n{_clip(run_output, 6000)}"
        prompt = (f"Yêu cầu ban đầu:\n{base.prompt}\n\nCode hiện tại:\n{files_block(base.files)}{extra}\n\n"
                  f"Yêu cầu chỉnh sửa:\n{instruction.strip()}\n\n"
                  "Trả lại TOÀN BỘ các tệp của phiên bản mới (kể cả tệp không đổi). Giữ đường dẫn tệp cũ nếu không cần đổi.")
        progress("Gemini đang chỉnh sửa code…", 0.15)
        res = self.parse(self._ask(prompt, token), base.prompt, base.language)
        res.parent = base.id
        res.rounds = 1
        progress("Đang kiểm tra cú pháp và lỗi…", 0.5)

        def repair(cur: CodeResult) -> str:
            return (f"{prompt}\n\nPhiên bản bạn vừa trả có lỗi:\n{errors_block(cur.checks)}\n\n"
                    f"Code đó:\n{files_block(cur.files)}\n\nHãy trả lại TOÀN BỘ các tệp đã sửa hết lỗi.")
        return self._finish(res, repair, token, progress, base.language)


def _n_errors(cs: list[FileCheck]) -> int:
    return sum(len(c.messages) or 1 for c in cs if c.status == "error")


def result_brief(res: CodeResult) -> str:
    """Tóm tắt một dòng cho log/ghi chú hội thoại."""
    return json.dumps({"title": res.title, "files": [f.path for f in res.files], "check": res.check_status},
                      ensure_ascii=False)
