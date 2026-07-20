"""
Deeper Intelligence — Phase 5.3

Embedding generation, semantic search, cross-session synthesis,
auto-generated knowledge books, and longitudinal quality tracking.
"""
import os
import sqlite3
import time
import json
import math
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple

MEMORY_DB_PATH = Path(os.environ.get("SES_MEMORY_DB", "data/memory.db"))


def _memory_db_path() -> Path:
    return Path(os.environ.get("SES_MEMORY_DB", "data/memory.db"))


def init_intelligence_schema():
    """Create intelligence tables for embeddings and synthesis."""
    conn = sqlite3.connect(str(_memory_db_path()))
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS session_embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            content TEXT NOT NULL,
            embedding TEXT NOT NULL,
            chunk_type TEXT DEFAULT 'summary',
            created_at REAL DEFAULT (julianday('now')),
            FOREIGN KEY (session_id) REFERENCES memory_sessions(session_id)
        );

        CREATE TABLE IF NOT EXISTS semantic_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            term TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            FOREIGN KEY (session_id) REFERENCES memory_sessions(session_id)
        );

        CREATE TABLE IF NOT EXISTS cross_session_synthesis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            session_ids TEXT NOT NULL,
            synthesis TEXT NOT NULL,
            confidence REAL DEFAULT 0.0,
            created_at REAL DEFAULT (julianday('now'))
        );

        CREATE TABLE IF NOT EXISTS auto_knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            persona_id TEXT NOT NULL,
            domain TEXT NOT NULL,
            knowledge TEXT NOT NULL,
            source_sessions TEXT NOT NULL,
            confidence REAL DEFAULT 0.0,
            created_at REAL DEFAULT (julianday('now')),
            updated_at REAL DEFAULT (julianday('now'))
        );

        CREATE TABLE IF NOT EXISTS quality_trends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            week TEXT NOT NULL,
            social_score REAL DEFAULT 0,
            emotional_score REAL DEFAULT 0,
            spiritual_score REAL DEFAULT 0,
            avg_turn_length REAL DEFAULT 0,
            unique_topics REAL DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES memory_sessions(session_id)
        );

        CREATE INDEX IF NOT EXISTS idx_embeddings_session ON session_embeddings(session_id);
        CREATE INDEX IF NOT EXISTS idx_semantic_term ON semantic_index(term);
        CREATE INDEX IF NOT EXISTS idx_semantic_session ON semantic_index(session_id);
        CREATE INDEX IF NOT EXISTS idx_synthesis_topic ON cross_session_synthesis(topic);
        CREATE INDEX IF NOT EXISTS idx_auto_knowledge_persona ON auto_knowledge(persona_id);
        CREATE INDEX IF NOT EXISTS idx_auto_knowledge_domain ON auto_knowledge(domain);
        CREATE INDEX IF NOT EXISTS idx_quality_week ON quality_trends(week);
    """)
    conn.commit()
    conn.close()


# ─── EMBEDDING GENERATION (TF-IDF style, no external deps) ──────────────────

def tokenize(text: str) -> List[str]:
    """Simple tokenizer: lowercase, split on non-alphanumeric."""
    import re
    return [t.lower() for t in re.findall(r'[a-z0-9]+', text.lower()) if len(t) > 2]


def compute_tfidf_vector(text: str, vocabulary: List[str]) -> Dict[str, float]:
    """Compute TF-IDF vector for a text against a vocabulary."""
    tokens = tokenize(text)
    if not tokens or not vocabulary:
        return {}

    # Term frequency
    tf = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    tf_len = len(tokens) or 1
    for t in tf:
        tf[t] = tf[t] / tf_len

    # IDF (simplified - log of total docs / docs containing term)
    # For now use uniform IDF = 1.0 (can be improved with corpus stats)
    vector = {}
    for term in vocabulary:
        if term in tf:
            vector[term] = tf[term] * 1.0  # IDF = 1.0 baseline
    return vector


def cosine_similarity(vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
    """Compute cosine similarity between two sparse vectors."""
    if not vec1 or not vec2:
        return 0.0

    # Find common terms
    common = set(vec1.keys()) & set(vec2.keys())
    if not common:
        return 0.0

    # Dot product
    dot = sum(vec1[t] * vec2[t] for t in common)

    # Magnitudes
    mag1 = math.sqrt(sum(v ** 2 for v in vec1.values()))
    mag2 = math.sqrt(sum(v ** 2 for v in vec2.values()))

    if mag1 == 0 or mag2 == 0:
        return 0.0

    return dot / (mag1 * mag2)


def generate_session_embedding(session_id: str, content: str, chunk_type: str = "summary"):
    """Generate and store an embedding for a session chunk."""
    conn = sqlite3.connect(str(_memory_db_path()))
    cur = conn.cursor()

    # Get vocabulary from all existing content
    cur.execute("SELECT DISTINCT term FROM semantic_index")
    vocabulary = [row[0] for row in cur.fetchall()]

    # Tokenize and build vocabulary
    tokens = tokenize(content)
    new_terms = set(tokens) - set(vocabulary)
    vocabulary.extend(new_terms)

    # Compute vector
    vector = compute_tfidf_vector(content, vocabulary)
    vector_json = json.dumps(vector)

    # Store embedding
    cur.execute(
        """INSERT INTO session_embeddings (session_id, content, embedding, chunk_type)
           VALUES (?, ?, ?, ?)""",
        (session_id, content[:500], vector_json, chunk_type)
    )

    # Update semantic index
    for term in set(tokens):
        cur.execute(
            """INSERT INTO semantic_index (session_id, term, weight)
               VALUES (?, ?, ?)
               ON CONFLICT DO NOTHING""",
            (session_id, term, 1.0)
        )

    conn.commit()
    conn.close()


def generate_session_embeddings(session_id: str):
    """Generate embeddings for a session's summary and key messages."""
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get session topic
    cur.execute("SELECT topic FROM memory_sessions WHERE session_id = ?", (session_id,))
    session = cur.fetchone()
    if not session:
        conn.close()
        return

    # Embed topic
    generate_session_embedding(session_id, session["topic"], "topic")

    # Get messages
    cur.execute(
        "SELECT content FROM memory_messages WHERE session_id = ? ORDER BY turn_number LIMIT 20",
        (session_id,)
    )
    messages = cur.fetchall()
    conn.close()

    # Embed first few messages as summaries
    for i, msg in enumerate(messages[:5]):
        generate_session_embedding(session_id, msg["content"], f"message_{i}")

    # Embed combined summary
    combined = " ".join(m["content"] for m in messages[:10])
    generate_session_embedding(session_id, combined, "summary")


# ─── SEMANTIC SEARCH ────────────────────────────────────────────────────────

def semantic_search(query: str, limit: int = 10, min_score: float = 0.1) -> List[Dict]:
    """Search sessions semantically using TF-IDF vectors."""
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get vocabulary
    cur.execute("SELECT DISTINCT term FROM semantic_index")
    vocabulary = [row[0] for row in cur.fetchall()]

    # Compute query vector
    query_vector = compute_tfidf_vector(query, vocabulary)
    if not query_vector:
        conn.close()
        return []

    # Get all sessions with their content
    cur.execute("SELECT DISTINCT session_id FROM session_embeddings")
    sessions = cur.fetchall()

    results = []
    for s in sessions:
        session_id = s["session_id"]

        # Get session embedding
        cur.execute(
            "SELECT embedding FROM session_embeddings WHERE session_id = ? AND chunk_type = 'summary'",
            (session_id,)
        )
        emb_row = cur.fetchone()
        if not emb_row:
            continue

        session_vector = json.loads(emb_row["embedding"])
        score = cosine_similarity(query_vector, session_vector)

        if score >= min_score:
            # Get session info
            cur.execute("SELECT topic, turn_count, started_at FROM memory_sessions WHERE session_id = ?", (session_id,))
            session_info = cur.fetchone()
            if session_info:
                results.append({
                    "session_id": session_id,
                    "topic": session_info["topic"],
                    "turn_count": session_info["turn_count"],
                    "started_at": session_info["started_at"],
                    "score": round(score, 4),
                })

    conn.close()

    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


# ─── CROSS-SESSION SYNTHESIS ────────────────────────────────────────────────

def synthesize_across_sessions(topics: List[str], max_sessions: int = 10) -> Dict:
    """Synthesize insights across multiple sessions on related topics."""
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Find sessions matching any topic
    session_ids = []
    for topic in topics:
        cur.execute(
            "SELECT session_id FROM session_embeddings WHERE content LIKE ? LIMIT ?",
            (f"%{topic}%", max_sessions)
        )
        for row in cur.fetchall():
            if row["session_id"] not in session_ids:
                session_ids.append(row["session_id"])

    if not session_ids:
        conn.close()
        return {"topic": " | ".join(topics), "sessions_found": 0, "synthesis": "No related sessions found."}

    # Get insights from these sessions
    insights = []
    for sid in session_ids[:max_sessions]:
        try:
            cur.execute(
                "SELECT content FROM session_insights WHERE session_id = ?",
                (sid,)
            )
            for row in cur.fetchall():
                insights.append(row["content"])
        except Exception:
            pass

    # Get key messages
    key_messages = []
    for sid in session_ids[:max_sessions]:
        try:
            cur.execute(
                "SELECT content FROM memory_messages WHERE session_id = ? ORDER BY turn_number DESC LIMIT 3",
                (sid,)
            )
            for row in cur.fetchall():
                key_messages.append(row["content"])
        except Exception:
            pass

    conn.close()

    # Generate synthesis (simple aggregation for now)
    synthesis_parts = []
    synthesis_parts.append(f"Across {len(session_ids)} sessions on '{' | '.join(topics)}':")
    synthesis_parts.append("")

    if insights:
        synthesis_parts.append("## Key Insights")
        for i, insight in enumerate(insights[:10], 1):
            synthesis_parts.append(f"{i}. {insight[:200]}")
        synthesis_parts.append("")

    if key_messages:
        synthesis_parts.append("## Notable Discussion Points")
        for i, msg in enumerate(key_messages[:5], 1):
            synthesis_parts.append(f"{i}. {msg[:200]}")
        synthesis_parts.append("")

    synthesis = "\n".join(synthesis_parts)

    # Store synthesis
    conn = sqlite3.connect(str(_memory_db_path()))
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO cross_session_synthesis (topic, session_ids, synthesis, confidence)
           VALUES (?, ?, ?, ?)""",
        (" | ".join(topics), json.dumps(session_ids), synthesis, 0.7)
    )
    conn.commit()
    conn.close()

    return {
        "topic": " | ".join(topics),
        "sessions_found": len(session_ids),
        "session_ids": session_ids,
        "insights_count": len(insights),
        "synthesis": synthesis,
    }


# ─── AUTO-GENERATED KNOWLEDGE BOOKS ─────────────────────────────────────────

def generate_knowledge_from_sessions(persona_id: str, domain: str = "general") -> List[Dict]:
    """Generate knowledge entries for a persona from their session history."""
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get sessions with this persona
    cur.execute(
        "SELECT session_id, topic FROM memory_sessions WHERE persona_ids LIKE ? ORDER BY started_at DESC LIMIT 20",
        (f"%{persona_id}%",)
    )
    sessions = cur.fetchall()

    knowledge_entries = []
    for session in sessions:
        # Get messages from this persona
        cur.execute(
            "SELECT content FROM memory_messages WHERE session_id = ? AND persona_id = ? ORDER BY turn_number",
            (session["session_id"], persona_id)
        )
        messages = cur.fetchall()

        if not messages:
            continue

        # Extract key knowledge points (first and last messages tend to be most informative)
        for msg in [messages[0], messages[-1]]:
            content = msg["content"][:300]
            knowledge_entries.append({
                "persona_id": persona_id,
                "domain": domain,
                "knowledge": content,
                "source_session": session["session_id"],
                "topic": session["topic"],
            })

    conn.close()

    # Store in auto_knowledge table
    conn = sqlite3.connect(str(_memory_db_path()))
    cur = conn.cursor()
    for entry in knowledge_entries:
        cur.execute(
            """INSERT INTO auto_knowledge (persona_id, domain, knowledge, source_sessions, confidence)
               VALUES (?, ?, ?, ?, ?)""",
            (entry["persona_id"], entry["domain"], entry["knowledge"],
             json.dumps([entry["source_session"]]), 0.6)
        )
    conn.commit()
    conn.close()

    return knowledge_entries


def get_persona_knowledge(persona_id: str, domain: str = None) -> List[Dict]:
    """Get all auto-generated knowledge for a persona."""
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if domain:
        cur.execute(
            "SELECT * FROM auto_knowledge WHERE persona_id = ? AND domain = ? ORDER BY updated_at DESC",
            (persona_id, domain)
        )
    else:
        cur.execute(
            "SELECT * FROM auto_knowledge WHERE persona_id = ? ORDER BY updated_at DESC",
            (persona_id,)
        )

    rows = cur.fetchall()
    conn.close()

    result = []
    for row in rows:
        entry = dict(row)
        entry["source_sessions"] = json.loads(entry.get("source_sessions", "[]"))
        result.append(entry)
    return result


# ─── LONGITUDINAL QUALITY TRACKING ──────────────────────────────────────────

def compute_quality_trend(session_id: str) -> Dict:
    """Compute quality metrics for a session and track over time."""
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get session info
    cur.execute("SELECT * FROM memory_sessions WHERE session_id = ?", (session_id,))
    session = cur.fetchone()
    if not session:
        conn.close()
        return {}

    # Get messages
    cur.execute(
        "SELECT content FROM memory_messages WHERE session_id = ?",
        (session_id,)
    )
    messages = cur.fetchall()

    # Compute metrics
    total_words = sum(len(m["content"].split()) for m in messages)
    avg_turn_length = total_words / len(messages) if messages else 0

    # Get evaluation scores if available
    social_score = 0
    emotional_score = 0
    spiritual_score = 0
    try:
        cur.execute(
            "SELECT dimension, score FROM evaluation_scores WHERE session_id = ?",
            (session_id,)
        )
        for row in cur.fetchall():
            if row["dimension"] == "social_presence":
                social_score = row["score"]
            elif row["dimension"] == "emotional_depth":
                emotional_score = row["score"]
            elif row["dimension"] == "spiritual_depth":
                spiritual_score = row["score"]
    except Exception:
        pass

    conn.close()

    # Compute week identifier
    week = datetime.fromtimestamp(session["started_at"]).strftime("%Y-W%W")

    # Store trend data
    conn = sqlite3.connect(str(_memory_db_path()))
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO quality_trends (session_id, week, social_score, emotional_score, spiritual_score, avg_turn_length)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (session_id, week, social_score, emotional_score, spiritual_score, avg_turn_length)
    )
    conn.commit()
    conn.close()

    return {
        "session_id": session_id,
        "week": week,
        "social_score": social_score,
        "emotional_score": emotional_score,
        "spiritual_score": spiritual_score,
        "avg_turn_length": round(avg_turn_length, 1),
    }


def get_quality_overview(weeks: int = 12) -> List[Dict]:
    """Get quality trends overview for the last N weeks."""
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """SELECT week,
                  AVG(social_score) as avg_social,
                  AVG(emotional_score) as avg_emotional,
                  AVG(spiritual_score) as avg_spiritual,
                  AVG(avg_turn_length) as avg_turn_len,
                  COUNT(*) as session_count
           FROM quality_trends
           GROUP BY week
           ORDER BY week DESC
           LIMIT ?""",
        (weeks,)
    )

    rows = cur.fetchall()
    conn.close()

    result = []
    for row in rows:
        result.append({
            "week": row["week"],
            "avg_social": round(row["avg_social"], 2) if row["avg_social"] else 0,
            "avg_emotional": round(row["avg_emotional"], 2) if row["avg_emotional"] else 0,
            "avg_spiritual": round(row["avg_spiritual"], 2) if row["avg_spiritual"] else 0,
            "avg_turn_length": round(row["avg_turn_len"], 1) if row["avg_turn_len"] else 0,
            "session_count": row["session_count"],
        })

    return result
