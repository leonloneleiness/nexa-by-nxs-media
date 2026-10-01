"""3D Job Manager: chạy việc tạo mô hình NỀN, ngoài executor tuần tự và ngoài luồng giao diện/cử chỉ.

- submit() trả Job ngay (trạng thái queued) — tool generate_3d_model trả job_id tức thì.
- Mỗi job có CancelToken riêng (mặc định gắn epoch của SafetyManager: dừng khẩn cấp / "hủy" tự hủy job).
- Watchdog: quá generation_timeout → hủy và báo lỗi timeout.
- Trạng thái cuối (ready/failed/cancelled/needs_input) là bất biến: kết quả đến muộn sau khi hủy KHÔNG thể chuyển
  job sang ready, nên không bao giờ mở viewer cho job đã hủy.
- Listener nhận ảnh chụp trạng thái (dict) sau mỗi thay đổi để UI hiện tiến độ.
"""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from nexa.core.safety import Cancelled, CancelToken
from nexa.three_d.models import JOB_STATE_LABELS_VI, TERMINAL_STATES, JobState
from nexa.utils.logging import get_logger

log = get_logger("3d.jobs")


class NeedsInput(Exception):
    """Thiếu thông số bắt buộc — job dừng ở needs_input kèm câu hỏi."""

    def __init__(self, questions: list[str], resume: str = "") -> None:
        super().__init__("; ".join(questions))
        self.questions = questions
        self.resume = resume


class JobFailed(Exception):
    def __init__(self, message: str, code: str = "failed") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass
class Job:
    id: str
    prompt: str
    mode: str = "auto"
    quality: str = "standard"
    source: str = "keyboard"
    open_when_ready: bool = True
    state: JobState = JobState.QUEUED
    progress: float = 0.0
    message: str = ""
    created: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    project_id: str | None = None
    error: str = ""
    error_code: str = ""
    questions: list[str] = field(default_factory=list)
    resume: str = ""
    warnings: list[str] = field(default_factory=list)
    cached: bool = False
    quality_score: float | None = None
    quality_status: str = ""
    stage_times: dict[str, float] = field(default_factory=dict)
    token: CancelToken | None = field(default=None, repr=False)
    options: dict[str, Any] = field(default_factory=dict)

    @property
    def terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def snapshot(self) -> dict:
        return {"id": self.id, "prompt": self.prompt, "mode": self.mode, "quality": self.quality, "state": self.state.value,
                "label": JOB_STATE_LABELS_VI[self.state], "progress": round(self.progress, 3), "message": self.message,
                "created": self.created, "started": self.started, "finished": self.finished,
                "project_id": self.project_id, "error": self.error, "error_code": self.error_code,
                "questions": list(self.questions), "warnings": list(self.warnings)[-6:], "cached": self.cached,
                "quality_score": self.quality_score, "quality_status": self.quality_status,
                "stage_times": dict(self.stage_times), "terminal": self.terminal,
                "elapsed": round((self.finished or time.time()) - (self.started or self.created), 2)}


class JobContext:
    """Truyền cho runner: báo tiến độ và kiểm tra hủy/quá hạn."""

    def __init__(self, manager: "JobManager", job: Job) -> None:
        self.manager = manager
        self.job = job
        self._stage_t0 = time.monotonic()
        self._stage: JobState | None = None

    @property
    def token(self) -> CancelToken:
        return self.job.token  # type: ignore[return-value]

    @property
    def cancelled(self) -> bool:
        return self.job.token is not None and self.job.token.cancelled

    def check(self) -> None:
        if self.cancelled:
            raise Cancelled(self.job.token.reason or "cancelled")

    def stage(self, state: JobState, progress: float, message: str = "") -> None:
        self.check()
        now = time.monotonic()
        if self._stage is not None:
            self.job.stage_times[self._stage.value] = round(self.job.stage_times.get(self._stage.value, 0.0) +
                                                            now - self._stage_t0, 3)
        self._stage, self._stage_t0 = state, now
        self.manager._update(self.job, state=state, progress=progress, message=message or JOB_STATE_LABELS_VI[state])

    def progress(self, progress: float, message: str = "") -> None:
        self.check()
        self.manager._update(self.job, progress=progress, message=message or None)

    def warn(self, text: str) -> None:
        self.job.warnings.append(text)

    def close_stage(self) -> None:
        if self._stage is not None:
            self.job.stage_times[self._stage.value] = round(self.job.stage_times.get(self._stage.value, 0.0) +
                                                            time.monotonic() - self._stage_t0, 3)
            self._stage = None


Runner = Callable[[Job, JobContext], str]


class JobManager:
    def __init__(self, runner: Runner, max_workers: int = 1, timeout_s: float = 900.0,
                 token_factory: Callable[[], CancelToken] | None = None, max_history: int = 50) -> None:
        self.runner = runner
        self.timeout_s = float(timeout_s)
        self.token_factory = token_factory or (lambda: CancelToken(None, 0, "3d"))
        self._pool = ThreadPoolExecutor(max_workers=max(1, int(max_workers)), thread_name_prefix="nexa-3d")
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._listeners: list[Callable[[dict], None]] = []
        self._finish_listeners: list[Callable[[Job], None]] = []
        self._max_history = max_history
        self._stop = threading.Event()
        self._watchdog = threading.Thread(target=self._watch, name="nexa-3d-watchdog", daemon=True)
        self._watchdog.start()

    # ----- listener -----
    def add_listener(self, fn: Callable[[dict], None]) -> None:
        self._listeners.append(fn)

    def add_finish_listener(self, fn: Callable[[Job], None]) -> None:
        """fn(job) khi job vào trạng thái cuối (gọi đúng một lần)."""
        self._finish_listeners.append(fn)

    def _emit(self, job: Job) -> None:
        snap = job.snapshot()
        for fn in list(self._listeners):
            try:
                fn(snap)
            except Exception:
                log.exception("Listener job 3D lỗi")

    # ----- API -----
    def submit(self, prompt: str, mode: str = "auto", quality: str = "standard", source: str = "keyboard",
               open_when_ready: bool = True, **options: Any) -> Job:
        job = Job(id="3d-" + uuid.uuid4().hex[:10], prompt=prompt, mode=mode, quality=quality, source=source,
                  open_when_ready=open_when_ready, token=self.token_factory(), options=options,
                  message="Đang xếp hàng")
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            while len(self._order) > self._max_history:
                old = self._order.pop(0)
                if self._jobs.get(old) is not None and self._jobs[old].terminal:
                    self._jobs.pop(old, None)
                else:
                    self._order.insert(0, old)
                    break
        self._emit(job)
        self._pool.submit(self._run, job)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def jobs(self) -> list[Job]:
        with self._lock:
            return [self._jobs[j] for j in self._order if j in self._jobs]

    def active(self) -> list[Job]:
        return [j for j in self.jobs() if not j.terminal]

    def latest(self) -> Job | None:
        js = self.jobs()
        return js[-1] if js else None

    def cancel(self, job_id: str, reason: str = "Người dùng hủy") -> bool:
        job = self.get(job_id)
        if job is None or job.terminal:
            return False
        if job.token is not None:
            job.token.cancel(reason)
        # queued: kết thúc ngay; đang chạy: runner sẽ gặp Cancelled ở lần kiểm tra kế tiếp — vẫn khóa trạng thái
        # ngay bây giờ để kết quả đến muộn không thể thành ready.
        self._finish(job, JobState.CANCELLED, message=f"Đã hủy ({reason})", code="cancelled")
        return True

    def cancel_all(self, reason: str = "Dừng khẩn cấp") -> int:
        return sum(1 for j in self.active() if self.cancel(j.id, reason))

    def shutdown(self) -> None:
        self._stop.set()
        self.cancel_all("Tắt NEXA")
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ----- nội bộ -----
    def _update(self, job: Job, state: JobState | None = None, progress: float | None = None,
                message: str | None = None) -> None:
        with self._lock:
            if job.terminal:
                raise Cancelled("job đã kết thúc")
            if state is not None:
                job.state = state
            if progress is not None:
                job.progress = float(min(1.0, max(job.progress if state is None else 0.0, progress)))
            if message is not None:
                job.message = message
        self._emit(job)

    def _finish(self, job: Job, state: JobState, message: str = "", code: str = "", project_id: str | None = None) -> bool:
        with self._lock:
            if job.terminal:
                return False                   # đã hủy/lỗi trước đó: bỏ qua kết quả đến muộn
            job.state = state
            job.finished = time.time()
            job.message = message or JOB_STATE_LABELS_VI[state]
            if state == JobState.READY:
                job.progress = 1.0
                job.project_id = project_id
            else:
                job.error = message if state != JobState.NEEDS_INPUT else ""
                job.error_code = code
        log.info("Job 3D %s → %s (%s)", job.id, state.value, message[:80])
        self._emit(job)
        for fn in list(self._finish_listeners):
            try:
                fn(job)
            except Exception:
                log.exception("Listener kết thúc job 3D lỗi")
        return True

    def _run(self, job: Job) -> None:
        if job.terminal:
            return
        job.started = time.time()
        ctx = JobContext(self, job)
        try:
            ctx.check()
            project_id = self.runner(job, ctx)
            ctx.close_stage()
            ctx.check()
            if not self._finish(job, JobState.READY, job.message if job.message.startswith("Mô hình") else "Mô hình đã sẵn sàng",
                                project_id=project_id):
                log.info("Job %s đã kết thúc trước khi có kết quả — bỏ kết quả đến muộn", job.id)
        except NeedsInput as exc:
            job.questions = exc.questions
            job.resume = exc.resume
            self._finish(job, JobState.NEEDS_INPUT, message=exc.questions[0] if exc.questions else "Cần thêm thông tin",
                         code="needs_input")
        except Cancelled as exc:
            reason = job.token.reason if job.token is not None else str(exc)
            if reason == "timeout":
                self._finish(job, JobState.FAILED, message="Quá thời gian tạo mô hình (timeout).", code="timeout")
            else:
                self._finish(job, JobState.CANCELLED, message=f"Đã hủy ({reason or 'hủy'})", code="cancelled")
        except JobFailed as exc:
            self._finish(job, JobState.FAILED, message=exc.message, code=exc.code)
        except Exception as exc:
            log.exception("Job 3D %s lỗi", job.id)
            self._finish(job, JobState.FAILED, message=f"Lỗi khi tạo mô hình: {type(exc).__name__}: {str(exc)[:160]}",
                         code="exception")
        finally:
            ctx.close_stage()

    def _watch(self) -> None:
        while not self._stop.wait(0.5):
            now = time.time()
            for job in self.active():
                if job.started and now - job.started > self.timeout_s:
                    log.warning("Job 3D %s quá %.0f s — hủy", job.id, self.timeout_s)
                    if job.token is not None:
                        job.token.cancel("timeout")
                    self._finish(job, JobState.FAILED, message="Quá thời gian tạo mô hình (timeout).", code="timeout")
