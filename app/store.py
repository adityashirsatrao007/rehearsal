"""SQLite persistence.

A friend's practice history is private by default: it lives in a single local
file (`data/rehearsal.db`) that never leaves the machine. The file is
gitignored so it can't be pushed to GitHub by accident.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("REHEARSAL_DB", Path(__file__).resolve().parent.parent / "data" / "rehearsal.db"))

_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario        TEXT    NOT NULL,
    scenario_title  TEXT    NOT NULL,
    model           TEXT    NOT NULL,
    created_at      TEXT    NOT NULL,
    ended_at        TEXT,
    score_fluency   INTEGER,
    score_accuracy  INTEGER,
    score_vocabulary INTEGER,
    summary         TEXT,
    next_step       TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role        TEXT    NOT NULL,           -- 'learner' | 'partner'
    content     TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS corrections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    message_id  INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    corrected   TEXT    NOT NULL,
    why         TEXT    NOT NULL,
    better      TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
CREATE INDEX IF NOT EXISTS idx_corrections_msg  ON corrections(message_id);
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with _lock, _connect() as conn:
        conn.executescript(_SCHEMA)


def reset_db() -> None:
    """Wipe all data, keeping the schema. Used by the test suite."""
    init_db()
    with _lock, _connect() as conn:
        conn.execute("DELETE FROM corrections")
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM sessions")
        conn.execute("DELETE FROM sqlite_sequence")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# -- sessions ---------------------------------------------------------------

def create_session(scenario_id: str, scenario_title: str, model: str) -> dict:
    with _lock, _connect() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (scenario, scenario_title, model, created_at) "
            "VALUES (?, ?, ?, ?)",
            (scenario_id, scenario_title, model, now()),
        )
        session_id = cur.lastrowid
    return get_session(session_id)  # type: ignore[return-value]


def get_session(session_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return dict(row) if row else None


def list_sessions(limit: int = 50) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_session(session_id: int) -> bool:
    with _lock, _connect() as conn:
        cur = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return cur.rowcount > 0


def finish_session(
    session_id: int,
    fluency: int,
    accuracy: int,
    vocabulary: int,
    summary: str,
    next_step: str,
) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            "UPDATE sessions SET ended_at = ?, score_fluency = ?, score_accuracy = ?, "
            "score_vocabulary = ?, summary = ?, next_step = ? WHERE id = ?",
            (now(), fluency, accuracy, vocabulary, summary, next_step, session_id),
        )


# -- messages ---------------------------------------------------------------

def add_message(session_id: int, role: str, content: str) -> int:
    with _lock, _connect() as conn:
        cur = conn.execute(
            "INSERT INTO messages (session_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?)",
            (session_id, role, content, now()),
        )
        return int(cur.lastrowid)


def get_messages(session_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY id", (session_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def add_correction(
    session_id: int, message_id: int, corrected: str, why: str, better: str
) -> int:
    with _lock, _connect() as conn:
        cur = conn.execute(
            "INSERT INTO corrections (session_id, message_id, corrected, why, better, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, message_id, corrected, why, better, now()),
        )
        return int(cur.lastrowid)


def get_corrections(session_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM corrections WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def learner_turns(session_id: int) -> list[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT content FROM messages WHERE session_id = ? AND role = 'learner' ORDER BY id",
            (session_id,),
        ).fetchall()
    return [r["content"] for r in rows]


# -- aggregate stats for the progress view ---------------------------------

def progress_stats() -> dict:
    with _connect() as conn:
        sessions = conn.execute(
            "SELECT COUNT(*) AS n, "
            "AVG(score_fluency) AS f, AVG(score_accuracy) AS a, AVG(score_vocabulary) AS v "
            "FROM sessions WHERE ended_at IS NOT NULL"
        ).fetchone()
        messages = conn.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE role = 'learner'"
        ).fetchone()
        corrections = conn.execute("SELECT COUNT(*) AS n FROM corrections").fetchone()

    def _round(value: float | None) -> float:
        return round(value, 1) if value is not None else 0.0

    return {
        "sessions_completed": sessions["n"],
        "learner_messages": messages["n"],
        "corrections": corrections["n"],
        "avg_fluency": _round(sessions["f"]),
        "avg_accuracy": _round(sessions["a"]),
        "avg_vocabulary": _round(sessions["v"]),
    }
