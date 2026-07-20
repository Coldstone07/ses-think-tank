"""Phase 5.5: Collaboration Tests"""
import pytest
import sys
import os
import tempfile
import time
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from collaboration import (
    init_collab_schema, fork_session, get_forks, get_fork_history,
    create_comparison, get_comparison,
    create_annotation, get_annotations, update_annotation,
    delete_annotation, get_annotation_summary,
)


@pytest.fixture
def tmp_collab_db(tmp_path):
    """Create temp DB with collab schema + test data."""
    os.environ["SES_MEMORY_DB"] = str(tmp_path / "memory.db")

    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "memory.db"))
    cur = conn.cursor()
    # Base schema
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS memory_sessions (
            session_id TEXT PRIMARY KEY,
            topic TEXT NOT NULL,
            persona_ids TEXT NOT NULL,
            started_at REAL DEFAULT (julianday('now')),
            ended_at REAL,
            turn_count INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS memory_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            persona_id TEXT DEFAULT '',
            role TEXT DEFAULT 'assistant',
            content TEXT DEFAULT '',
            turn_number INTEGER DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES memory_sessions(session_id)
        );
        CREATE TABLE IF NOT EXISTS evaluation_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            dimension TEXT NOT NULL,
            score REAL DEFAULT 0,
            notes TEXT DEFAULT '',
            FOREIGN KEY (session_id) REFERENCES memory_sessions(session_id)
        );
    """)

    # Collab schema
    init_collab_schema()

    # Test sessions
    now = time.time()
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, persona_ids, started_at, turn_count) VALUES (?, ?, ?, ?, ?)",
        ("sess-1", "AI Ethics", "rook,elena", now, 5)
    )
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, persona_ids, started_at, turn_count) VALUES (?, ?, ?, ?, ?)",
        ("sess-2", "Climate Policy", "elena,maya", now + 100, 4)
    )
    cur.executescript("""
        INSERT INTO memory_messages (session_id, persona_id, role, content, turn_number) VALUES
        ('sess-1', 'rook', 'assistant', 'AI ethics discussion point 1', 1),
        ('sess-1', 'elena', 'assistant', 'AI ethics discussion point 2', 2),
        ('sess-1', 'rook', 'assistant', 'AI ethics discussion point 3', 3),
        ('sess-1', 'elena', 'assistant', 'AI ethics discussion point 4', 4),
        ('sess-1', 'rook', 'assistant', 'AI ethics discussion point 5', 5),
        ('sess-2', 'elena', 'assistant', 'Climate policy point 1', 1),
        ('sess-2', 'maya', 'assistant', 'Climate policy point 2', 2),
        ('sess-2', 'elena', 'assistant', 'Climate policy point 3', 3),
        ('sess-2', 'maya', 'assistant', 'Climate policy point 4', 4);
    """)
    cur.executescript("""
        INSERT INTO evaluation_scores (session_id, dimension, score) VALUES
        ('sess-1', 'social_presence', 4.2),
        ('sess-1', 'emotional_depth', 3.8),
        ('sess-2', 'social_presence', 4.5),
        ('sess-2', 'emotional_depth', 4.0);
    """)

    conn.commit()
    conn.close()
    return tmp_path


# ─── FORK TESTS ─────────────────────────────────────────────────────────────

def test_fork_session(tmp_collab_db):
    fork = fork_session("sess-1", forked_by="testuser")
    assert fork is not None
    assert fork["original_session_id"] == "sess-1"
    assert fork["forked_session_id"].startswith("sess-1_fork_")
    assert fork["fork_point"] == 0


def test_fork_session_at_turn(tmp_collab_db):
    fork = fork_session("sess-1", forked_by="testuser", fork_point=2)
    assert fork["fork_point"] == 2

    # Verify messages were copied
    import sqlite3
    conn = sqlite3.connect(str(tmp_collab_db / "memory.db"))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM memory_messages WHERE session_id = ?", (fork["forked_session_id"],))
    count = cur.fetchone()[0]
    conn.close()
    assert count >= 2


def test_fork_session_not_found(tmp_collab_db):
    fork = fork_session("nonexistent")
    assert fork is None


def test_get_forks(tmp_collab_db):
    fork_session("sess-1", forked_by="user1")
    fork_session("sess-1", forked_by="user2")
    forks = get_forks("sess-1")
    assert len(forks) == 2


def test_get_forks_empty(tmp_collab_db):
    forks = get_forks("sess-1")
    assert forks == []


def test_get_fork_history(tmp_collab_db):
    fork = fork_session("sess-1", forked_by="testuser")
    history = get_fork_history(fork["forked_session_id"])
    assert history is not None
    assert history["original_session_id"] == "sess-1"


def test_get_fork_history_not_forked(tmp_collab_db):
    history = get_fork_history("sess-1")
    assert history is None


# ─── COMPARISON TESTS ───────────────────────────────────────────────────────

def test_create_comparison(tmp_collab_db):
    comp = create_comparison("sess-1", "sess-2", created_by="testuser")
    assert comp is not None
    assert comp["session_a"]["session_id"] == "sess-1"
    assert comp["session_b"]["session_id"] == "sess-2"


def test_create_comparison_not_found(tmp_collab_db):
    comp = create_comparison("nonexistent", "sess-1")
    assert comp is None


def test_get_comparison(tmp_collab_db):
    comp = create_comparison("sess-1", "sess-2", created_by="testuser")
    result = get_comparison(comp["comparison_id"])
    assert result is not None
    assert result["session_a"]["turn_count"] == 5
    assert result["session_b"]["turn_count"] == 4
    assert "scores" in result["session_a"]


def test_get_comparison_not_found(tmp_collab_db):
    assert get_comparison("nonexistent") is None


# ─── ANNOTATION TESTS ───────────────────────────────────────────────────────

def test_create_annotation(tmp_collab_db):
    ann = create_annotation("sess-1", turn_number=1, content="Great point!", user_id="user1")
    assert ann is not None
    assert ann["session_id"] == "sess-1"
    assert ann["turn_number"] == 1
    assert ann["annotation_type"] == "comment"


def test_create_annotation_not_found(tmp_collab_db):
    ann = create_annotation("nonexistent", turn_number=1, content="test")
    assert ann is None


def test_create_annotation_types(tmp_collab_db):
    ann = create_annotation("sess-1", turn_number=1, content="Why?", user_id="user1", annotation_type="question")
    assert ann["annotation_type"] == "question"


def test_get_annotations(tmp_collab_db):
    create_annotation("sess-1", turn_number=1, content="Note 1", user_id="user1")
    create_annotation("sess-1", turn_number=1, content="Note 2", user_id="user2")
    create_annotation("sess-1", turn_number=2, content="Note 3", user_id="user1")
    annotations = get_annotations("sess-1")
    assert len(annotations) == 3


def test_get_annotations_by_turn(tmp_collab_db):
    create_annotation("sess-1", turn_number=1, content="Note 1", user_id="user1")
    create_annotation("sess-1", turn_number=1, content="Note 2", user_id="user2")
    create_annotation("sess-1", turn_number=2, content="Note 3", user_id="user1")
    annotations = get_annotations("sess-1", turn_number=1)
    assert len(annotations) == 2


def test_get_annotations_empty(tmp_collab_db):
    annotations = get_annotations("sess-1")
    assert annotations == []


def test_update_annotation(tmp_collab_db):
    ann = create_annotation("sess-1", turn_number=1, content="Original", user_id="user1")
    assert update_annotation(ann["annotation_id"], "Updated content") is True

    updated = get_annotations("sess-1")
    assert len(updated) == 1
    assert updated[0]["content"] == "Updated content"


def test_update_annotation_not_found(tmp_collab_db):
    assert update_annotation("nonexistent", "content") is False


def test_delete_annotation(tmp_collab_db):
    ann = create_annotation("sess-1", turn_number=1, content="To delete", user_id="user1")
    assert delete_annotation(ann["annotation_id"]) is True
    assert len(get_annotations("sess-1")) == 0


def test_delete_annotation_not_found(tmp_collab_db):
    assert delete_annotation("nonexistent") is False


def test_annotation_summary(tmp_collab_db):
    create_annotation("sess-1", turn_number=1, content="Comment", user_id="user1", annotation_type="comment")
    create_annotation("sess-1", turn_number=1, content="Question", user_id="user1", annotation_type="question")
    create_annotation("sess-1", turn_number=2, content="Feedback", user_id="user1", annotation_type="feedback")

    summary = get_annotation_summary("sess-1")
    assert summary["session_id"] == "sess-1"
    assert summary["total"] == 3
    assert summary["comments"] == 1
    assert summary["questions"] == 1
    assert summary["feedback"] == 1
    assert summary["annotated_turns"] == 2


def test_annotation_summary_empty(tmp_collab_db):
    summary = get_annotation_summary("sess-1")
    assert summary["total"] == 0


def test_init_collab_schema(tmp_collab_db):
    """Verify all collab tables exist."""
    import sqlite3
    conn = sqlite3.connect(str(tmp_collab_db / "memory.db"))
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cur.fetchall()]
    conn.close()

    assert "session_forks" in tables
    assert "session_comparisons" in tables
    assert "annotations" in tables


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
