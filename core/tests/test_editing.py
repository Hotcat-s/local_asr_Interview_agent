"""Tests for :mod:`core.editing` and edit persistence semantics.

All tests are pure-data: no audio, GPU or network access.  They cover the new
v3 pure helpers and verify that saving edited content overwrites the stored
rows without disturbing the recording's lifecycle status.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.editing import (
    normalize_qa_pairs,
    transcript_from_segments,
    update_qa_text,
    update_segment_text,
)
from core.schemas import QAPair, Transcript, TranscriptSegment
from core.status import RecordingStatus
from core.storage.repository import Repository


def _transcript() -> Transcript:
    return Transcript(
        segments=[
            TranscriptSegment(0.0, 1.0, "你好", "SPK0"),
            TranscriptSegment(1.0, 2.0, "我很好", "SPK1"),
            TranscriptSegment(2.0, 3.0, "   ", "SPK0"),
        ],
        duration=3.0,
        language="zh",
        raw_text="你好 我很好",
    )


def _pairs() -> list[QAPair]:
    return [
        QAPair(0, "q0", "a0", "SPK0", "SPK1", 0.0, 1.0),
        QAPair(1, "q1", "a1", "SPK0", "SPK1", 1.0, 2.0),
    ]


class UpdateSegmentTextTest(unittest.TestCase):
    def test_updates_target_segment(self) -> None:
        updated = update_segment_text(_transcript(), 1, "我非常好")
        self.assertEqual(updated.segments[1].text, "我非常好")
        self.assertEqual(updated.segments[0].text, "你好")
        self.assertEqual(updated.duration, 3.0)

    def test_does_not_mutate_original(self) -> None:
        original = _transcript()
        update_segment_text(original, 0, "改了")
        self.assertEqual(original.segments[0].text, "你好")
        # a new segment object is produced, not an in-place edit
        updated = update_segment_text(original, 0, "改了")
        self.assertIsNot(updated.segments[0], original.segments[0])
        self.assertIsNot(updated, original)

    def test_out_of_range_raises(self) -> None:
        with self.assertRaises(IndexError):
            update_segment_text(_transcript(), 99, "x")

    def test_negative_index_supported(self) -> None:
        updated = update_segment_text(_transcript(), -1, "结尾")
        self.assertEqual(updated.segments[-1].text, "结尾")


class UpdateQaTextTest(unittest.TestCase):
    def test_update_question_only(self) -> None:
        updated = update_qa_text(_pairs(), 0, question="新问题")
        self.assertEqual(updated[0].question, "新问题")
        self.assertEqual(updated[0].answer, "a0")

    def test_update_answer_only(self) -> None:
        updated = update_qa_text(_pairs(), 1, answer="新回答")
        self.assertEqual(updated[1].answer, "新回答")
        self.assertEqual(updated[1].question, "q1")

    def test_update_both(self) -> None:
        updated = update_qa_text(_pairs(), 0, question="Q", answer="A")
        self.assertEqual((updated[0].question, updated[0].answer), ("Q", "A"))

    def test_no_fields_leaves_values_unchanged(self) -> None:
        updated = update_qa_text(_pairs(), 0)
        self.assertEqual((updated[0].question, updated[0].answer), ("q0", "a0"))

    def test_does_not_mutate_original(self) -> None:
        original = _pairs()
        update_qa_text(original, 0, question="Q")
        self.assertEqual(original[0].question, "q0")

    def test_out_of_range_raises(self) -> None:
        with self.assertRaises(IndexError):
            update_qa_text(_pairs(), 5, question="x")


class NormalizeQaPairsTest(unittest.TestCase):
    def test_renumbers_indices_in_order(self) -> None:
        pairs = [
            QAPair(7, "q0", "a0", "SPK0", "SPK1", 0.0, 1.0),
            QAPair(3, "q1", "a1", "SPK0", "SPK1", 1.0, 2.0),
        ]
        normalized = normalize_qa_pairs(pairs)
        self.assertEqual([p.index for p in normalized], [0, 1])
        # content preserved
        self.assertEqual(normalized[0].question, "q0")
        self.assertEqual(normalized[1].answer, "a1")

    def test_does_not_mutate_original(self) -> None:
        pairs = [QAPair(9, "q", "a", "SPK0", "SPK1", 0, 1)]
        normalize_qa_pairs(pairs)
        self.assertEqual(pairs[0].index, 9)

    def test_empty(self) -> None:
        self.assertEqual(normalize_qa_pairs([]), [])


class TranscriptFromSegmentsTest(unittest.TestCase):
    def test_recomputes_raw_text_ignoring_blank(self) -> None:
        segments = [
            TranscriptSegment(0.0, 1.0, "你好", "SPK0"),
            TranscriptSegment(1.0, 2.0, "   ", "SPK0"),
            TranscriptSegment(2.0, 3.0, "世界", "SPK1"),
        ]
        transcript = transcript_from_segments(segments, duration=3.0, language="zh")
        self.assertEqual(transcript.raw_text, "你好 世界")
        self.assertEqual(transcript.duration, 3.0)
        self.assertEqual(transcript.language, "zh")

    def test_copies_segment_list(self) -> None:
        segments = [TranscriptSegment(0.0, 1.0, "你好", "SPK0")]
        transcript = transcript_from_segments(segments)
        self.assertIsNot(transcript.segments, segments)

    def test_all_blank_yields_empty_raw_text(self) -> None:
        transcript = transcript_from_segments(
            [TranscriptSegment(0.0, 1.0, "  ", "SPK0")]
        )
        self.assertEqual(transcript.raw_text, "")

    def test_empty_segments(self) -> None:
        transcript = transcript_from_segments([])
        self.assertEqual(transcript.segments, [])
        self.assertEqual(transcript.raw_text, "")


class RenameRecordingTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmp.name) / "test.db")
        self.repo = Repository(self.db_path)

    def tearDown(self) -> None:
        self.repo.close()
        self._tmp.cleanup()

    def test_rename_updates_title(self) -> None:
        rid = self.repo.create_recording("旧名", "a.wav")
        self.repo.rename_recording(rid, "新名字")
        recording = self.repo.get_recording(rid)
        assert recording is not None
        self.assertEqual(recording.title, "新名字")

    def test_blank_title_is_ignored(self) -> None:
        rid = self.repo.create_recording("保留我", "a.wav")
        self.repo.rename_recording(rid, "")
        self.repo.rename_recording(rid, "   ")
        recording = self.repo.get_recording(rid)
        assert recording is not None
        self.assertEqual(recording.title, "保留我")

    def test_rename_refreshes_updated_at(self) -> None:
        rid = self.repo.create_recording("旧名", "a.wav")
        before = self.repo.get_recording(rid)
        assert before is not None
        self.repo.rename_recording(rid, "新名字")
        after = self.repo.get_recording(rid)
        assert after is not None
        self.assertGreaterEqual(after.updated_at, before.updated_at)
        self.assertNotEqual(after.updated_at, "")

    def test_rename_trims_surrounding_whitespace(self) -> None:
        rid = self.repo.create_recording("旧名", "a.wav")
        self.repo.rename_recording(rid, "  正式名称  ")
        recording = self.repo.get_recording(rid)
        assert recording is not None
        self.assertEqual(recording.title, "正式名称")


class EditPersistenceTest(unittest.TestCase):
    """Saving edited content overwrites rows and leaves status untouched."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmp.name) / "test.db")
        self.repo = Repository(self.db_path)

    def tearDown(self) -> None:
        self.repo.close()
        self._tmp.cleanup()

    def test_save_edited_transcript_overwrites_and_keeps_status(self) -> None:
        rid = self.repo.create_recording("t", "a.wav")
        self.repo.save_transcript(rid, _transcript())
        self.repo.update_status(rid, RecordingStatus.TRANSCRIBED.value)

        edited = update_segment_text(_transcript(), 0, "编辑后的文本")
        self.repo.save_transcript(rid, edited)

        loaded = self.repo.load_transcript(rid)
        assert loaded is not None
        self.assertEqual(loaded.segments[0].text, "编辑后的文本")
        self.assertEqual(len(loaded.segments), 3)
        recording = self.repo.get_recording(rid)
        assert recording is not None
        # status is not changed by a content save
        self.assertEqual(recording.status, RecordingStatus.TRANSCRIBED.value)

    def test_save_edited_qa_overwrites_and_updates_count(self) -> None:
        rid = self.repo.create_recording("q", "a.wav")
        self.repo.save_qa_pairs(rid, _pairs())

        edited = update_qa_text(_pairs(), 1, answer="编辑后的回答")
        self.repo.save_qa_pairs(rid, edited)

        loaded = self.repo.load_qa_pairs(rid)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[1].answer, "编辑后的回答")
        recording = self.repo.get_recording(rid)
        assert recording is not None
        self.assertEqual(recording.qa_count, 2)

    def test_save_edit_keeps_report(self) -> None:
        rid = self.repo.create_recording("r", "a.wav")
        from core.schemas import InterviewReport

        self.repo.save_report(rid, InterviewReport(overall_score=70.0, summary="旧报告"))
        self.repo.save_transcript(rid, update_segment_text(_transcript(), 0, "改"))
        self.repo.save_qa_pairs(rid, update_qa_text(_pairs(), 0, question="改"))

        report = self.repo.load_report(rid)
        assert report is not None
        self.assertEqual(report.overall_score, 70.0)


if __name__ == "__main__":
    unittest.main()
