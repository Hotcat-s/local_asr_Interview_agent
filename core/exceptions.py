"""Exception hierarchy for the core layer."""

from __future__ import annotations


class CoreError(Exception):
    """Base class for all core-layer errors."""


class ModelNotFoundError(CoreError):
    """Raised when a required local model directory is missing."""


class AudioLoadError(CoreError):
    """Raised when an audio file cannot be read or decoded."""


class TranscriptionError(CoreError):
    """Raised when the ASR / diarization pipeline fails."""


class LLMError(CoreError):
    """Raised when an LLM request or response cannot be handled."""


class CancelledError(CoreError):
    """Raised internally when a caller cancels a running task.

    Raised cooperatively from progress callbacks.  Pipeline stages must let it
    propagate untouched instead of wrapping it in a stage-specific error.
    """


class StorageError(CoreError):
    """Raised when the SQLite persistence layer cannot complete an operation."""
