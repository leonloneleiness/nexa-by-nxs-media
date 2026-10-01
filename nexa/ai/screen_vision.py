"""Đọc màn hình theo yêu cầu bằng Gemini (chỉ khi NEXA_CLOUD_SCREEN_VISION=true).

Ảnh chỉ được chụp khi người dùng yêu cầu, hiển thị xem trước để người dùng cắt vùng và bấm Đồng ý
(qua cơ chế xác nhận của executor), sau đó mới gửi đúng vùng đã chọn. Ảnh được thu nhỏ (cạnh dài
tối đa 1600 px) và mã hóa PNG/JPEG — định dạng Gemini API hỗ trợ. Tệp tạm bị xóa sau khi gửi.
NEXA không khẳng định tự phát hiện được mọi thông tin bí mật trong ảnh; người dùng tự chọn vùng.
"""
from __future__ import annotations

import io
from typing import Any, Callable

from nexa.core.events import ToolResult
from nexa.core.safety import Cancelled
from nexa.utils.logging import get_logger

log = get_logger("vision")

MAX_SIDE = 1600
MAX_BYTES = 4 * 1024 * 1024


def prepare_image(path: str, crop: list[float] | None = None) -> tuple[bytes, str, tuple[int, int]]:
    from PIL import Image
    with Image.open(path) as img:
        img = img.convert("RGB")
        if crop and len(crop) == 4:
            x, y, w, h = (int(round(v)) for v in crop)
            x, y = max(0, x), max(0, y)
            w, h = max(8, min(w, img.width - x)), max(8, min(h, img.height - y))
            img = img.crop((x, y, x + w, y + h))
        scale = min(1.0, MAX_SIDE / float(max(img.width, img.height)))
        if scale < 1.0:
            img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        data, mime = buf.getvalue(), "image/png"
        if len(data) > MAX_BYTES:
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=85)
            data, mime = buf.getvalue(), "image/jpeg"
        return data, mime, (img.width, img.height)


class ScreenVision:
    def __init__(self, config: Any, provider: Any, notify: Callable[[str, dict], None] | None = None) -> None:
        self.config = config
        self.provider = provider
        self.notify = notify

    def available(self) -> bool:
        return bool(self.config.cloud_screen_vision) and self.provider.status()[0]

    def describe(self, path: str, question: str, crop: list[float] | None, token: Any) -> ToolResult:
        if not self.config.cloud_screen_vision:
            return ToolResult.failure("Tính năng đọc màn hình đang tắt.", "vision_disabled")
        from nexa.ai.gemini_provider import AIError
        data, mime, size = prepare_image(path, crop)
        if self.notify:
            self.notify("vision_sending", {"active": True, "width": size[0], "height": size[1]})
        try:
            text = self.provider.describe_image(data, mime, question, token)
        except AIError as exc:
            return ToolResult.failure(exc.message, exc.kind)
        except Cancelled:
            return ToolResult.failure("Đã hủy gửi ảnh.", "cancelled")
        finally:
            if self.notify:
                self.notify("vision_sending", {"active": False})
        log.info("Đã gửi ảnh %dx%d (%d KB) cho Gemini", size[0], size[1], len(data) // 1024)
        return ToolResult.success(text, verified=True, image_size=list(size))
