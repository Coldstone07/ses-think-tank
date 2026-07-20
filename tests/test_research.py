"""Phase 5.4: Research & Benchmarking Tests"""
import pytest
import sys
import os
import tempfile
import time
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from research import (
    init_research_schema, create_template, get_template, list_templates,
    use_template, delete_template,
    create_ab_test, get_ab_test, record_ab_result, get_ab_test_summary,
    create_provider_comparison, record_provider_result, get_provider_comparison,
    create_reproducible_session, get_reproducible_session, verify_reproducibility,
    compute_ses_scores, get_ses_scores, export_ses_scores_csv,
)


@pytest.fixture
def tmp_research_db(tmp_path):
    """Create temp DB with research schema + test data."""
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

    # Research schema
    init_research_schema()

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
        ('sess-1', 'rook', 'assistant', 'We need to share our understanding and listen to each other to find meaning and purpose in AI ethics', 1),
        ('sess-1', 'elena', 'assistant', 'This connection helps us feel the emotion and passion for growth and transformation', 2),
        ('sess-2', 'elena', 'assistant', 'Together we can transform climate policy with wisdom and purpose', 1),
        ('sess-2', 'maya', 'assistant', 'Individual action matters but we need systemic change and meaning', 2);
    """)
    cur.executescript("""
        INSERT INTO evaluation_scores (session_id, dimension, score) VALUES
        ('sess-1', 'social_presence', 4.2),
        ('sess-1', 'emotional_depth', 3.8),
        ('sess-1', 'spiritual_depth', 3.5),
        ('sess-2', 'social_presence', 4.5),
        ('sess-2', 'emotional_depth', 4.0),
        ('sess-2', 'spiritual_depth', 3.8);
    """)

    conn.commit()
    conn.close()
    return tmp_path


# ─── TEMPLATE TESTS ─────────────────────────────────────────────────────────

def test_create_template(tmp_research_db):
    t = create_template(
        name="AI Ethics Discussion",
        description="Explore AI ethics with Rook and Elena",
        personas=["rook", "elena"],
        topic="AI Ethics",
        workflow="open_discussion",
        created_by="testuser",
    )
    assert t["name"] == "AI Ethics Discussion"
    assert t["personas"] == ["rook", "elena"]
    assert t["usage_count"] == 0


def test_get_template(tmp_research_db):
    t = create_template("Test Template", "desc", ["rook"], created_by="testuser")
    fetched = get_template(t["template_id"])
    assert fetched is not None
    assert fetched["name"] == "Test Template"


def test_get_template_not_found(tmp_research_db):
    assert get_template("nonexistent") is None


def test_list_templates(tmp_research_db):
    create_template("Template A", "a", ["rook"], created_by="testuser")
    create_template("Template B", "b", ["elena"], created_by="testuser")
    templates = list_templates()
    assert len(templates) == 2


def test_use_template(tmp_research_db):
    t = create_template("Popular", "p", ["rook"], created_by="testuser")
    used = use_template(t["template_id"])
    assert used["usage_count"] == 1
    used2 = use_template(t["template_id"])
    assert used2["usage_count"] == 2


def test_delete_template(tmp_research_db):
    t = create_template("ToDelete", "d", ["rook"], created_by="testuser")
    assert delete_template(t["template_id"]) is True
    assert get_template(t["template_id"]) is None


def test_delete_template_not_found(tmp_research_db):
    assert delete_template("nonexistent") is False


# ─── A/B TEST TESTS ─────────────────────────────────────────────────────────

def test_create_ab_test(tmp_research_db):
    test = create_ab_test(
        name="Rook vs Kael",
        description="Compare personas",
        variant_a_personas=["rook"],
        variant_b_personas=["kael"],
        topic="AI Ethics",
    )
    assert test["name"] == "Rook vs Kael"
    assert test["variant_a_personas"] == ["rook"]
    assert test["variant_b_personas"] == ["kael"]
    assert test["status"] == "pending"


def test_record_ab_result(tmp_research_db):
    test = create_ab_test("AB Test", "desc", ["rook"], ["kael"])
    result = record_ab_result(
        test_id=test["test_id"],
        variant="A",
        session_id="sess-a",
        social_score=4.0,
        emotional_score=3.5,
        spiritual_score=3.0,
        turn_count=10,
    )
    assert result["variant"] == "A"


def test_ab_test_summary(tmp_research_db):
    test = create_ab_test("Full Test", "desc", ["rook"], ["kael"])
    record_ab_result(test["test_id"], "A", "sess-a", social_score=4.0, emotional_score=3.5, spiritual_score=3.0, turn_count=10)
    record_ab_result(test["test_id"], "B", "sess-b", social_score=3.5, emotional_score=4.0, spiritual_score=3.5, turn_count=12)

    summary = get_ab_test_summary(test["test_id"])
    assert summary is not None
    assert summary["variants"]["A"]["count"] == 1
    assert summary["variants"]["B"]["count"] == 1
    assert summary["winner"] in ["A", "B"]


def test_ab_test_summary_inconclusive(tmp_research_db):
    test = create_ab_test("Empty Test", "desc", ["rook"], ["kael"])
    summary = get_ab_test_summary(test["test_id"])
    assert summary["winner"] == "inconclusive"


# ─── PROVIDER COMPARISON TESTS ──────────────────────────────────────────────

def test_create_provider_comparison(tmp_research_db):
    comp = create_provider_comparison("Model Comparison", "Tell me about AI ethics")
    assert comp["name"] == "Model Comparison"
    assert comp["prompt"] == "Tell me about AI ethics"


def test_record_provider_result(tmp_research_db):
    comp = create_provider_comparison("Comparison", "Prompt")
    result = record_provider_result(
        comparison_id=comp["comparison_id"],
        provider="openai",
        model="gpt-4",
        response="AI ethics is important",
        response_time=1.5,
        token_count=50,
        social_score=4.0,
        emotional_score=3.5,
        spiritual_score=3.0,
    )
    assert result["provider"] == "openai"


def test_get_provider_comparison(tmp_research_db):
    comp = create_provider_comparison("Full Comparison", "Prompt")
    record_provider_result(comp["comparison_id"], "openai", "gpt-4", "Response A", social_score=4.0)
    record_provider_result(comp["comparison_id"], "anthropic", "claude-3", "Response B", social_score=4.5)

    result = get_provider_comparison(comp["comparison_id"])
    assert result["provider_count"] == 2
    assert len(result["results"]) == 2


def test_get_provider_comparison_not_found(tmp_research_db):
    assert get_provider_comparison("nonexistent") is None


# ─── REPRODUCIBILITY TESTS ──────────────────────────────────────────────────

def test_create_reproducible_session(tmp_research_db):
    result = create_reproducible_session(
        session_id="sess-1",
        seed="test-seed-123",
        prompt="Discuss AI ethics",
        personas=["rook", "elena"],
        config={"max_turns": 10},
    )
    assert result["seed"] == "test-seed-123"
    assert result["checksum"] is not None
    assert len(result["checksum"]) == 16


def test_get_reproducible_session(tmp_research_db):
    create_reproducible_session("sess-1", "my-seed", "Prompt", ["rook"])
    result = get_reproducible_session("my-seed")
    assert result is not None
    assert result["session_id"] == "sess-1"
    assert result["personas"] == ["rook"]


def test_get_reproducible_session_not_found(tmp_research_db):
    assert get_reproducible_session("nonexistent") is None


def test_verify_reproducibility(tmp_research_db):
    create_reproducible_session("sess-1", "verify-seed", "Original prompt", ["rook"])
    assert verify_reproducibility("sess-1", "verify-seed", "Original prompt", ["rook"]) is True


def test_verify_reproducibility_mismatch(tmp_research_db):
    create_reproducible_session("sess-1", "verify-seed", "Original prompt", ["rook"])
    assert verify_reproducibility("sess-1", "verify-seed", "Different prompt", ["rook"]) is False


def test_verify_reproducibility_not_found(tmp_research_db):
    assert verify_reproducibility("sess-1", "nonexistent", "prompt", ["rook"]) is False


# ─── SES SCORES TESTS ───────────────────────────────────────────────────────

def test_compute_ses_scores(tmp_research_db):
    scores = compute_ses_scores("sess-1")
    assert scores["session_id"] == "sess-1"
    assert scores["social_score"] == 4.2
    assert scores["emotional_score"] == 3.8
    assert scores["spiritual_score"] == 3.5
    assert scores["overall_score"] == pytest.approx(3.83, abs=0.01)


def test_compute_ses_scores_no_eval(tmp_research_db):
    # Create session with no eval scores
    import sqlite3
    conn = sqlite3.connect(str(tmp_research_db / "memory.db"))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, persona_ids, started_at, turn_count) VALUES (?, ?, ?, ?, ?)",
        ("sess-noeval", "Test", "rook", time.time(), 2)
    )
    cur.execute(
        "INSERT INTO memory_messages (session_id, persona_id, role, content, turn_number) VALUES (?, ?, ?, ?, ?)",
        ("sess-noeval", "rook", "assistant", "We share understanding and find meaning in growth", 1)
    )
    conn.commit()
    conn.close()

    scores = compute_ses_scores("sess-noeval")
    assert scores["session_id"] == "sess-noeval"
    assert scores["overall_score"] > 0


def test_get_ses_scores(tmp_research_db):
    compute_ses_scores("sess-1")
    compute_ses_scores("sess-2")
    scores = get_ses_scores()
    assert len(scores) == 2


def test_get_ses_scores_by_session(tmp_research_db):
    compute_ses_scores("sess-1")
    scores = get_ses_scores(session_id="sess-1")
    assert len(scores) == 1
    assert scores[0]["session_id"] == "sess-1"


def test_export_ses_scores_csv(tmp_research_db):
    compute_ses_scores("sess-1")
    csv_content = export_ses_scores_csv()
    assert "session_id" in csv_content
    assert "sess-1" in csv_content
    assert "social_score" in csv_content


def test_export_ses_scores_csv_empty(tmp_research_db):
    csv_content = export_ses_scores_csv()
    assert csv_content == ""


def test_init_research_schema(tmp_research_db):
    """Verify all research tables exist."""
    import sqlite3
    conn = sqlite3.connect(str(tmp_research_db / "memory.db"))
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cur.fetchall()]
    conn.close()

    assert "session_templates" in tables
    assert "ab_tests" in tables
    assert "ab_test_results" in tables
    assert "provider_comparisons" in tables
    assert "provider_results" in tables
    assert "reproducible_sessions" in tables
    assert "ses_scores" in tables


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
