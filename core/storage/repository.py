"""High level CRUD operations over the v2 recording dataclasses."""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone

from core.exceptions import StorageError
from core.schemas import (
    InterviewReport,
    QAAnalysis,
    QAPair,
    Recording,
    RecordingDetail,
    Transcript,
    TranscriptSegment,
)
from core.status import RecordingStatus, status_values
from core.storage.database import Database

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Repository:
    """Persist and load recordings, transcripts, Q/A pairs and reports."""

    def __init__(self, db_path: str) -> None:
        self.db = Database(db_path)
        self.init_db()

    def init_db(self) -> None:
        self.db.init_schema()

    def close(self) -> None:
        self.db.close()

    # ------------------------------------------------------------------ recordings

    def create_recording(self, title: str, audio_path: str) -> int:
        now = _now()
        with self.db.lock:
            try:
                cursor = self.db.connection.execute(
                    "INSERT INTO recordings "
                    "(title, audio_path, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (title, audio_path, RecordingStatus.IMPORTED.value, now, now),
                )
                self.db.connection.commit()
            except sqlite3.Error as exc:
                raise StorageError(f"Failed to create recording: {exc}") from exc
            return int(cursor.lastrowid)

    def get_recording(self, recording_id: int) -> Recording | None:
        with self.db.lock:
            row = self.db.connection.execute(
                "SELECT * FROM recordings WHERE id = ?", (recording_id,)
            ).fetchone()
        return _row_to_recording(row) if row else None

    def list_recordings(
        self,
        status: str | None = None,
        search: str | None = None,
    ) -> list[Recording]:
        clauses: list[str] = []
        params: list[object] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if search:
            clauses.append("(title LIKE ? OR audio_path LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = (
            f"SELECT * FROM recordings {where} ORDER BY updated_at DESC, id DESC"
        )
        with self.db.lock:
            rows = self.db.connection.execute(query, params).fetchall()
        return [_row_to_recording(row) for row in rows]

    def update_status(self, recording_id: int, status: str, error_message: str = "") -> None:
        now = _now()
        sets = ["status = ?", "error_message = ?", "updated_at = ?"]
        params: list[object] = [status, error_message, now]
        if status == RecordingStatus.TRANSCRIBED.value:
            sets.append("transcribed_at = ?")
            params.append(now)
        elif status == RecordingStatus.ANALYZED.value:
            sets.append("analyzed_at = ?")
            params.append(now)
        params.append(recording_id)
        with self.db.lock:
            self.db.connection.execute(
                f"UPDATE recordings SET {', '.join(sets)} WHERE id = ?", params
            )
            self.db.connection.commit()

    def update_metadata(
        self,
        recording_id: int,
        *,
        title: str | None = None,
        duration: float | None = None,
        language: str | None = None,
    ) -> None:
        sets = ["updated_at = ?"]
        params: list[object] = [_now()]
        if title is not None:
            sets.append("title = ?")
            params.append(title)
        if duration is not None:
            sets.append("duration = ?")
            params.append(duration)
        if language is not None:
            sets.append("language = ?")
            params.append(language)
        params.append(recording_id)
        with self.db.lock:
            self.db.connection.execute(
                f"UPDATE recordings SET {', '.join(sets)} WHERE id = ?", params
            )
            self.db.connection.commit()

    def rename_recording(self, recording_id: int, title: str) -> None:
        """Update a recording's title and refresh ``updated_at``.

        A blank (empty or whitespace-only) title is ignored so the UI can never
        erase a name by accident.  This is the single entry point the UI uses
        for renaming; it delegates to :meth:`update_metadata`.
        """

        cleaned = (title or "").strip()
        if not cleaned:
            return
        self.update_metadata(recording_id, title=cleaned)

    def mark_analyzed(self, recording_id: int, overall_score: float | None = None) -> None:
        now = _now()
        with self.db.lock:
            self.db.connection.execute(
                "UPDATE recordings SET status = ?, analyzed_at = ?, updated_at = ?, "
                "overall_score = COALESCE(?, overall_score) WHERE id = ?",
                (RecordingStatus.ANALYZED.value, now, now, overall_score, recording_id),
            )
            self.db.connection.commit()

    def delete_recording(self, recording_id: int) -> None:
        with self.db.lock:
            for table in ("segments", "qa_pairs", "reports"):
                self.db.connection.execute(
                    f"DELETE FROM {table} WHERE recording_id = ?", (recording_id,)
                )
            self.db.connection.execute("DELETE FROM recordings WHERE id = ?", (recording_id,))
            self.db.connection.commit()

    # ------------------------------------------------------------------ transcript

    def save_transcript(self, recording_id: int, transcript: Transcript) -> None:
        with self.db.lock:
            self.db.connection.execute(
                "DELETE FROM segments WHERE recording_id = ?", (recording_id,)
            )
            self.db.connection.executemany(
                "INSERT INTO segments (recording_id, idx, start, end, text, speaker) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (recording_id, idx, seg.start, seg.end, seg.text, seg.speaker)
                    for idx, seg in enumerate(transcript.segments)
                ],
            )
            self.db.connection.execute(
                "UPDATE recordings SET duration = ?, language = ?, updated_at = ? WHERE id = ?",
                (transcript.duration, transcript.language, _now(), recording_id),
            )
            self.db.connection.commit()

    def load_transcript(self, recording_id: int) -> Transcript | None:
        with self.db.lock:
            recording = self.get_recording(recording_id)
            if recording is None:
                return None
            rows = self.db.connection.execute(
                "SELECT start, end, text, speaker FROM segments "
                "WHERE recording_id = ? ORDER BY idx",
                (recording_id,),
            ).fetchall()
        segments = [
            TranscriptSegment(
                start=row["start"], end=row["end"], text=row["text"], speaker=row["speaker"]
            )
            for row in rows
        ]
        raw_text = " ".join(segment.text for segment in segments if segment.text)
        return Transcript(
            segments=segments,
            duration=recording.duration,
            language=recording.language,
            raw_text=raw_text,
        )

    # -------------------------------------------------------------------- QA pairs

    def save_qa_pairs(self, recording_id: int, qa_pairs: list[QAPair]) -> None:
        with self.db.lock:
            self.db.connection.execute(
                "DELETE FROM qa_pairs WHERE recording_id = ?", (recording_id,)
            )
            self.db.connection.executemany(
                "INSERT INTO qa_pairs "
                "(recording_id, idx, question, answer, question_speaker, answer_speaker, start, end) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        recording_id,
                        pair.index,
                        pair.question,
                        pair.answer,
                        pair.question_speaker,
                        pair.answer_speaker,
                        pair.start,
                        pair.end,
                    )
                    for pair in qa_pairs
                ],
            )
            self.db.connection.execute(
                "UPDATE recordings SET qa_count = ?, updated_at = ? WHERE id = ?",
                (len(qa_pairs), _now(), recording_id),
            )
            self.db.connection.commit()

    def load_qa_pairs(self, recording_id: int) -> list[QAPair]:
        with self.db.lock:
            rows = self.db.connection.execute(
                "SELECT idx, question, answer, question_speaker, answer_speaker, start, end "
                "FROM qa_pairs WHERE recording_id = ? ORDER BY idx",
                (recording_id,),
            ).fetchall()
        return [
            QAPair(
                index=row["idx"],
                question=row["question"],
                answer=row["answer"],
                question_speaker=row["question_speaker"],
                answer_speaker=row["answer_speaker"],
                start=row["start"],
                end=row["end"],
            )
            for row in rows
        ]

    # --------------------------------------------------------------------- report

    def save_report(self, recording_id: int, report: InterviewReport) -> None:
        items_json = json.dumps([asdict(item) for item in report.items], ensure_ascii=False)
        improvements_json = json.dumps(report.improvements, ensure_ascii=False)
        with self.db.lock:
            self.db.connection.execute(
                "INSERT INTO reports "
                "(recording_id, overall_score, summary, items_json, improvements_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(recording_id) DO UPDATE SET "
                "overall_score = excluded.overall_score, summary = excluded.summary, "
                "items_json = excluded.items_json, improvements_json = excluded.improvements_json, "
                "created_at = excluded.created_at",
                (
                    recording_id,
                    report.overall_score,
                    report.summary,
                    items_json,
                    improvements_json,
                    report.created_at or _now(),
                ),
            )
            self.db.connection.execute(
                "UPDATE recordings SET updated_at = ? WHERE id = ?", (_now(), recording_id)
            )
            self.db.connection.commit()

    def load_report(self, recording_id: int) -> InterviewReport | None:
        with self.db.lock:
            row = self.db.connection.execute(
                "SELECT * FROM reports WHERE recording_id = ?", (recording_id,)
            ).fetchone()
        if row is None:
            return None
        items = [QAAnalysis(**item) for item in json.loads(row["items_json"])]
        improvements = list(json.loads(row["improvements_json"]))
        return InterviewReport(
            overall_score=row["overall_score"],
            summary=row["summary"],
            items=items,
            improvements=improvements,
            created_at=row["created_at"],
        )

    # ------------------------------------------------------------------- aggregate

    def get_detail(self, recording_id: int) -> RecordingDetail | None:
        recording = self.get_recording(recording_id)
        if recording is None:
            return None
        return RecordingDetail(
            recording=recording,
            transcript=self.load_transcript(recording_id),
            qa_pairs=self.load_qa_pairs(recording_id),
            report=self.load_report(recording_id),
        )

    def count_recordings(self) -> dict[str, int]:
        with self.db.lock:
            rows = self.db.connection.execute(
                "SELECT status, COUNT(*) AS n FROM recordings GROUP BY status"
            ).fetchall()
        counts = {value: 0 for value in status_values()}
        total = 0
        for row in rows:
            counts[row["status"]] = int(row["n"])
            total += int(row["n"])
        result = {"all": total}
        result.update(counts)
        return result


def _row_to_recording(row) -> Recording:
    return Recording(
        id=row["id"],
        title=row["title"],
        audio_path=row["audio_path"],
        status=row["status"],
        duration=row["duration"],
        language=row["language"],
        error_message=row["error_message"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        transcribed_at=row["transcribed_at"],
        analyzed_at=row["analyzed_at"],
        qa_count=row["qa_count"],
        overall_score=row["overall_score"],
    )
