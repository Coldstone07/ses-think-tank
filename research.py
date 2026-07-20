"""
Research & Benchmarking — Phase 5.4

Session templates, A/B persona testing, provider comparison,
seed-based reproducibility, and SES scoring export.
"""
import os
import sqlite3
import time
import json
import hashlib
import random
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple

MEMORY_DB_PATH = Path(os.environ.get("SES_MEMORY_DB", "data/memory.db"))


def _memory_db_path() -> Path:
    return Path(os.environ.get("SES_MEMORY_DB", "data/memory.db"))


def init_research_schema():
    """Create research tables for templates, A/B tests, and reproducibility."""
    conn = sqlite3.connect(str(_memory_db_path()))
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS session_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            personas TEXT NOT NULL,
            topic TEXT DEFAULT '',
            workflow TEXT DEFAULT '',
            system_prompt TEXT DEFAULT '',
            max_turns INTEGER DEFAULT 20,
            created_by TEXT DEFAULT '',
            created_at REAL DEFAULT (julianday('now')),
            usage_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS ab_tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            variant_a_personas TEXT NOT NULL,
            variant_b_personas TEXT NOT NULL,
            topic TEXT DEFAULT '',
            seed_input TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at REAL DEFAULT (julianday('now')),
            completed_at REAL
        );

        CREATE TABLE IF NOT EXISTS ab_test_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id TEXT NOT NULL,
            variant TEXT NOT NULL CHECK(variant IN ('A', 'B')),
            session_id TEXT NOT NULL,
            social_score REAL DEFAULT 0,
            emotional_score REAL DEFAULT 0,
            spiritual_score REAL DEFAULT 0,
            turn_count INTEGER DEFAULT 0,
            avg_response_time REAL DEFAULT 0,
            completed_at REAL DEFAULT (julianday('now')),
            FOREIGN KEY (test_id) REFERENCES ab_tests(test_id)
        );

        CREATE TABLE IF NOT EXISTS provider_comparisons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comparison_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            prompt TEXT NOT NULL,
            created_at REAL DEFAULT (julianday('now'))
        );

        CREATE TABLE IF NOT EXISTS provider_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            comparison_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT DEFAULT '',
            response TEXT DEFAULT '',
            response_time REAL DEFAULT 0,
            token_count INTEGER DEFAULT 0,
            social_score REAL DEFAULT 0,
            emotional_score REAL DEFAULT 0,
            spiritual_score REAL DEFAULT 0,
            completed_at REAL DEFAULT (julianday('now')),
            FOREIGN KEY (comparison_id) REFERENCES provider_comparisons(comparison_id)
        );

        CREATE TABLE IF NOT EXISTS reproducible_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            seed TEXT NOT NULL,
            prompt TEXT NOT NULL,
            personas TEXT NOT NULL,
            config TEXT DEFAULT '{}',
            checksum TEXT DEFAULT '',
            created_at REAL DEFAULT (julianday('now'))
        );

        CREATE TABLE IF NOT EXISTS ses_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            social_score REAL DEFAULT 0,
            emotional_score REAL DEFAULT 0,
            spiritual_score REAL DEFAULT 0,
            overall_score REAL DEFAULT 0,
            breakdown TEXT DEFAULT '{}',
            evaluated_at REAL DEFAULT (julianday('now')),
            FOREIGN KEY (session_id) REFERENCES memory_sessions(session_id)
        );

        CREATE INDEX IF NOT EXISTS idx_templates_name ON session_templates(name);
        CREATE INDEX IF NOT EXISTS idx_ab_tests_status ON ab_tests(status);
        CREATE INDEX IF NOT EXISTS idx_ab_results_test ON ab_test_results(test_id);
        CREATE INDEX IF NOT EXISTS idx_provider_comparison ON provider_comparisons(comparison_id);
        CREATE INDEX IF NOT EXISTS idx_reproducible_seed ON reproducible_sessions(seed);
        CREATE INDEX IF NOT EXISTS idx_ses_scores_session ON ses_scores(session_id);
    """)
    conn.commit()
    conn.close()


# ─── SESSION TEMPLATES ──────────────────────────────────────────────────────

def create_template(name: str, description: str, personas: List[str],
                     topic: str = "", workflow: str = "",
                     system_prompt: str = "", max_turns: int = 20,
                     created_by: str = "") -> dict:
    """Create a reusable session template."""
    template_id = f"tpl_{int(time.time() * 1000) % 1000000000:09d}"

    conn = sqlite3.connect(str(_memory_db_path()))
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO session_templates
           (template_id, name, description, personas, topic, workflow,
            system_prompt, max_turns, created_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (template_id, name, description, json.dumps(personas), topic,
         workflow, system_prompt, max_turns, created_by)
    )
    conn.commit()
    conn.close()

    return get_template(template_id)


def get_template(template_id: str) -> Optional[dict]:
    """Get a template by ID."""
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM session_templates WHERE template_id = ?", (template_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    template = dict(row)
    template["personas"] = json.loads(template.get("personas", "[]"))
    return template


def list_templates(limit: int = 50) -> List[dict]:
    """List all templates sorted by usage."""
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM session_templates ORDER BY usage_count DESC, created_at DESC LIMIT ?",
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()

    result = []
    for row in rows:
        t = dict(row)
        t["personas"] = json.loads(t.get("personas", "[]"))
        result.append(t)
    return result


def use_template(template_id: str) -> Optional[dict]:
    """Increment usage count and return template."""
    conn = sqlite3.connect(str(_memory_db_path()))
    cur = conn.cursor()
    cur.execute(
        "UPDATE session_templates SET usage_count = usage_count + 1 WHERE template_id = ?",
        (template_id,)
    )
    conn.commit()
    conn.close()

    return get_template(template_id)


def delete_template(template_id: str) -> bool:
    """Delete a template."""
    conn = sqlite3.connect(str(_memory_db_path()))
    cur = conn.cursor()
    cur.execute("DELETE FROM session_templates WHERE template_id = ?", (template_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


# ─── A/B PERSONA TESTING ────────────────────────────────────────────────────

def create_ab_test(name: str, description: str, variant_a_personas: List[str],
                    variant_b_personas: List[str], topic: str = "",
                    seed_input: str = "") -> dict:
    """Create an A/B test comparing two persona configurations."""
    test_id = f"ab_{int(time.time() * 1000) % 1000000000:09d}"

    conn = sqlite3.connect(str(_memory_db_path()))
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO ab_tests
           (test_id, name, description, variant_a_personas, variant_b_personas,
            topic, seed_input)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (test_id, name, description, json.dumps(variant_a_personas),
         json.dumps(variant_b_personas), topic, seed_input)
    )
    conn.commit()
    conn.close()

    return get_ab_test(test_id)


def get_ab_test(test_id: str) -> Optional[dict]:
    """Get an A/B test by ID."""
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM ab_tests WHERE test_id = ?", (test_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    test = dict(row)
    test["variant_a_personas"] = json.loads(test.get("variant_a_personas", "[]"))
    test["variant_b_personas"] = json.loads(test.get("variant_b_personas", "[]"))
    return test


def record_ab_result(test_id: str, variant: str, session_id: str,
                      social_score: float = 0, emotional_score: float = 0,
                      spiritual_score: float = 0, turn_count: int = 0,
                      avg_response_time: float = 0) -> dict:
    """Record results for one variant of an A/B test."""
    conn = sqlite3.connect(str(_memory_db_path()))
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO ab_test_results
           (test_id, variant, session_id, social_score, emotional_score,
            spiritual_score, turn_count, avg_response_time)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (test_id, variant, session_id, social_score, emotional_score,
         spiritual_score, turn_count, avg_response_time)
    )
    conn.commit()
    conn.close()

    return {"test_id": test_id, "variant": variant, "session_id": session_id}


def get_ab_test_summary(test_id: str) -> Optional[dict]:
    """Get summary statistics for an A/B test."""
    test = get_ab_test(test_id)
    if not test:
        return None

    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    summary = {**test, "variants": {}}

    for variant in ["A", "B"]:
        cur.execute(
            """SELECT COUNT(*) as count,
                      AVG(social_score) as avg_social,
                      AVG(emotional_score) as avg_emotional,
                      AVG(spiritual_score) as avg_spiritual,
                      AVG(turn_count) as avg_turns,
                      AVG(avg_response_time) as avg_time
               FROM ab_test_results WHERE test_id = ? AND variant = ?""",
            (test_id, variant)
        )
        row = cur.fetchone()
        summary["variants"][variant] = {
            "count": row["count"],
            "avg_social": round(row["avg_social"], 2) if row["avg_social"] else 0,
            "avg_emotional": round(row["avg_emotional"], 2) if row["avg_emotional"] else 0,
            "avg_spiritual": round(row["avg_spiritual"], 2) if row["avg_spiritual"] else 0,
            "avg_turns": round(row["avg_turns"], 1) if row["avg_turns"] else 0,
            "avg_response_time": round(row["avg_time"], 2) if row["avg_time"] else 0,
        }

    # Determine winner
    a = summary["variants"]["A"]
    b = summary["variants"]["B"]
    if a["count"] > 0 and b["count"] > 0:
        a_total = a["avg_social"] + a["avg_emotional"] + a["avg_spiritual"]
        b_total = b["avg_social"] + b["avg_emotional"] + b["avg_spiritual"]
        summary["winner"] = "A" if a_total > b_total else "B"
        summary["margin"] = round(abs(a_total - b_total), 2)
    else:
        summary["winner"] = "inconclusive"
        summary["margin"] = 0

    conn.close()
    return summary


# ─── PROVIDER COMPARISON ────────────────────────────────────────────────────

def create_provider_comparison(name: str, prompt: str) -> dict:
    """Create a new provider comparison test."""
    comparison_id = f"cmp_{int(time.time() * 1000) % 1000000000:09d}"

    conn = sqlite3.connect(str(_memory_db_path()))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO provider_comparisons (comparison_id, name, prompt) VALUES (?, ?, ?)",
        (comparison_id, name, prompt)
    )
    conn.commit()
    conn.close()

    return {"comparison_id": comparison_id, "name": name, "prompt": prompt}


def record_provider_result(comparison_id: str, provider: str, model: str,
                            response: str, response_time: float = 0,
                            token_count: int = 0,
                            social_score: float = 0,
                            emotional_score: float = 0,
                            spiritual_score: float = 0) -> dict:
    """Record a provider's result in a comparison."""
    conn = sqlite3.connect(str(_memory_db_path()))
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO provider_results
           (comparison_id, provider, model, response, response_time,
            token_count, social_score, emotional_score, spiritual_score)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (comparison_id, provider, model, response, response_time,
         token_count, social_score, emotional_score, spiritual_score)
    )
    conn.commit()
    conn.close()

    return {"comparison_id": comparison_id, "provider": provider}


def get_provider_comparison(comparison_id: str) -> Optional[dict]:
    """Get a full provider comparison with all results."""
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM provider_comparisons WHERE comparison_id = ?", (comparison_id,))
    comp = cur.fetchone()
    if not comp:
        conn.close()
        return None

    cur.execute(
        "SELECT * FROM provider_results WHERE comparison_id = ? ORDER BY provider",
        (comparison_id,)
    )
    results = [dict(row) for row in cur.fetchall()]
    conn.close()

    return {
        "comparison_id": comparison_id,
        "name": comp["name"],
        "prompt": comp["prompt"],
        "created_at": comp["created_at"],
        "results": results,
        "provider_count": len(results),
    }


# ─── REPRODUCIBILITY (SEED-BASED SESSIONS) ──────────────────────────────────

def create_reproducible_session(session_id: str, seed: str, prompt: str,
                                 personas: List[str], config: dict = None) -> dict:
    """Register a session as reproducible with a specific seed."""
    checksum = hashlib.sha256(
        f"{seed}:{prompt}:{json.dumps(personas, sort_keys=True)}".encode()
    ).hexdigest()[:16]

    conn = sqlite3.connect(str(_memory_db_path()))
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO reproducible_sessions
           (session_id, seed, prompt, personas, config, checksum)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (session_id, seed, prompt, json.dumps(personas),
         json.dumps(config or {}), checksum)
    )
    conn.commit()
    conn.close()

    return {
        "session_id": session_id,
        "seed": seed,
        "checksum": checksum,
        "personas": personas,
    }


def get_reproducible_session(seed: str) -> Optional[dict]:
    """Look up a reproducible session by seed."""
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM reproducible_sessions WHERE seed = ?", (seed,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    result = dict(row)
    result["personas"] = json.loads(result.get("personas", "[]"))
    result["config"] = json.loads(result.get("config", "{}"))
    return result


def verify_reproducibility(session_id: str, seed: str, prompt: str,
                            personas: List[str]) -> bool:
    """Verify a session matches its seed configuration."""
    stored = get_reproducible_session(seed)
    if not stored:
        return False

    expected_checksum = hashlib.sha256(
        f"{seed}:{prompt}:{json.dumps(personas, sort_keys=True)}".encode()
    ).hexdigest()[:16]

    return stored["checksum"] == expected_checksum


# ─── SES SCORING EXPORT ─────────────────────────────────────────────────────

def compute_ses_scores(session_id: str) -> dict:
    """Compute and store SES scores for a session."""
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get evaluation scores if available
    social = 0
    emotional = 0
    spiritual = 0

    try:
        cur.execute(
            "SELECT dimension, score FROM evaluation_scores WHERE session_id = ?",
            (session_id,)
        )
        for row in cur.fetchall():
            if row["dimension"] == "social_presence":
                social = row["score"]
            elif row["dimension"] == "emotional_depth":
                emotional = row["score"]
            elif row["dimension"] == "spiritual_depth":
                spiritual = row["score"]
    except Exception:
        pass

    # If no eval scores, compute from message patterns
    if social == 0 and emotional == 0 and spiritual == 0:
        try:
            cur.execute(
                "SELECT content FROM memory_messages WHERE session_id = ? ORDER BY turn_number",
                (session_id,)
            )
            messages = cur.fetchall()
            if messages:
                all_text = " ".join(m["content"] for m in messages).lower()
                # Simple heuristic scoring
                social = min(5.0, count_pattern_score(all_text, ["we", "together", "share", "listen", "understand"]) * 0.5 + 2.0)
                emotional = min(5.0, count_pattern_score(all_text, ["feel", "heart", "emotion", "passion", "connection"]) * 0.5 + 2.0)
                spiritual = min(5.0, count_pattern_score(all_text, ["meaning", "purpose", "growth", "transform", "wisdom"]) * 0.5 + 2.0)
        except Exception:
            pass

    overall = round((social + emotional + spiritual) / 3, 2)

    # Store scores
    cur.execute(
        """INSERT INTO ses_scores
           (session_id, social_score, emotional_score, spiritual_score, overall_score)
           VALUES (?, ?, ?, ?, ?)""",
        (session_id, social, emotional, spiritual, overall)
    )
    conn.commit()
    conn.close()

    return {
        "session_id": session_id,
        "social_score": round(social, 2),
        "emotional_score": round(emotional, 2),
        "spiritual_score": round(spiritual, 2),
        "overall_score": overall,
    }


def count_pattern_score(text: str, patterns: List[str]) -> int:
    """Count how many patterns appear in text."""
    return sum(1 for p in patterns if p in text)


def get_ses_scores(session_id: str = None, limit: int = 50) -> list:
    """Get SES scores, optionally filtered by session."""
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if session_id:
        cur.execute(
            "SELECT * FROM ses_scores WHERE session_id = ? ORDER BY evaluated_at DESC",
            (session_id,)
        )
    else:
        cur.execute(
            "SELECT * FROM ses_scores ORDER BY evaluated_at DESC LIMIT ?",
            (limit,)
        )

    rows = cur.fetchall()
    conn.close()

    result = []
    for row in rows:
        entry = dict(row)
        entry["breakdown"] = json.loads(entry.get("breakdown", "{}"))
        result.append(entry)
    return result


def export_ses_scores_csv() -> str:
    """Export all SES scores as CSV."""
    scores = get_ses_scores()
    if not scores:
        return ""

    lines = ["session_id,social_score,emotional_score,spiritual_score,overall_score,evaluated_at"]
    for s in scores:
        ts = datetime.fromtimestamp(s["evaluated_at"]).strftime("%Y-%m-%d %H:%M")
        lines.append(
            f"{s['session_id']},{s['social_score']},{s['emotional_score']},"
            f"{s['spiritual_score']},{s['overall_score']},{ts}"
        )

    return "\n".join(lines)
