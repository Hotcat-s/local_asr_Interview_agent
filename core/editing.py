"""Pure helpers for editing transcripts and Q/A pairs.

The GUI lets the user edit transcription text and question/answer text in place.
To keep that logic testable and free of UI concerns every helper here is a pure
function: the inputs are never mutated, a new object graph is returned instead.
That makes it safe for callers to keep the previous value around (for undo,
dirty-tracking or equality checks) without defensive copying.

Out-of-range indices raise :class:`IndexError` rather than being silently
ignored: the UI always derives indices from a model that mirrors the same list,
so a mismatch signals a real bug that should surface during development.
"""

from __future__ import annotations

from dataclasses import replace

from core.schemas import QAPair, Transcript, TranscriptSegment


def update_segment_text(transcript: Transcript, index: int, text: str) -> Transcript:
    """Return a copy of ``transcript`` with segment ``index``'s text replaced.

    ``index`` is a position in :attr:`Transcript.segments` and follows normal
    Python list semantics (negative values count from the end).  An out-of-range
    index raises :class:`IndexError`.  The original ``transcript`` and its
    segments are left untouched.
    """

    segments = list(transcript.segments)
    segments[index] = replace(segments[index], text=text)
    return replace(transcript, segments=segments)


def update_qa_text(
    qa_pairs: list[QAPair],
    index: int,
    *,
    question: str | None = None,
    answer: str | None = None,
) -> list[QAPair]:
    """Return a copy of ``qa_pairs`` with one pair's text fields updated.

    ``index`` is a position in the passed list (not ``QAPair.index``).  Only the
    fields whose argument is not ``None`` are changed, so a caller may update the
    question, the answer, or both.  An out-of-range index raises
    :class:`IndexError`.
    """

    pairs = list(qa_pairs)
    target = pairs[index]
    changes: dict[str, str] = {}
    if question is not None:
        changes["question"] = question
    if answer is not None:
        changes["answer"] = answer
    pairs[index] = replace(target, **changes)
    return pairs


def normalize_qa_pairs(qa_pairs: list[QAPair]) -> list[QAPair]:
    """Return a copy with ``index`` renumbered as ``0..n-1`` in list order.

    Every other field is preserved.  Used after a rebuild or after pairs are
    inserted/removed so the stored indices stay contiguous.
    """

    return [replace(pair, index=position) for position, pair in enumerate(qa_pairs)]


def transcript_from_segments(
    segments: list[TranscriptSegment],
    duration: float = 0.0,
    language: str = "zh",
) -> Transcript:
    """Rebuild a :class:`Transcript` from edited segments.

    ``raw_text`` is recomputed by joining the non-blank segment texts with a
    single space.  The passed ``segments`` list is copied so later mutations of
    the returned transcript do not leak back to the caller.
    """

    copied = list(segments)
    raw_text = " ".join(seg.text for seg in copied if seg.text.strip())
    return Transcript(
        segments=copied,
        duration=duration,
        language=language,
        raw_text=raw_text,
    )
