"""
Persona Evolution — Phase 4.6

Personas learn from feedback, adapt style, and grow expertise over time.
Builds on evaluation dashboard + session intelligence + knowledge system.
"""
import sqlite3
import os
import time
import json
import math
from pathlib import Path
from typing import Optional
from collections import Counter, defaultdict

MEMORY_DB_PATH = Path(os.environ.get("SES_MEMORY_DB", "data/memory.db"))


def init_evolution_schema():
    """Add evolution tables to the existing memory DB."""
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS persona_evolution (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            persona_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            adaptation_type TEXT NOT NULL,
            before_value TEXT DEFAULT '',
            after_value TEXT DEFAULT '',
            reason TEXT DEFAULT '',
            score_change REAL DEFAULT 0.0,
            created_at REAL DEFAULT (julianday('now')),
            FOREIGN KEY (session_id) REFERENCES memory_sessions(session_id)
        );

        CREATE TABLE IF NOT EXISTS persona_expertise (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            persona_id TEXT NOT NULL,
            domain TEXT NOT NULL,
            level REAL DEFAULT 0.0,
            sessions_in_domain INTEGER DEFAULT 0,
            key_topics TEXT DEFAULT '',
            last_updated REAL DEFAULT 0,
            UNIQUE(persona_id, domain)
        );

        CREATE TABLE IF NOT EXISTS persona_style_drift (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            persona_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            avg_sentence_length REAL DEFAULT 0.0,
            vocab_diversity REAL DEFAULT 0.0,
            emotional_tone REAL DEFAULT 0.0,
            formality_score REAL DEFAULT 0.0,
            created_at REAL DEFAULT (julianday('now')),
            FOREIGN KEY (session_id) REFERENCES memory_sessions(session_id)
        );

        CREATE INDEX IF NOT EXISTS idx_persona_evolution_persona ON persona_evolution(persona_id);
        CREATE INDEX IF NOT EXISTS idx_persona_expertise_persona ON persona_expertise(persona_id);
        CREATE INDEX IF NOT EXISTS idx_persona_style_drift_persona ON persona_style_drift(persona_id);
    """)
    conn.commit()
    conn.close()


def compute_style_metrics(text: str) -> dict:
    """
    Compute style metrics for a text sample.
    Returns: avg_sentence_length, vocab_diversity, emotional_tone, formality_score
    """
    if not text or not text.strip():
        return {
            "avg_sentence_length": 0,
            "vocab_diversity": 0,
            "emotional_tone": 0.5,
            "formality_score": 0.5,
        }

    # Sentence splitting
    sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
    avg_sentence_length = (
        sum(len(s.split()) for s in sentences) / len(sentences) if sentences else 0
    )

    # Vocabulary diversity (type-token ratio)
    words = text.lower().split()
    unique_words = set(w.strip(".,!?;:\"'()[]{}-") for w in words if len(w) > 2)
    vocab_diversity = len(unique_words) / len(words) if words else 0

    # Emotional tone (simple keyword-based)
    emotional_positive = ["love", "feel", "beautiful", "wonderful", "inspiring", "hope",
                          "joy", "warmth", "grateful", "passionate", "empathy", "compassion"]
    emotional_negative = ["hate", "angry", "terrible", "awful", "disappointing", "fear",
                          "pain", "sorrow", "frustrated", "hostile", "cold", "indifferent"]
    lower = text.lower()
    pos_count = sum(1 for w in emotional_positive if w in lower)
    neg_count = sum(1 for w in emotional_negative if w in lower)
    total = pos_count + neg_count
    emotional_tone = pos_count / total if total > 0 else 0.5

    # Formality score (formal vs informal indicators)
    formal_words = ["furthermore", "however", "therefore", "consequently", "moreover",
                    "nevertheless", "subsequently", "additionally", "notwithstanding",
                    "predominantly", "fundamentally", "comprehensive", "methodology"]
    informal_words = ["gonna", "wanna", " kinda", " sorta", "stuff", "thing",
                      "like", "cool", "awesome", "yeah", "nah", "lol"]
    form_pos = sum(1 for w in formal_words if w in lower)
    form_neg = sum(1 for w in informal_words if w in lower)
    form_total = form_pos + form_neg
    formality_score = form_pos / form_total if form_total > 0 else 0.5

    return {
        "avg_sentence_length": round(avg_sentence_length, 2),
        "vocab_diversity": round(vocab_diversity, 3),
        "emotional_tone": round(emotional_tone, 3),
        "formality_score": round(formality_score, 3),
    }


def extract_domains(text: str) -> list:
    """Extract topic domains from text using keyword mapping."""
    domain_keywords = {
        "technology": ["code", "software", "algorithm", "AI", "machine learning", "neural",
                       "API", "database", "system", "framework", "programming"],
        "philosophy": ["ethics", "morality", "existence", "consciousness", "meaning",
                       "virtue", "epistemology", "ontology", "metaphysics"],
        "psychology": ["behavior", "cognition", "emotion", "therapy", "mental health",
                       "personality", "motivation", "perception", "subconscious"],
        "science": ["experiment", "hypothesis", "data", "research", "physics", "biology",
                    "chemistry", "empirical", "observation", "theory"],
        "art": ["creative", "expression", "aesthetic", "design", "music", "literature",
                "visual", "composition", "imagery", "narrative"],
        "business": ["strategy", "market", "revenue", "growth", "leadership", "innovation",
                     "startup", "product", "customer", "competitive"],
        "education": ["learning", "teaching", "curriculum", "pedagogy", "knowledge",
                      "skill", "development", "training", "academic"],
        "social": ["community", "society", "culture", "relationship", "communication",
                   "diversity", "equity", "inclusion", "social justice"],
    }

    lower = text.lower()
    domains = []
    for domain, keywords in domain_keywords.items():
        matches = sum(1 for kw in keywords if kw in lower)
        if matches >= 2:
            domains.append({"domain": domain, "relevance": matches / len(keywords)})

    domains.sort(key=lambda x: -x["relevance"])
    return domains[:3]  # Top 3 domains


def record_style_snapshot(persona_id: str, session_id: str, text: str):
    """Record a persona's style metrics for a session."""
    metrics = compute_style_metrics(text)
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO persona_style_drift
           (persona_id, session_id, avg_sentence_length, vocab_diversity,
            emotional_tone, formality_score)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (persona_id, session_id, metrics["avg_sentence_length"],
         metrics["vocab_diversity"], metrics["emotional_tone"],
         metrics["formality_score"])
    )
    conn.commit()
    conn.close()
    return metrics


def update_persona_expertise(persona_id: str, session_id: str, text: str, topics: str = ""):
    """Update a persona's expertise based on session content."""
    domains = extract_domains(text + " " + topics)
    if not domains:
        return []

    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    cur = conn.cursor()

    updated = []
    for d in domains:
        domain = d["domain"]
        # Get current level
        cur.execute(
            "SELECT level, sessions_in_domain FROM persona_expertise WHERE persona_id = ? AND domain = ?",
            (persona_id, domain)
        )
        row = cur.fetchone()
        if row:
            new_level = min(1.0, row[0] + 0.05 * d["relevance"])
            new_sessions = row[1] + 1
            cur.execute(
                """UPDATE persona_expertise SET level = ?, sessions_in_domain = ?,
                   last_updated = ? WHERE persona_id = ? AND domain = ?""",
                (new_level, new_sessions, time.time(), persona_id, domain)
            )
        else:
            new_level = 0.1 * d["relevance"]
            cur.execute(
                """INSERT INTO persona_expertise
                   (persona_id, domain, level, sessions_in_domain, last_updated)
                   VALUES (?, ?, ?, 1, ?)""",
                (persona_id, domain, new_level, time.time())
            )
        updated.append({"domain": domain, "level": round(new_level, 3)})

    conn.commit()
    conn.close()
    return updated


def record_adaptation(persona_id: str, session_id: str, adaptation_type: str,
                      before: str, after: str, reason: str, score_change: float = 0):
    """Record that a persona adapted in some way."""
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO persona_evolution
           (persona_id, session_id, adaptation_type, before_value, after_value, reason, score_change)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (persona_id, session_id, adaptation_type, before, after, reason, score_change)
    )
    conn.commit()
    conn.close()


def get_persona_profile(persona_id: str) -> dict:
    """Get complete evolution profile for a persona."""
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Expertise areas
    cur.execute(
        "SELECT * FROM persona_expertise WHERE persona_id = ? ORDER BY level DESC",
        (persona_id,)
    )
    expertise = [dict(row) for row in cur.fetchall()]

    # Style drift over time
    cur.execute(
        """SELECT ps.*, ms.topic
           FROM persona_style_drift ps
           LEFT JOIN memory_sessions ms ON ms.session_id = ps.session_id
           WHERE ps.persona_id = ?
           ORDER BY ps.created_at DESC
           LIMIT 20""",
        (persona_id,)
    )
    style_history = [dict(row) for row in cur.fetchall()]

    # Adaptations
    cur.execute(
        """SELECT pe.*, ms.topic
           FROM persona_evolution pe
           LEFT JOIN memory_sessions ms ON ms.session_id = pe.session_id
           WHERE pe.persona_id = ?
           ORDER BY pe.created_at DESC
           LIMIT 20""",
        (persona_id,)
    )
    adaptations = [dict(row) for row in cur.fetchall()]

    # Current style (average of recent)
    if style_history:
        current_style = {
            "avg_sentence_length": round(sum(s["avg_sentence_length"] for s in style_history) / len(style_history), 2),
            "vocab_diversity": round(sum(s["vocab_diversity"] for s in style_history) / len(style_history), 3),
            "emotional_tone": round(sum(s["emotional_tone"] for s in style_history) / len(style_history), 3),
            "formality_score": round(sum(s["formality_score"] for s in style_history) / len(style_history), 3),
        }
    else:
        current_style = {}

    # Style drift (change from first to latest)
    style_drift = {}
    if len(style_history) >= 2:
        first = style_history[-1]  # Oldest
        latest = style_history[0]  # Newest
        style_drift = {
            "sentence_length_change": round(latest["avg_sentence_length"] - first["avg_sentence_length"], 2),
            "vocab_diversity_change": round(latest["vocab_diversity"] - first["vocab_diversity"], 3),
            "emotional_tone_change": round(latest["emotional_tone"] - first["emotional_tone"], 3),
            "formality_change": round(latest["formality_score"] - first["formality_score"], 3),
        }

    conn.close()

    return {
        "persona_id": persona_id,
        "expertise": expertise,
        "current_style": current_style,
        "style_drift": style_drift,
        "style_history": style_history,
        "adaptations": adaptations,
        "total_sessions": len(style_history),
        "total_adaptations": len(adaptations),
        "expertise_areas": len(expertise),
    }


def generate_adaptation_prompt(persona_id: str, recent_scores: dict) -> str:
    """
    Generate a prompt that instructs a persona to adapt based on recent feedback.
    Returns empty string if no adaptation needed.
    """
    if not recent_scores:
        return ""

    # Find weakest and strongest dimensions
    dims = {k: v for k, v in recent_scores.items() if isinstance(v, (int, float))}
    if not dims:
        return ""

    weakest = min(dims, key=dims.get)
    strongest = max(dims, key=dims.get)

    adaptation_areas = []

    if dims.get("emotional_presence", 0.5) < 0.4:
        adaptation_areas.append(
            "Your emotional presence has been rated low. "
            "Try to be more empathetic, acknowledge feelings, and show genuine warmth in responses."
        )
    if dims.get("depth", 0.5) < 0.4:
        adaptation_areas.append(
            "Your responses have been rated as lacking depth. "
            "Explore topics more thoroughly, consider multiple perspectives, and unpack complexity."
        )
    if dims.get("synergy", 0.5) < 0.4:
        adaptation_areas.append(
            "Your synergy with others has been low. "
            "Build on others' points more actively, reference previous speakers, and find connections."
        )
    if dims.get("originality", 0.5) < 0.4:
        adaptation_areas.append(
            "Your originality has been rated low. "
            "Offer fresh perspectives, challenge assumptions, and bring novel angles to discussions."
        )
    if dims.get("clarity", 0.5) < 0.4:
        adaptation_areas.append(
            "Your clarity has been rated low. "
            "Structure your thoughts more clearly, use precise language, and avoid ambiguity."
        )

    if not adaptation_areas:
        return ""

    # Strengths to maintain
    strengths = []
    if dims.get("emotional_presence", 0) > 0.7:
        strengths.append("emotional presence")
    if dims.get("depth", 0) > 0.7:
        strengths.append("analytical depth")
    if dims.get("synergy", 0) > 0.7:
        strengths.append("collaborative synergy")
    if dims.get("originality", 0) > 0.7:
        strengths.append("original thinking")
    if dims.get("clarity", 0) > 0.7:
        strengths.append("clarity of expression")

    prompt_parts = ["\n--- PERSONA ADAPTATION INSTRUCTIONS ---"]
    prompt_parts.append(f"Based on recent feedback, focus on improving:")
    for area in adaptation_areas:
        prompt_parts.append(f"  • {area}")

    if strengths:
        prompt_parts.append(f"Continue leveraging your strengths in: {', '.join(strengths)}")

    prompt_parts.append("--- END ADAPTATION INSTRUCTIONS ---\n")
    return "\n".join(prompt_parts)


def get_evolution_summary() -> dict:
    """Get overview stats about persona evolution."""
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT COUNT(DISTINCT persona_id) as total FROM persona_expertise")
    personas_with_expertise = cur.fetchone()["total"]

    cur.execute("SELECT COUNT(*) as total FROM persona_expertise")
    total_expertise_areas = cur.fetchone()["total"]

    cur.execute("SELECT COUNT(DISTINCT persona_id) as total FROM persona_style_drift")
    personas_with_style = cur.fetchone()["total"]

    cur.execute("SELECT COUNT(*) as total FROM persona_evolution")
    total_adaptations = cur.fetchone()["total"]

    # Top expertise areas
    cur.execute(
        """SELECT domain, COUNT(*) as personas, AVG(level) as avg_level
           FROM persona_expertise GROUP BY domain ORDER BY avg_level DESC LIMIT 5"""
    )
    top_domains = [dict(row) for row in cur.fetchall()]

    conn.close()

    return {
        "personas_with_expertise": personas_with_expertise,
        "total_expertise_areas": total_expertise_areas,
        "personas_with_style_tracking": personas_with_style,
        "total_adaptations": total_adaptations,
        "top_domains": top_domains,
    }


def process_session_evolution(session_id: str, messages: list, scores: dict = None):
    """
    Process a completed session to update persona evolution.
    Records style snapshots, updates expertise, and generates adaptations.
    """
    # Group messages by persona
    persona_texts = defaultdict(list)
    for msg in messages:
        if isinstance(msg, dict):
            persona_texts[msg.get("persona_id", "unknown")].append(msg.get("content", ""))

    topic = ""
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "system":
            topic = msg.get("content", "")[:200]
            break

    results = {}
    for pid, texts in persona_texts.items():
        if pid == "system" or pid == "unknown":
            continue

        combined = " ".join(texts)

        # Record style
        style = record_style_snapshot(pid, session_id, combined)

        # Update expertise
        expertise = update_persona_expertise(pid, session_id, combined, topic)

        # Generate and record adaptation if scores available
        adaptation = ""
        if scores and pid in scores:
            adaptation = generate_adaptation_prompt(pid, scores[pid])
            if adaptation:
                # Find what changed
                weak_dims = [k for k, v in scores[pid].items()
                           if isinstance(v, (int, float)) and v < 0.4]
                if weak_dims:
                    record_adaptation(
                        pid, session_id, "feedback_driven",
                        json.dumps({d: scores[pid].get(d, 0) for d in weak_dims}),
                        "",
                        f"Low scores in: {', '.join(weak_dims)}",
                        sum(scores[pid].get(d, 0) for d in weak_dims) / len(weak_dims) if weak_dims else 0
                    )

        results[pid] = {
            "style": style,
            "expertise": expertise,
            "adaptation": adaptation,
        }

    return results
