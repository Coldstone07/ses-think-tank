"""
Export & Distribution — Phase 5.2

Session export to markdown, PDF reports, RSS feed, and public session viewer.
"""
import os
import sqlite3
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from db import get_connection

MEMORY_DB_PATH = Path(os.environ.get("SES_MEMORY_DB", "data/memory.db"))
SHARES_DB_PATH = Path(os.environ.get("SES_AUTH_DB", "data/auth.db"))


def _memory_db_path() -> Path:
    """Get memory DB path from current env (re-reads on each call)."""
    return Path(os.environ.get("SES_MEMORY_DB", "data/memory.db"))


def _shares_db_path() -> Path:
    """Get auth DB path from current env (re-reads on each call)."""
    return Path(os.environ.get("SES_AUTH_DB", "data/auth.db"))


# ─── MARKDOWN EXPORT ─────────────────────────────────────────────────────────

def export_session_markdown(session_id: str) -> Optional[str]:
    """Export a session as formatted markdown."""
    conn = get_connection(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get session info
    cur.execute("SELECT * FROM memory_sessions WHERE session_id = ?", (session_id,))
    session = cur.fetchone()
    if not session:
        return None
    session = dict(session)

    # Get messages
    cur.execute(
        "SELECT * FROM memory_messages WHERE session_id = ? ORDER BY turn_number",
        (session_id,)
    )
    messages = cur.fetchall()
    messages = [dict(row) for row in messages]

    # Get evaluation scores if available
    try:
        cur.execute(
            "SELECT * FROM evaluation_scores WHERE session_id = ? ORDER BY dimension",
            (session_id,)
        )
        scores = [dict(row) for row in cur.fetchall()]
    except Exception:
        scores = []

    # Get insights if available
    try:
        cur.execute(
            "SELECT * FROM session_insights WHERE session_id = ? ORDER BY category",
            (session_id,)
        )
        insights = [dict(row) for row in cur.fetchall()]
    except Exception:
        insights = []


    # Build markdown
    md = []
    md.append(f"# {session['topic']}")
    md.append("")
    md.append(f"**Session:** {session_id}")
    md.append(f"**Started:** {datetime.fromtimestamp(session['started_at']).strftime('%Y-%m-%d %H:%M')}")
    if session.get('ended_at') and session['ended_at']:
        md.append(f"**Ended:** {datetime.fromtimestamp(session['ended_at']).strftime('%Y-%m-%d %H:%M')}")
    md.append(f"**Turns:** {session['turn_count']}")
    md.append(f"**Personas:** {session['persona_ids']}")
    md.append("")
    md.append("---")
    md.append("")

    # Messages
    md.append("## Discussion")
    md.append("")
    for msg in messages:
        persona = msg.get('persona_id', 'system')
        role = msg.get('role', 'assistant')
        content = msg.get('content', '')
        turn = msg.get('turn_number', 0)
        if role == 'user':
            md.append(f"### Turn {turn}: User")
            md.append(f"> {content}")
            md.append("")
        else:
            md.append(f"### Turn {turn}: {persona}")
            md.append(f"{content}")
            md.append("")

    # Evaluation scores
    if scores:
        md.append("---")
        md.append("")
        md.append("## Evaluation Scores")
        md.append("")
        md.append("| Dimension | Score | Notes |")
        md.append("|-----------|-------|-------|")
        for s in scores:
            md.append(f"| {s.get('dimension', 'N/A')} | {s.get('score', 'N/A')} | {s.get('notes', '')} |")
        md.append("")

    # Insights
    if insights:
        md.append("---")
        md.append("")
        md.append("## Key Insights")
        md.append("")
        for i, insight in enumerate(insights, 1):
            md.append(f"{i}. **{insight.get('category', 'general')}**: {insight.get('content', '')}")
        md.append("")

    return "\n".join(md)


def export_all_sessions_markdown(user_id: str = "default") -> List[dict]:
    """Get summary of all sessions for a user."""
    conn = get_connection(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM memory_sessions ORDER BY started_at DESC"
    )
    sessions = cur.fetchall()

    return [
        {
            "session_id": s["session_id"],
            "topic": s["topic"],
            "turn_count": s["turn_count"],
            "started_at": datetime.fromtimestamp(s["started_at"]).strftime("%Y-%m-%d %H:%M"),
            "persona_ids": s["persona_ids"],
        }
        for s in sessions
    ]


# ─── PUBLIC SESSION VIEWER ──────────────────────────────────────────────────

def get_public_session(share_id: str) -> Optional[dict]:
    """Get a shared session for public viewing."""
    # Check shares DB
    conn = get_connection(str(_shares_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM session_shares WHERE share_id = ?", (share_id,))
    share = cur.fetchone()

    if not share:
        return None

    # Get session from memory DB
    conn = get_connection(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM memory_sessions WHERE session_id = ?", (share["session_id"],))
    session = cur.fetchone()
    if not session:
        return None

    cur.execute(
        "SELECT * FROM memory_messages WHERE session_id = ? ORDER BY turn_number",
        (share["session_id"],)
    )
    messages = [dict(row) for row in cur.fetchall()]

    return {
        "share_id": share_id,
        "session_id": session["session_id"],
        "topic": session["topic"],
        "persona_ids": session["persona_ids"],
        "started_at": session["started_at"],
        "ended_at": session["ended_at"],
        "turn_count": session["turn_count"],
        "messages": messages,
        "shared_by": share["owner_id"],
    }


# ─── RSS FEED ────────────────────────────────────────────────────────────────

def generate_rss_feed(base_url: str = "http://localhost:8773", limit: int = 20) -> str:
    """Generate RSS 2.0 feed of recent sessions."""
    conn = get_connection(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM memory_sessions ORDER BY started_at DESC LIMIT ?",
        (limit,)
    )
    sessions = cur.fetchall()

    rss = []
    rss.append('<?xml version="1.0" encoding="UTF-8"?>')
    rss.append('<rss version="2.0">')
    rss.append('  <channel>')
    rss.append('    <title>SES Think Tank Sessions</title>')
    rss.append(f'    <link>{base_url}</link>')
    rss.append('    <description>Recent Think Tank discussion sessions</description>')
    rss.append(f'    <lastBuildDate>{datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")}</lastBuildDate>')

    for s in sessions:
        started = datetime.fromtimestamp(s["started_at"]).strftime("%a, %d %b %Y %H:%M:%S GMT")
        topic = s["topic"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        share_url = f"{base_url}/share/{s['session_id']}"
        rss.append(f'    <item>')
        rss.append(f'      <title>{topic}</title>')
        rss.append(f'      <link>{share_url}</link>')
        rss.append(f'      <guid>{s["session_id"]}</guid>')
        rss.append(f'      <pubDate>{started}</pubDate>')
        rss.append(f'      <description>{topic} ({s["turn_count"]} turns)</description>')
        rss.append(f'    </item>')

    rss.append('  </channel>')
    rss.append('</rss>')

    return "\n".join(rss)


# ─── PUBLISH SESSION ────────────────────────────────────────────────────────

def publish_session(session_id: str, owner_id: str) -> Optional[str]:
    """Publish a session and return share link."""
    from auth import create_session_share
    share_id = create_session_share(session_id, owner_id, is_public=True)
    return share_id


def unpublish_session(share_id: str, owner_id: str):
    """Unpublish a session by revoking its share."""
    from auth import revoke_session_share
    revoke_session_share(share_id, owner_id)
