"""
Session Intelligence — Phase 4.4

Builds on the existing memory system to add:
1. Insight extraction from session transcripts
2. Session graph linking related sessions by topic/insight overlap
3. Smart recall: inject relevant past insights into new conversations
"""
import sqlite3
import os
import time
import json
import math
from pathlib import Path
from typing import Optional
from collections import Counter

MEMORY_DB_PATH = Path(os.environ.get("SES_MEMORY_DB", "data/memory.db"))

# Keyword stop words for insight extraction
STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "can",
    "will", "just", "don", "should", "now", "would", "that", "this",
    "these", "those", "it", "its", "he", "she", "they", "them", "their",
    "we", "you", "what", "which", "who", "whom", "and", "but", "or",
    "because", "if", "while", "about", "up", "do", "does", "did",
    "have", "has", "had", "having", "also", "may", "much", "any",
    "could", "get", "like", "new", "one", "see", "way", "well",
}


def init_intelligence_schema():
    """Add intelligence tables to the existing memory DB."""
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            insight TEXT NOT NULL,
            keywords TEXT DEFAULT '',
            category TEXT DEFAULT 'general',
            relevance_score REAL DEFAULT 1.0,
            created_at REAL DEFAULT (julianday('now')),
            FOREIGN KEY (session_id) REFERENCES memory_sessions(session_id)
        );

        CREATE TABLE IF NOT EXISTS session_graph (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_a TEXT NOT NULL,
            session_b TEXT NOT NULL,
            similarity REAL DEFAULT 0.0,
            shared_keywords TEXT DEFAULT '',
            created_at REAL DEFAULT (julianday('now')),
            UNIQUE(session_a, session_b),
            FOREIGN KEY (session_a) REFERENCES memory_sessions(session_id),
            FOREIGN KEY (session_b) REFERENCES memory_sessions(session_id)
        );

        CREATE INDEX IF NOT EXISTS idx_insights_session ON insights(session_id);
        CREATE INDEX IF NOT EXISTS idx_insights_keywords ON insights(keywords);
        CREATE INDEX IF NOT EXISTS idx_insights_category ON insights(category);
        CREATE INDEX IF NOT EXISTS idx_session_graph_a ON session_graph(session_a);
        CREATE INDEX IF NOT EXISTS idx_session_graph_b ON session_graph(session_b);
    """)
    conn.commit()
    conn.close()


def tokenize(text: str) -> list:
    """Simple tokenizer: lowercase, strip punctuation, remove stop words."""
    words = text.lower().replace("_", " ").split()
    cleaned = []
    for w in words:
        w = w.strip(".,!?;:\"'()[]{}-")
        if w and len(w) > 2 and w not in STOP_WORDS:
            cleaned.append(w)
    return cleaned


def keyword_overlap_score(text_a: str, text_b: str) -> float:
    """Jaccard similarity between two texts based on keyword sets."""
    tokens_a = set(tokenize(text_a))
    tokens_b = set(tokenize(text_b))
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union > 0 else 0.0


def tfidf_keywords(text: str, top_n: int = 10) -> list:
    """Extract top keywords using simple TF-IDF heuristic."""
    tokens = tokenize(text)
    if not tokens:
        return []
    tf = Counter(tokens)
    total = len(tokens)
    # Simple TF-IDF: term frequency * log(1 + 1/document_frequency)
    # Since we don't have a corpus here, use term frequency weighted by length
    scored = {}
    for word, count in tf.items():
        tf_score = count / total
        # Penalize very common words by their length
        idf_boost = math.log(1 + len(word))
        scored[word] = tf_score * idf_boost * count
    return [w for w, _ in sorted(scored.items(), key=lambda x: -x[1])[:top_n]]


def extract_insights_from_session(session_id: str, messages: list) -> list:
    """
    Extract key insights from a conversation transcript.
    Uses pattern matching for insight-like statements.
    Returns list of {insight, keywords, category}.
    """
    insights = []
    insight_patterns = [
        ("key_finding", ["key insight", "important finding", "crucial point", "main takeaway"]),
        ("framework", ["framework", "model", "approach", "methodology", "pattern"]),
        ("recommendation", ["recommend", "suggest", "should", "would be to", "best approach"]),
        ("contrast", ["however", "but", "on the other hand", "conversely", "in contrast"]),
        ("principle", ["principle", "rule", "law", "truth", "fundamental"]),
        ("example", ["for example", "for instance", "such as", "like when"]),
    ]

    full_text = " ".join(m.get("content", "") for m in messages if isinstance(m, dict))
    sentences = full_text.replace("\n", " ").split(". ")

    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 50 or len(sentence) > 500:
            continue

        lower = sentence.lower()
        for category, patterns in insight_patterns:
            if any(p in lower for p in patterns):
                keywords = tfidf_keywords(sentence, top_n=8)
                insights.append({
                    "insight": sentence[:500],
                    "keywords": ",".join(keywords),
                    "category": category,
                    "relevance_score": len(keywords) / 8.0,
                })
                break  # Only categorize once per sentence

    # Deduplicate similar insights
    seen = set()
    unique = []
    for ins in insights:
        key = ins["insight"][:50].lower()
        if key not in seen:
            seen.add(key)
            unique.append(ins)

    return unique[:20]  # Cap at 20 insights per session


def save_insights(session_id: str, insights: list):
    """Save extracted insights to the database."""
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    cur = conn.cursor()
    for ins in insights:
        cur.execute(
            "INSERT INTO insights (session_id, insight, keywords, category, relevance_score) VALUES (?, ?, ?, ?, ?)",
            (session_id, ins["insight"], ins["keywords"], ins["category"], ins["relevance_score"])
        )
    conn.commit()
    conn.close()


def build_session_graph(top_n: int = 50):
    """
    Build/update the session graph by computing pairwise similarity
    between recent sessions. Links sessions with similarity > 0.15.
    """
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    cur = conn.cursor()

    # Get recent sessions
    cur.execute(
        "SELECT session_id, topic, summary FROM memory_sessions ORDER BY started_at DESC LIMIT ?",
        (top_n,)
    )
    sessions = cur.fetchall()
    conn.close()

    if len(sessions) < 2:
        return []

    # Compute pairwise similarities
    connections = []
    for i in range(len(sessions)):
        for j in range(i + 1, len(sessions)):
            sid_a, topic_a, summary_a = sessions[i]
            sid_b, topic_b, summary_b = sessions[j]

            # Combine topic + summary for comparison
            text_a = f"{topic_a} {summary_a}"
            text_b = f"{topic_b} {summary_b}"

            similarity = keyword_overlap_score(text_a, text_b)

            if similarity > 0.15:
                shared = tfidf_keywords(text_a, 5) + tfidf_keywords(text_b, 5)
                shared = list(set(shared))[:8]
                connections.append({
                    "session_a": sid_a,
                    "session_b": sid_b,
                    "similarity": round(similarity, 3),
                    "shared_keywords": ",".join(shared),
                })

    # Upsert into DB
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    cur = conn.cursor()
    for c in connections:
        cur.execute(
            """INSERT OR REPLACE INTO session_graph (session_a, session_b, similarity, shared_keywords)
               VALUES (?, ?, ?, ?)""",
            (c["session_a"], c["session_b"], c["similarity"], c["shared_keywords"])
        )
    conn.commit()
    conn.close()

    return connections


def get_related_sessions(session_id: str, limit: int = 5) -> list:
    """Get sessions most related to the given session."""
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """SELECT ms.session_id, ms.topic, ms.started_at, ms.persona_ids,
                  sg.similarity, sg.shared_keywords
           FROM session_graph sg
           JOIN memory_sessions ms ON (ms.session_id = sg.session_b OR ms.session_id = sg.session_a)
           WHERE (sg.session_a = ? AND ms.session_id = sg.session_b)
              OR (sg.session_b = ? AND ms.session_id = sg.session_a)
           ORDER BY sg.similarity DESC
           LIMIT ?""",
        (session_id, session_id, limit)
    )

    results = [dict(row) for row in cur.fetchall()]
    conn.close()
    return results


def smart_recall(topic: str, persona_ids: list = None, limit: int = 5) -> list:
    """
    Find relevant past insights for a new conversation topic.
    Returns insights ranked by relevance to the current topic.
    """
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get all insights and score them against the topic
    cur.execute(
        """SELECT i.insight, i.keywords, i.category, i.relevance_score,
                  ms.topic as session_topic, ms.session_id, ms.started_at
           FROM insights i
           JOIN memory_sessions ms ON ms.session_id = i.session_id
           ORDER BY ms.started_at DESC
           LIMIT 200"""
    )

    all_insights = [dict(row) for row in cur.fetchall()]
    conn.close()

    # Score each insight against the current topic
    scored = []
    for ins in all_insights:
        combined = f"{ins['insight']} {ins['session_topic']} {ins['keywords']}"
        sim = keyword_overlap_score(topic, combined)
        if sim > 0.05:
            # Filter by persona if specified
            if persona_ids:
                # Simple heuristic: insights from sessions with overlapping keywords are more relevant
                pass  # Persona filtering would need session persona data
            scored.append({
                **ins,
                "topic_similarity": round(sim, 3),
            })

    # Sort by combined score
    scored.sort(key=lambda x: -(x["topic_similarity"] * x["relevance_score"]))
    return scored[:limit]


def get_session_insights(session_id: str) -> list:
    """Get all insights for a specific session."""
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM insights WHERE session_id = ? ORDER BY relevance_score DESC",
        (session_id,)
    )
    results = [dict(row) for row in cur.fetchall()]
    conn.close()
    return results


def get_insight_summary() -> dict:
    """Get summary stats about the intelligence system."""
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) as total FROM insights")
    total_insights = cur.fetchone()["total"]

    cur.execute("SELECT category, COUNT(*) as count FROM insights GROUP BY category")
    by_category = {row["category"]: row["count"] for row in cur.fetchall()}

    cur.execute("SELECT COUNT(*) as total FROM session_graph")
    total_connections = cur.fetchone()["total"]

    cur.execute("SELECT COUNT(DISTINCT session_id) as total FROM insights")
    sessions_with_insights = cur.fetchone()["total"]

    conn.close()

    return {
        "total_insights": total_insights,
        "by_category": by_category,
        "total_connections": total_connections,
        "sessions_with_insights": sessions_with_insights,
    }


def build_recall_prompt(topic: str, persona_ids: list = None) -> str:
    """
    Build a prompt injection block with relevant past insights
    for use in system prompts.
    """
    insights = smart_recall(topic, persona_ids, limit=5)
    if not insights:
        return ""

    lines = ["\n--- RELEVANT PAST INSIGHTS ---"]
    for i, ins in enumerate(insights, 1):
        lines.append(
            f"[{i}] From: '{ins['session_topic']}' ({ins.get('category', 'general')})\n"
            f"    {ins['insight'][:200]}"
        )
    lines.append("--- END PAST INSIGHTS ---\n")
    return "\n".join(lines)
