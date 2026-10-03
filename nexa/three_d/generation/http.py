"""HTTP dùng chung cho provider 3D (httpx, đồng bộ): timeout, ánh xạ lỗi, tải tệp có giới hạn dung lượng và hủy.

Không bao giờ ghi API key vào log/thông báo (logging đã lọc key đã đăng ký; ở đây còn cắt bỏ header).
"""
from __future__ import annotations

import time
import math
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable

import httpx

from nexa.three_d.generation.base import ProviderError
from nexa.utils.logging import get_logger, register_secret

log = get_logger("3d.http")


def retry_delay(value: str | None, attempt: int) -> float:
    """Bounded backoff; Retry-After may be seconds or an HTTP date."""
    fallback = min(8.0, 1.5 * 2 ** attempt)
    if not value:
        return fallback
    try:
        delay = float(value)
    except (ValueError, TypeError):
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            delay = date.timestamp() - time.time()
        except (ValueError, TypeError, OverflowError):
            return fallback
    return min(8.0, max(0.0, delay)) if math.isfinite(delay) else fallback


class HttpClient:
    def __init__(self, base_url: str, api_key: str, timeout_s: float = 30.0,
                 factory: Callable[..., httpx.Client] | None = None) -> None:
        register_secret(api_key)
        self.base_url = base_url.rstrip("/")
        self._key = api_key
        self._timeout = timeout_s
        make = factory or httpx.Client
        self._client = make(timeout=httpx.Timeout(timeout_s, connect=10.0), follow_redirects=False)

    def _headers(self, extra: dict | None = None) -> dict:
        h = {"Authorization": f"Bearer {self._key}", "Accept": "application/json"}
        if extra:
            h.update(extra)
        return h

    def request(self, method: str, path: str, *, json_body: Any = None, files: Any = None, params: dict | None = None,
                retries: int = 2) -> httpx.Response:
        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        # A lost response does not mean a POST was rejected. Never replay a paid
        # submission/upload or other mutation without provider-specific idempotency.
        safe = method.upper() in ("GET", "HEAD", "OPTIONS")
        retries = max(0, int(retries)) if safe else 0
        last: ProviderError | None = None
        for attempt in range(retries + 1):
            try:
                resp = self._client.request(method, url, json=json_body, files=files, params=params, headers=self._headers())
            except httpx.TimeoutException:
                if not safe:
                    raise ProviderError("submission_unknown", "Chưa xác định dịch vụ đã nhận yêu cầu hay chưa. "
                                        "NEXA không gửi lại; hãy kiểm tra tác vụ trên dịch vụ trước khi tạo lại.") from None
                last = ProviderError("timeout", "Dịch vụ 3D phản hồi quá thời gian chờ.", retryable=True)
            except httpx.HTTPError as exc:
                if not safe:
                    raise ProviderError("submission_unknown", "Mất kết nối khi gửi yêu cầu. NEXA không gửi lại để "
                                        "tránh tạo trùng; hãy kiểm tra tác vụ trên dịch vụ trước khi tạo lại.") from None
                last = ProviderError("network", f"Không kết nối được dịch vụ 3D ({type(exc).__name__}).", retryable=True)
            else:
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                    time.sleep(retry_delay(resp.headers.get("Retry-After"), attempt))
                    continue
                return resp
            if attempt < retries:
                time.sleep(min(8.0, 1.5 * 2 ** attempt))
        raise last or ProviderError("network", "Lỗi mạng không xác định")

    def download(self, url: str, dest: Path, max_bytes: int, cancelled: Callable[[], bool] | None = None) -> Path:
        """Tải URL đã ký sẵn (không gửi API key) vào dest, dừng nếu vượt max_bytes hoặc bị hủy."""
        if not url.startswith("https://"):
            raise ProviderError("invalid", "URL kết quả không phải HTTPS — từ chối tải.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        total = 0
        try:
            with self._client.stream("GET", url, headers={"Accept": "*/*"}, timeout=httpx.Timeout(120.0, connect=10.0)) as r:
                if r.status_code != 200:
                    raise ProviderError("failed", f"Tải kết quả thất bại (HTTP {r.status_code}).")
                declared = int(r.headers.get("Content-Length") or 0)
                if declared and declared > max_bytes:
                    raise ProviderError("invalid", f"Tệp kết quả {declared / 1e6:.0f} MB vượt giới hạn {max_bytes / 1e6:.0f} MB.")
                with tmp.open("wb") as fh:
                    for chunk in r.iter_bytes(65536):
                        if cancelled and cancelled():
                            raise ProviderError("cancelled", "Đã hủy trong lúc tải.")
                        total += len(chunk)
                        if total > max_bytes:
                            raise ProviderError("invalid", f"Tệp kết quả vượt giới hạn {max_bytes / 1e6:.0f} MB.")
                        fh.write(chunk)
        except httpx.HTTPError as exc:
            tmp.unlink(missing_ok=True)
            raise ProviderError("network", f"Lỗi mạng khi tải kết quả ({type(exc).__name__}).", retryable=True) from exc
        except ProviderError:
            tmp.unlink(missing_ok=True)
            raise
        tmp.replace(dest)
        log.info("Đã tải kết quả 3D %d KB", total // 1024)
        return dest

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass
