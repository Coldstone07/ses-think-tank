"""Phase 4.4: Session Intelligence Tests"""
import pytest
import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from session_intelligence import (
    init_intelligence_schema, tokenize, keyword_overlap_score,
    tfidf_keywords, extract_insights_from_session, save_insights,
    build_session_graph, get_related_sessions, smart_recall,
    get_session_insights, get_insight_summary, build_recall_prompt,
)
import sqlite3
from pathlib import Path


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary memory DB with schema."""
    os.environ["SES_MEMORY_DB"] = str(tmp_path / "memory.db")
    from session_intelligence import MEMORY_DB_PATH
    # Re-import to pick up new path
    import importlib
    import session_intelligence
    importlib.reload(session_intelligence)
    session_intelligence.init_intelligence_schema()

    # Create base tables
    conn = sqlite3.connect(str(tmp_path / "memory.db"))
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS memory_sessions (
            session_id TEXT PRIMARY KEY, topic TEXT NOT NULL,
            workflow_mode TEXT DEFAULT 'salon', started_at REAL,
            ended_at REAL, turn_count INTEGER DEFAULT 0,
            deliverable TEXT DEFAULT '', summary TEXT DEFAULT '',
            persona_ids TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()
    return tmp_path


def test_tokenize():
    tokens = tokenize("The quick brown fox jumps over the lazy dog!")
    assert "quick" in tokens
    assert "brown" in tokens
    assert "the" not in tokens
    assert "fox" in tokens


def test_tokenize_strips_punctuation():
    tokens = tokenize('Hello, world! It\'s a "test".')
    assert "hello" in tokens
    assert "world" in tokens
    assert "test" in tokens


def test_keyword_overlap_identical():
    score = keyword_overlap_score("machine learning models", "machine learning models")
    assert score == 1.0


def test_keyword_overlap_partial():
    score = keyword_overlap_score("machine learning models", "deep learning networks")
    assert 0.0 < score < 1.0


def test_keyword_overlap_no_overlap():
    score = keyword_overlap_score("machine learning", "cooking recipes")
    assert score == 0.0


def test_keyword_overlap_empty():
    score = keyword_overlap_score("", "something")
    assert score == 0.0


def test_tfidf_keywords():
    keywords = tfidf_keywords("machine learning is great, machine learning is powerful")
    assert "machine" in keywords or "learning" in keywords
    assert len(keywords) <= 10


def test_tfidf_keywords_empty():
    keywords = tfidf_keywords("")
    assert keywords == []


def test_extract_insights_key_finding():
    messages = [{"content": "The key insight is that reasoning models need emotional grounding."}]
    insights = extract_insights_from_session("test", messages)
    assert len(insights) >= 1
    assert any(i["category"] == "key_finding" for i in insights)


def test_extract_insights_recommendation():
    messages = [{"content": "We recommend using a multi-agent approach for complex reasoning tasks."}]
    insights = extract_insights_from_session("test", messages)
    assert len(insights) >= 1


def test_extract_insights_short_sentences_ignored():
    messages = [{"content": "Hi there."}]
    insights = extract_insights_from_session("test", messages)
    assert len(insights) == 0


def test_extract_insights_deduplication():
    content = "The key finding is X. The key finding is X. The key finding is X."
    messages = [{"content": content}]
    insights = extract_insights_from_session("test", messages)
    assert len(insights) <= 2  # Should deduplicate


def test_save_and_retrieve_insights(tmp_db):
    import importlib
    import session_intelligence
    importlib.reload(session_intelligence)

    insights = [{"insight": "Test insight", "keywords": "test", "category": "general", "relevance_score": 1.0}]
    session_intelligence.save_insights("test_session", insights)
    result = session_intelligence.get_session_insights("test_session")
    assert len(result) == 1
    assert result[0]["insight"] == "Test insight"


def test_build_session_graph(tmp_db):
    import importlib
    import session_intelligence
    importlib.reload(session_intelligence)

    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, summary) VALUES (?, ?, ?)",
        ("s1", "machine learning models", "discussed neural networks and transformers")
    )
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, summary) VALUES (?, ?, ?)",
        ("s2", "deep learning architectures", "explored transformer models and attention")
    )
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, summary) VALUES (?, ?, ?)",
        ("s3", "cooking recipes", "how to make pasta")
    )
    conn.commit()
    conn.close()

    connections = session_intelligence.build_session_graph()
    # s1 and s2 should be linked (ML overlap)
    linked_pairs = [(c["session_a"], c["session_b"]) for c in connections]
    assert ("s1", "s2") in linked_pairs or ("s2", "s1") in linked_pairs


def test_get_related_sessions(tmp_db):
    import importlib
    import session_intelligence
    importlib.reload(session_intelligence)

    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, summary) VALUES (?, ?, ?)",
        ("s1", "AI safety alignment", "discussed reward modeling")
    )
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, summary) VALUES (?, ?, ?)",
        ("s2", "AI safety research", "explored alignment techniques")
    )
    conn.commit()
    conn.close()

    session_intelligence.build_session_graph()
    related = session_intelligence.get_related_sessions("s1")
    assert len(related) >= 1
    assert related[0]["session_id"] == "s2"


def test_smart_recall(tmp_db):
    import importlib
    import session_intelligence
    importlib.reload(session_intelligence)

    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, summary) VALUES (?, ?, ?)",
        ("s1", "emotional intelligence in AI", "how to build empathetic systems")
    )
    cur.execute(
        "INSERT INTO insights (session_id, insight, keywords, category, relevance_score) VALUES (?, ?, ?, ?, ?)",
        ("s1", "Empathetic AI requires understanding human emotional states", "empathy,emotion,ai", "key_finding", 0.9)
    )
    conn.commit()
    conn.close()

    results = session_intelligence.smart_recall("building empathetic AI systems")
    assert len(results) >= 1


def test_smart_recall_no_match(tmp_db):
    import importlib
    import session_intelligence
    importlib.reload(session_intelligence)

    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, summary) VALUES (?, ?, ?)",
        ("s1", "cooking pasta", "recipe for spaghetti")
    )
    cur.execute(
        "INSERT INTO insights (session_id, insight, keywords, category, relevance_score) VALUES (?, ?, ?, ?, ?)",
        ("s1", "Use boiling water for pasta", "pasta,cooking,water", "example", 0.5)
    )
    conn.commit()
    conn.close()

    results = session_intelligence.smart_recall("quantum physics entanglement")
    assert len(results) == 0  # No overlap


def test_insight_summary(tmp_db):
    import importlib
    import session_intelligence
    importlib.reload(session_intelligence)

    summary = session_intelligence.get_insight_summary()
    assert "total_insights" in summary
    assert "by_category" in summary
    assert "total_connections" in summary
    assert "sessions_with_insights" in summary


def test_build_recall_prompt(tmp_db):
    import importlib
    import session_intelligence
    importlib.reload(session_intelligence)

    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, summary) VALUES (?, ?, ?)",
        ("s1", "design patterns", "SOLID principles and clean architecture")
    )
    cur.execute(
        "INSERT INTO insights (session_id, insight, keywords, category, relevance_score) VALUES (?, ?, ?, ?, ?)",
        ("s1", "Favor composition over inheritance for flexible designs", "composition,inheritance,design", "principle", 0.8)
    )
    conn.commit()
    conn.close()

    prompt = session_intelligence.build_recall_prompt("software design architecture")
    assert "RELEVANT PAST INSIGHTS" in prompt
    assert "composition" in prompt


def test_build_recall_prompt_no_match():
    prompt = build_recall_prompt("xyz non-existent topic")
    assert prompt == ""


def test_integration_insight_lifecycle(tmp_db):
    """Full lifecycle: extract → save → recall."""
    import importlib
    import session_intelligence
    importlib.reload(session_intelligence)

    # Seed a session
    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, summary) VALUES (?, ?, ?)",
        ("sess1", "AI ethics framework", "discussed responsible AI development")
    )
    conn.commit()
    conn.close()

    # Extract insights from conversation
    messages = [
        {"content": "The key insight is that AI systems should prioritize human well-being over pure efficiency."},
        {"content": "We recommend implementing ethical review boards for all ML deployments."},
    ]
    insights = session_intelligence.extract_insights_from_session("sess1", messages)
    assert len(insights) >= 1

    # Save
    session_intelligence.save_insights("sess1", insights)

    # Verify stored
    stored = session_intelligence.get_session_insights("sess1")
    assert len(stored) >= 1

    # Recall for related topic
    recalled = session_intelligence.smart_recall("responsible AI development ethics")
    assert len(recalled) >= 1


def test_session_graph_symmetric(tmp_db):
    """Session graph links should be bidirectional."""
    import importlib
    import session_intelligence
    importlib.reload(session_intelligence)

    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, summary) VALUES (?, ?, ?)",
        ("a", "neural networks deep learning", "backpropagation and gradient descent")
    )
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, summary) VALUES (?, ?, ?)",
        ("b", "deep learning neural architectures", "CNNs and RNNs for sequence modeling")
    )
    conn.commit()
    conn.close()

    connections = session_intelligence.build_session_graph()
    assert len(connections) >= 1

    # Both directions should find each other
    related_a = session_intelligence.get_related_sessions("a")
    related_b = session_intelligence.get_related_sessions("b")
    assert any(r["session_id"] == "b" for r in related_a)
    assert any(r["session_id"] == "a" for r in related_b)
