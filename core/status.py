"""Recording lifecycle status shared by the storage and UI layers.

The status is persisted as a plain string in SQLite so that databases remain
inspectable without importing Python.  ``RecordingStatus`` is a ``str`` enum so
its members compare equal to their raw values.
"""

from __future__ import annotations

from enum import Enum


class RecordingStatus(str, Enum):
    """Lifecycle of a recording in the local library."""

    IMPORTED = "imported"        # imported, not transcribed yet
    TRANSCRIBING = "transcribing"  # transcription in progress (crash recovery)
    TRANSCRIBED = "transcribed"  # transcript available, not analysed yet
    ANALYZING = "analyzing"      # LLM analysis in progress
    ANALYZED = "analyzed"        # report available
    FAILED = "failed"            # last operation failed (see error_message)


_STATUS_VALUES = frozenset(status.value for status in RecordingStatus)


def is_valid_status(value: str) -> bool:
    """Return ``True`` when ``value`` is a known :class:`RecordingStatus`."""

    return value in _STATUS_VALUES


def status_values() -> tuple[str, ...]:
    """Return all valid status values in declaration order."""

    return tuple(status.value for status in RecordingStatus)
