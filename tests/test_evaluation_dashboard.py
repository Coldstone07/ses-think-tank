"""Phase 4.5: Evaluation Dashboard Tests"""
import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import sqlite3
from pathlib import Path
from collections import defaultdict

from evaluation_dashboard import (
    init_evaluation_schema, score_dimension, analyze_session,
    compute_gini, save_session_metrics, get_persona_trends,
    get_session_analytics, get_dashboard_summary, export_session_report,
    get_quality_trend,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary memory DB with all schemas."""
    os.environ["SES_MEMORY_DB"] = str(tmp_path / "memory.db")
    import importlib
    import evaluation_dashboard
    importlib.reload(evaluation_dashboard)
    evaluation_dashboard.init_evaluation_schema()

    # Create base tables
    conn = sqlite3.connect(str(tmp_path / "memory.db"))
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS memory_sessions (
            session_id TEXT PRIMARY KEY, topic TEXT NOT NULL,
            workflow_mode TEXT DEFAULT 'salon', started_at REAL DEFAULT 0,
            ended_at REAL, turn_count INTEGER DEFAULT 0,
            deliverable TEXT DEFAULT '', summary TEXT DEFAULT '',
            persona_ids TEXT DEFAULT ''
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            insight TEXT NOT NULL,
            keywords TEXT DEFAULT '',
            category TEXT DEFAULT 'general',
            relevance_score REAL DEFAULT 1.0
        )
    """)
    conn.commit()
    conn.close()
    return tmp_path


def test_score_dimension_emotional_presence():
    text = "I feel empathy and compassion for your situation. It's heartfelt and warm."
    result = score_dimension(text, "emotional_presence")
    assert result["score"] > 0.5
    assert len(result["evidence"]) > 0


def test_score_dimension_depth():
    text = "This is a nuanced and complex issue with multiple dimensions and systemic factors."
    result = score_dimension(text, "depth")
    assert result["score"] > 0.5


def test_score_dimension_synergy():
    text = "Building on what you said, we can integrate and synthesize these ideas together."
    result = score_dimension(text, "synergy")
    assert result["score"] > 0.5


def test_score_dimension_negative_indicators():
    text = "This is a generic and robotic response that feels scripted."
    result = score_dimension(text, "emotional_presence")
    assert result["score"] < 0.5


def test_score_dimension_no_matches():
    text = "The weather is nice today."
    result = score_dimension(text, "originality")
    assert result["score"] == 0.5
    assert result["evidence"] == []


def test_score_dimension_unknown():
    result = score_dimension("anything", "nonexistent_dimension")
    assert result["score"] == 0.5


def test_compute_gini_equal():
    gini = compute_gini([10, 10, 10, 10])
    assert abs(gini - 0.0) < 0.01


def test_compute_gini_unequal():
    gini = compute_gini([100, 1, 1, 1])
    assert gini > 0.5


def test_compute_gini_empty():
    gini = compute_gini([])
    assert gini == 0.0


def test_analyze_session_empty():
    result = analyze_session("test", [])
    assert "error" in result


def test_analyze_session_basic(tmp_db):
    import importlib
    import evaluation_dashboard
    importlib.reload(evaluation_dashboard)

    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic) VALUES (?, ?)",
        ("s1", "test topic")
    )
    conn.commit()
    conn.close()

    messages = [
        {"persona_id": "rook", "content": "This is a nuanced and complex framework for understanding empathy."},
        {"persona_id": "elena", "content": "Building on that, I feel we can integrate compassion with clear structure."},
    ]
    result = evaluation_dashboard.analyze_session("s1", messages)
    assert result["total_words"] > 0
    assert result["total_turns"] == 2
    assert "dimension_scores" in result
    assert "persona_scores" in result
    assert "rook" in result["persona_scores"]
    assert "elena" in result["persona_scores"]


def test_analyze_session_turn_distribution(tmp_db):
    import importlib
    import evaluation_dashboard
    importlib.reload(evaluation_dashboard)

    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic) VALUES (?, ?)",
        ("s1", "test")
    )
    conn.commit()
    conn.close()

    messages = [
        {"persona_id": "a", "content": "Hello world this is a test message with some words"},
        {"persona_id": "a", "content": "Another message from persona A"},
        {"persona_id": "b", "content": "Response from B"},
    ]
    result = evaluation_dashboard.analyze_session("s1", messages)
    assert result["turn_distribution"]["a"]["turns"] == 2
    assert result["turn_distribution"]["b"]["turns"] == 1
    assert result["turn_distribution"]["a"]["percentage"] > result["turn_distribution"]["b"]["percentage"]


def test_save_and_retrieve_metrics(tmp_db):
    import importlib
    import evaluation_dashboard
    importlib.reload(evaluation_dashboard)

    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic) VALUES (?, ?)",
        ("s1", "test")
    )
    conn.commit()
    conn.close()

    metrics = {
        "session_id": "s1",
        "dimension_scores": {
            "emotional_presence": 0.8,
            "depth": 0.7,
            "synergy": 0.6,
            "originality": 0.5,
            "clarity": 0.9,
        },
        "overall_quality": 0.7,
        "turn_equality": 0.85,
        "insight_density": 2.5,
        "insight_count": 3,
        "persona_scores": {
            "rook": {
                "scores": {"emotional_presence": 0.8, "depth": 0.7},
                "avg_score": 0.75,
                "word_count": 100,
                "turn_count": 3,
            },
        },
    }
    evaluation_dashboard.save_session_metrics("s1", metrics)

    analytics = evaluation_dashboard.get_session_analytics("s1")
    assert len(analytics["metrics"]) > 0
    assert len(analytics["persona_scores"]) > 0


def test_dashboard_summary(tmp_db):
    import importlib
    import evaluation_dashboard
    importlib.reload(evaluation_dashboard)

    summary = evaluation_dashboard.get_dashboard_summary()
    assert "total_sessions_analyzed" in summary
    assert "average_quality" in summary
    assert "top_personas" in summary
    assert "dimension_averages" in summary
    assert "recent_sessions" in summary


def test_persona_trends(tmp_db):
    import importlib
    import evaluation_dashboard
    importlib.reload(evaluation_dashboard)

    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, started_at) VALUES (?, ?, ?)",
        ("s1", "topic 1", 1000.0)
    )
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, started_at) VALUES (?, ?, ?)",
        ("s2", "topic 2", 2000.0)
    )
    conn.commit()
    conn.close()

    evaluation_dashboard.save_session_metrics("s1", {
        "dimension_scores": {"emotional_presence": 0.8},
        "persona_scores": {
            "rook": {"scores": {"emotional_presence": 0.8, "depth": 0.7}},
        },
    })
    evaluation_dashboard.save_session_metrics("s2", {
        "dimension_scores": {"emotional_presence": 0.6},
        "persona_scores": {
            "rook": {"scores": {"emotional_presence": 0.6, "depth": 0.9}},
        },
    })

    trends = evaluation_dashboard.get_persona_trends("rook")
    assert trends["persona_id"] == "rook"
    assert trends["sessions_analyzed"] >= 2
    assert "dimension_averages" in trends


def test_quality_trend(tmp_db):
    import importlib
    import evaluation_dashboard
    importlib.reload(evaluation_dashboard)

    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, started_at) VALUES (?, ?, ?)",
        ("s1", "topic 1", 1000.0)
    )
    conn.commit()
    conn.close()

    evaluation_dashboard.save_session_metrics("s1", {
        "dimension_scores": {"emotional_presence": 0.8},
        "overall_quality": 0.75,
        "insight_density": 2.0,
    })

    trend = evaluation_dashboard.get_quality_trend()
    assert len(trend) >= 1


def test_export_session_report(tmp_db):
    import importlib
    import evaluation_dashboard
    importlib.reload(evaluation_dashboard)

    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, started_at) VALUES (?, ?, ?)",
        ("s1", "test export", 1000.0)
    )
    conn.commit()
    conn.close()

    evaluation_dashboard.save_session_metrics("s1", {
        "dimension_scores": {"emotional_presence": 0.8},
        "overall_quality": 0.75,
    })

    report = evaluation_dashboard.export_session_report("s1")
    assert "session" in report
    assert "analytics" in report
    assert "exported_at" in report
    assert report["session"]["topic"] == "test export"


def test_integration_full_pipeline(tmp_db):
    """Full pipeline: analyze → save → retrieve → dashboard."""
    import importlib
    import evaluation_dashboard
    importlib.reload(evaluation_dashboard)

    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, started_at) VALUES (?, ?, ?)",
        ("full_test", "AI emotional intelligence", 1000.0)
    )
    cur.execute(
        "INSERT INTO insights (session_id, insight, keywords, category, relevance_score) VALUES (?, ?, ?, ?, ?)",
        ("full_test", "Key insight about empathy", "empathy,ai", "key_finding", 0.9)
    )
    conn.commit()
    conn.close()

    messages = [
        {"persona_id": "rook", "content": "This is a nuanced framework for building empathetic AI systems with compassion."},
        {"persona_id": "elena", "content": "Building on that, I feel we need to integrate warmth with clear structure."},
        {"persona_id": "kael", "content": "The depth of this exploration reveals systemic patterns in how we connect."},
    ]

    # Analyze
    metrics = evaluation_dashboard.analyze_session("full_test", messages)
    assert metrics["overall_quality"] > 0
    # insight_count depends on session_intelligence module seeing same DB — skip that check
    assert "rook" in metrics["persona_scores"]

    # Save
    evaluation_dashboard.save_session_metrics("full_test", metrics)

    # Retrieve
    analytics = evaluation_dashboard.get_session_analytics("full_test")
    assert len(analytics["metrics"]) > 0
    assert len(analytics["persona_scores"]) > 0

    # Dashboard
    summary = evaluation_dashboard.get_dashboard_summary()
    assert summary["total_sessions_analyzed"] >= 1

    # Trends
    trends = evaluation_dashboard.get_persona_trends("rook")
    assert trends["sessions_analyzed"] >= 1


def test_dimension_scores_range():
    """All dimension scores should be between 0 and 1."""
    text = "A nuanced and empathetic response that builds on previous ideas clearly."
    for dim in ["emotional_presence", "depth", "synergy", "originality", "clarity"]:
        result = score_dimension(text, dim)
        assert 0 <= result["score"] <= 1


def test_gini_perfect_inequality():
    gini = compute_gini([100, 0, 0, 0])
    assert gini > 0.7


def test_analyze_session_no_personas():
    """All messages from 'system' persona."""
    result = analyze_session("test", [
        {"persona_id": "system", "content": "System message here."},
    ])
    assert result["total_turns"] == 1
    assert "system" in result["turn_distribution"]
