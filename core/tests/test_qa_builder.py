"""Tests for :class:`core.diarization.qa_builder.QABuilder`."""

from __future__ import annotations

import unittest

from core.diarization.qa_builder import QABuilder
from core.schemas import Transcript, TranscriptSegment


class QABuilderTest(unittest.TestCase):
    def _transcript(self, *items: tuple[str, float, float, str]) -> Transcript:
        return Transcript(
            segments=[
                TranscriptSegment(start=s, end=e, text=t, speaker=spk)
                for spk, s, e, t in items
            ]
        )

    def test_simple_alternation(self) -> None:
        transcript = self._transcript(
            ("SPK0", 0.0, 1.0, "请自我介绍"),
            ("SPK1", 1.0, 3.0, "我叫张三"),
            ("SPK0", 3.0, 4.0, "你的优势是什么"),
            ("SPK1", 4.0, 6.0, "我擅长后端"),
        )
        pairs = QABuilder().build(transcript)
        self.assertEqual(len(pairs), 2)
        self.assertEqual(pairs[0].index, 0)
        self.assertEqual(pairs[0].question, "请自我介绍")
        self.assertEqual(pairs[0].answer, "我叫张三")
        self.assertEqual(pairs[0].question_speaker, "SPK0")
        self.assertEqual(pairs[0].answer_speaker, "SPK1")
        self.assertEqual(pairs[1].question, "你的优势是什么")
        self.assertEqual(pairs[1].start, 3.0)
        self.assertEqual(pairs[1].end, 6.0)

    def test_consecutive_same_speaker_is_merged(self) -> None:
        transcript = self._transcript(
            ("SPK0", 0.0, 1.0, "问题一"),
            ("SPK0", 1.0, 2.0, "补充条件"),
            ("SPK1", 2.0, 4.0, "回答一"),
            ("SPK1", 4.0, 5.0, "补充回答"),
        )
        pairs = QABuilder().build(transcript)
        self.assertEqual(len(pairs), 1)
        self.assertIn("问题一", pairs[0].question)
        self.assertIn("补充条件", pairs[0].question)
        self.assertIn("回答一", pairs[0].answer)
        self.assertIn("补充回答", pairs[0].answer)

    def test_interviewer_override(self) -> None:
        transcript = self._transcript(
            ("SPK1", 0.0, 1.0, "请介绍项目"),
            ("SPK0", 1.0, 3.0, "做过一个系统"),
        )
        pairs = QABuilder(interviewer_speaker="SPK1").build(transcript)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].question_speaker, "SPK1")
        self.assertEqual(pairs[0].answer_speaker, "SPK0")

    def test_single_speaker_yields_empty_answer(self) -> None:
        transcript = self._transcript(("SPK0", 0.0, 1.0, "只有提问"))
        pairs = QABuilder().build(transcript)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].answer, "")
        self.assertEqual(pairs[0].end, 1.0)

    def test_empty_transcript(self) -> None:
        self.assertEqual(QABuilder().build(Transcript()), [])


if __name__ == "__main__":
    unittest.main()
