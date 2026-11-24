"""Tests for the automatic v1 -> v2 database migration."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from core.status import RecordingStatus
from core.storage.repository import Repository

_V1_SCHEMA = """
CREATE TABLE sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    audio_path  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    duration    REAL NOT NULL DEFAULT 0,
    language    TEXT NOT NULL DEFAULT 'zh',
    raw_text    TEXT NOT NULL DEFAULT ''
);
CREATE TABLE segments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL,
    idx         INTEGER NOT NULL,
    start       REAL NOT NULL,
    end         REAL NOT NULL,
    text        TEXT NOT NULL,
    speaker     TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE TABLE qa_pairs (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id         INTEGER NOT NULL,
    idx                INTEGER NOT NULL,
    question           TEXT NOT NULL,
    answer             TEXT NOT NULL,
    question_speaker   TEXT NOT NULL,
    answer_speaker     TEXT NOT NULL,
    start              REAL NOT NULL,
    end                REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE TABLE reports (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        INTEGER NOT NULL UNIQUE,
    overall_score     REAL NOT NULL,
    summary           TEXT NOT NULL,
    items_json        TEXT NOT NULL,
    improvements_json TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
"""


def _build_v1_db(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(_V1_SCHEMA)
    # session 1: transcribed only
    conn.execute(
        "INSERT INTO sessions (id, title, audio_path, created_at, duration, language, raw_text) "
        "VALUES (1, '已转写', 'a.wav', '2024-01-01T00:00:00+00:00', 10.0, 'zh', '你好')"
    )
    conn.execute(
        "INSERT INTO segments (session_id, idx, start, end, text, speaker) "
        "VALUES (1, 0, 0.0, 1.0, '你好', 'SPK0')"
    )
    # session 2: analyzed
    conn.execute(
        "INSERT INTO sessions (id, title, audio_path, created_at, duration, language, raw_text) "
        "VALUES (2, '已分析', 'b.wav', '2024-02-02T00:00:00+00:00', 20.0, 'zh', '问题 回答')"
    )
    conn.execute(
        "INSERT INTO segments (session_id, idx, start, end, text, speaker) "
        "VALUES (2, 0, 0.0, 1.0, '问题', 'SPK0')"
    )
    conn.execute(
        "INSERT INTO qa_pairs "
        "(session_id, idx, question, answer, question_speaker, answer_speaker, start, end) "
        "VALUES (2, 0, '问题', '回答', 'SPK0', 'SPK1', 0.0, 2.0)"
    )
    conn.execute(
        "INSERT INTO reports "
        "(session_id, overall_score, summary, items_json, improvements_json, created_at) "
        "VALUES (2, 77.0, '还行', '[]', '[\"多练习\"]', '2024-02-02T01:00:00+00:00')"
    )
    # session 3: imported only (no children)
    conn.execute(
        "INSERT INTO sessions (id, title, audio_path, created_at, duration, language, raw_text) "
        "VALUES (3, '仅导入', 'c.wav', '2024-03-03T00:00:00+00:00', 0, 'zh', '')"
    )
    conn.commit()
    conn.close()


class MigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmp.name) / "legacy.db")
        _build_v1_db(self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_migrates_statuses_and_data(self) -> None:
        repo = Repository(self.db_path)

        r1 = repo.get_recording(1)
        assert r1 is not None
        self.assertEqual(r1.title, "已转写")
        self.assertEqual(r1.status, RecordingStatus.TRANSCRIBED.value)
        self.assertTrue(r1.transcribed_at)
        self.assertEqual(r1.qa_count, 0)

        r2 = repo.get_recording(2)
        assert r2 is not None
        self.assertEqual(r2.status, RecordingStatus.ANALYZED.value)
        self.assertTrue(r2.transcribed_at)
        self.assertTrue(r2.analyzed_at)
        self.assertEqual(r2.qa_count, 1)
        self.assertEqual(r2.overall_score, 77.0)

        r3 = repo.get_recording(3)
        assert r3 is not None
        self.assertEqual(r3.status, RecordingStatus.IMPORTED.value)

        transcript = repo.load_transcript(1)
        assert transcript is not None
        self.assertEqual(transcript.segments[0].text, "你好")

        qa_pairs = repo.load_qa_pairs(2)
        self.assertEqual(len(qa_pairs), 1)
        self.assertEqual(qa_pairs[0].answer, "回答")

        report = repo.load_report(2)
        assert report is not None
        self.assertEqual(report.overall_score, 77.0)

        repo.close()

    def test_legacy_tables_are_preserved(self) -> None:
        repo = Repository(self.db_path)
        repo.close()
        conn = sqlite3.connect(self.db_path)
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        conn.close()
        # legacy sessions stay; child tables were renamed aside, new ones created
        self.assertIn("sessions", tables)
        self.assertIn("recordings", tables)
        self.assertIn("_v1_segments", tables)

    def test_migration_is_idempotent(self) -> None:
        Repository(self.db_path).close()
        second = Repository(self.db_path)
        # reopening must not duplicate rows or re-run migration
        self.assertEqual(len(second.list_recordings()), 3)
        self.assertEqual(second.get_recording(2).qa_count, 1)
        second.close()

    def test_fresh_db_has_no_legacy_tables(self) -> None:
        fresh = str(Path(self._tmp.name) / "fresh.db")
        repo = Repository(fresh)
        repo.create_recording("x", "a.wav")
        repo.close()
        conn = sqlite3.connect(fresh)
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        conn.close()
        self.assertNotIn("sessions", tables)
        self.assertIn("recordings", tables)


if __name__ == "__main__":
    unittest.main()
