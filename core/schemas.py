"""Shared data models exchanged between the core layer and the GUI.

These dataclasses are the frozen contract from ``INTERFACES.md``.  Keep field
names and ordering stable; the UI serialises them 1:1.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class TranscriptSegment:
    """A single speaker-attributed utterance with second-granularity timing."""

    start: float
    end: float
    text: str
    speaker: str


@dataclass
class Transcript:
    """Full transcription result for one audio file."""

    segments: list[TranscriptSegment] = field(default_factory=list)
    duration: float = 0.0
    language: str = "zh"
    raw_text: str = ""


@dataclass
class QAPair:
    """One question / answer pair reconstructed from speaker turns."""

    index: int
    question: str
    answer: str
    question_speaker: str
    answer_speaker: str
    start: float
    end: float


@dataclass
class QAAnalysis:
    """LLM review of a single Q/A pair."""

    index: int
    question: str
    answer: str
    score: float
    strengths: list[str]
    weaknesses: list[str]
    reference_answer: str
    suggestion: str


@dataclass
class InterviewReport:
    """Aggregated review across all Q/A pairs."""

    overall_score: float
    summary: str
    items: list[QAAnalysis] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    created_at: str = ""


# --------------------------------------------------------------------- v2 library

@dataclass
class Recording:
    """One entry in the local recording library.

    Mirrors the ``recordings`` SQLite table.  Timestamp fields are ISO-8601
    strings; ``transcribed_at`` / ``analyzed_at`` stay empty until the matching
    stage has completed at least once.
    """

    id: int = 0
    title: str = ""
    audio_path: str = ""
    status: str = "imported"
    duration: float = 0.0
    language: str = "zh"
    error_message: str = ""
    created_at: str = ""
    updated_at: str = ""
    transcribed_at: str = ""
    analyzed_at: str = ""
    qa_count: int = 0
    overall_score: float | None = None


@dataclass
class RecordingDetail:
    """A recording together with all of its lazily loaded content."""

    recording: Recording
    transcript: Transcript | None = None
    qa_pairs: list[QAPair] = field(default_factory=list)
    report: InterviewReport | None = None

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation (mainly for debugging)."""

        return {
            "recording": asdict(self.recording),
            "transcript": asdict(self.transcript) if self.transcript else None,
            "qa_pairs": [asdict(pair) for pair in self.qa_pairs],
            "report": asdict(self.report) if self.report else None,
        }
