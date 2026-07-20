"""
Collaboration — Phase 5.5

Fork sessions, side-by-side comparison, turn-level annotations/comments.
"""
import os
import sqlite3
import time
import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

MEMORY_DB_PATH = Path(os.environ.get("SES_MEMORY_DB", "data/memory.db"))


def _memory_db_path() -> Path:
    return Path(os.environ.get("SES_MEMORY_DB", "data/memory.db"))


def init_collab_schema():
    """Create collaboration tables for forks, comparisons, and annotations."""
    conn = sqlite3.connect(str(_memory_db_path()))
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS session_forks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fork_id TEXT UNIQUE NOT NULL,
            original_session_id TEXT NOT NULL,
            forked_session_id TEXT NOT NULL,
            forked_by TEXT DEFAULT '',
            fork_point INTEGER DEFAULT 0,
            created_at REAL DEFAULT (julianday('now')),
            FOREIGN KEY (original_session_id) REFERENCES memory_sessions(session_id)
        );

        CREATE TABLE IF NOT EXISTS session_comparisons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comparison_id TEXT UNIQUE NOT NULL,
            session_a_id TEXT NOT NULL,
            session_b_id TEXT NOT NULL,
            created_by TEXT DEFAULT '',
            created_at REAL DEFAULT (julianday('now')),
            FOREIGN KEY (session_a_id) REFERENCES memory_sessions(session_id),
            FOREIGN KEY (session_b_id) REFERENCES memory_sessions(session_id)
        );

        CREATE TABLE IF NOT EXISTS annotations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            annotation_id TEXT UNIQUE NOT NULL,
            session_id TEXT NOT NULL,
            turn_number INTEGER NOT NULL,
            user_id TEXT DEFAULT '',
            content TEXT NOT NULL,
            annotation_type TEXT DEFAULT 'comment',
            created_at REAL DEFAULT (julianday('now')),
            updated_at REAL DEFAULT (julianday('now')),
            FOREIGN KEY (session_id) REFERENCES memory_sessions(session_id)
        );

        CREATE INDEX IF NOT EXISTS idx_forks_original ON session_forks(original_session_id);
        CREATE INDEX IF NOT EXISTS idx_forks_session ON session_forks(forked_session_id);
        CREATE INDEX IF NOT EXISTS idx_annotations_session ON annotations(session_id);
        CREATE INDEX IF NOT EXISTS idx_annotations_turn ON annotations(session_id, turn_number);
    """)
    conn.commit()
    conn.close()


# ─── FORK SESSIONS ──────────────────────────────────────────────────────────

def fork_session(original_session_id: str, forked_by: str = "",
                 fork_point: int = 0) -> Optional[dict]:
    """Fork a session from a specific turn point."""
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get original session
    cur.execute("SELECT * FROM memory_sessions WHERE session_id = ?", (original_session_id,))
    original = cur.fetchone()
    if not original:
        conn.close()
        return None

    original = dict(original)

    # Create forked session
    forked_session_id = f"{original_session_id}_fork_{int(time.time() * 1000) % 1000000:06d}"
    fork_id = f"fork_{int(time.time() * 1000) % 1000000000:09d}"

    cur.execute(
        """INSERT INTO memory_sessions (session_id, topic, persona_ids, started_at, turn_count)
           VALUES (?, ?, ?, ?, ?)""",
        (forked_session_id, f"[Fork] {original['topic']}", original["persona_ids"],
         time.time(), 0)
    )

    # Copy messages up to fork point
    if fork_point > 0:
        cur.execute(
            "SELECT * FROM memory_messages WHERE session_id = ? AND turn_number <= ? ORDER BY turn_number",
            (original_session_id, fork_point)
        )
        messages = cur.fetchall()
        for msg in messages:
            cur.execute(
                """INSERT INTO memory_messages (session_id, persona_id, role, content, turn_number)
                   VALUES (?, ?, ?, ?, ?)""",
                (forked_session_id, msg["persona_id"], msg["role"], msg["content"], msg["turn_number"])
            )
        cur.execute(
            "UPDATE memory_sessions SET turn_count = ? WHERE session_id = ?",
            (fork_point, forked_session_id)
        )
    else:
        # Copy just the system prompt / topic
        cur.execute(
            """INSERT INTO memory_messages (session_id, persona_id, role, content, turn_number)
               VALUES (?, 'system', 'system', ?, 0)""",
            (forked_session_id, f"Forked from {original_session_id}")
        )

    # Record fork
    cur.execute(
        """INSERT INTO session_forks (fork_id, original_session_id, forked_session_id,
                                       forked_by, fork_point)
           VALUES (?, ?, ?, ?, ?)""",
        (fork_id, original_session_id, forked_session_id, forked_by, fork_point)
    )

    conn.commit()
    conn.close()

    return {
        "fork_id": fork_id,
        "original_session_id": original_session_id,
        "forked_session_id": forked_session_id,
        "forked_by": forked_by,
        "fork_point": fork_point,
        "topic": f"[Fork] {original['topic']}",
    }


def get_forks(original_session_id: str) -> List[dict]:
    """Get all forks of a session."""
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM session_forks WHERE original_session_id = ? ORDER BY created_at DESC",
        (original_session_id,)
    )
    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_fork_history(forked_session_id: str) -> Optional[dict]:
    """Get the fork history for a session."""
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM session_forks WHERE forked_session_id = ?",
        (forked_session_id,)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return None
    return dict(row)


# ─── SIDE-BY-SIDE COMPARISON ────────────────────────────────────────────────

def create_comparison(session_a_id: str, session_b_id: str,
                       created_by: str = "") -> Optional[dict]:
    """Create a side-by-side comparison of two sessions."""
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Verify both sessions exist
    cur.execute("SELECT session_id, topic FROM memory_sessions WHERE session_id IN (?, ?)",
                (session_a_id, session_b_id))
    sessions = cur.fetchall()
    if len(sessions) != 2:
        conn.close()
        return None

    comparison_id = f"cmp_{int(time.time() * 1000) % 1000000000:09d}"
    cur.execute(
        """INSERT INTO session_comparisons (comparison_id, session_a_id, session_b_id, created_by)
           VALUES (?, ?, ?, ?)""",
        (comparison_id, session_a_id, session_b_id, created_by)
    )
    conn.commit()
    conn.close()

    session_a = dict(sessions[0])
    session_b = dict(sessions[1])

    return {
        "comparison_id": comparison_id,
        "session_a": session_a,
        "session_b": session_b,
        "created_by": created_by,
    }


def get_comparison(comparison_id: str) -> Optional[dict]:
    """Get a comparison with full session details."""
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM session_comparisons WHERE comparison_id = ?", (comparison_id,))
    comp = cur.fetchone()
    if not comp:
        conn.close()
        return None

    comp = dict(comp)

    # Get messages for both sessions
    messages_a = _get_session_messages(conn, comp["session_a_id"])
    messages_b = _get_session_messages(conn, comp["session_b_id"])

    # Get evaluation scores
    scores_a = _get_session_scores(conn, comp["session_a_id"])
    scores_b = _get_session_scores(conn, comp["session_b_id"])

    conn.close()

    return {
        "comparison_id": comparison_id,
        "session_a": {
            "session_id": comp["session_a_id"],
            "messages": messages_a,
            "scores": scores_a,
            "turn_count": len(messages_a),
        },
        "session_b": {
            "session_id": comp["session_b_id"],
            "messages": messages_b,
            "scores": scores_b,
            "turn_count": len(messages_b),
        },
        "created_by": comp["created_by"],
        "created_at": comp["created_at"],
    }


def _get_session_messages(conn, session_id: str) -> List[dict]:
    """Get messages for a session."""
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT * FROM memory_messages WHERE session_id = ? ORDER BY turn_number",
            (session_id,)
        )
        return [dict(row) for row in cur.fetchall()]
    except Exception:
        return []


def _get_session_scores(conn, session_id: str) -> Dict[str, float]:
    """Get evaluation scores for a session."""
    cur = conn.cursor()
    scores = {}
    try:
        cur.execute(
            "SELECT dimension, score FROM evaluation_scores WHERE session_id = ?",
            (session_id,)
        )
        for row in cur.fetchall():
            scores[row["dimension"]] = row["score"]
    except Exception:
        pass
    return scores


# ─── TURN-LEVEL ANNOTATIONS ─────────────────────────────────────────────────

def create_annotation(session_id: str, turn_number: int, content: str,
                       user_id: str = "", annotation_type: str = "comment") -> Optional[dict]:
    """Add an annotation/comment to a specific turn in a session."""
    conn = sqlite3.connect(str(_memory_db_path()))
    cur = conn.cursor()

    # Verify session exists
    cur.execute("SELECT session_id FROM memory_sessions WHERE session_id = ?", (session_id,))
    if not cur.fetchone():
        conn.close()
        return None

    annotation_id = f"ann_{int(time.time() * 1000) % 1000000000:09d}"
    cur.execute(
        """INSERT INTO annotations (annotation_id, session_id, turn_number, user_id,
                                     content, annotation_type)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (annotation_id, session_id, turn_number, user_id, content, annotation_type)
    )
    conn.commit()
    conn.close()

    return {
        "annotation_id": annotation_id,
        "session_id": session_id,
        "turn_number": turn_number,
        "user_id": user_id,
        "content": content,
        "annotation_type": annotation_type,
    }


def get_annotations(session_id: str, turn_number: int = None) -> List[dict]:
    """Get annotations for a session, optionally filtered by turn."""
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if turn_number is not None:
        cur.execute(
            "SELECT * FROM annotations WHERE session_id = ? AND turn_number = ? ORDER BY created_at",
            (session_id, turn_number)
        )
    else:
        cur.execute(
            "SELECT * FROM annotations WHERE session_id = ? ORDER BY turn_number, created_at",
            (session_id,)
        )

    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def update_annotation(annotation_id: str, content: str) -> bool:
    """Update an annotation's content."""
    conn = sqlite3.connect(str(_memory_db_path()))
    cur = conn.cursor()
    cur.execute(
        "UPDATE annotations SET content = ?, updated_at = julianday('now') WHERE annotation_id = ?",
        (content, annotation_id)
    )
    updated = cur.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def delete_annotation(annotation_id: str) -> bool:
    """Delete an annotation."""
    conn = sqlite3.connect(str(_memory_db_path()))
    cur = conn.cursor()
    cur.execute("DELETE FROM annotations WHERE annotation_id = ?", (annotation_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_annotation_summary(session_id: str) -> Dict:
    """Get annotation summary for a session."""
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """SELECT COUNT(*) as total,
                  COUNT(CASE WHEN annotation_type = 'comment' THEN 1 END) as comments,
                  COUNT(CASE WHEN annotation_type = 'question' THEN 1 END) as questions,
                  COUNT(CASE WHEN annotation_type = 'feedback' THEN 1 END) as feedback,
                  COUNT(DISTINCT turn_number) as annotated_turns
           FROM annotations WHERE session_id = ?""",
        (session_id,)
    )
    row = cur.fetchone()
    conn.close()

    return {
        "session_id": session_id,
        "total": row["total"] if row else 0,
        "comments": row["comments"] if row else 0,
        "questions": row["questions"] if row else 0,
        "feedback": row["feedback"] if row else 0,
        "annotated_turns": row["annotated_turns"] if row else 0,
    }
