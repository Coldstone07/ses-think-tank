"""Phase 5.3: Intelligence Tests"""
import pytest
import sys
import os
import tempfile
import time
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from intelligence import (
    init_intelligence_schema, tokenize, compute_tfidf_vector, cosine_similarity,
    generate_session_embedding, generate_session_embeddings,
    semantic_search, synthesize_across_sessions,
    generate_knowledge_from_sessions, get_persona_knowledge,
    compute_quality_trend, get_quality_overview,
)


@pytest.fixture
def tmp_intelligence_db(tmp_path):
    """Create temp DB with intelligence schema + test data."""
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
        CREATE TABLE IF NOT EXISTS session_insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            category TEXT NOT NULL,
            content TEXT DEFAULT '',
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

    # Intelligence schema
    init_intelligence_schema()

    # Test data
    now = time.time()
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, persona_ids, started_at, turn_count) VALUES (?, ?, ?, ?, ?)",
        ("sess-1", "AI Ethics and Responsibility", "rook,elena", now, 5)
    )
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, persona_ids, started_at, turn_count) VALUES (?, ?, ?, ?, ?)",
        ("sess-2", "Machine Learning Fairness", "rook,kael", now + 100, 4)
    )
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, persona_ids, started_at, turn_count) VALUES (?, ?, ?, ?, ?)",
        ("sess-3", "Climate Change Solutions", "elena,maya", now + 200, 3)
    )

    # Messages
    cur.executescript("""
        INSERT INTO memory_messages (session_id, persona_id, role, content, turn_number) VALUES
        ('sess-1', 'rook', 'assistant', 'AI ethics requires careful consideration of bias and fairness in algorithms', 1),
        ('sess-1', 'elena', 'assistant', 'We need frameworks that prioritize human wellbeing over profit', 2),
        ('sess-2', 'rook', 'assistant', 'Machine learning models can perpetuate systemic bias if not carefully audited', 1),
        ('sess-2', 'kael', 'assistant', 'Fairness metrics need to be domain-specific and context-aware', 2),
        ('sess-3', 'elena', 'assistant', 'Climate solutions require both technology and policy changes', 1),
        ('sess-3', 'maya', 'assistant', 'Individual action matters but systemic change is essential', 2);
    """)

    # Insights
    cur.executescript("""
        INSERT INTO session_insights (session_id, category, content) VALUES
        ('sess-1', 'key_takeaway', 'AI ethics requires interdisciplinary approaches'),
        ('sess-1', 'action_item', 'Develop bias audit frameworks'),
        ('sess-2', 'key_takeaway', 'Fairness in ML requires domain-specific metrics'),
        ('sess-3', 'key_takeaway', 'Climate action needs both tech and policy');
    """)

    # Evaluation scores
    cur.executescript("""
        INSERT INTO evaluation_scores (session_id, dimension, score, notes) VALUES
        ('sess-1', 'social_presence', 4.2, 'Good engagement'),
        ('sess-1', 'emotional_depth', 3.8, 'Could go deeper'),
        ('sess-2', 'social_presence', 3.9, 'Solid discussion'),
        ('sess-2', 'emotional_depth', 4.0, 'Good depth'),
        ('sess-3', 'social_presence', 4.5, 'Excellent engagement'),
        ('sess-3', 'emotional_depth', 4.2, 'Very emotional');
    """)

    conn.commit()
    conn.close()
    return tmp_path


def test_tokenize():
    tokens = tokenize("Hello World! This is a test.")
    assert "hello" in tokens
    assert "world" in tokens
    assert "test" in tokens
    assert len(tokens) == 4  # "is" and "a" are < 3 chars


def test_tfidf_vector():
    vocab = ["hello", "world", "test", "foo"]
    vec = compute_tfidf_vector("hello world hello test", vocab)
    assert "hello" in vec
    assert vec["hello"] > vec["world"]  # hello appears twice
    assert "foo" not in vec


def test_cosine_similarity_identical():
    vec = {"a": 1.0, "b": 2.0}
    assert cosine_similarity(vec, vec) == pytest.approx(1.0, abs=0.01)


def test_cosine_similarity_orthogonal():
    vec1 = {"a": 1.0, "b": 0.0}
    vec2 = {"a": 0.0, "b": 1.0}
    assert cosine_similarity(vec1, vec2) == pytest.approx(0.0, abs=0.01)


def test_cosine_similarity_empty():
    assert cosine_similarity({}, {}) == 0.0
    assert cosine_similarity({"a": 1}, {}) == 0.0


def test_generate_session_embedding(tmp_intelligence_db):
    generate_session_embedding("sess-1", "AI ethics and responsibility discussion", "test")

    import sqlite3
    conn = sqlite3.connect(str(tmp_intelligence_db / "memory.db"))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM session_embeddings")
    count = cur.fetchone()[0]
    conn.close()
    assert count >= 1


def test_generate_session_embeddings(tmp_intelligence_db):
    generate_session_embeddings("sess-1")

    import sqlite3
    conn = sqlite3.connect(str(tmp_intelligence_db / "memory.db"))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM session_embeddings WHERE session_id = ?", ("sess-1",))
    count = cur.fetchone()[0]
    conn.close()
    assert count >= 3  # topic + messages + summary


def test_semantic_search(tmp_intelligence_db):
    # Generate embeddings first
    generate_session_embeddings("sess-1")
    generate_session_embeddings("sess-2")
    generate_session_embeddings("sess-3")

    results = semantic_search("AI ethics bias", limit=5)
    assert len(results) > 0
    # sess-1 should rank high for "AI ethics"
    assert results[0]["session_id"] == "sess-1"
    assert results[0]["score"] > 0


def test_semantic_search_no_results():
    results = semantic_search("xyznonexistent123", min_score=0.5)
    assert len(results) == 0


def test_synthesize_across_sessions(tmp_intelligence_db):
    # Generate embeddings so content is indexed
    generate_session_embeddings("sess-1")
    generate_session_embeddings("sess-2")
    generate_session_embeddings("sess-3")

    result = synthesize_across_sessions(["AI", "ethics"], max_sessions=5)
    assert result["sessions_found"] >= 2
    assert "synthesis" in result
    assert result["insights_count"] >= 2


def test_synthesize_no_matches(tmp_intelligence_db):
    result = synthesize_across_sessions(["xyznonexistent"], max_sessions=5)
    assert result["sessions_found"] == 0


def test_generate_knowledge_from_sessions(tmp_intelligence_db):
    entries = generate_knowledge_from_sessions("rook")
    assert len(entries) > 0
    assert entries[0]["persona_id"] == "rook"


def test_get_persona_knowledge(tmp_intelligence_db):
    # Generate knowledge first
    generate_knowledge_from_sessions("rook")

    knowledge = get_persona_knowledge("rook")
    assert len(knowledge) > 0
    assert knowledge[0]["persona_id"] == "rook"


def test_get_persona_knowledge_by_domain(tmp_intelligence_db):
    generate_knowledge_from_sessions("rook", "ethics")
    knowledge = get_persona_knowledge("rook", "ethics")
    assert len(knowledge) > 0


def test_compute_quality_trend(tmp_intelligence_db):
    metrics = compute_quality_trend("sess-1")
    assert metrics["session_id"] == "sess-1"
    assert "social_score" in metrics
    assert "emotional_score" in metrics
    assert metrics["avg_turn_length"] > 0


def test_compute_quality_trend_not_found(tmp_intelligence_db):
    metrics = compute_quality_trend("nonexistent")
    assert metrics == {}


def test_get_quality_overview(tmp_intelligence_db):
    # Compute trends first
    compute_quality_trend("sess-1")
    compute_quality_trend("sess-2")
    compute_quality_trend("sess-3")

    overview = get_quality_overview(weeks=12)
    assert len(overview) > 0
    assert "avg_social" in overview[0]
    assert "session_count" in overview[0]


def test_init_intelligence_schema(tmp_intelligence_db):
    """Test that schema initializes all required tables."""
    import sqlite3
    conn = sqlite3.connect(str(tmp_intelligence_db / "memory.db"))
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cur.fetchall()]
    conn.close()

    assert "session_embeddings" in tables
    assert "semantic_index" in tables
    assert "cross_session_synthesis" in tables
    assert "auto_knowledge" in tables
    assert "quality_trends" in tables


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
