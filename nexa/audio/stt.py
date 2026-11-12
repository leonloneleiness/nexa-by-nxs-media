"""Nhận dạng tiếng Việt cục bộ bằng faster-whisper (CPU mặc định, int8).

- Model đa ngôn ngữ, tự nhận Việt/Anh mặc định (stt.language=auto); tên model đổi được trong Settings (tiny/base/small/medium/
  large-v3/large-v3-turbo). Model tải một lần từ Hugging Face (Systran) rồi cache trong models/whisper.
- Lọc câu im lặng/nhiễu: vad_filter của faster-whisper (Silero VAD), ngưỡng no_speech_prob,
  avg_logprob và danh sách câu "ảo giác" thường gặp của Whisper khi gặp im lặng.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

from nexa.utils.logging import get_logger
from nexa.utils.text import fold

log = get_logger("stt")

SUPPORTED_MODELS = ["auto", "tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]
# "auto": có GPU NVIDIA + thư viện CUDA → large-v3-turbo trên GPU; không có → small trên CPU.
# Đo trên máy anh Sơn (RTX 4050, 16 câu lệnh có từ tiếng Anh): small/CPU 1,63 s/câu; small/GPU 0,14 s;
# large-v3-turbo/GPU 0,33 s và nhận đúng nhiều lệnh nhất.
AUTO_GPU_MODEL, AUTO_CPU_MODEL = "large-v3-turbo", "small"


def _add_cuda_dll_dirs() -> list[str]:
    """Thêm thư mục DLL của các gói pip nvidia-* (cuBLAS…) vào đường tìm DLL để ctranslate2 nạp được CUDA."""
    import glob
    import os
    import sys
    roots = {os.path.join(sys.prefix, "Lib", "site-packages")}
    base = getattr(sys, "_MEIPASS", None)
    if base:
        roots.add(base)
    try:
        import nvidia  # gói namespace của nvidia-cublas-cu12
        roots.update(os.path.dirname(p) for p in getattr(nvidia, "__path__", []))
    except Exception:
        pass
    added = []
    for root in roots:
        for d in glob.glob(os.path.join(root, "nvidia", "*", "bin")):
            if d in added:
                continue
            try:
                os.add_dll_directory(d)
            except (OSError, AttributeError):
                continue
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            added.append(d)
    return added


def cuda_ready() -> tuple[bool, str]:
    """GPU dùng được cho nhận dạng? Kiểm tra TRƯỚC khi nạp: thiếu cuBLAS thì ctranslate2 có thể treo khi nạp."""
    _add_cuda_dll_dirs()
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() < 1:
            return False, "không có GPU NVIDIA"
    except Exception as exc:
        return False, f"ctranslate2: {exc}"
    import ctypes
    for dll in ("cublas64_12.dll", "cublasLt64_12.dll", "cudnn64_9.dll"):
        try:
            ctypes.WinDLL(dll)
        except OSError:
            try:
                import os
                import ctranslate2
                ctypes.WinDLL(os.path.join(os.path.dirname(ctranslate2.__file__), dll))
            except OSError:
                return False, f"thiếu {dll}"
    return True, ""

# Câu Whisper hay bịa ra khi gặp im lặng/nhạc nền (đã quan sát phổ biến với tiếng Việt).
HALLUCINATIONS = [
    "subscribe", "ghien mi go", "dang ky kenh", "cam on cac ban da theo doi", "cam on cac ban da xem",
    "hen gap lai cac ban", "nhung video tiep theo", "like va share", "nhan chuong", "vietsub",
    "phu de", "amara.org",
    # bộ đo chuẩn (docs/research_asr.md) bắt được: "Các bạn hãy đăng kí cho kênh … để không bỏ lỡ những video hấp dẫn"
    "dang ki kenh", "dang ki cho kenh", "dang ky cho kenh", "khong bo lo nhung video",
]

# Câu mẫu trộn tiếng Anh: Whisper bắt chước văn phong của gợi ý, nên ghi "file", "folder", "YouTube" đúng chính tả
# thay vì phiên âm "phai", "phôn đơ", "iu túp".
INITIAL_PROMPT = ("Nexa, mở YouTube, mở VS Code, mở file báo cáo, tạo folder dự án, tìm trên Google, mở ChatGPT, "
                    "bật Wi-Fi, copy, paste, đặt âm lượng ba mươi phần trăm, chụp màn hình, mở video đầu tiên, "
                    "chạy thử code, chọn bài học con lắc đơn, dừng lại. "
                    "Nexa, open Notepad, set volume to thirty percent, take a screenshot, open settings, "
                    "select lesson pendulum, run code tests, emergency stop.")


def static_hotwords(config: Any) -> list[str]:
    """Tên riêng (ứng dụng quen thuộc + ứng dụng anh tự thêm trong Cài đặt) để Whisper ưu tiên viết đúng chính tả."""
    from nexa.desktop.app_aliases import whisper_vocabulary
    custom = [str(i.get("name", "")).strip() for i in (config.get("apps.custom") or []) if isinstance(i, dict)]
    extra = [str(w).strip() for w in (config.get("stt.hotwords") or []) if str(w).strip()]
    return whisper_vocabulary([*extra, *custom, "Nexa", "YouTube", "file", "folder", "Google", "Wi-Fi", "PDF"],
                              limit=30)


def build_hotwords(config: Any) -> str:
    return ", ".join(static_hotwords(config))


@dataclass
class SttResult:
    text: str
    ok: bool
    reason: str = ""
    duration_s: float = 0.0
    elapsed_s: float = 0.0
    avg_logprob: float = 0.0
    no_speech_prob: float = 0.0
    bias_mode: str = ""
    context_terms: tuple[str, ...] = ()
    language: str = ""
    language_probability: float = 0.0
    retried: bool = False
    retry_elapsed_s: float = 0.0


class SpeechRecognizer:
    def __init__(self, config: Any, models_dir: Path, bias: Any = None) -> None:
        self.config = config
        self.bias = bias                         # ContextBias (gợi ý theo cửa sổ đang mở); None = chỉ gợi ý tĩnh
        self.models_dir = models_dir / "whisper"
        self._model = None
        self._model_name = ""
        self._lock = threading.Lock()
        self.loading = False
        self.error = ""
        self.device = ""
        self.gpu_note = ""

    @property
    def ready(self) -> bool:
        return self._model is not None

    @property
    def model_name(self) -> str:
        return f"{self._model_name} · {self.device.upper()}" if self._model_name and self.device else self._model_name

    def _plan(self) -> tuple[str, str, str]:
        """(tên model, thiết bị, compute_type) theo cấu hình stt.model / stt.device."""
        name = self.config.get("stt.model") or "auto"
        device = (self.config.get("stt.device") or "auto").lower()
        if device in ("auto", "cuda"):
            ok, why = cuda_ready()
            if not ok and device == "cuda":
                log.warning("Không dùng được GPU cho nhận dạng (%s) — chuyển sang CPU", why)
            device = "cuda" if ok else "cpu"
            if not ok:
                self.gpu_note = why
        if name == "auto":
            name = AUTO_GPU_MODEL if device == "cuda" else AUTO_CPU_MODEL
        ct = self.config.get("stt.compute_type") or "auto"
        if ct == "auto" or (device == "cpu" and "float16" in ct):
            ct = "float16" if device == "cuda" else "int8"
        return name, device, ct

    def load(self, on_status: Callable[[str], None] | None = None) -> bool:
        configured = self.config.get("stt.model") or "auto"
        if configured not in SUPPORTED_MODELS:
            self.error = f"Model STT '{configured}' không được hỗ trợ"
            return False
        with self._lock:
            name, device, compute_type = self._plan()
            if self._model is not None and self._model_name == name and self.device == device:
                return True
            self.loading = True
            self.error = ""
            try:
                from faster_whisper import WhisperModel
                if on_status:
                    on_status(f"Đang nạp model nhận dạng giọng nói '{name}' (lần đầu sẽ tải về, có thể mất vài phút)…")
                self.models_dir.mkdir(parents=True, exist_ok=True)
                t = time.monotonic()
                threads = int(self.config.get("stt.cpu_threads") or 0)
                if threads <= 0:
                    # Đo trên máy 6 nhân/12 luồng: số nhân vật lý nhanh hơn mặc định ~14%.
                    import psutil
                    threads = psutil.cpu_count(logical=False) or 4
                try:
                    self._model = WhisperModel(name, device=device, compute_type=compute_type, cpu_threads=threads,
                                               download_root=str(self.models_dir))
                    if device == "cuda":
                        # Lần chạy GPU đầu tiên chậm ~1 s (khởi tạo kernel): chạy nháp để câu thật đầu tiên đã nhanh.
                        list(self._model.transcribe(np.zeros(16000, np.float32), language="vi", beam_size=1)[0])
                except Exception as exc:
                    if device != "cuda":
                        raise
                    log.warning("Nạp %s trên GPU lỗi (%s) — dùng %s trên CPU", name, exc, AUTO_CPU_MODEL)
                    name, device, compute_type = (AUTO_CPU_MODEL if configured == "auto" else name), "cpu", "int8"
                    self._model = WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=threads,
                                               download_root=str(self.models_dir))
                self._model_name = name
                self.device = device
                log.info("Đã nạp faster-whisper %s trên %s (%s) trong %.1fs", name, device.upper(), compute_type,
                         time.monotonic() - t)
                if on_status:
                    on_status(f"Model nhận dạng '{name}' sẵn sàng.")
                return True
            except Exception as exc:
                self._model = None
                self.error = f"Không nạp được model STT '{name}': {exc}"
                log.error(self.error)
                if on_status:
                    on_status(self.error)
                return False
            finally:
                self.loading = False

    def unload(self) -> None:
        with self._lock:
            self._model = None
            self._model_name = ""

    def prompt_for(self, context: Sequence[str] | None = None) -> tuple[str, str | None, str | None, tuple[str, ...]]:
        """(chế độ, initial_prompt, hotwords, tên ngữ cảnh đã dùng) theo stt.bias_mode.

        context truyền vào (bộ đo chuẩn) thay cho ngữ cảnh đọc từ máy."""
        from nexa.audio.context_bias import BIAS_MODES, merge_terms
        mode = str(self.config.get("stt.bias_mode") or "context").lower()
        mode = mode if mode in BIAS_MODES else "context"
        if mode == "none":
            return mode, None, None, ()
        static = static_hotwords(self.config)
        if mode == "static":
            return mode, INITIAL_PROMPT, ", ".join(static), ()
        if context is not None:
            ctx = [c for c in context if c]
        elif self.bias is not None:
            ctx = self.bias.context_terms()
        else:
            ctx = []
        return mode, INITIAL_PROMPT, ", ".join(merge_terms(ctx, static, 30)), tuple(ctx)

    def transcribe(self, audio: np.ndarray, sr: int = 16000, context: Sequence[str] | None = None) -> SttResult:
        duration = audio.size / float(sr)
        if self._model is None:
            return SttResult("", False, "Model nhận dạng chưa sẵn sàng", duration)
        if duration < 0.3:
            return SttResult("", False, "Quá ngắn", duration)
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        if peak < 1e-3:
            return SttResult("", False, "Chỉ có im lặng", duration)
        if self.config.get("stt.audio_normalize"):
            # Mic nhỏ và giọng khàn thường có biên độ thấp. Khử DC + chuẩn hóa RMS giúp Whisper
            # nghe rõ phụ âm hơn, nhưng giới hạn gain để tiếng ồn không bị phóng đại vô hạn.
            audio = audio.astype(np.float32, copy=True)
            audio -= float(np.median(audio))
            rms = float(np.sqrt(np.mean(audio * audio)) + 1e-8)
            target = 0.075
            gain = min(4.0, max(1.0, target / rms))
            audio = np.clip(audio * gain, -1.0, 1.0)
        elif peak < 0.3:
            audio = audio * (0.3 / peak)  # tương thích cấu hình cũ
        mode, prompt, hotwords, ctx = self.prompt_for(context)
        t = time.monotonic()
        retried, retry_elapsed = False, 0.0
        configured_language = str(self.config.get("stt.language") or "auto").lower()
        language = None if configured_language in ("auto", "", "multilingual") else configured_language
        beam_size = max(1, int(self.config.get("stt.beam_size") or 5))
        with self._lock:
            segments, info = self._model.transcribe(
                audio.astype(np.float32), language=language,
                beam_size=beam_size, vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 400}, condition_on_previous_text=False,
                without_timestamps=True, initial_prompt=prompt, temperature=0.0,
                hotwords=hotwords or None)
            segs = list(segments)

        def result(text: str, ok: bool, reason: str = "", lp: float = 0.0, nsp: float = 0.0) -> SttResult:
            return SttResult(text, ok, reason, duration, time.monotonic() - t, lp, nsp,
                             bias_mode=mode, context_terms=ctx,
                             language=getattr(info, "language", ""),
                             language_probability=float(getattr(info, "language_probability", 0.0)),
                             retried=retried, retry_elapsed_s=retry_elapsed)

        if not segs:
            return result("", False, "Không có lời nói")
        text = " ".join(s.text.strip() for s in segs).strip()
        avg_lp = float(np.mean([s.avg_logprob for s in segs]))
        nsp = float(np.max([s.no_speech_prob for s in segs]))
        # Với giọng khàn, nói nhỏ hoặc trộn Việt/Anh, một lượt decode cố định ngôn ngữ dễ sai.
        # Thử lại bằng auto-detect với beam rộng hơn khi lượt đầu có tín hiệu yếu.
        recovery = bool(self.config.get("stt.bilingual_recovery", True))
        if recovery and (avg_lp < -0.65 or nsp > 0.45) and duration <= float(
                self.config.get("stt.recovery_max_audio_s", 8.0)):
            retried = True
            retry_start = time.monotonic()
            try:
                with self._lock:
                    retry_segments, retry_info = self._model.transcribe(
                        audio.astype(np.float32), language=None, beam_size=min(10, max(7, beam_size + 2)), vad_filter=True,
                        vad_parameters={"min_silence_duration_ms": 400}, condition_on_previous_text=False,
                        without_timestamps=True, initial_prompt=prompt, temperature=0.2,
                        hotwords=hotwords or None)
                    retry = list(retry_segments)
            except Exception:
                log.warning("Không giải mã lại được; giữ kết quả lượt đầu", exc_info=True)
                retry = []
            retry_elapsed = time.monotonic() - retry_start
            if retry:
                retry_lp = float(np.mean([s.avg_logprob for s in retry]))
                retry_nsp = float(np.max([s.no_speech_prob for s in retry]))
                if retry_lp > avg_lp and retry_nsp <= max(0.45, nsp):
                    segs, avg_lp, nsp = retry, retry_lp, retry_nsp
                    info = retry_info
                    text = " ".join(s.text.strip() for s in segs).strip()
        text = re.sub(r"\s+", " ", text).strip(" .,…")
        if not text:
            return result("", False, "Không có lời nói", avg_lp, nsp)
        folded = fold(text)
        if any(h in folded for h in HALLUCINATIONS) and "nexa" not in folded:
            return result("", False, "Nghi là nhiễu (câu Whisper tự sinh)", avg_lp, nsp)
        if nsp > 0.7 and avg_lp < -0.8:
            return result("", False, "Độ tin cậy thấp, nghi là nhiễu", avg_lp, nsp)
        # Whisper đôi khi đọc lại chính câu gợi ý khi gặp im lặng. So 40 ký tự để lệnh thật nhiều bước
        # ("Nexa, mở YouTube, mở VS Code") không bị bỏ nhầm.
        if prompt and folded.startswith(fold(INITIAL_PROMPT)[:40]):
            return result("", False, "Lặp lại gợi ý", avg_lp, nsp)
        return result(text, True, "", avg_lp, nsp)
