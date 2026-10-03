"""ThreeDService — mặt tiền duy nhất controller/tool registry/UI dùng để làm việc với mô hình 3D.

Gom: kho asset, planner, pipeline, JobManager (chạy nền), ViewerController (trạng thái viewer), máy trạng thái cử chỉ
VIEWER_3D. Nối với an toàn của NEXA: dừng khẩn cấp hủy mọi job và khóa tương tác; job đã hủy không bao giờ mở viewer.
"""
from __future__ import annotations

import threading
from typing import Any, Callable

from nexa.core.safety import CancelToken
from nexa.three_d.asset_store import AssetStore
from nexa.three_d.generation.base import get_provider
from nexa.three_d.gesture_controller import ViewerGestureParams, ViewerGestureStateMachine
from nexa.three_d.job_manager import Job, JobManager
from nexa.three_d.models import JobState
from nexa.three_d.pipeline import GenerationPipeline, summarize_report
from nexa.three_d.planner import LocalPlanner, Planner
from nexa.three_d.spec import CATEGORY_GROUP, ModelSpec, is_complete
from nexa.three_d.viewer_controller import ViewerController
from nexa.utils.logging import get_logger

log = get_logger("3d.service")


class ThreeDService:
    def __init__(self, config: Any, notify: Callable[[str, dict], None] | None = None, gemini: Any = None,
                 token_factory: Callable[[], CancelToken] | None = None, store: AssetStore | None = None,
                 provider_factory: Callable[[], Any] | None = None) -> None:
        self.config = config
        self._notify = notify or (lambda k, d: None)
        self.gemini = gemini
        self.store = store or AssetStore.from_config(config)
        self.planner = Planner(gemini, use_gemini=bool(config.get("three_d.use_gemini_planner", True)))
        self.provider_factory = provider_factory or (lambda: get_provider(config, gemini=gemini))
        self.pipeline = GenerationPipeline(config, self.store, self.planner, gemini, self.provider_factory)
        self.jobs = JobManager(self.pipeline.run, max_workers=1,
                               timeout_s=float(config.get("three_d.generation_timeout_s") or 900),
                               token_factory=token_factory)
        self.viewer = ViewerController(self.store, self._notify, on_open_change=self._on_viewer_open)
        self.gesture_sm = ViewerGestureStateMachine(ViewerGestureParams.from_config(config))
        self._gesture_lock = threading.Lock()
        self.jobs.add_listener(lambda snap: self._notify("3d_job", snap))
        self.jobs.add_finish_listener(self._on_finished)
        # do controller gắn: phản hồi (chữ, câu đọc), đặt câu chờ trả lời (resume), bật/tắt chế độ cử chỉ viewer
        self.on_message: Callable[[str, str], None] | None = None
        self.on_resume: Callable[[str], None] | None = None
        self.on_viewer_mode: Callable[[bool], None] | None = None
        self._latest_job: str | None = None
        self.locked = False
        self.media_cancel = threading.Event()

    # ----- cấu hình -----
    @property
    def enabled(self) -> bool:
        return bool(self.config.get("three_d.enabled", True))

    def reload_params(self) -> None:
        with self._gesture_lock:
            self.gesture_sm.update_params(ViewerGestureParams.from_config(self.config))
        self.jobs.timeout_s = float(self.config.get("three_d.generation_timeout_s") or 900)

    def provider_status(self) -> dict:
        prov = self.provider_factory()
        if prov is None:
            return {"name": "none", "ok": False, "reason": "Chưa chọn dịch vụ 3D cloud (NEXA_3D_PROVIDER=none)."}
        ok, reason = prov.available()
        return {"name": prov.name, "ok": ok, "reason": reason, "free": bool(getattr(prov, "free_tier", False))}

    # ----- tạo mô hình -----
    def precheck(self, prompt: str) -> list[str]:
        """Câu hỏi thông số bắt buộc còn thiếu (nhanh, cục bộ) — chỉ với nhóm cơ khí, nơi con số là bắt buộc."""
        raw = LocalPlanner().parse(prompt)
        if CATEGORY_GROUP.get(raw["category"]) not in ("mechanical", "components"):
            return []
        return [q["question"] for q in is_complete(ModelSpec(category=raw["category"], params=raw["params"]))]

    def submit(self, prompt: str, mode: str = "auto", quality: str = "standard", source: str = "keyboard",
               open_when_ready: bool = True, reference_images: dict[str, str] | None = None) -> Job:
        if not self.enabled or self.locked:
            raise RuntimeError("NEXA đang khóa hoặc tính năng 3D chưa bật.")
        if mode not in ("auto", "parametric", "cloud", "reference_cad") or quality not in ("standard", "high"):
            raise ValueError("Chế độ hoặc chất lượng tạo mô hình không hợp lệ.")
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Hãy nhập mô tả mô hình.")
        options = {"reference_images": dict(reference_images)} if reference_images else {}
        job = self.jobs.submit(prompt, mode=mode, quality=quality, source=source, open_when_ready=open_when_ready, **options)
        self._latest_job = job.id
        return job

    def cancel_jobs(self, reason: str = "Người dùng hủy") -> int:
        return self.jobs.cancel_all(reason)

    def _on_finished(self, job: Job) -> None:
        if job.state == JobState.READY:
            project = None
            try:
                project = self.store.load(job.project_id) if job.project_id else None
            except Exception:
                log.exception("Không nạp được dự án %s", job.project_id)
            if project is None:
                return
            text = f"Mô hình {project.name} đã sẵn sàng" + (" (lấy từ cache)" if job.cached else "") + ". "
            text += summarize_report(project.quality_report) if not project.quality_report.get("status") == "best_effort" \
                else "Đây là kết quả best effort (ngoài nhóm hỗ trợ). "
            from nexa.three_d.spec import SAFETY_CRITICAL
            if project.category in SAFETY_CRITICAL:
                text += " Lưu ý: mô hình chưa được kiểm chứng độ bền, trọng tâm, khí động học, tải trọng và an toàn vận hành."
            spoken = f"Mô hình {project.name} đã sẵn sàng."
            if job.open_when_ready and job.id == self._latest_job and not self.locked and bool(
                    self.config.get("three_d.open_viewer_when_ready", True)):
                try:
                    self.viewer.open(project.id)
                    spoken += " Em đã mở trình xem 3D."
                except Exception as exc:
                    text += f" (Không mở được viewer: {exc})"
            self._say(text, spoken)
        elif job.state == JobState.NEEDS_INPUT:
            q = job.questions[0] if job.questions else "Anh bổ sung thông tin giúp em."
            if self.on_resume and job.resume:
                self.on_resume(job.resume)
            self._say(q, q)
        elif job.state == JobState.FAILED:
            msg = job.error or "Tạo mô hình thất bại."
            if job.error_code == "quality_gate":
                self._say(msg + " Anh có thể nói 'mở mô hình vừa tạo' để xem bản chưa đạt, thử lại, hoặc bổ sung thông tin.",
                          "Mô hình chưa đạt tiêu chuẩn chất lượng.")
            else:
                self._say(msg, msg.split(".")[0] + ".")
        elif job.state == JobState.CANCELLED:
            self._notify("3d_job", job.snapshot())

    def _say(self, text: str, spoken: str) -> None:
        if self.on_message:
            try:
                self.on_message(text, spoken)
            except Exception:
                log.exception("on_message lỗi")

    # ----- viewer / cử chỉ -----
    def _on_viewer_open(self, open_: bool) -> None:
        with self._gesture_lock:
            self.gesture_sm.reset("mở viewer" if open_ else "đóng viewer")
        if self.on_viewer_mode:
            self.on_viewer_mode(open_)

    @property
    def viewer_active(self) -> bool:
        return self.viewer.is_open

    def feed_gesture(self, obs: Any, t_frame: float | None = None) -> list:
        """Gọi từ luồng camera khi ở chế độ VIEWER_3D."""
        import time as _t
        with self._gesture_lock:
            events = self.gesture_sm.update(obs, self.viewer.exploded)
        for ev in events:
            if ev.kind == "rotate" and t_frame is not None:
                ev.extra["latency_ms"] = (_t.monotonic() - t_frame) * 1000.0
            self.viewer.apply_gesture(ev)
        return events

    def toggle_animation(self, source: str = "") -> tuple[bool, str]:
        if not self.viewer.is_open:
            return False, "Chưa mở mô hình 3D nào."
        ok, msg = self.viewer.toggle_animation()
        if source:
            log.info("Bật/tắt chuyển động 3D (%s): %s", source, "chạy" if self.viewer.animating else "dừng")
        if source in ("mic", "camera"):
            self._notify("3d_toast", {"text": msg, "error": not ok})
        return ok, msg

    def set_animation(self, on: bool) -> tuple[bool, str]:
        return self.viewer.set_animating(on)

    def on_emergency(self, reason: str) -> None:
        self.locked = True
        self.media_cancel.set()
        n = self.jobs.cancel_all(f"dừng khẩn cấp: {reason}")
        with self._gesture_lock:
            self.gesture_sm.lock(True)
        self.viewer.lock(True, reason)
        if n:
            log.warning("Dừng khẩn cấp: hủy %d job 3D", n)

    def on_resume_control(self) -> None:
        self.locked = False
        with self._gesture_lock:
            self.gesture_sm.lock(False)
        self.viewer.lock(False)

    def status(self) -> dict:
        latest = self.jobs.latest()
        return {"enabled": self.enabled, "provider": self.provider_status(), "active_jobs": len(self.jobs.active()),
                "latest_job": latest.snapshot() if latest else None, "viewer_open": self.viewer.is_open,
                "cache_mb": round(self.store.total_bytes() / 1e6, 1), "gesture": self.gesture_sm.status(),
                "perf": self.viewer.perf()}

    def shutdown(self) -> None:
        self.media_cancel.set()
        self.jobs.shutdown()
