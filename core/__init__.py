"""Core business logic package for the local interview agent.

The package is intentionally free of any GUI dependency so it can be reused
from a CLI, tests, or the PySide6 front-end in ``ui``.
"""

from __future__ import annotations

from core.config import AnalysisConfig, AppConfig, LLMConfig, ModelConfig
from core.engine import InterviewEngine
from core.exceptions import (
    AudioLoadError,
    CancelledError,
    CoreError,
    LLMError,
    ModelNotFoundError,
    StorageError,
    TranscriptionError,
)
from core.progress import ProgressCallback, ProgressEvent
from core.schemas import (
    InterviewReport,
    QAAnalysis,
    QAPair,
    Recording,
    RecordingDetail,
    Transcript,
    TranscriptSegment,
)
from core.status import RecordingStatus, is_valid_status

__all__ = [
    "AnalysisConfig",
    "AppConfig",
    "AudioLoadError",
    "CancelledError",
    "CoreError",
    "InterviewEngine",
    "InterviewReport",
    "LLMConfig",
    "LLMError",
    "ModelConfig",
    "ModelNotFoundError",
    "ProgressCallback",
    "ProgressEvent",
    "QAAnalysis",
    "QAPair",
    "Recording",
    "RecordingDetail",
    "RecordingStatus",
    "StorageError",
    "Transcript",
    "TranscriptSegment",
    "TranscriptionError",
    "is_valid_status",
]
