"""Router: Session CRUD, Whiteboard, Interventions, Metrics, State, Websocket, Memory."""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse

from app import (
    init_memory_db, load_sessions_from_disk,
    get_session_memory, search_memory_by_topic, search_memory_by_persona,
    get_cross_session_insights, recommend_team_from_memory,
)

router = APIRouter()


@router.get("/api/memory/sessions")
async def memory_search(topic: str = "", persona: str = ""):
    """Search memory for past sessions by topic or persona."""
    if topic:
        return search_memory_by_topic(topic)
    if persona:
        return search_memory_by_persona(persona)
    return []


@router.get("/api/memory/session/{session_id}")
async def memory_get_session(session_id: str):
    """Get full session memory record."""
    result = get_session_memory(session_id)
    if not result:
        return {"error": "Session not found in memory"}
    return result


@router.get("/api/memory/insights/{topic:path}")
async def memory_insights(topic: str):
    """Get cross-session insights for a topic."""
    return get_cross_session_insights(topic)


@router.get("/api/memory/recommended-team/{topic:path}")
async def memory_recommended_team(topic: str):
    """Recommend team based on past performance for a topic."""
    return recommend_team_from_memory(topic)


def find_free_port(start_port: int = 8773, max_attempts: int = 10) -> int:
    """Find a free port, auto-hopping to avoid Windows TIME_WAIT conflicts."""
    import socket

    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise RuntimeError(
        f"No free port found in range {start_port}-{start_port + max_attempts}"
    )


if __name__ == "__main__":
    import uvicorn

    init_memory_db()
    load_sessions_from_disk()
    port = find_free_port(8773)
    log.info("Starting SES Think Tank on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port, reload=True, reload_dirs=["plugins"])

