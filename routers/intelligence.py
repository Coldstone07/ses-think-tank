"""Router: Session Intelligence, Eval Dashboard, Evolution, Deeper Intelligence."""

import sqlite3
from pathlib import Path
from fastapi import (
    APIRouter,
    Request,
    Request as FastAPIRequest,
    Depends,
    HTTPException,
)
from fastapi.responses import JSONResponse

from auth import get_current_user
from db import get_connection
from session_intelligence import (
    get_insight_summary,
    get_session_insights,
    get_related_sessions,
    smart_recall,
    extract_insights_from_session,
    save_insights,
    build_session_graph,
    _memory_db_path,
)
from evaluation_dashboard import (
    get_dashboard_summary,
    get_session_analytics,
    get_persona_trends,
    get_quality_trend,
    export_session_report,
)
from persona_evolution import (
    get_evolution_summary,
    get_persona_profile,
)
from intelligence import (
    semantic_search,
    synthesize_across_sessions,
    generate_session_embeddings,
    get_persona_knowledge,
    generate_knowledge_from_sessions,
    get_quality_overview,
    compute_quality_trend,
)

router = APIRouter()


@router.get("/api/intelligence/summary")
async def intelligence_summary():
    """Get summary stats about the intelligence system."""
    return get_insight_summary()


@router.get("/api/intelligence/insights")
async def get_insights_api(session_id: str = None, limit: int = 20):
    """Get insights, optionally filtered by session."""
    if session_id:
        return get_session_insights(session_id)
    conn = sqlite3.connect(str(_memory_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """SELECT i.*, ms.topic as session_topic
           FROM insights i JOIN memory_sessions ms ON ms.session_id = i.session_id
           ORDER BY i.relevance_score DESC, ms.started_at DESC LIMIT ?""",
        (limit,),
    )
    results = [dict(row) for row in cur.fetchall()]
    return results


@router.get("/api/intelligence/related/{session_id}")
async def get_related_sessions_api(session_id: str, limit: int = 5):
    """Get sessions related to the given session."""
    return get_related_sessions(session_id, limit)


@router.get("/api/intelligence/recall")
async def smart_recall_api(topic: str, limit: int = 5):
    """Get relevant past insights for a topic."""
    return smart_recall(topic, limit=limit)


@router.post("/api/intelligence/extract")
async def extract_insights_api(request: FastAPIRequest):
    """Extract insights from a session transcript."""
    body = await request.json()
    session_id = body.get("session_id", "")
    messages = body.get("messages", [])
    insights = extract_insights_from_session(session_id, messages)
    if insights:
        save_insights(session_id, insights)
    return {"extracted": len(insights), "insights": insights}


@router.post("/api/intelligence/graph")
async def rebuild_graph_api():
    """Force rebuild the session graph."""
    connections = build_session_graph(top_n=50)
    return {"connections": len(connections), "graph": connections}


@router.get("/api/eval/dashboard")
async def eval_dashboard_api():
    """Get evaluation dashboard summary."""
    return get_dashboard_summary()


@router.get("/api/eval/session/{session_id}")
async def eval_session_api(session_id: str):
    """Get analytics for a specific session."""
    return get_session_analytics(session_id)


@router.get("/api/eval/persona/{persona_id}")
async def eval_persona_api(persona_id: str, limit: int = 20):
    """Get persona performance trends."""
    return get_persona_trends(persona_id, limit)


@router.get("/api/eval/trend")
async def eval_trend_api(limit: int = 30):
    """Get quality trend over recent sessions."""
    return get_quality_trend(limit)


@router.get("/api/eval/export/{session_id}")
async def eval_export_api(session_id: str):
    """Export comprehensive session report."""
    return export_session_report(session_id)


@router.get("/api/evolution/summary")
async def evolution_summary_api():
    """Get evolution overview stats."""
    return get_evolution_summary()


@router.get("/api/evolution/persona/{persona_id}")
async def evolution_persona_api(persona_id: str):
    """Get complete evolution profile for a persona."""
    return get_persona_profile(persona_id)


@router.get("/api/intelligence/search")
async def search_sessions_api(q: str, limit: int = 10, min_score: float = 0.1):
    """Semantic search across all sessions."""
    results = semantic_search(q, limit=limit, min_score=min_score)
    return results


@router.post("/api/intelligence/synthesize")
async def synthesize_api(request: Request):
    """Synthesize insights across sessions on related topics."""
    body = await request.json()
    topics = body.get("topics", [])
    max_sessions = body.get("max_sessions", 10)
    result = synthesize_across_sessions(topics, max_sessions)
    return result


@router.post("/api/intelligence/embed/{session_id}")
async def embed_session_api(
    session_id: str, current_user: dict = Depends(get_current_user)
):
    """Generate embeddings for a session."""
    generate_session_embeddings(session_id)
    return {"status": "ok", "session_id": session_id}


@router.get("/api/intelligence/knowledge/{persona_id}")
async def persona_knowledge_api(persona_id: str, domain: str = None):
    """Get auto-generated knowledge for a persona."""
    knowledge = get_persona_knowledge(persona_id, domain)
    return {"persona_id": persona_id, "knowledge": knowledge}


@router.post("/api/intelligence/knowledge/{persona_id}/generate")
async def generate_knowledge_api(
    persona_id: str,
    domain: str = "general",
    current_user: dict = Depends(get_current_user),
):
    """Generate knowledge for a persona from session history."""
    entries = generate_knowledge_from_sessions(persona_id, domain)
    return {
        "persona_id": persona_id,
        "domain": domain,
        "entries_generated": len(entries),
    }


@router.get("/api/intelligence/quality/overview")
async def quality_overview_api(weeks: int = 12):
    """Get quality trends overview."""
    trends = get_quality_overview(weeks)
    return {"weeks": weeks, "trends": trends}


@router.post("/api/intelligence/quality/{session_id}")
async def compute_quality_api(
    session_id: str, current_user: dict = Depends(get_current_user)
):
    """Compute and store quality metrics for a session."""
    metrics = compute_quality_trend(session_id)
    return metrics
