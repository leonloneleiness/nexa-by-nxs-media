"""Tripo 3D API — mặc định v3 (https://openapi.tripo3d.ai/v3), v2 giữ làm tùy chọn (three_d.tripo_api: v2).

v3 (đối chiếu developers.tripo3d.ai 2026-09-25: Quick Start, Text/Image/Multiview to 3D Model, Task Query, File Upload,
Mesh Segmentation, Account, Error Handling, Pricing, Migration v2→v3):
- Endpoint riêng cho từng việc, không còn "type": POST /generation/text-to-model | image-to-model | multiview-to-model,
  POST /mesh/segment, POST /files (multipart "file" → data.file_token), GET /tasks/{id}, GET /account/balance.
- Tham số: prompt (≤1024), model (v3.1-20260211 mới nhất), negative_prompt (≤255), texture, pbr, texture_quality
  (standard | detailed | extreme 8K), geometry_quality (standard | detailed = Ultra, chỉ model ≥ v3.0), face_limit
  (v3.1 ≤1,5 triệu; Ultra ≤2 triệu), auto_size (kích thước thật, mét). Ảnh: "input" = file_token/URL/task_id;
  multiview: "inputs" = [{"front": token}, {"left": …}, …] (bắt buộc front, ≥2 ảnh).
- Kết quả: data.status ∈ queued | running | success | failed | cancelled; data.output.model_url, rendered_image_url;
  credits_consumed; error_code/error_message khi lỗi. Lỗi HTTP: {code, message, suggestion}.
- Tách bộ phận: /mesh/segment {input: task_id, model: v2.0-20260430 (Beta, ngữ nghĩa có nhãn) | v1.0-20250506}.
- Không có endpoint hủy trong tài liệu → cancel_job() trả False (NEXA bỏ qua kết quả đến muộn). Tác vụ lỗi/hủy không bị
  trừ credit (Billing: credit bị đóng băng rồi hoàn lại).
- Giá (1 credit = 0,01 USD): text→3D 10 (không texture) / 20 (texture); ảnh→3D 20/30; cộng thêm: texture HD +10,
  texture 8K +20, hình học HD +20; segmentation 40.

v2 (https://api.tripo3d.ai/v2/openapi) — đối chiếu tài liệu chính thức 2026-09-25:
docs.tripo3d.ai (quick start, text/image/multiview-to-model v3.x, mesh segmentation v1.0-20250506, smart low poly,
texture model, get task, errors, rate limits, pricing) và SDK chính thức VAST-AI-Research/tripo-python-sdk.

- Xác thực: header "Authorization: Bearer <TRIPO_API_KEY>" (key dạng tsk_…).
- Tạo tác vụ: POST /task {"type": …}; phản hồi {"code": 0, "data": {"task_id": …}}; lỗi: code ≠ 0 + message.
- Trạng thái: GET /task/{id} → data.status ∈ queued, running, success, failed, banned, expired, cancelled, unknown;
  data.progress 0–100; data.output.{model, base_model, pbr_model, rendered_image}. URL kết quả hết hạn sau ~5 phút
  → tải NGAY khi thành công.
- Ảnh: POST /upload (multipart "file") → data.image_token → {"type": "png", "file_token": …}. Multiview: đúng 4 ô
  theo thứ tự [front, left, back, right], ô thiếu = {} (đường dẫn upload lấy theo SDK).
- Không có endpoint hủy trong tài liệu → cancel_job() trả False; NEXA bỏ qua kết quả đến muộn.
- refine_model chỉ thấy trong SDK/rate-limit (dành cho bản nháp v1.4) → gắn cờ chưa kiểm chứng.
Chi phí (credit, $1 = 100): text 10–20 (+10 texture, +20 geometry detailed), segmentation 40, smart low poly 30.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from nexa.three_d.generation.base import ProviderError, ProviderTask, ThreeDProvider
from nexa.three_d.generation.http import HttpClient
from nexa.utils.config import is_placeholder_secret

BASE_URL = "https://api.tripo3d.ai/v2/openapi"
BASE_URL_V3 = "https://openapi.tripo3d.ai/v3"
SEGMENT_V2_MODEL = "v2.0-20260430"          # tách bộ phận ngữ nghĩa có nhãn (Beta)
# v3: 1000 key sai, 1001 thiếu Authorization, 1004 tham số không hợp lệ, 2000 giới hạn tốc độ, 2002 tham số không hỗ
# trợ, 2003 tệp rỗng, 2004 định dạng không hỗ trợ, 2008 vi phạm nội dung, 2010 hết credit, 2015 phiên bản ngừng hỗ trợ,
# 2018 mô hình quá phức tạp
ERROR_KINDS_V3 = {1000: "auth", 1001: "auth", 1004: "invalid", 2000: "rate_limit", 2002: "invalid", 2003: "invalid",
                  2004: "invalid", 2008: "content_policy", 2010: "quota", 2015: "unsupported", 2018: "invalid"}
DEFAULT_MODEL_VERSION = "v3.1-20260211"
SEGMENT_MODEL_VERSION = "v1.0-20250506"
STATUS_MAP = {"queued": "queued", "running": "running", "success": "success", "failed": "failed", "banned": "failed",
              "expired": "failed", "cancelled": "cancelled", "unknown": "failed"}
ERROR_KINDS = {1002: "auth", 1003: "invalid", 1004: "invalid", 1005: "auth", 1007: "rate_limit", 2000: "rate_limit",
               2001: "not_found", 2002: "unsupported", 2003: "invalid", 2004: "invalid", 2008: "content_policy",
               2009: "invalid", 2010: "quota", 2015: "unsupported", 2016: "unsupported", 2017: "invalid", 2018: "invalid",
               1000: "server", 1001: "server"}


def _mime_type(mime: str) -> str:
    return {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/webp": "webp"}.get(mime, "png")


class TripoProvider(ThreeDProvider):
    reference_views = {"front", "back", "left", "right"}
    multiview_requires_front = True
    name = "tripo"
    capabilities = {"text_to_model", "image_to_model", "multiview_to_model", "segment_model", "remesh_model",
                    "generate_texture", "refine_model"}

    def __init__(self, config: Any, http_factory: Callable[..., Any] | None = None) -> None:
        self.config = config
        self._http_factory = http_factory
        self._http: HttpClient | None = None

    # ----- cấu hình -----
    def _key(self) -> str:
        k = os.environ.get("TRIPO_API_KEY", "")
        return "" if is_placeholder_secret(k) else k.strip()

    def available(self) -> tuple[bool, str]:
        if not self._key():
            return False, "Chưa có TRIPO_API_KEY trong .env nên chưa tạo mô hình bằng dịch vụ cloud Tripo được."
        k = self._key()
        if k.startswith("tcli_"):
            return False, ("TRIPO_API_KEY đang là mã định danh (tcli_…), không phải secret. Dán secret bắt đầu bằng "
                           "tsk_ (chỉ hiện một lần khi tạo/xoay vòng key trên platform.tripo3d.ai) vào .env.")
        return True, f"Tripo 3D API {self.api}"

    @property
    def api(self) -> str:
        v = str(self.config.get("three_d.tripo_api") or "v3").lower() if self.config else "v3"
        return "v2" if v == "v2" else "v3"

    @property
    def auto_size(self) -> bool:
        """v3 auto_size: Tripo trả mô hình theo kích thước thật (mét) → pipeline không phải đoán cỡ."""
        if self.api != "v3":
            return False
        v = self.config.get("three_d.tripo_auto_size") if self.config else None
        return True if v is None else bool(v)

    def _client(self) -> HttpClient:
        key = self._key()
        if not key:
            raise ProviderError("missing_key", self.available()[1])
        base = BASE_URL_V3 if self.api == "v3" else BASE_URL
        if self._http is None or self._http._key != key or self._http.base_url != base:
            self._http = HttpClient(base, key, factory=self._http_factory)
        return self._http

    @property
    def model_version(self) -> str:
        return (self.config.get("three_d.tripo_model_version") or DEFAULT_MODEL_VERSION) if self.config else DEFAULT_MODEL_VERSION

    # ----- phản hồi -----
    def _parse(self, resp) -> dict:
        try:
            data = resp.json()
        except ValueError:
            data = {}
        code = data.get("code") if isinstance(data, dict) else None
        if resp.status_code >= 400 or (code not in (None, 0)):
            msg = str((data or {}).get("message") or f"HTTP {resp.status_code}")[:200]
            hint = str((data or {}).get("suggestion") or "")[:120] if isinstance(data, dict) else ""
            if hint:
                msg = f"{msg}; {hint}"
            table = ERROR_KINDS_V3 if self.api == "v3" else ERROR_KINDS
            kind = table.get(int(code), "") if isinstance(code, int) else ""
            if not kind:
                kind = {401: "auth", 403: "quota" if "credit" in msg.lower() else "auth", 404: "not_found",
                        429: "rate_limit"}.get(resp.status_code, "server" if resp.status_code >= 500 else "failed")
            vi = {"auth": "Tripo từ chối API key hoặc không có quyền.", "quota": "Tài khoản Tripo không đủ credit.",
                  "rate_limit": "Tripo đang giới hạn tốc độ/số tác vụ đồng thời.",
                  "content_policy": "Tripo từ chối nội dung yêu cầu (chính sách nội dung).",
                  "server": "Máy chủ Tripo đang lỗi."}.get(kind, "Tripo báo lỗi")
            raise ProviderError(kind, f"{vi} ({msg})", retryable=kind in ("rate_limit", "server"), code=code)
        return data.get("data") or {}

    def _create(self, body: dict, kind: str) -> ProviderTask:
        data = self._parse(self._client().request("POST", "/task", json_body=body))
        tid = data.get("task_id")
        if not tid:
            raise ProviderError("failed", "Tripo không trả task_id")
        return ProviderTask(task_id=str(tid), kind=kind)

    # ----- v3 -----
    def _create_v3(self, path: str, body: dict, kind: str) -> ProviderTask:
        data = self._parse(self._client().request("POST", path, json_body=body))
        tid = data.get("task_id")
        if not tid:
            raise ProviderError("failed", "Tripo không trả task_id")
        return ProviderTask(task_id=str(tid), kind=kind)

    def _cfg(self, key: str, default: Any) -> Any:
        v = self.config.get(f"three_d.{key}") if self.config else None
        return default if v in (None, "") else v

    def _v3_opts(self, quality: str, pbr: bool) -> dict:
        """Mặc định texture HD + hình học Ultra (chi tiết, sát thật); chất lượng cao → texture 8K."""
        high = quality == "high"
        tex = str(self._cfg("tripo_texture_quality_high" if high else "tripo_texture_quality",
                            "extreme" if high else "detailed"))
        geo = str(self._cfg("tripo_geometry_quality", "detailed"))
        opts: dict[str, Any] = {"model": self.model_version, "texture": True, "pbr": bool(pbr), "texture_quality": tex}
        if not self.model_version.startswith("v2."):          # geometry_quality chỉ cho model ≥ v3.0
            opts["geometry_quality"] = geo
        face = int(self._cfg("tripo_face_limit", 0) or 0)
        if face:
            cap = 2_000_000 if geo == "detailed" else 1_500_000
            opts["face_limit"] = int(min(face, int(self._cfg("max_triangles", 2_000_000)), cap))
        if self.auto_size:
            opts["auto_size"] = True
        return opts

    def _upload_v3(self, image: bytes, mime: str) -> str:
        files = {"file": (f"image.{_mime_type(mime)}", image, mime)}
        data = self._parse(self._client().request("POST", "/files", files=files))
        token = data.get("file_token")
        if not token:
            raise ProviderError("failed", "Tripo không trả file_token khi tải ảnh lên")
        return str(token)

    def _quality_opts(self, quality: str, pbr: bool) -> dict:
        high = quality == "high"
        opts = {"model_version": self.model_version, "texture": True, "pbr": bool(pbr),
                "texture_quality": "detailed" if high else "standard"}
        if high:
            opts["geometry_quality"] = "detailed"
        limit = int(self.config.get("three_d.max_triangles") or 2_000_000) if self.config else 2_000_000
        opts["face_limit"] = int(min(limit, 500_000 if high else 200_000))
        return opts

    # ----- tạo -----
    def create_from_text(self, prompt: str, *, negative_prompt: str = "", pbr: bool = True, quality: str = "standard",
                         face_limit: int | None = None) -> ProviderTask:
        if self.api == "v3":
            body = {"prompt": prompt[:1024], **self._v3_opts(quality, pbr)}
            if negative_prompt:
                body["negative_prompt"] = negative_prompt[:255]
            if face_limit:
                body["face_limit"] = int(face_limit)
            return self._create_v3("/generation/text-to-model", body, "text_to_model")
        body = {"type": "text_to_model", "prompt": prompt[:1024], **self._quality_opts(quality, pbr)}
        if negative_prompt:
            body["negative_prompt"] = negative_prompt[:255]
        if face_limit:
            body["face_limit"] = int(face_limit)
        return self._create(body, "text_to_model")

    def _upload(self, image: bytes, mime: str) -> dict:
        files = {"file": (f"image.{_mime_type(mime)}", image, mime)}
        data = self._parse(self._client().request("POST", "/upload", files=files))
        token = data.get("image_token") or data.get("file_token")
        if not token:
            raise ProviderError("failed", "Tripo không trả image_token khi tải ảnh lên")
        return {"type": _mime_type(mime), "file_token": token}

    def create_from_image(self, image: bytes, mime: str, *, pbr: bool = True, quality: str = "standard") -> ProviderTask:
        if self.api == "v3":
            body = {"input": self._upload_v3(image, mime), **self._v3_opts(quality, pbr)}
            return self._create_v3("/generation/image-to-model", body, "image_to_model")
        body = {"type": "image_to_model", "file": self._upload(image, mime), **self._quality_opts(quality, pbr)}
        return self._create(body, "image_to_model")

    def create_from_multiview(self, images: dict[str, tuple[bytes, str]], *, pbr: bool = True,
                              quality: str = "standard") -> ProviderTask:
        if "front" not in images or len(images) < 2:
            raise ProviderError("invalid", "Multiview cần ảnh trước (front) và ít nhất 2 ảnh")
        if self.api == "v3":
            inputs = [{v: self._upload_v3(*images[v])} for v in ("front", "left", "back", "right") if v in images]
            return self._create_v3("/generation/multiview-to-model", {"inputs": inputs, **self._v3_opts(quality, pbr)},
                                   "multiview_to_model")
        files = [self._upload(*images[v]) if v in images else {} for v in ("front", "left", "back", "right")]
        body = {"type": "multiview_to_model", "files": files, **self._quality_opts(quality, pbr)}
        return self._create(body, "multiview_to_model")

    # ----- theo dõi / tải -----
    def get_job_status(self, task: ProviderTask) -> ProviderTask:
        if self.api == "v3":
            return self._status_v3(task)
        data = self._parse(self._client().request("GET", f"/task/{task.task_id}"))
        raw = str(data.get("status", "unknown"))
        task.raw_status = raw
        task.status = STATUS_MAP.get(raw, "failed")
        try:
            task.progress = float(data.get("progress") or 0)
        except (TypeError, ValueError):
            pass
        out = data.get("output") or {}
        task.outputs = {k: str(v) for k, v in out.items() if isinstance(v, str) and v.startswith("http")}
        if data.get("consumed_credit") is not None:
            try:
                task.credits = float(data["consumed_credit"])
            except (TypeError, ValueError):
                pass
        if task.status == "failed":
            task.error = str(data.get("error_msg") or f"Tripo báo trạng thái {raw}")
        return task

    def _status_v3(self, task: ProviderTask) -> ProviderTask:
        data = self._parse(self._client().request("GET", f"/tasks/{task.task_id}"))
        raw = str(data.get("status", "failed"))
        task.raw_status = raw
        task.status = STATUS_MAP.get(raw, "failed")
        try:
            task.progress = float(data.get("progress") or 0)
        except (TypeError, ValueError):
            pass
        out = data.get("output") or {}
        # v3: model_url, pbr_model_url, rendered_image_url… → khóa kiểu v2 (model, pbr_model…) để phần tải dùng chung
        task.outputs = {(k[:-4] if k.endswith("_url") else k): str(v) for k, v in out.items()
                        if isinstance(v, str) and v.startswith("http")}
        if data.get("credits_consumed") is not None:
            try:
                task.credits = float(data["credits_consumed"])
            except (TypeError, ValueError):
                pass
        if task.status == "failed":
            task.error = str(data.get("error_message") or data.get("error_msg") or f"Tripo báo trạng thái {raw}")
            if data.get("error_code"):
                task.error += f" (mã {data['error_code']})"
        return task

    def download_result(self, task: ProviderTask, dest: Path, max_bytes: int,
                        cancelled: Callable[[], bool] | None = None) -> Path:
        url = task.outputs.get("pbr_model") or task.outputs.get("model") or task.outputs.get("base_model")
        if not url:
            raise ProviderError("failed", "Tác vụ Tripo không có tệp mô hình để tải")
        return self._client().download(url, dest, max_bytes, cancelled)

    # ----- hậu xử lý -----
    def segment_model(self, task: ProviderTask) -> ProviderTask:
        if self.api == "v3":
            model = str(self._cfg("tripo_segment_model", SEGMENT_V2_MODEL))
            body: dict[str, Any] = {"input": task.task_id, "model": model}
            if model == SEGMENT_V2_MODEL:
                body.update({"segmentation_granularity": "balanced", "split_by_connectivity": True})
            return self._create_v3("/mesh/segment", body, "mesh_segmentation")
        return self._create({"type": "mesh_segmentation", "original_model_task_id": task.task_id,
                             "model_version": SEGMENT_MODEL_VERSION}, "mesh_segmentation")

    def remesh_model(self, task: ProviderTask, face_limit: int) -> ProviderTask:
        if self.api == "v3":
            raise ProviderError("unsupported", "Retopology v3 (/mesh/decimate) chưa dùng — tham số chưa đối chiếu")
        return self._create({"type": "highpoly_to_lowpoly", "original_model_task_id": task.task_id, "quad": False,
                             "face_limit": int(max(500, min(20000, face_limit)))}, "highpoly_to_lowpoly")

    def generate_texture(self, task: ProviderTask, prompt: str, pbr: bool = True) -> ProviderTask:
        if self.api == "v3":
            raise ProviderError("unsupported", "Texture v3 (/models/texture) chưa dùng — tham số chưa đối chiếu")
        return self._create({"type": "texture_model", "original_model_task_id": task.task_id,
                             "texture_prompt": {"text": prompt[:1024]}, "texture": True, "pbr": bool(pbr)}, "texture_model")

    def refine_model(self, task: ProviderTask) -> ProviderTask:
        # Chỉ có trong SDK (bản nháp v1.4); chưa kiểm chứng với model mới — pipeline không dùng mặc định.
        if self.api == "v3":
            raise ProviderError("unsupported", "refine_model chỉ dành cho bản nháp v1.4 (API v2)")
        return self._create({"type": "refine_model", "draft_model_task_id": task.task_id}, "refine_model")

    def balance(self) -> float | None:
        try:
            path = "/account/balance" if self.api == "v3" else "/user/balance"
            data = self._parse(self._client().request("GET", path, retries=0))
            return float(data.get("balance")) if data.get("balance") is not None else None
        except ProviderError:
            return None
