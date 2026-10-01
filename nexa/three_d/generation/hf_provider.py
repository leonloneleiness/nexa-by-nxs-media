"""Mức 3 không cần key trả phí — Hugging Face Spaces công khai qua gradio_client.

Luồng: chữ → ảnh sản phẩm (model ảnh Gemini nếu key có hạn mức, không thì Space FLUX.1-schnell) → ảnh → 3D bằng Space
image-to-3D (TRELLIS / Hunyuan3D) → GLB → NEXA làm sạch lưới, chấm điểm như mọi mô hình khác.

Endpoint và tham số lấy từ `Client.view_api()` của chính các Space (đối chiếu 2026-09-25), không tự đặt:
  black-forest-labs/FLUX.1-schnell  /infer(prompt, seed, randomize_seed, width, height, num_inference_steps) → (ảnh, seed)
  trellis-community/TRELLIS         /start_session() ; /generate_and_extract_glb(image, multiimages, seed,
                                    ss_guidance_strength, ss_sampling_steps, slat_guidance_strength, slat_sampling_steps,
                                    multiimage_algo, mesh_simplify, texture_size) → (video, GLB, GLB tải về)
  tencent/Hunyuan3D-2               /shape_generation(caption, image, mv_image_front/back/left/right, steps,
                                    guidance_scale, seed, octree_resolution, check_box_rembg, num_chunks, randomize_seed)
  tencent/Hunyuan3D-2.1             /shape_generation(image, mv_image_*, steps, … giống trên, không có caption)
Space chạy trên ZeroGPU: người dùng ẩn danh có hạn mức GPU rất nhỏ mỗi ngày; đặt HF_TOKEN (token đọc miễn phí của tài
khoản Hugging Face) trong .env để có hạn mức lớn hơn. Space có thể ngủ/lỗi/đổi API: NEXA báo rõ và thử Space kế tiếp.
Quyền riêng tư: câu mô tả (tiếng Anh) và ảnh sinh ra được gửi tới Space công khai — không gửi ảnh màn hình/dữ liệu cá nhân.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from nexa.three_d.generation.base import ProviderError, ProviderTask, ThreeDProvider
from nexa.utils.logging import get_logger, register_secret

log = get_logger("3d.hf")

IMAGE_SPACE = "black-forest-labs/FLUX.1-schnell"
DEFAULT_3D_SPACES = ["trellis-community/TRELLIS", "tencent/Hunyuan3D-2", "tencent/Hunyuan3D-2.1"]
IMAGE_STYLE = ("Photorealistic product photo of {subject}. Single real-world object only, centered, three-quarter front view, "
               "the whole object fully visible with margin, plain pure white background, soft even studio lighting, sharp "
               "focus, realistic materials and proportions, exactly as described with no extra decorations, no cartoon "
               "faces or characters unless described, no text, no logo, no hands, no other objects")
_gemini_image_blocked_until = 0.0          # key Gemini không có hạn mức model ảnh → khỏi thử lại trong 1 giờ


def _hf_token() -> str | None:
    tok = (os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN") or "").strip()
    if tok and not tok.upper().startswith("YOUR_"):
        register_secret(tok)
        return tok
    return None


def _file_of(value: Any) -> str | None:
    """Kết quả gradio: đường dẫn str | {'path'|'value': …} | {'video': …}."""
    if isinstance(value, str):
        return value if os.path.exists(value) else None
    if isinstance(value, dict):
        for k in ("path", "value", "name"):
            if isinstance(value.get(k), str) and os.path.exists(value[k]):
                return value[k]
    return None


def classify_hf_error(exc: BaseException, space: str) -> ProviderError:
    msg = str(exc)
    low = msg.lower()
    if "zerogpu quota" in low or "exceeded your" in low and "quota" in low:
        if _hf_token():
            return ProviderError("quota", f"{space}: tài khoản Hugging Face đã dùng hết hạn mức GPU miễn phí hôm nay "
                                          "(thử lại sau, hoặc nâng gói trên huggingface.co).", retryable=False)
        return ProviderError("quota", f"{space}: hết hạn mức GPU miễn phí của Hugging Face (đặt HF_TOKEN trong .env để "
                                      "có hạn mức lớn hơn, hoặc thử lại sau).", retryable=False)
    if "queue is full" in low or "too many" in low or "429" in low:
        return ProviderError("rate_limit", f"{space}: hàng đợi đang đầy.", retryable=True)
    if "could not fetch" in low or "internal server error" in low or "sleeping" in low or "502" in low or "503" in low:
        return ProviderError("server", f"{space}: Space đang ngủ/lỗi máy chủ.", retryable=True)
    if isinstance(exc, (TimeoutError,)) or "timed out" in low or "timeout" in low:
        return ProviderError("timeout", f"{space}: quá thời gian chờ.", retryable=True)
    if "nsfw" in low or "safety" in low and "content" in low:
        return ProviderError("content_policy", f"{space}: nội dung bị bộ lọc an toàn từ chối.")
    return ProviderError("failed", f"{space}: {msg[:200]}", retryable=True)


@dataclass
class _HFJob:
    task: ProviderTask
    prompt: str = ""
    image: tuple[bytes, str] | None = None
    views: dict[str, tuple[bytes, str]] = field(default_factory=dict)
    cancel: threading.Event = field(default_factory=threading.Event)
    gradio_job: Any = None
    result_path: str | None = None
    workdir: Path | None = None
    space_used: str = ""
    image_source: str = ""
    log: list[str] = field(default_factory=list)
    clients: dict[str, Any] = field(default_factory=dict)   # một client/Space mỗi job: giữ phiên (session) gradio


class HFSpaceProvider(ThreeDProvider):
    name = "Hugging Face Space"
    free_tier = True                       # miễn phí nhưng chậm, giới hạn GPU: auto chỉ dùng khi cần (pipeline._route)
    capabilities = {"text_to_model", "image_to_model", "multiview_to_model", "cancel_job"}

    def __init__(self, config: Any, gemini: Any = None, client_factory: Callable[..., Any] | None = None) -> None:
        self.config = config
        self.gemini = gemini
        self._client_factory = client_factory
        self._jobs: dict[str, _HFJob] = {}
        self._lock = threading.Lock()

    def cfg(self, key: str, default: Any) -> Any:
        v = self.config.get(f"three_d.{key}") if self.config is not None else None
        return default if v is None else v

    @property
    def preferred(self) -> bool:
        """Có HF_TOKEN → dùng làm đường chính cho vật thể tự do (mức 3, lưới AI chi tiết); mức 2 là dự phòng."""
        return bool(_hf_token()) and bool(self.cfg("hf_prefer_with_token", True))

    @property
    def spaces(self) -> list[str]:
        s = [str(x).strip() for x in (self.cfg("hf_3d_spaces", None) or DEFAULT_3D_SPACES) if str(x).strip()]
        return s or list(DEFAULT_3D_SPACES)

    def available(self) -> tuple[bool, str]:
        if not bool(self.cfg("hf_enabled", True)):
            return False, "Tạo 3D qua Hugging Face Space đang tắt (three_d.hf_enabled)."
        if self._client_factory is None:
            import importlib.util
            if importlib.util.find_spec("gradio_client") is None:
                return False, "Thiếu thư viện gradio_client (pip install gradio_client) để dùng Hugging Face Space."
        return True, ("Hugging Face Space miễn phí (" + ", ".join(self.spaces[:2]) + ")"
                      + ("" if _hf_token() else " — chưa có HF_TOKEN: hạn mức GPU ẩn danh rất nhỏ"))

    # ------------------------------------------------------------------ gradio
    def _client(self, space: str, workdir: Path) -> Any:
        if self._client_factory is not None:
            return self._client_factory(space, workdir)
        from gradio_client import Client
        return Client(space, token=_hf_token(), verbose=False, analytics_enabled=False, download_files=str(workdir),
                      httpx_kwargs={"timeout": 60.0})

    def _run(self, job: _HFJob, space: str, api_name: str, deadline: float, p0: float, p1: float, **kwargs) -> Any:
        """Gọi một endpoint gradio có hủy/timeout; cập nhật tiến độ theo hàng đợi."""
        if job.cancel.is_set():
            raise ProviderError("cancelled", "Đã hủy")
        try:
            client = job.clients.get(space)
            if client is None:
                client = job.clients[space] = self._client(space, job.workdir)
            gj = client.submit(api_name=api_name, **kwargs)
        except ProviderError:
            raise
        except Exception as exc:
            raise classify_hf_error(exc, space) from exc
        job.gradio_job = gj
        t0 = time.monotonic()
        expect = float(self.cfg("hf_expected_s", 120))
        while not gj.done():
            if job.cancel.is_set():
                try:
                    gj.cancel()
                except Exception:
                    pass
                raise ProviderError("cancelled", "Đã hủy")
            if time.monotonic() > deadline:
                try:
                    gj.cancel()
                except Exception:
                    pass
                raise ProviderError("timeout", f"{space}: quá thời gian chờ ({time.monotonic() - t0:.0f} s)", retryable=True)
            try:
                st = gj.status()
                code = str(getattr(st, "code", "")).split(".")[-1]
                if code in ("IN_QUEUE", "JOINING_QUEUE", "STARTING"):
                    rank = getattr(st, "rank", None)
                    job.task.raw_status = f"{space.split('/')[-1]}: xếp hàng" + (f" #{rank + 1}" if isinstance(rank, int) else "")
                    job.task.progress = max(job.task.progress, p0)
                else:
                    frac = min(0.95, (time.monotonic() - t0) / expect)
                    job.task.progress = max(job.task.progress, p0 + (p1 - p0) * frac)
                    job.task.raw_status = f"{space.split('/')[-1]}: đang chạy {time.monotonic() - t0:.0f} s"
            except Exception:
                pass
            time.sleep(0.5)
        if job.cancel.is_set():
            raise ProviderError("cancelled", "Đã hủy")        # kết quả đến sau khi hủy bị bỏ
        try:
            return gj.result()
        except Exception as exc:
            if job.cancel.is_set():
                raise ProviderError("cancelled", "Đã hủy") from exc
            raise classify_hf_error(exc, space) from exc

    # ------------------------------------------------------------------ các bước
    def _image_from_gemini(self, job: _HFJob) -> tuple[bytes, str] | None:
        global _gemini_image_blocked_until
        if self.gemini is None or not hasattr(self.gemini, "generate_image") or time.monotonic() < _gemini_image_blocked_until:
            return None
        try:
            if not self.gemini.status()[0]:
                return None
            from nexa.core.safety import CancelToken
            tok = CancelToken(None, 0, "hf-image")
            img = self.gemini.generate_image(IMAGE_STYLE.format(subject=job.prompt[:600]), tok,
                                             str(self.cfg("reference_image_model", "gemini-3.1-flash-image")))
            job.image_source = "gemini"
            return img
        except Exception as exc:
            kind = getattr(exc, "kind", "")
            if kind in ("quota", "not_found", "permission"):
                _gemini_image_blocked_until = time.monotonic() + 3600
            job.log.append(f"Ảnh Gemini lỗi ({kind or type(exc).__name__}) — dùng FLUX.1-schnell")
            return None

    def _image_from_flux(self, job: _HFJob, deadline: float) -> tuple[bytes, str]:
        space = str(self.cfg("hf_image_space", IMAGE_SPACE))
        deadline = min(deadline, time.monotonic() + float(self.cfg("hf_image_timeout_s", 180)))
        res = self._run(job, space, "/infer", deadline, 2.0, 15.0, prompt=IMAGE_STYLE.format(subject=job.prompt[:600]),
                        seed=int(self.cfg("hf_seed", 7)), randomize_seed=False, width=1024, height=1024,
                        num_inference_steps=4)
        path = _file_of(res[0] if isinstance(res, (list, tuple)) else res)
        if not path:
            raise ProviderError("failed", f"{space}: không trả ảnh")
        data = Path(path).read_bytes()
        job.image_source = "flux"
        from PIL import Image
        import io
        buf = io.BytesIO()
        Image.open(io.BytesIO(data)).convert("RGB").save(buf, "PNG")
        return buf.getvalue(), "image/png"

    def _to_3d(self, job: _HFJob, image_path: Path, extra_views: dict[str, Path], overall: float) -> str:
        import random
        seed = random.Random(job.task.task_id).randrange(2**31)
        errors: list[str] = []
        last: ProviderError | None = None
        try:
            from gradio_client import handle_file
        except ImportError:                      # client giả lập trong test
            def handle_file(path: str) -> str:
                return path
        for space in self.spaces:
            if job.cancel.is_set():
                raise ProviderError("cancelled", "Đã hủy")
            if time.monotonic() > overall - 20:
                errors.append(f"{space}: không còn thời gian để thử")
                break
            deadline = min(overall, time.monotonic() + float(self.cfg("hf_space_timeout_s", 360)))
            try:
                if "TRELLIS" in space and "TRELLIS.2" not in space:
                    try:
                        self._run(job, space, "/start_session", deadline, 15.0, 18.0)
                    except ProviderError as exc:
                        if exc.kind in ("quota", "cancelled"):
                            raise
                    multi = [{"image": handle_file(str(p)), "caption": None} for p in extra_views.values()]
                    res = self._run(job, space, "/generate_and_extract_glb", deadline, 18.0, 95.0,
                                    image=handle_file(str(image_path)), multiimages=multi, seed=seed,
                                    ss_guidance_strength=7.5, ss_sampling_steps=12, slat_guidance_strength=3.0,
                                    slat_sampling_steps=12, multiimage_algo="stochastic", mesh_simplify=0.95,
                                    texture_size=1024)
                    cand = [res[2], res[1]] if isinstance(res, (list, tuple)) and len(res) >= 3 else [res]
                elif "Hunyuan3D" in space:
                    if extra_views:
                        raise ProviderError("unsupported", f"{space}: bộ gọi hiện tại không nhận đủ ảnh đa góc; không bỏ ảnh tham chiếu.")
                    kw = dict(image=handle_file(str(image_path)), mv_image_front=None, mv_image_back=None,
                              mv_image_left=None, mv_image_right=None, steps=30, guidance_scale=5.0, seed=seed,
                              octree_resolution=256, check_box_rembg=True, num_chunks=8000, randomize_seed=False)
                    if space.rstrip("/").endswith("Hunyuan3D-2"):
                        kw["caption"] = None
                    res = self._run(job, space, "/shape_generation", deadline, 18.0, 95.0, **kw)
                    cand = [res[0]] if isinstance(res, (list, tuple)) else [res]
                else:
                    raise ProviderError("unsupported", f"{space}: NEXA chưa có bộ gọi cho Space này")
                path = next((p for p in (_file_of(c) for c in cand) if p and p.lower().endswith((".glb", ".gltf"))), None)
                if not path:
                    raise ProviderError("failed", f"{space}: không trả tệp GLB")
                job.space_used = space
                return path
            except ProviderError as exc:
                if exc.kind == "cancelled":
                    raise
                errors.append(exc.message)
                last = exc
                job.log.append(exc.message)
                log.info("HF Space %s lỗi: %s", space, exc.message)
                continue
        kind = last.kind if last is not None and all("hạn mức" in e for e in errors) else "failed"
        raise ProviderError(kind, "Không Space image-to-3D nào tạo được mô hình: " + " | ".join(errors[:3]))

    def _worker(self, job: _HFJob) -> None:
        t = job.task
        deadline = time.monotonic() + float(self.cfg("hf_timeout_s", 840))
        try:
            t.status = "running"
            wd = job.workdir
            if job.image is None:
                t.raw_status = "Đang tạo ảnh sản phẩm từ mô tả"
                job.image = self._image_from_gemini(job) or self._image_from_flux(job, deadline)
            img_path = wd / ("input.png" if "png" in job.image[1] else "input.jpg")
            img_path.write_bytes(job.image[0])
            views = {}
            for k, (data, mime) in job.views.items():
                p = wd / f"view_{k}.{'png' if 'png' in mime else 'jpg'}"
                p.write_bytes(data)
                views[k] = p
            t.progress = max(t.progress, 15.0)
            job.result_path = self._to_3d(job, img_path, views, deadline)
            t.outputs = {"model": job.result_path, "image": str(img_path)}
            t.progress = 100.0
            t.status = "success"
            t.raw_status = f"{job.space_used} (ảnh: {job.image_source or 'người dùng'})"
        except ProviderError as exc:
            t.status = "cancelled" if exc.kind == "cancelled" or job.cancel.is_set() else "failed"
            t.error = exc.message
            t.raw_status = exc.kind
        except Exception as exc:             # lỗi không lường trước: báo lỗi, không làm sập NEXA
            log.warning("HF worker lỗi", exc_info=True)
            t.status = "failed"
            t.error = f"{type(exc).__name__}: {str(exc)[:200]}"
            t.raw_status = "failed"

    def _start(self, kind: str, prompt: str = "", image: tuple[bytes, str] | None = None,
               views: dict[str, tuple[bytes, str]] | None = None) -> ProviderTask:
        ok, reason = self.available()
        if not ok:
            raise ProviderError("missing_key", reason)
        task = ProviderTask(task_id=f"hf_{uuid.uuid4().hex[:12]}", kind=kind, status="queued")
        job = _HFJob(task=task, prompt=prompt, image=image, views=dict(views or {}),
                     workdir=Path(tempfile.mkdtemp(prefix="nexa_hf_")))
        with self._lock:
            self._jobs[task.task_id] = job
        threading.Thread(target=self._worker, args=(job,), name=f"nexa-hf-{task.task_id}", daemon=True).start()
        return task

    # ------------------------------------------------------------------ ThreeDProvider
    def create_from_text(self, prompt: str, *, negative_prompt: str = "", pbr: bool = True, quality: str = "standard",
                         face_limit: int | None = None) -> ProviderTask:
        return self._start("text_to_model", prompt=prompt)

    def create_from_image(self, image: bytes, mime: str, *, pbr: bool = True, quality: str = "standard") -> ProviderTask:
        return self._start("image_to_model", image=(image, mime))

    def create_from_multiview(self, images: dict[str, tuple[bytes, str]], *, pbr: bool = True,
                              quality: str = "standard") -> ProviderTask:
        front = images.get("front") or next(iter(images.values()))
        rest = {k: v for k, v in images.items() if v is not front}
        return self._start("multiview_to_model", image=front, views=rest)

    def get_job_status(self, task: ProviderTask) -> ProviderTask:
        job = self._jobs.get(task.task_id)
        if job is None:
            raise ProviderError("not_found", "Không tìm thấy tác vụ Hugging Face")
        return job.task

    def cancel_job(self, task: ProviderTask) -> bool:
        job = self._jobs.get(task.task_id)
        if job is None:
            return False
        job.cancel.set()
        gj = job.gradio_job
        if gj is not None:
            try:
                gj.cancel()
            except Exception:
                pass
        return True

    def download_result(self, task: ProviderTask, dest: Path, max_bytes: int,
                        cancelled: Callable[[], bool] | None = None) -> Path:
        job = self._jobs.get(task.task_id)
        if job is None or not job.result_path or not os.path.exists(job.result_path):
            raise ProviderError("failed", "Hugging Face chưa có tệp kết quả")
        if cancelled is not None and cancelled():
            raise ProviderError("cancelled", "Đã hủy")
        size = os.path.getsize(job.result_path)
        if size > max_bytes:
            raise ProviderError("invalid", f"Tệp kết quả {size / 1e6:.1f} MB vượt giới hạn {max_bytes / 1e6:.0f} MB")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(job.result_path, dest)
        img = task.outputs.get("image")
        if img and os.path.exists(img):
            shutil.copy2(img, dest.with_suffix(Path(img).suffix))
        return dest

    def job_log(self, task: ProviderTask) -> list[str]:
        job = self._jobs.get(task.task_id)
        return list(job.log) if job else []


__all__ = ["HFSpaceProvider", "classify_hf_error", "DEFAULT_3D_SPACES", "IMAGE_SPACE"]
