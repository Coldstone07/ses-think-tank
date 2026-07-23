"""Router: Authentication, Export, Session Sharing."""
from fastapi import APIRouter, Request, Request as FastAPIRequest, Depends, HTTPException
from fastapi.responses import JSONResponse

from auth import (
    get_current_user, register_user, create_access_token, create_refresh_token,
    authenticate_user, verify_refresh_token, get_user_by_id, get_quota_status,
    get_user_shares, create_session_share, revoke_session_share, get_shared_session,
)
from export import (
    export_session_markdown, publish_session, unpublish_session,
    generate_rss_feed, export_all_sessions_markdown, MEMORY_DB_PATH,
)
from db import get_connection
import sqlite3
import os

router = APIRouter()


@router.post("/api/auth/register")
async def auth_register(request: FastAPIRequest):
    """Register a new user."""
    body = await request.json()
    user = register_user(
        body["username"],
        body["password"],
        body.get("email", ""),
        body.get("display_name", "")
    )
    access_token = create_access_token(user["user_id"], user["role"])
    refresh_token = create_refresh_token(user["user_id"])
    return {
        "user": user,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/api/auth/login")
async def auth_login(request: FastAPIRequest):
    """Login and get tokens."""
    body = await request.json()
    result = authenticate_user(body["username"], body["password"])
    return result


@router.post("/api/auth/refresh")
async def auth_refresh(request: FastAPIRequest):
    """Refresh access token using refresh token."""
    body = await request.json()
    payload = verify_refresh_token(body["refresh_token"])
    user = get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    access_token = create_access_token(user["user_id"], user["role"])
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/api/auth/me")
async def auth_me(current_user: dict = Depends(get_current_user)):
    """Get current user info + quota status."""
    return {
        "user": {
            "user_id": current_user["user_id"],
            "username": current_user["username"],
            "display_name": current_user["display_name"],
            "email": current_user["email"],
            "role": current_user["role"],
            "created_at": current_user["created_at"],
            "last_login": current_user["last_login"],
        },
        "quota": get_quota_status(current_user["user_id"]),
    }


@router.get("/api/auth/shares")
async def auth_shares(current_user: dict = Depends(get_current_user)):
    """Get all session shares for current user."""
    return get_user_shares(current_user["user_id"])


@router.post("/api/sessions/{session_id}/share")
async def share_session_api(session_id: str, current_user: dict = Depends(get_current_user)):
    """Create a shareable link for a session."""
    share_id = create_session_share(session_id, current_user["user_id"])
    return {"share_id": share_id, "share_url": f"/share/{share_id}"}


@router.delete("/api/shares/{share_id}")
async def revoke_share_api(share_id: str, current_user: dict = Depends(get_current_user)):
    """Revoke a session share."""
    revoke_session_share(share_id, current_user["user_id"])
    return {"status": "ok"}


@router.get("/api/share/{share_id}")
async def view_shared_session_api(share_id: str):
    """View a shared session (public read-only)."""
    share = get_shared_session(share_id)
    if not share:
        raise HTTPException(status_code=404, detail="Share not found")
    # Load session from memory DB
    conn = get_connection(str(MEMORY_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM memory_sessions WHERE session_id = ?", (share["session_id"],))
    session = cur.fetchone()
    if session:
        cur.execute("SELECT * FROM memory_messages WHERE session_id = ? ORDER BY turn_number", (share["session_id"],))
        messages = [dict(row) for row in cur.fetchall()]
        return {
            "session_id": session["session_id"],
            "topic": session["topic"],
            "persona_ids": session["persona_ids"],
            "started_at": session["started_at"],
            "ended_at": session["ended_at"],
            "turn_count": session["turn_count"],
            "messages": messages,
            "shared_by": share["owner_id"],
        }
    raise HTTPException(status_code=404, detail="Session not found")


@router.get("/api/sessions/{session_id}/export/markdown")
async def export_session_md(session_id: str, current_user: dict = Depends(get_current_user)):
    """Export a session as markdown."""
    md = export_session_markdown(session_id)
    if not md:
        raise HTTPException(status_code=404, detail="Session not found")
    from fastapi.responses import Response
    return Response(content=md, media_type="text/markdown", headers={
        "Content-Disposition": f'attachment; filename="{session_id}.md"'
    })


@router.get("/api/sessions/{session_id}/export/json")
async def export_session_json(session_id: str, current_user: dict = Depends(get_current_user)):
    """Export a session as JSON (full data including insights/evals)."""
    conn = get_connection(str(MEMORY_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM memory_sessions WHERE session_id = ?", (session_id,))
    session = cur.fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    cur.execute(
        "SELECT * FROM memory_messages WHERE session_id = ? ORDER BY turn_number",
        (session_id,)
    )
    messages = [dict(row) for row in cur.fetchall()]
    return {
        "session_id": session["session_id"],
        "topic": session["topic"],
        "persona_ids": session["persona_ids"],
        "started_at": session["started_at"],
        "ended_at": session["ended_at"],
        "turn_count": session["turn_count"],
        "messages": messages,
    }


@router.get("/api/sessions/export/list")
async def export_sessions_list(current_user: dict = Depends(get_current_user)):
    """List all sessions for export."""
    return export_all_sessions_markdown(current_user["user_id"])


@router.get("/api/rss")
async def rss_feed_api():
    """RSS feed of recent sessions (public)."""
    from fastapi.responses import Response
    base_url = os.environ.get("SES_BASE_URL", "http://localhost:8773")
    rss = generate_rss_feed(base_url)
    return Response(content=rss, media_type="application/rss+xml")


@router.post("/api/sessions/{session_id}/publish")
async def publish_session_api(session_id: str, current_user: dict = Depends(get_current_user)):
    """Publish a session with a shareable link."""
    share_id = publish_session(session_id, current_user["user_id"])
    return {"share_id": share_id, "share_url": f"/share/{share_id}"}


@router.delete("/api/sessions/{session_id}/unpublish")
async def unpublish_session_api(session_id: str, current_user: dict = Depends(get_current_user)):
    """Unpublish a session."""
    # Find and revoke the share
    shares = get_user_shares(current_user["user_id"])
    for s in shares:
        if s["session_id"] == session_id:
            unpublish_session(s["share_id"], current_user["user_id"])
            return {"status": "ok", "unpublished": s["share_id"]}
    raise HTTPException(status_code=404, detail="No active share found for this session")

