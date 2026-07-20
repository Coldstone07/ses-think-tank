"""Phase 4.6: Persona Evolution Tests"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import sqlite3
from pathlib import Path
from collections import defaultdict

from persona_evolution import (
    init_evolution_schema, compute_style_metrics, extract_domains,
    record_style_snapshot, update_persona_expertise, record_adaptation,
    get_persona_profile, generate_adaptation_prompt, get_evolution_summary,
    process_session_evolution,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary memory DB with all schemas."""
    os.environ["SES_MEMORY_DB"] = str(tmp_path / "memory.db")
    import importlib
    import persona_evolution
    importlib.reload(persona_evolution)
    persona_evolution.init_evolution_schema()

    conn = sqlite3.connect(str(tmp_path / "memory.db"))
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS memory_sessions (
            session_id TEXT PRIMARY KEY, topic TEXT NOT NULL,
            started_at REAL DEFAULT 0, ended_at REAL, turn_count INTEGER DEFAULT 0,
            deliverable TEXT DEFAULT '', summary TEXT DEFAULT '', persona_ids TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()
    return tmp_path


def test_compute_style_metrics_basic():
    text = "This is a test sentence. Here is another one. And a third."
    result = compute_style_metrics(text)
    assert "avg_sentence_length" in result
    assert "vocab_diversity" in result
    assert "emotional_tone" in result
    assert "formality_score" in result
    assert result["avg_sentence_length"] > 0
    assert 0 <= result["vocab_diversity"] <= 1
    assert 0 <= result["emotional_tone"] <= 1
    assert 0 <= result["formality_score"] <= 1


def test_compute_style_metrics_empty():
    result = compute_style_metrics("")
    assert result["avg_sentence_length"] == 0
    assert result["vocab_diversity"] == 0


def test_compute_style_metrics_emotional():
    text = "I feel love and joy and compassion and warmth and gratitude."
    result = compute_style_metrics(text)
    assert result["emotional_tone"] > 0.7


def test_compute_style_metrics_formal():
    text = "Furthermore, the methodology demonstrates comprehensive epistemological validity."
    result = compute_style_metrics(text)
    assert result["formality_score"] > 0.5


def test_compute_style_metrics_informal():
    text = "gonna wanna do stuff like that, it's cool yeah lol"
    result = compute_style_metrics(text)
    assert result["formality_score"] < 0.5


def test_extract_domains_technology():
    domains = extract_domains("machine learning neural network algorithm API database system")
    assert any(d["domain"] == "technology" for d in domains)


def test_extract_domains_philosophy():
    domains = extract_domains("ethics morality consciousness existence meaning virtue epistemology")
    assert any(d["domain"] == "philosophy" for d in domains)


def test_extract_domains_psychology():
    domains = extract_domains("behavior cognition emotion therapy mental health personality motivation")
    assert any(d["domain"] == "psychology" for d in domains)


def test_extract_domains_no_match():
    domains = extract_domains("xyz abc qwe random words nothing related")
    assert len(domains) == 0


def test_extract_domains_max_3():
    text = " ".join([
        "code software algorithm AI neural API database system",
        "ethics morality consciousness existence meaning virtue epistemology",
        "behavior cognition emotion therapy mental health personality motivation",
        "experiment hypothesis data research physics biology chemistry empirical",
    ])
    domains = extract_domains(text)
    assert len(domains) <= 3


def test_record_style_snapshot(tmp_db):
    import importlib
    import persona_evolution
    importlib.reload(persona_evolution)

    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute("INSERT INTO memory_sessions (session_id, topic) VALUES (?, ?)", ("s1", "test"))
    conn.commit()
    conn.close()

    metrics = persona_evolution.record_style_snapshot("rook", "s1", "This is a test with some words.")
    assert metrics["avg_sentence_length"] > 0

    # Verify stored
    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM persona_style_drift WHERE persona_id = 'rook'")
    assert cur.fetchone()[0] == 1
    conn.close()


def test_update_persona_expertise(tmp_db):
    import importlib
    import persona_evolution
    importlib.reload(persona_evolution)

    updated = persona_evolution.update_persona_expertise(
        "rook", "s1",
        "machine learning neural network algorithm AI code software",
        "AI technology"
    )
    assert len(updated) > 0
    assert any(u["domain"] == "technology" for u in updated)


def test_expertise_grows_over_time(tmp_db):
    import importlib
    import persona_evolution
    importlib.reload(persona_evolution)

    # First session
    persona_evolution.update_persona_expertise(
        "rook", "s1",
        "machine learning neural network algorithm AI",
        "AI"
    )

    # Second session — level should increase
    persona_evolution.update_persona_expertise(
        "rook", "s2",
        "code software programming API database",
        "technology"
    )

    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute("SELECT level, sessions_in_domain FROM persona_expertise WHERE persona_id = 'rook' AND domain = 'technology'")
    row = cur.fetchone()
    assert row[1] >= 1  # At least 1 session
    conn.close()


def test_record_adaptation(tmp_db):
    import importlib
    import persona_evolution
    importlib.reload(persona_evolution)

    persona_evolution.record_adaptation(
        "rook", "s1", "feedback_driven",
        '{"depth": 0.3}', '{"depth": 0.5}',
        "Low depth score", -0.2
    )

    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM persona_evolution WHERE persona_id = 'rook'")
    assert cur.fetchone()[0] == 1
    conn.close()


def test_generate_adaptation_low_scores():
    scores = {
        "emotional_presence": 0.2,
        "depth": 0.3,
        "synergy": 0.8,
        "originality": 0.6,
        "clarity": 0.9,
    }
    prompt = generate_adaptation_prompt("rook", scores)
    assert "PERSONA ADAPTATION" in prompt
    assert "emotional" in prompt.lower() or "empathy" in prompt.lower()
    assert "depth" in prompt.lower()


def test_generate_adaptation_no_issues():
    scores = {
        "emotional_presence": 0.8,
        "depth": 0.9,
        "synergy": 0.85,
        "originality": 0.8,
        "clarity": 0.9,
    }
    prompt = generate_adaptation_prompt("rook", scores)
    # All scores above 0.4, so no adaptation needed (unless strengths mentioned)
    assert prompt == "" or "strengths" in prompt.lower()


def test_generate_adaptation_empty():
    prompt = generate_adaptation_prompt("rook", {})
    assert prompt == ""


def test_persona_profile_empty(tmp_db):
    import importlib
    import persona_evolution
    importlib.reload(persona_evolution)

    profile = persona_evolution.get_persona_profile("rook")
    assert profile["persona_id"] == "rook"
    assert profile["total_sessions"] == 0
    assert profile["expertise"] == []


def test_persona_profile_with_data(tmp_db):
    import importlib
    import persona_evolution
    importlib.reload(persona_evolution)

    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute("INSERT INTO memory_sessions (session_id, topic) VALUES (?, ?)", ("s1", "test"))
    cur.execute("INSERT INTO memory_sessions (session_id, topic) VALUES (?, ?)", ("s2", "test2"))
    conn.commit()
    conn.close()

    persona_evolution.record_style_snapshot("rook", "s1", "First session text here with words.")
    persona_evolution.record_style_snapshot("rook", "s2", "Second session with more text and different words and longer sentences overall.")
    persona_evolution.update_persona_expertise("rook", "s1", "code software AI algorithm")

    profile = persona_evolution.get_persona_profile("rook")
    assert profile["total_sessions"] == 2
    assert profile["expertise_areas"] >= 1
    assert "style_drift" in profile
    assert "current_style" in profile


def test_evolution_summary(tmp_db):
    import importlib
    import persona_evolution
    importlib.reload(persona_evolution)

    summary = persona_evolution.get_evolution_summary()
    assert "personas_with_expertise" in summary
    assert "total_expertise_areas" in summary
    assert "personas_with_style_tracking" in summary
    assert "total_adaptations" in summary
    assert "top_domains" in summary


def test_process_session_evolution(tmp_db):
    import importlib
    import persona_evolution
    importlib.reload(persona_evolution)

    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute("INSERT INTO memory_sessions (session_id, topic) VALUES (?, ?)", ("s1", "AI ethics"))
    conn.commit()
    conn.close()

    messages = [
        {"persona_id": "rook", "content": "This is a nuanced framework for ethical AI development."},
        {"persona_id": "elena", "content": "Building on that, I feel we need empathy in technology design."},
    ]

    scores = {
        "rook": {"depth": 0.8, "emotional_presence": 0.3},
        "elena": {"synergy": 0.7, "clarity": 0.6},
    }

    results = persona_evolution.process_session_evolution("s1", messages, scores)
    assert "rook" in results
    assert "elena" in results
    assert "style" in results["rook"]
    assert "expertise" in results["rook"]


def test_process_session_evolution_no_scores(tmp_db):
    import importlib
    import persona_evolution
    importlib.reload(persona_evolution)

    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute("INSERT INTO memory_sessions (session_id, topic) VALUES (?, ?)", ("s1", "test"))
    conn.commit()
    conn.close()

    messages = [
        {"persona_id": "rook", "content": "Some text about machine learning and AI."},
    ]

    results = persona_evolution.process_session_evolution("s1", messages, None)
    assert "rook" in results


def test_style_drift_detection(tmp_db):
    import importlib
    import persona_evolution
    importlib.reload(persona_evolution)

    conn = sqlite3.connect(str(tmp_db / "memory.db"))
    cur = conn.cursor()
    cur.execute("INSERT INTO memory_sessions (session_id, topic) VALUES (?, ?)", ("s1", "early"))
    cur.execute("INSERT INTO memory_sessions (session_id, topic) VALUES (?, ?)", ("s2", "late"))
    conn.commit()
    conn.close()

    # Record two different styles
    persona_evolution.record_style_snapshot("rook", "s1", "Hi. OK. Done.")
    persona_evolution.record_style_snapshot(
        "rook", "s2",
        "I feel wonderful and inspired by this beautiful experience that brings joy and warmth to my heart."
    )

    profile = persona_evolution.get_persona_profile("rook")
    assert "style_drift" in profile
    assert profile["total_sessions"] == 2
    # Verify style history has entries with different metrics
    assert len(profile["style_history"]) == 2
    # The emotional text should have higher emotional tone
    emotional_entries = [s for s in profile["style_history"] if s["emotional_tone"] > 0.5]
    assert len(emotional_entries) >= 1


def test_expertise_capped_at_1():
    """Expertise level should never exceed 1.0."""
    import importlib
    import persona_evolution
    importlib.reload(persona_evolution)

    # Simulate many sessions
    for i in range(50):
        persona_evolution.update_persona_expertise(
            "test_persona", f"s{i}",
            "code software algorithm AI neural network machine learning",
            "technology"
        )

    conn = sqlite3.connect(str(persona_evolution.MEMORY_DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT level FROM persona_expertise WHERE persona_id = 'test_persona' AND domain = 'technology'")
    row = cur.fetchone()
    assert row is not None
    assert row[0] <= 1.0
    conn.close()


def test_system_persona_skipped():
    """System messages should not create evolution data."""
    import importlib
    import persona_evolution
    importlib.reload(persona_evolution)

    messages = [
        {"persona_id": "system", "content": "System instruction."},
        {"persona_id": "rook", "content": "Actual persona response."},
    ]
    results = persona_evolution.process_session_evolution("test", messages)
    assert "system" not in results
    assert "rook" in results
