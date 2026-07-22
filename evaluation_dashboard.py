"""
Evaluation Dashboard — Phase 4.5

Real-time quality metrics, persona scoring, session analytics.
Tracks: emotional presence, depth, synergy, turn distribution, insight density.
"""
import sqlite3
import os
import time
import math
import json
from pathlib import Path
from typing import Optional
from collections import Counter, defaultdict
from db import get_connection, reset_pool

MEMORY_DB_PATH = Path(os.environ.get("SES_MEMORY_DB", "data/memory.db"))

# Quality dimensions and their keyword indicators
QUALITY_INDICATORS = {
    "emotional_presence": {
        "positive": ["empathy", "feeling", "emotion", "vulnerable", "heartfelt", "compassion",
                      "understanding", "connect", "resonate", "warmth", "gentle", "authentic"],
        "negative": ["robotic", "generic", "superficial", "formulaic", "scripted"],
    },
    "depth": {
        "positive": ["nuanced", "complexity", "paradox", "tension", "layer", "dimension",
                      "interconnected", "systemic", "fundamental", "underlying", "explore",
                      "unpack", "examine", "investigate", "framework", "model"],
        "negative": ["shallow", "surface", "obvious", "basic", "simple answer"],
    },
    "synergy": {
        "positive": ["building on", "extends", "complement", "together", "combine",
                      "synthesis", "integrate", "merge", "connect", "bridge", "collaboration",
                      "weave", "blend", "harmonize", "complement"],
        "negative": ["contradict", "ignore", "disagree without", "missed point"],
    },
    "originality": {
        "positive": ["novel", "unique", "unconventional", "fresh perspective", "new angle",
                      "innovative", "creative", "unexpected", "unexplored", "original",
                      "breakthrough", "paradigm shift", "rethink"],
        "negative": ["cliché", "typical", "standard", "predictable", "well-worn"],
    },
    "clarity": {
        "positive": ["clear", "precise", "articulate", "well-structured", "organized",
                      "coherent", "logical", "straightforward", "transparent", "accessible"],
        "negative": ["confusing", "vague", "unclear", "contradictory", "muddled"],
    },
}


def init_evaluation_schema():
    """Add evaluation tables to the existing memory DB."""
    conn = get_connection(str(MEMORY_DB_PATH))
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS session_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            metric_category TEXT DEFAULT 'quality',
            created_at REAL DEFAULT (julianday('now')),
            FOREIGN KEY (session_id) REFERENCES memory_sessions(session_id)
        );

        CREATE TABLE IF NOT EXISTS persona_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            persona_id TEXT NOT NULL,
            dimension TEXT NOT NULL,
            score REAL NOT NULL,
            evidence TEXT DEFAULT '',
            created_at REAL DEFAULT (julianday('now')),
            FOREIGN KEY (session_id) REFERENCES memory_sessions(session_id)
        );

        CREATE TABLE IF NOT EXISTS turn_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            turn_number INTEGER NOT NULL,
            persona_id TEXT NOT NULL,
            word_count INTEGER DEFAULT 0,
            sentiment_score REAL DEFAULT 0.0,
            novelty_score REAL DEFAULT 0.0,
            created_at REAL DEFAULT (julianday('now')),
            FOREIGN KEY (session_id) REFERENCES memory_sessions(session_id)
        );

        CREATE INDEX IF NOT EXISTS idx_session_metrics_session ON session_metrics(session_id);
        CREATE INDEX IF NOT EXISTS idx_session_metrics_name ON session_metrics(metric_name);
        CREATE INDEX IF NOT EXISTS idx_persona_scores_persona ON persona_scores(persona_id);
        CREATE INDEX IF NOT EXISTS idx_persona_scores_dimension ON persona_scores(dimension);
        CREATE INDEX IF NOT EXISTS idx_turn_analytics_session ON turn_analytics(session_id);
    """)
    conn.commit()


def score_dimension(text: str, dimension: str) -> dict:
    """
    Score a text segment on a specific quality dimension.
    Returns {score: 0-1, evidence: list_of_matched_keywords, raw_counts}.
    """
    if dimension not in QUALITY_INDICATORS:
        return {"score": 0.5, "evidence": [], "raw_counts": {"positive": 0, "negative": 0}}

    indicators = QUALITY_INDICATORS[dimension]
    lower = text.lower()

    positive_matches = [w for w in indicators["positive"] if w in lower]
    negative_matches = [w for w in indicators["negative"] if w in lower]

    pos_count = len(positive_matches)
    neg_count = len(negative_matches)
    total = pos_count + neg_count

    if total == 0:
        return {"score": 0.5, "evidence": [], "raw_counts": {"positive": 0, "negative": 0}}

    # Score: ratio of positive to total, with penalty for negatives
    score = pos_count / (total + neg_count * 2)
    score = max(0.0, min(1.0, score))

    return {
        "score": round(score, 3),
        "evidence": positive_matches + [f"-{w}" for w in negative_matches],
        "raw_counts": {"positive": pos_count, "negative": neg_count},
    }


def analyze_session(session_id: str, messages: list) -> dict:
    """
    Analyze a session and compute quality metrics.
    Returns comprehensive metrics dict.
    """
    if not messages:
        return {"session_id": session_id, "error": "No messages"}

    # Combine all messages by persona
    persona_texts = defaultdict(list)
    full_text = ""
    word_counts = Counter()

    for i, msg in enumerate(messages):
        if isinstance(msg, dict):
            content = msg.get("content", "")
            persona = msg.get("persona_id", "unknown")
            persona_texts[persona].append(content)
            full_text += content + " "
            word_counts[persona] += len(content.split())

    full_text = full_text.strip()
    total_words = len(full_text.split())

    # Score each dimension on the full conversation
    dimension_scores = {}
    for dim in QUALITY_INDICATORS:
        result = score_dimension(full_text, dim)
        dimension_scores[dim] = result

    # Turn distribution analysis
    turn_counts = Counter()
    for msg in messages:
        if isinstance(msg, dict):
            turn_counts[msg.get("persona_id", "unknown")] += 1

    total_turns = sum(turn_counts.values())
    turn_distribution = {
        pid: {"turns": count, "percentage": round(count / total_turns * 100, 1) if total_turns else 0}
        for pid, count in turn_counts.items()
    }

    # Gini coefficient for turn equality (0 = perfect equality, 1 = total inequality)
    gini = compute_gini(list(turn_counts.values())) if turn_counts else 0

    # Insight density (insights per 1000 words)
    insights = get_insights_for_session(session_id)
    insight_density = (len(insights) / total_words * 1000) if total_words else 0

    # Persona-level scores
    persona_scores = {}
    for pid, texts in persona_texts.items():
        combined = " ".join(texts)
        scores = {}
        for dim in QUALITY_INDICATORS:
            result = score_dimension(combined, dim)
            scores[dim] = result["score"]
        persona_scores[pid] = {
            "scores": scores,
            "avg_score": round(sum(scores.values()) / len(scores), 3) if scores else 0,
            "word_count": word_counts[pid],
            "turn_count": turn_counts[pid],
        }

    return {
        "session_id": session_id,
        "total_words": total_words,
        "total_turns": total_turns,
        "dimension_scores": {dim: result["score"] for dim, result in dimension_scores.items()},
        "dimension_evidence": {dim: result["evidence"] for dim, result in dimension_scores.items()},
        "turn_distribution": turn_distribution,
        "turn_equality": round(1 - gini, 3),  # Higher = more equal
        "insight_density": round(insight_density, 2),
        "insight_count": len(insights),
        "persona_scores": persona_scores,
        "overall_quality": round(sum(dimension_scores[d]["score"] for d in dimension_scores) / len(dimension_scores), 3) if dimension_scores else 0,
    }


def compute_gini(values: list) -> float:
    """Compute Gini coefficient for inequality measurement."""
    if not values or sum(values) == 0:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    cumulative = sum((i + 1) * v for i, v in enumerate(sorted_vals))
    return (2 * cumulative) / (n * sum(sorted_vals)) - (n + 1) / n


def save_session_metrics(session_id: str, metrics: dict):
    """Save computed metrics to the database."""
    conn = get_connection(str(MEMORY_DB_PATH))
    cur = conn.cursor()

    # Save dimension scores
    for dim, score in metrics.get("dimension_scores", {}).items():
        cur.execute(
            "INSERT INTO session_metrics (session_id, metric_name, metric_value, metric_category) VALUES (?, ?, ?, ?)",
            (session_id, dim, score, "quality")
        )

    # Save aggregate metrics
    for metric_name in ["overall_quality", "turn_equality", "insight_density", "insight_count"]:
        if metric_name in metrics:
            cur.execute(
                "INSERT INTO session_metrics (session_id, metric_name, metric_value, metric_category) VALUES (?, ?, ?, ?)",
                (session_id, metric_name, metrics[metric_name], "aggregate")
            )

    # Save persona scores
    for pid, pdata in metrics.get("persona_scores", {}).items():
        for dim, score in pdata.get("scores", {}).items():
            cur.execute(
                "INSERT INTO persona_scores (session_id, persona_id, dimension, score) VALUES (?, ?, ?, ?)",
                (session_id, pid, dim, score)
            )

    conn.commit()


def get_insights_for_session(session_id: str) -> list:
    """Get insights for a session from the intelligence system."""
    try:
        from session_intelligence import get_session_insights
        return get_session_insights(session_id)
    except Exception:
        return []


def get_persona_trends(persona_id: str, limit: int = 20) -> dict:
    """Get a persona's performance trends across sessions."""
    conn = get_connection(str(MEMORY_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get dimension scores over time
    cur.execute(
        """SELECT ps.dimension, ps.score, ms.topic, ms.started_at
           FROM persona_scores ps
           JOIN memory_sessions ms ON ms.session_id = ps.session_id
           WHERE ps.persona_id = ?
           ORDER BY ms.started_at DESC
           LIMIT ?""",
        (persona_id, limit)
    )
    rows = [dict(row) for row in cur.fetchall()]

    # Aggregate by dimension
    dimension_avg = defaultdict(list)
    for row in rows:
        dimension_avg[row["dimension"]].append(row["score"])

    return {
        "persona_id": persona_id,
        "sessions_analyzed": len(rows),
        "dimension_averages": {
            dim: round(sum(scores) / len(scores), 3)
            for dim, scores in dimension_avg.items() if scores
        },
        "recent_scores": rows,
    }


def get_session_analytics(session_id: str) -> dict:
    """Get full analytics for a specific session."""
    conn = get_connection(str(MEMORY_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Session metrics
    cur.execute(
        "SELECT * FROM session_metrics WHERE session_id = ?",
        (session_id,)
    )
    metrics = [dict(row) for row in cur.fetchall()]

    # Persona scores
    cur.execute(
        "SELECT * FROM persona_scores WHERE session_id = ?",
        (session_id,)
    )
    scores = [dict(row) for row in cur.fetchall()]


    return {
        "session_id": session_id,
        "metrics": metrics,
        "persona_scores": scores,
    }


def get_dashboard_summary() -> dict:
    """Get overview stats for the evaluation dashboard."""
    conn = get_connection(str(MEMORY_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Total sessions with metrics
    cur.execute("SELECT COUNT(DISTINCT session_id) as total FROM session_metrics")
    total_sessions = cur.fetchone()["total"]

    # Average quality across sessions
    cur.execute(
        "SELECT AVG(metric_value) as avg_quality FROM session_metrics WHERE metric_name = 'overall_quality'"
    )
    row = cur.fetchone()
    avg_quality = round(row["avg_quality"], 3) if row["avg_quality"] else 0

    # Top personas by average score
    cur.execute(
        """SELECT persona_id, AVG(score) as avg_score, COUNT(*) as assessments
           FROM persona_scores GROUP BY persona_id ORDER BY avg_score DESC LIMIT 5"""
    )
    top_personas = [dict(row) for row in cur.fetchall()]

    # Dimension averages
    cur.execute(
        """SELECT metric_name, AVG(metric_value) as avg_val, COUNT(*) as sessions
           FROM session_metrics
           WHERE metric_name IN ('emotional_presence', 'depth', 'synergy', 'originality', 'clarity')
           GROUP BY metric_name"""
    )
    dimension_avgs = {row["metric_name"]: round(row["avg_val"], 3) for row in cur.fetchall()}

    # Recent sessions with quality scores
    cur.execute(
        """SELECT ms.session_id, ms.topic, sm.metric_value as quality
           FROM memory_sessions ms
           JOIN session_metrics sm ON sm.session_id = ms.session_id
           WHERE sm.metric_name = 'overall_quality'
           ORDER BY ms.started_at DESC LIMIT 10"""
    )
    recent = [dict(row) for row in cur.fetchall()]


    return {
        "total_sessions_analyzed": total_sessions,
        "average_quality": avg_quality,
        "top_personas": top_personas,
        "dimension_averages": dimension_avgs,
        "recent_sessions": recent,
    }


def export_session_report(session_id: str) -> dict:
    """Export a comprehensive report for a session (JSON-serializable)."""
    analytics = get_session_analytics(session_id)

    # Get session info
    conn = get_connection(str(MEMORY_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM memory_sessions WHERE session_id = ?", (session_id,))
    session_row = cur.fetchone()
    session_info = dict(session_row) if session_row else {}

    return {
        "session": session_info,
        "analytics": analytics,
        "exported_at": time.time(),
    }


def get_quality_trend(limit: int = 30) -> list:
    """Get quality trend over recent sessions for charting."""
    conn = get_connection(str(MEMORY_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """SELECT ms.session_id, ms.topic, ms.started_at,
                  sm.metric_value as quality,
                  sm2.metric_value as insight_density
           FROM memory_sessions ms
           LEFT JOIN session_metrics sm ON sm.session_id = ms.session_id AND sm.metric_name = 'overall_quality'
           LEFT JOIN session_metrics sm2 ON sm2.session_id = ms.session_id AND sm2.metric_name = 'insight_density'
           ORDER BY ms.started_at DESC
           LIMIT ?""",
        (limit,)
    )

    rows = [dict(row) for row in cur.fetchall()]

    # Reverse to chronological order
    return list(reversed(rows))
