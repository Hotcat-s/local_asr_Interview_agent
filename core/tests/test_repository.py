"""Tests for :class:`core.storage.repository.Repository` (v2 recording library)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.schemas import InterviewReport, QAAnalysis, QAPair, Transcript, TranscriptSegment
from core.status import RecordingStatus
from core.storage.repository import Repository


class RepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmp.name) / "test.db")
        self.repo = Repository(self.db_path)

    def tearDown(self) -> None:
        self.repo.close()
        self._tmp.cleanup()

    def test_create_and_get_recording(self) -> None:
        rid = self.repo.create_recording("面试 A", "/tmp/a.wav")
        recording = self.repo.get_recording(rid)
        assert recording is not None
        self.assertEqual(recording.title, "面试 A")
        self.assertEqual(recording.status, RecordingStatus.IMPORTED.value)
        self.assertTrue(recording.created_at)
        self.assertTrue(recording.updated_at)
        self.assertEqual(recording.transcribed_at, "")
        self.assertEqual(recording.analyzed_at, "")
        self.assertEqual(recording.qa_count, 0)
        self.assertIsNone(recording.overall_score)

    def test_transcript_round_trip(self) -> None:
        rid = self.repo.create_recording("测试面试", "/tmp/a.wav")
        transcript = Transcript(
            segments=[
                TranscriptSegment(0.0, 1.0, "你好", "SPK0"),
                TranscriptSegment(1.0, 2.5, "你好呀", "SPK1"),
            ],
            duration=2.5,
            language="zh",
            raw_text="你好 你好呀",
        )
        self.repo.save_transcript(rid, transcript)

        loaded = self.repo.load_transcript(rid)
        assert loaded is not None
        self.assertEqual(len(loaded.segments), 2)
        self.assertEqual(loaded.segments[1].text, "你好呀")
        self.assertEqual(loaded.segments[1].speaker, "SPK1")
        self.assertAlmostEqual(loaded.duration, 2.5)
        self.assertEqual(loaded.raw_text, "你好 你好呀")

    def test_save_transcript_overwrites(self) -> None:
        rid = self.repo.create_recording("t", "a.wav")
        self.repo.save_transcript(rid, Transcript(segments=[TranscriptSegment(0, 1, "旧", "SPK0")]))
        self.repo.save_transcript(rid, Transcript(segments=[TranscriptSegment(0, 1, "新", "SPK1")]))
        loaded = self.repo.load_transcript(rid)
        assert loaded is not None
        self.assertEqual(len(loaded.segments), 1)
        self.assertEqual(loaded.segments[0].text, "新")

    def test_qa_pairs_round_trip_updates_count(self) -> None:
        rid = self.repo.create_recording("q", "a.wav")
        pairs = [
            QAPair(0, "q0", "a0", "SPK0", "SPK1", 0.0, 1.0),
            QAPair(1, "q1", "a1", "SPK0", "SPK1", 1.0, 2.0),
        ]
        self.repo.save_qa_pairs(rid, pairs)
        loaded = self.repo.load_qa_pairs(rid)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[1].question, "q1")
        self.assertEqual(loaded[1].answer_speaker, "SPK1")
        recording = self.repo.get_recording(rid)
        assert recording is not None
        self.assertEqual(recording.qa_count, 2)

    def test_report_round_trip_and_upsert(self) -> None:
        rid = self.repo.create_recording("r", "a.wav")
        report = InterviewReport(
            overall_score=80.0,
            summary="不错",
            items=[QAAnalysis(0, "q", "a", 80.0, ["亮点"], ["不足"], "参考答案", "建议")],
            improvements=["多练习"],
            created_at="2025-01-01T00:00:00+00:00",
        )
        self.repo.save_report(rid, report)
        report.overall_score = 90.0
        self.repo.save_report(rid, report)  # upsert, not duplicate

        loaded = self.repo.load_report(rid)
        assert loaded is not None
        self.assertEqual(loaded.overall_score, 90.0)
        self.assertEqual(loaded.items[0].reference_answer, "参考答案")
        self.assertEqual(loaded.improvements, ["多练习"])

    def test_update_status_writes_timestamps(self) -> None:
        rid = self.repo.create_recording("s", "a.wav")
        self.repo.update_status(rid, RecordingStatus.TRANSCRIBED.value)
        recording = self.repo.get_recording(rid)
        assert recording is not None
        self.assertEqual(recording.status, "transcribed")
        self.assertTrue(recording.transcribed_at)
        self.assertEqual(recording.analyzed_at, "")

        self.repo.update_status(rid, RecordingStatus.ANALYZED.value)
        recording = self.repo.get_recording(rid)
        assert recording is not None
        self.assertTrue(recording.analyzed_at)

    def test_mark_analyzed_sets_score_and_status(self) -> None:
        rid = self.repo.create_recording("m", "a.wav")
        self.repo.mark_analyzed(rid, overall_score=88.5)
        recording = self.repo.get_recording(rid)
        assert recording is not None
        self.assertEqual(recording.status, RecordingStatus.ANALYZED.value)
        self.assertEqual(recording.overall_score, 88.5)
        self.assertTrue(recording.analyzed_at)

    def test_update_metadata(self) -> None:
        rid = self.repo.create_recording("old", "a.wav")
        self.repo.update_metadata(rid, title="new", duration=12.0, language="en")
        recording = self.repo.get_recording(rid)
        assert recording is not None
        self.assertEqual(recording.title, "new")
        self.assertEqual(recording.duration, 12.0)
        self.assertEqual(recording.language, "en")

    def test_list_filter_search_and_order(self) -> None:
        self.repo.create_recording("后端面试", "a.wav")
        self.repo.create_recording("前端面试", "b.wav")
        r3 = self.repo.create_recording("算法岗", "c.wav")
        self.repo.update_status(r3, RecordingStatus.TRANSCRIBED.value)

        all_recordings = self.repo.list_recordings()
        self.assertEqual(len(all_recordings), 3)
        # most recently updated first
        self.assertEqual(all_recordings[0].id, r3)

        transcribed = self.repo.list_recordings(status="transcribed")
        self.assertEqual([r.id for r in transcribed], [r3])

        found = self.repo.list_recordings(search="前端")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].title, "前端面试")

    def test_delete_recording_cascades(self) -> None:
        rid = self.repo.create_recording("d", "a.wav")
        self.repo.save_transcript(
            rid, Transcript(segments=[TranscriptSegment(0, 1, "x", "SPK0")])
        )
        self.repo.save_qa_pairs(rid, [QAPair(0, "q", "a", "SPK0", "SPK1", 0, 1)])
        self.repo.save_report(rid, InterviewReport(overall_score=1.0, summary="s"))
        self.repo.delete_recording(rid)
        self.assertIsNone(self.repo.get_recording(rid))
        self.assertEqual(self.repo.load_qa_pairs(rid), [])
        self.assertIsNone(self.repo.load_transcript(rid))

    def test_get_detail_and_counts(self) -> None:
        rid = self.repo.create_recording("detail", "a.wav")
        self.repo.save_transcript(rid, Transcript(segments=[TranscriptSegment(0, 1, "x", "SPK0")]))
        self.repo.save_qa_pairs(rid, [QAPair(0, "q", "a", "SPK0", "SPK1", 0, 1)])

        detail = self.repo.get_detail(rid)
        assert detail is not None
        self.assertEqual(detail.recording.id, rid)
        self.assertIsNotNone(detail.transcript)
        self.assertEqual(len(detail.qa_pairs), 1)

        counts = self.repo.count_recordings()
        self.assertEqual(counts["all"], 1)
        self.assertEqual(counts["imported"], 1)

    def test_get_missing_returns_none(self) -> None:
        self.assertIsNone(self.repo.get_recording(999))
        self.assertIsNone(self.repo.get_detail(999))
        self.assertIsNone(self.repo.load_transcript(999))
        self.assertIsNone(self.repo.load_report(999))


if __name__ == "__main__":
    unittest.main()
