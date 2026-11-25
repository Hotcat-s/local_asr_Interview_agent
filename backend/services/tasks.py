"""Serial job queue for ASR and LLM work.

Only one heavy job runs at a time.  This mirrors the old QThread behaviour and
avoids competing for GPU memory / model weights while keeping the HTTP server
responsive.
"""

from __future__ import annotations

import logging
import queue
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from core.exceptions import CancelledError
from core.progress import ProgressEvent

if TYPE_CHECKING:
    from backend.runtime import AppState

logger = logging.getLogger(__name__)

JobKind = Literal["transcribe", "analyze"]
JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class Job:
    id: str
    recording_id: int
    kind: JobKind
    previous_status: str
    status: JobStatus = "queued"
    stage: str = "queued"
    percent: float = 0.0
    message: str = "排队中"
    detail: str = ""
    error: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "recording_id": self.recording_id,
            "kind": self.kind,
            "status": self.status,
            "stage": self.stage,
            "percent": round(self.percent, 1),
            "message": self.message,
            "detail": self.detail,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TaskQueue:
    def __init__(self, state: AppState) -> None:
        self._state = state
        self._queue: queue.Queue[Job | None] = queue.Queue()
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._worker = threading.Thread(
            target=self._run,
            name="interview-task-worker",
            daemon=True,
        )
        self._worker.start()

    # ------------------------------------------------------------------ public

    def submit(self, recording_id: int, kind: JobKind) -> Job:
        recording = self._state.repo.get_recording(recording_id)
        if recording is None:
            raise KeyError(f"Recording {recording_id} was not found")

        with self._lock:
            active = [
                job
                for job in self._jobs.values()
                if job.recording_id == recording_id and job.status in {"queued", "running"}
            ]
            if active:
                raise RuntimeError("该录音已有任务在运行")
            job = Job(
                id=uuid.uuid4().hex[:12],
                recording_id=recording_id,
                kind=kind,
                previous_status=recording.status,
            )
            self._jobs[job.id] = job

        self._queue.put(job)
        self._publish(job)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def active(self) -> list[Job]:
        with self._lock:
            return [job for job in self._jobs.values() if job.status in {"queued", "running"}]

    def cancel_recording(self, recording_id: int) -> Job | None:
        with self._lock:
            job = next(
                (
                    item
                    for item in self._jobs.values()
                    if item.recording_id == recording_id
                    and item.status in {"queued", "running"}
                ),
                None,
            )
        if job is None:
            return None

        job.cancel_event.set()
        if job.status == "queued":
            self._set(job, status="cancelled", stage="cancelled", message="已取消")
            self._restore_status(job)
        else:
            self._set(job, message="正在取消…")
        return job

    def stop(self) -> None:
        self._queue.put(None)
        self._worker.join(timeout=5)

    # ------------------------------------------------------------------ worker

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            try:
                if job is None:
                    return
                if job.cancel_event.is_set():
                    self._set(job, status="cancelled", stage="cancelled", message="已取消")
                    self._restore_status(job)
                    continue

                self._set(job, status="running", stage="start", message="任务开始")
                try:
                    if job.kind == "transcribe":
                        self._transcribe(job)
                    else:
                        self._analyze(job)
                except CancelledError:
                    self._set(job, status="cancelled", stage="cancelled", message="已取消")
                    self._restore_status(job)
                except Exception as exc:  # noqa: BLE001 - surface any pipeline failure
                    logger.exception("Job %s failed", job.id)
                    self._set(
                        job,
                        status="failed",
                        stage="error",
                        message="任务失败",
                        error=str(exc),
                    )
                    self._state.repo.update_status(job.recording_id, "failed", str(exc))
                    self._publish_recording(job.recording_id, "failed", error=str(exc))
                else:
                    self._set(
                        job,
                        status="succeeded",
                        stage="done",
                        percent=100.0,
                        message="任务完成",
                    )
            finally:
                self._queue.task_done()

    def _transcribe(self, job: Job) -> None:
        state = self._state
        recording = state.repo.get_recording(job.recording_id)
        if recording is None:
            raise RuntimeError("录音已不存在")

        state.repo.update_status(job.recording_id, "transcribing")
        self._publish_recording(job.recording_id, "transcribing")

        engine = state.engine()
        transcript = engine.transcribe(
            recording.audio_path,
            progress=self._progress(job),
            chunk_seconds=state.config.chunk_seconds,
        )
        if job.cancel_event.is_set():
            raise CancelledError("任务已取消")

        # Persist the transcript before Q/A reconstruction so a failed pairing
        # step never destroys an otherwise valid transcription.
        state.repo.save_transcript(job.recording_id, transcript)
        qa_pairs = engine.build_qa(transcript, progress=self._progress(job))
        if job.cancel_event.is_set():
            raise CancelledError("任务已取消")
        state.repo.save_qa_pairs(job.recording_id, qa_pairs)
        state.repo.update_status(job.recording_id, "transcribed")
        self._publish_recording(job.recording_id, "transcribed")

    def _analyze(self, job: Job) -> None:
        state = self._state
        qa_pairs = state.repo.load_qa_pairs(job.recording_id)
        if not qa_pairs:
            raise RuntimeError("没有可分析的问答对，请先完成转写")

        state.repo.update_status(job.recording_id, "analyzing")
        self._publish_recording(job.recording_id, "analyzing")

        report = state.engine().analyze(
            qa_pairs,
            llm_config=state.config.llm,
            progress=self._progress(job),
            analysis_config=state.config.analysis,
        )
        if job.cancel_event.is_set():
            raise CancelledError("任务已取消")

        state.repo.save_report(job.recording_id, report)
        state.repo.mark_analyzed(job.recording_id, report.overall_score)
        self._publish_recording(job.recording_id, "analyzed")

    # ----------------------------------------------------------------- helpers

    def _progress(self, job: Job):
        def callback(event: ProgressEvent) -> None:
            if job.cancel_event.is_set():
                raise CancelledError("任务已取消")
            self._set(
                job,
                stage=event.stage,
                percent=event.percent,
                message=event.message,
                detail=event.detail,
            )

        return callback

    def _set(self, job: Job, **changes) -> None:
        for key, value in changes.items():
            setattr(job, key, value)
        job.updated_at = _now()
        self._publish(job)

    def _publish(self, job: Job) -> None:
        self._state.events.publish({"type": "job", "job": job.to_dict()})

    def _publish_recording(self, recording_id: int, status: str, error: str = "") -> None:
        self._state.events.publish(
            {
                "type": "recording",
                "recording_id": recording_id,
                "status": status,
                "error": error,
            }
        )

    def _restore_status(self, job: Job) -> None:
        previous = job.previous_status
        if previous in {"transcribing", "analyzing"}:
            previous = "imported" if job.kind == "transcribe" else "transcribed"
        try:
            self._state.repo.update_status(job.recording_id, previous)
            self._publish_recording(job.recording_id, previous)
        except Exception:  # noqa: BLE001 - the recording may have been deleted
            logger.exception("Failed to restore status for recording %s", job.recording_id)
