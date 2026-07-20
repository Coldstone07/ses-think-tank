"""Phase 5.2: Export & Distribution Tests"""
import pytest
import sys
import os
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from export import (
    export_session_markdown, export_all_sessions_markdown,
    get_public_session, generate_rss_feed,
    publish_session, unpublish_session,
)


@pytest.fixture
def tmp_memory_db(tmp_path):
    """Create a temporary memory DB with test data."""
    os.environ["SES_MEMORY_DB"] = str(tmp_path / "memory.db")
    os.environ["SES_AUTH_DB"] = str(tmp_path / "auth.db")

    import sqlite3
    # Create memory DB schema
    conn = sqlite3.connect(str(tmp_path / "memory.db"))
    cur = conn.cursor()
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
        CREATE TABLE IF NOT EXISTS session_insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            category TEXT NOT NULL,
            content TEXT DEFAULT '',
            FOREIGN KEY (session_id) REFERENCES memory_sessions(session_id)
        );
    """)
    # Insert test data
    now = time.time()
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, persona_ids, started_at, turn_count) VALUES (?, ?, ?, ?, ?)",
        ("test-session-1", "AI Ethics", "rook,elena", now, 3)
    )
    cur.execute(
        "INSERT INTO memory_messages (session_id, persona_id, role, content, turn_number) VALUES (?, ?, ?, ?, ?)",
        ("test-session-1", "user", "user", "Let's discuss AI ethics", 1)
    )
    cur.execute(
        "INSERT INTO memory_messages (session_id, persona_id, role, content, turn_number) VALUES (?, ?, ?, ?, ?)",
        ("test-session-1", "rook", "assistant", "AI ethics is a critical field...", 1)
    )
    cur.execute(
        "INSERT INTO memory_messages (session_id, persona_id, role, content, turn_number) VALUES (?, ?, ?, ?, ?)",
        ("test-session-1", "elena", "assistant", "I agree, we need frameworks...", 2)
    )
    # Add evaluation scores
    cur.execute(
        "INSERT INTO evaluation_scores (session_id, dimension, score, notes) VALUES (?, ?, ?, ?)",
        ("test-session-1", "social_presence", 4.2, "Good engagement")
    )
    cur.execute(
        "INSERT INTO evaluation_scores (session_id, dimension, score, notes) VALUES (?, ?, ?, ?)",
        ("test-session-1", "emotional_depth", 3.8, "Could go deeper")
    )
    # Add insights
    cur.execute(
        "INSERT INTO session_insights (session_id, category, content) VALUES (?, ?, ?)",
        ("test-session-1", "key_takeaway", "AI ethics requires interdisciplinary approaches")
    )
    conn.commit()
    conn.close()

    # Create auth DB schema
    from auth import init_auth_schema
    init_auth_schema()

    return tmp_path


def test_export_session_markdown(tmp_memory_db):
    md = export_session_markdown("test-session-1")
    assert md is not None
    assert "# AI Ethics" in md
    assert "**Session:** test-session-1" in md
    assert "## Discussion" in md
    assert "rook" in md
    assert "elena" in md
    assert "## Evaluation Scores" in md
    assert "## Key Insights" in md
    assert "AI ethics requires interdisciplinary approaches" in md


def test_export_session_markdown_not_found(tmp_memory_db):
    md = export_session_markdown("nonexistent-session")
    assert md is None


def test_export_all_sessions_markdown(tmp_memory_db):
    sessions = export_all_sessions_markdown()
    assert len(sessions) >= 1
    assert sessions[0]["session_id"] == "test-session-1"
    assert sessions[0]["topic"] == "AI Ethics"
    assert sessions[0]["turn_count"] == 3


def test_generate_rss_feed(tmp_memory_db):
    rss = generate_rss_feed("http://test.example.com")
    assert '<?xml version="1.0"' in rss
    assert '<rss version="2.0">' in rss
    assert "SES Think Tank Sessions" in rss
    assert "AI Ethics" in rss
    assert '<link>http://test.example.com/share/test-session-1</link>' in rss
    assert '</rss>' in rss


def test_generate_rss_feed_empty(tmp_memory_db):
    # Create empty memory DB
    os.environ["SES_MEMORY_DB"] = str(tmp_memory_db / "empty.db")
    import sqlite3
    conn = sqlite3.connect(str(tmp_memory_db / "empty.db"))
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS memory_sessions (
        session_id TEXT PRIMARY KEY, topic TEXT NOT NULL,
        persona_ids TEXT NOT NULL, started_at REAL, ended_at REAL, turn_count INTEGER
    )""")
    conn.commit()
    conn.close()

    rss = generate_rss_feed()
    assert '<?xml version="1.0"' in rss
    assert '<item>' not in rss  # No sessions = no items


def test_publish_session(tmp_memory_db):
    import importlib
    import auth
    importlib.reload(auth)
    auth.init_auth_schema()

    auth.register_user("publisher", "password123")
    user = auth.get_user_by_username("publisher")

    share_id = publish_session("test-session-1", user["user_id"])
    assert share_id is not None
    assert len(share_id) > 0


def test_unpublish_session(tmp_memory_db):
    import importlib
    import auth
    importlib.reload(auth)
    auth.init_auth_schema()

    auth.register_user("unpublisher", "password123")
    user = auth.get_user_by_username("unpublisher")

    share_id = publish_session("test-session-1", user["user_id"])
    unpublish_session(share_id, user["user_id"])

    # Verify it's gone
    share = auth.get_shared_session(share_id)
    assert share is None


def test_get_public_session(tmp_memory_db):
    import importlib
    import auth
    importlib.reload(auth)
    auth.init_auth_schema()

    auth.register_user("publicuser", "password123")
    user = auth.get_user_by_username("publicuser")

    share_id = publish_session("test-session-1", user["user_id"])

    session = get_public_session(share_id)
    assert session is not None
    assert session["session_id"] == "test-session-1"
    assert session["topic"] == "AI Ethics"
    assert len(session["messages"]) == 3


def test_get_public_session_not_found(tmp_memory_db):
    import importlib
    import auth
    importlib.reload(auth)
    auth.init_auth_schema()

    session = get_public_session("nonexistent-share")
    assert session is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
