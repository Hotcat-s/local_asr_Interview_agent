"""Low level SQLite connection, schema management and v1→v2 migration."""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path

from core.exceptions import StorageError

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2

# v2 schema: recordings replaces the v1 "sessions" concept; child tables are
# keyed by recording_id and carries lifecycle timestamps.
SCHEMA = """
CREATE TABLE IF NOT EXISTS recordings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title          TEXT NOT NULL,
    audio_path     TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'imported',
    duration       REAL NOT NULL DEFAULT 0,
    language       TEXT NOT NULL DEFAULT 'zh',
    error_message  TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    transcribed_at TEXT NOT NULL DEFAULT '',
    analyzed_at    TEXT NOT NULL DEFAULT '',
    qa_count       INTEGER NOT NULL DEFAULT 0,
    overall_score  REAL
);

CREATE TABLE IF NOT EXISTS segments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id INTEGER NOT NULL,
    idx          INTEGER NOT NULL,
    start        REAL NOT NULL,
    end          REAL NOT NULL,
    text         TEXT NOT NULL,
    speaker      TEXT NOT NULL,
    FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qa_pairs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id     INTEGER NOT NULL,
    idx              INTEGER NOT NULL,
    question         TEXT NOT NULL,
    answer           TEXT NOT NULL,
    question_speaker TEXT NOT NULL,
    answer_speaker   TEXT NOT NULL,
    start            REAL NOT NULL,
    end              REAL NOT NULL,
    FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reports (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id      INTEGER NOT NULL UNIQUE,
    overall_score     REAL NOT NULL,
    summary           TEXT NOT NULL,
    items_json        TEXT NOT NULL,
    improvements_json TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    FOREIGN KEY (recording_id) REFERENCES recordings(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_LEGACY_CHILD_TABLES = ("segments", "qa_pairs", "reports")


class Database:
    """Own a single sqlite3 connection guarded by a lock.

    The GUI runs analysis on a worker thread, so the connection is created with
    ``check_same_thread=False`` and serialised through :attr:`lock`.
    """

    def __init__(self, db_path: str) -> None:
        path = Path(db_path).expanduser()
        if path.parent and str(path.parent):
            path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(path)
        self.lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    # ------------------------------------------------------------------- schema

    def init_schema(self) -> None:
        """Create the v2 schema, migrating a v1 database when detected.

        The migration is best-effort and transactional: on failure the original
        tables are left untouched and the error is logged.
        """

        with self.lock:
            legacy = self._is_legacy_db()
            try:
                if legacy:
                    self._rename_legacy_child_tables()
                self._conn.executescript(SCHEMA)
                if legacy:
                    self._copy_legacy_data()
                self._conn.execute(
                    "INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('version', ?)",
                    (str(SCHEMA_VERSION),),
                )
                self._conn.commit()
            except Exception as exc:  # noqa: BLE001 - never break the original DB
                self._conn.rollback()
                logger.exception("Schema init / migration failed: %s", exc)
                raise StorageError(f"Failed to initialise schema: {exc}") from exc

    # ---------------------------------------------------------------- migration

    def _table_exists(self, name: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (name,),
        ).fetchone()
        return row is not None

    def _columns(self, name: str) -> set[str]:
        rows = self._conn.execute(f"PRAGMA table_info({name})").fetchall()
        return {row["name"] for row in rows}

    def _is_legacy_db(self) -> bool:
        """A legacy DB has a ``sessions`` table but no ``recordings`` table."""

        return self._table_exists("sessions") and not self._table_exists("recordings")

    def _rename_legacy_child_tables(self) -> None:
        """Move v1 child tables aside so the new tables can be created."""

        for name in _LEGACY_CHILD_TABLES:
            if not self._table_exists(name):
                continue
            if "session_id" not in self._columns(name):
                continue
            backup = f"_v1_{name}"
            if self._table_exists(backup):
                continue
            self._conn.execute(f"ALTER TABLE {name} RENAME TO {backup}")

    def _copy_legacy_data(self) -> None:
        """Copy rows from the legacy ``sessions`` graph into ``recordings``."""

        sessions = self._conn.execute("SELECT * FROM sessions").fetchall()
        have = {name: self._table_exists(f"_v1_{name}") for name in _LEGACY_CHILD_TABLES}

        for session in sessions:
            sid = session["id"]
            has_segments = have["segments"] and self._count("_v1_segments", sid) > 0
            has_report = have["reports"] and self._count("_v1_reports", sid) > 0
            if has_report:
                status = "analyzed"
            elif has_segments:
                status = "transcribed"
            else:
                status = "imported"

            created_at = session["created_at"]
            transcribed_at = created_at if has_segments else ""
            analyzed_at = created_at if has_report else ""
            qa_count = self._count("_v1_qa_pairs", sid) if have["qa_pairs"] else 0
            overall_score = None
            if has_report:
                row = self._conn.execute(
                    "SELECT overall_score FROM _v1_reports WHERE session_id = ?",
                    (sid,),
                ).fetchone()
                overall_score = row["overall_score"] if row else None

            self._conn.execute(
                "INSERT OR IGNORE INTO recordings "
                "(id, title, audio_path, status, duration, language, error_message, "
                " created_at, updated_at, transcribed_at, analyzed_at, qa_count, overall_score) "
                "VALUES (?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?)",
                (
                    sid,
                    session["title"],
                    session["audio_path"],
                    status,
                    session["duration"],
                    session["language"],
                    created_at,
                    created_at,
                    transcribed_at,
                    analyzed_at,
                    qa_count,
                    overall_score,
                ),
            )

            if have["segments"]:
                rows = self._conn.execute(
                    "SELECT idx, start, end, text, speaker FROM _v1_segments "
                    "WHERE session_id = ? ORDER BY idx",
                    (sid,),
                ).fetchall()
                self._conn.executemany(
                    "INSERT INTO segments (recording_id, idx, start, end, text, speaker) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    [(sid, r["idx"], r["start"], r["end"], r["text"], r["speaker"]) for r in rows],
                )

            if have["qa_pairs"]:
                rows = self._conn.execute(
                    "SELECT idx, question, answer, question_speaker, answer_speaker, start, end "
                    "FROM _v1_qa_pairs WHERE session_id = ? ORDER BY idx",
                    (sid,),
                ).fetchall()
                self._conn.executemany(
                    "INSERT INTO qa_pairs "
                    "(recording_id, idx, question, answer, question_speaker, answer_speaker, start, end) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            sid,
                            r["idx"],
                            r["question"],
                            r["answer"],
                            r["question_speaker"],
                            r["answer_speaker"],
                            r["start"],
                            r["end"],
                        )
                        for r in rows
                    ],
                )

            if have["reports"]:
                rows = self._conn.execute(
                    "SELECT overall_score, summary, items_json, improvements_json, created_at "
                    "FROM _v1_reports WHERE session_id = ?",
                    (sid,),
                ).fetchall()
                self._conn.executemany(
                    "INSERT OR IGNORE INTO reports "
                    "(recording_id, overall_score, summary, items_json, improvements_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (
                            sid,
                            r["overall_score"],
                            r["summary"],
                            r["items_json"],
                            r["improvements_json"],
                            r["created_at"],
                        )
                        for r in rows
                    ],
                )

    def _count(self, table: str, session_id: int) -> int:
        row = self._conn.execute(
            f"SELECT COUNT(*) AS n FROM {table} WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row["n"]) if row else 0

    def close(self) -> None:
        with self.lock:
            self._conn.close()
