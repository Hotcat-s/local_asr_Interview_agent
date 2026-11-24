"""Progress reporting primitives shared with the UI layer.

Stages are exported as constants so the UI never has to hard-code strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

# Stage identifiers -----------------------------------------------------------
STAGE_LOAD = "load"          # read / normalise audio
STAGE_MODEL = "model"        # load the ASR models
STAGE_VAD = "vad"            # voice activity detection
STAGE_ASR = "asr"            # speech recognition
STAGE_DIARIZE = "diarize"    # speaker merge / alignment
STAGE_SEGMENT = "segment"    # optional semantic segmentation
STAGE_QA = "qa"              # question / answer pairing
STAGE_LLM = "llm"            # per-batch LLM analysis
STAGE_SUMMARY = "summary"    # overall summary
STAGE_SAVE = "save"          # persistence
STAGE_DONE = "done"
STAGE_ERROR = "error"


@dataclass
class ProgressEvent:
    """A single progress notification emitted during a long running task."""

    stage: str
    current: int
    total: int
    percent: float
    message: str
    detail: str = ""


ProgressCallback = Callable[[ProgressEvent], None]


def emit(
    callback: ProgressCallback | None,
    stage: str,
    current: int,
    total: int,
    message: str,
    detail: str = "",
) -> None:
    """Emit a :class:`ProgressEvent` if a callback was provided.

    ``percent`` is derived from ``current/total`` and clamped to ``[0, 100]``.
    A progress callback may raise :class:`core.exceptions.CancelledError` to
    request cooperative cancellation; that exception must be allowed to
    propagate through the pipeline unchanged.
    """

    if callback is None:
        return
    percent = 0.0
    if total > 0:
        percent = max(0.0, min(100.0, current / total * 100.0))
    callback(
        ProgressEvent(
            stage=stage,
            current=current,
            total=total,
            percent=percent,
            message=message,
            detail=detail,
        )
    )
