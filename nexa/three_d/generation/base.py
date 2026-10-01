"""ThreeDProvider — lớp trừu tượng cho dịch vụ tạo mô hình 3D (cloud) và các kiểu lỗi/tác vụ chung.

Provider thật (tripo_provider.py, meshy_provider.py) chỉ bọc đúng các endpoint trong tài liệu chính thức
(kiểm tra 2026-09-25). Khi thiếu API key: `available()` trả (False, lý do) — pipeline báo rõ, KHÔNG giả vờ đã tạo.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


class ProviderError(Exception):
    """kind: missing_key | auth | quota | rate_limit | network | timeout | invalid | unsupported | failed |
    content_policy | cancelled | not_found | server"""

    def __init__(self, kind: str, message: str, retryable: bool = False, code: Any = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.retryable = retryable
        self.code = code


@dataclass
class ProviderTask:
    task_id: str
    kind: str                               # text_to_model | image_to_model | multiview_to_model | segment | …
    status: str = "queued"                  # queued | running | success | failed | cancelled
    progress: float = 0.0                   # 0..100
    outputs: dict[str, str] = field(default_factory=dict)   # model | pbr_model | rendered_image … → URL
    error: str = ""
    credits: float | None = None
    raw_status: str = ""

    @property
    def done(self) -> bool:
        return self.status in ("success", "failed", "cancelled")


CAPABILITIES = {"text_to_model", "image_to_model", "multiview_to_model", "refine_model", "segment_model",
                "remesh_model", "generate_texture", "cancel_job"}


class ThreeDProvider(ABC):
    name: str = "base"
    capabilities: set[str] = set()

    @abstractmethod
    def available(self) -> tuple[bool, str]: ...

    @abstractmethod
    def create_from_text(self, prompt: str, *, negative_prompt: str = "", pbr: bool = True, quality: str = "standard",
                         face_limit: int | None = None) -> ProviderTask: ...

    def create_from_image(self, image: bytes, mime: str, *, pbr: bool = True, quality: str = "standard") -> ProviderTask:
        raise ProviderError("unsupported", f"{self.name} không hỗ trợ ảnh → 3D")

    def create_from_multiview(self, images: dict[str, tuple[bytes, str]], *, pbr: bool = True,
                              quality: str = "standard") -> ProviderTask:
        raise ProviderError("unsupported", f"{self.name} không hỗ trợ nhiều ảnh → 3D")

    @abstractmethod
    def get_job_status(self, task: ProviderTask) -> ProviderTask: ...

    def cancel_job(self, task: ProviderTask) -> bool:
        """Hủy phía dịch vụ nếu API có hỗ trợ; trả False nếu không (NEXA vẫn bỏ qua kết quả đến muộn)."""
        return False

    @abstractmethod
    def download_result(self, task: ProviderTask, dest: Path, max_bytes: int,
                        cancelled: Callable[[], bool] | None = None) -> Path: ...

    def refine_model(self, task: ProviderTask) -> ProviderTask:
        raise ProviderError("unsupported", f"{self.name} không hỗ trợ refine")

    def segment_model(self, task: ProviderTask) -> ProviderTask:
        raise ProviderError("unsupported", f"{self.name} không hỗ trợ tách bộ phận")

    def remesh_model(self, task: ProviderTask, face_limit: int) -> ProviderTask:
        raise ProviderError("unsupported", f"{self.name} không hỗ trợ remesh")

    def generate_texture(self, task: ProviderTask, prompt: str, pbr: bool = True) -> ProviderTask:
        raise ProviderError("unsupported", f"{self.name} không hỗ trợ tạo texture")

    def balance(self) -> float | None:
        return None


def get_provider(config: Any, http_factory: Callable[..., Any] | None = None, gemini: Any = None) -> ThreeDProvider | None:
    """Provider theo NEXA_3D_PROVIDER (biến môi trường) hoặc three_d.provider. 'none' → None.

    'auto': Tripo nếu có TRIPO_API_KEY → Meshy nếu có MESHY_API_KEY → Hugging Face Space miễn phí (nếu bật).
    """
    import os
    name = (os.environ.get("NEXA_3D_PROVIDER") or config.get("three_d.provider") or "auto").strip().lower()
    if name == "tripo":
        from nexa.three_d.generation.tripo_provider import TripoProvider
        return TripoProvider(config, http_factory=http_factory)
    if name == "meshy":
        from nexa.three_d.generation.meshy_provider import MeshyProvider
        return MeshyProvider(config, http_factory=http_factory)
    if name in ("hf", "hf_space", "huggingface"):
        from nexa.three_d.generation.hf_provider import HFSpaceProvider
        return HFSpaceProvider(config, gemini=gemini)
    if name == "auto":
        from nexa.three_d.generation.meshy_provider import MeshyProvider
        from nexa.three_d.generation.tripo_provider import TripoProvider
        for cand in (TripoProvider(config, http_factory=http_factory), MeshyProvider(config, http_factory=http_factory)):
            if cand.available()[0]:
                return cand
        from nexa.three_d.generation.hf_provider import HFSpaceProvider
        return HFSpaceProvider(config, gemini=gemini)
    return None
