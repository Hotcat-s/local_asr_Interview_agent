"""Turn speaker-attributed segments into ordered question / answer pairs.

The interview assumption is binary: one interviewer asks and one candidate
answers.  The speaker who talks first is treated as the interviewer unless the
caller overrides it, so all of that speaker's consecutive sentences become a
question and the following opposite-speaker sentences become its answer.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.schemas import QAPair, Transcript, TranscriptSegment


@dataclass
class _Turn:
    speaker: str
    text: str
    start: float
    end: float


class QABuilder:
    """Build :class:`QAPair` objects from a :class:`Transcript`."""

    def __init__(self, interviewer_speaker: str | None = None) -> None:
        self.interviewer_speaker = interviewer_speaker

    def build(self, transcript: Transcript) -> list[QAPair]:
        turns = self._to_turns(transcript.segments)
        if not turns:
            return []

        questioner = self.interviewer_speaker or turns[0].speaker
        roles = ["Q" if turn.speaker == questioner else "A" for turn in turns]
        merged = self._merge_turns(turns, roles)

        pairs: list[QAPair] = []
        index = 0
        i = 0
        while i < len(merged):
            role, turn = merged[i]
            if role == "Q":
                if i + 1 < len(merged) and merged[i + 1][0] == "A":
                    _, answer = merged[i + 1]
                    pairs.append(self._make_pair(index, turn, answer))
                    i += 2
                else:
                    # Question without an answer (e.g. trailing question).
                    pairs.append(self._make_pair(index, turn, None))
                    i += 1
            else:
                # Orphan answer before any question; keep it with empty question.
                pairs.append(self._make_pair(index, None, turn))
                i += 1
            index += 1
        return pairs

    @staticmethod
    def _to_turns(segments: list[TranscriptSegment]) -> list[_Turn]:
        turns: list[_Turn] = []
        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            if turns and turns[-1].speaker == seg.speaker:
                turns[-1].text = f"{turns[-1].text} {text}".strip()
                turns[-1].end = seg.end
            else:
                turns.append(_Turn(speaker=seg.speaker, text=text, start=seg.start, end=seg.end))
        return turns

    @staticmethod
    def _merge_turns(turns: list[_Turn], roles: list[str]) -> list[tuple[str, _Turn]]:
        """Collapse consecutive turns that share the same Q/A role."""

        merged: list[tuple[str, _Turn]] = []
        for role, turn in zip(roles, turns):
            if merged and merged[-1][0] == role:
                prev = merged[-1][1]
                prev.text = f"{prev.text} {turn.text}".strip()
                prev.end = turn.end
            else:
                merged.append((role, _Turn(turn.speaker, turn.text, turn.start, turn.end)))
        return merged

    @staticmethod
    def _make_pair(index: int, question: _Turn | None, answer: _Turn | None) -> QAPair:
        start = question.start if question else (answer.start if answer else 0.0)
        end = answer.end if answer else (question.end if question else start)
        return QAPair(
            index=index,
            question=question.text if question else "",
            answer=answer.text if answer else "",
            question_speaker=question.speaker if question else "",
            answer_speaker=answer.speaker if answer else "",
            start=start,
            end=end,
        )
