"""Meshy API (https://api.meshy.ai) — đối chiếu tài liệu chính thức 2026-09-25: docs.meshy.ai (text-to-3d, image-to-3d,
multi-image-to-3d, remesh, retexture, balance, errors, rate limits, asset retention, changelog).

- Xác thực: "Authorization: Bearer <MESHY_API_KEY>" (msy_…). Tạo tác vụ trả {"result": "<task_id>"}; lỗi {"message"}.
- Text to 3D hai bước: POST /openapi/v2/text-to-3d {"mode": "preview", "prompt"} → hình học; rồi {"mode": "refine",
  "preview_task_id", "enable_pbr"} → texture PBR.
- Image to 3D: POST /openapi/v1/image-to-3d {"image_url": data URI}; Multi-Image: /openapi/v1/multi-image-to-3d
  {"image_urls": [1–4 ảnh]}; Remesh: /openapi/v1/remesh; Retexture: /openapi/v1/retexture.
- GET …/{id}: status ∈ PENDING, IN_PROGRESS, SUCCEEDED, FAILED, CANCELED; progress 0–100; model_urls.glb;
  task_error.message. DELETE …/{id}: task PENDING được hoàn credit (IN_PROGRESS trả 409) — cách hủy duy nhất.
- Asset giữ tối đa 3 ngày → NEXA tải về cache ngay. Không có API tách bộ phận.
Chi phí (credit): preview 20 (meshy-6-lite: 5), refine 10, image-to-3D 20–35, remesh 5.
"""
from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any, Callable

from nexa.three_d.generation.base import ProviderError, ProviderTask, ThreeDProvider
from nexa.three_d.generation.http import HttpClient
from nexa.utils.config import is_placeholder_secret

BASE_URL = "https://api.meshy.ai"
ENDPOINTS = {"text_preview": "/openapi/v2/text-to-3d", "text_refine": "/openapi/v2/text-to-3d",
             "image_to_model": "/openapi/v1/image-to-3d", "multiview_to_model": "/openapi/v1/multi-image-to-3d",
             "remesh": "/openapi/v1/remesh", "retexture": "/openapi/v1/retexture"}
STATUS_MAP = {"PENDING": "queued", "IN_PROGRESS": "running", "SUCCEEDED": "success", "FAILED": "failed",
              "CANCELED": "cancelled"}


def _data_uri(image: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(image).decode("ascii")


class MeshyProvider(ThreeDProvider):
    reference_views = {"front", "back", "left", "right"}
    name = "meshy"
    capabilities = {"text_to_model", "image_to_model", "multiview_to_model", "remesh_model", "generate_texture",
                    "refine_model", "cancel_job"}

    def __init__(self, config: Any, http_factory: Callable[..., Any] | None = None) -> None:
        self.config = config
        self._http_factory = http_factory
        self._http: HttpClient | None = None

    def _key(self) -> str:
        k = os.environ.get("MESHY_API_KEY", "")
        return "" if is_placeholder_secret(k) else k.strip()

    def available(self) -> tuple[bool, str]:
        if not self._key():
            return False, "Chưa có MESHY_API_KEY trong .env nên chưa tạo mô hình bằng dịch vụ cloud Meshy được."
        return True, "Meshy API"

    def _client(self) -> HttpClient:
        key = self._key()
        if not key:
            raise ProviderError("missing_key", self.available()[1])
        if self._http is None or self._http._key != key:
            self._http = HttpClient(BASE_URL, key, factory=self._http_factory)
        return self._http

    @property
    def ai_model(self) -> str:
        return (self.config.get("three_d.meshy_ai_model") or "latest") if self.config else "latest"

    @staticmethod
    def _parse(resp) -> dict:
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if resp.status_code >= 400:
            msg = str((data or {}).get("message") or f"HTTP {resp.status_code}")[:200]
            kind = {400: "invalid", 401: "auth", 402: "quota", 403: "auth", 404: "not_found", 409: "failed",
                    429: "rate_limit"}.get(resp.status_code, "server" if resp.status_code >= 500 else "failed")
            vi = {"auth": "Meshy từ chối API key.", "quota": "Tài khoản Meshy không đủ credit.",
                  "rate_limit": "Meshy đang giới hạn tốc độ/hàng đợi.", "server": "Máy chủ Meshy đang lỗi."}.get(kind, "Meshy báo lỗi")
            raise ProviderError(kind, f"{vi} ({msg})", retryable=kind in ("rate_limit", "server"), code=resp.status_code)
        return data if isinstance(data, dict) else {}

    def _create(self, kind: str, body: dict) -> ProviderTask:
        data = self._parse(self._client().request("POST", ENDPOINTS[kind], json_body=body))
        tid = data.get("result")
        if not tid:
            raise ProviderError("failed", "Meshy không trả mã tác vụ")
        return ProviderTask(task_id=str(tid), kind=kind)

    def _polycount(self, quality: str) -> int:
        limit = int(self.config.get("three_d.max_triangles") or 2_000_000) if self.config else 2_000_000
        return int(min(limit, 300_000 if quality == "high" else 100_000))

    def create_from_text(self, prompt: str, *, negative_prompt: str = "", pbr: bool = True, quality: str = "standard",
                         face_limit: int | None = None) -> ProviderTask:
        body = {"mode": "preview", "prompt": prompt[:800], "ai_model": self.ai_model, "topology": "triangle",
                "target_polycount": int(face_limit or self._polycount(quality)), "should_remesh": True}
        return self._create("text_preview", body)

    def refine_model(self, task: ProviderTask) -> ProviderTask:
        """Bước texture PBR cho kết quả preview (Text to 3D refine)."""
        body = {"mode": "refine", "preview_task_id": task.task_id, "enable_pbr": True, "ai_model": self.ai_model}
        return self._create("text_refine", body)

    def create_from_image(self, image: bytes, mime: str, *, pbr: bool = True, quality: str = "standard") -> ProviderTask:
        body = {"image_url": _data_uri(image, mime), "should_texture": True, "enable_pbr": bool(pbr),
                "ai_model": self.ai_model, "target_polycount": self._polycount(quality), "should_remesh": True}
        return self._create("image_to_model", body)

    def create_from_multiview(self, images: dict[str, tuple[bytes, str]], *, pbr: bool = True,
                              quality: str = "standard") -> ProviderTask:
        urls = [_data_uri(*images[v]) for v in ("front", "left", "back", "right") if v in images][:4]
        if not urls:
            raise ProviderError("invalid", "Multi-image cần 1–4 ảnh")
        body = {"image_urls": urls, "should_texture": True, "enable_pbr": bool(pbr), "ai_model": self.ai_model,
                "target_polycount": self._polycount(quality), "should_remesh": True}
        return self._create("multiview_to_model", body)

    def get_job_status(self, task: ProviderTask) -> ProviderTask:
        data = self._parse(self._client().request("GET", f"{ENDPOINTS[task.kind]}/{task.task_id}"))
        raw = str(data.get("status", "FAILED"))
        task.raw_status = raw
        task.status = STATUS_MAP.get(raw, "failed")
        try:
            task.progress = float(data.get("progress") or 0)
        except (TypeError, ValueError):
            pass
        urls = data.get("model_urls") or {}
        task.outputs = {k: str(v) for k, v in urls.items() if isinstance(v, str) and v.startswith("http")}
        if isinstance(data.get("thumbnail_url"), str):
            task.outputs["rendered_image"] = data["thumbnail_url"]
        if data.get("consumed_credits") is not None:
            try:
                task.credits = float(data["consumed_credits"])
            except (TypeError, ValueError):
                pass
        if task.status == "failed":
            err = data.get("task_error") or {}
            task.error = str(err.get("message") if isinstance(err, dict) else err or "Meshy báo thất bại")
        return task

    def cancel_job(self, task: ProviderTask) -> bool:
        try:
            resp = self._client().request("DELETE", f"{ENDPOINTS[task.kind]}/{task.task_id}", retries=0)
        except ProviderError:
            return False
        return resp.status_code in (200, 204)

    def download_result(self, task: ProviderTask, dest: Path, max_bytes: int,
                        cancelled: Callable[[], bool] | None = None) -> Path:
        url = task.outputs.get("glb")
        if not url:
            raise ProviderError("failed", "Tác vụ Meshy không có tệp GLB")
        return self._client().download(url, dest, max_bytes, cancelled)

    def remesh_model(self, task: ProviderTask, face_limit: int) -> ProviderTask:
        return self._create("remesh", {"input_task_id": task.task_id, "target_formats": ["glb"], "topology": "triangle",
                                       "target_polycount": int(max(100, min(300_000, face_limit)))})

    def generate_texture(self, task: ProviderTask, prompt: str, pbr: bool = True) -> ProviderTask:
        return self._create("retexture", {"input_task_id": task.task_id, "text_style_prompt": prompt[:600],
                                          "enable_pbr": bool(pbr), "ai_model": self.ai_model})

    def balance(self) -> float | None:
        try:
            data = self._parse(self._client().request("GET", "/openapi/v1/balance", retries=0))
            return float(data.get("balance")) if data.get("balance") is not None else None
        except ProviderError:
            return None
