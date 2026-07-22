"""Router: Collaboration (fork, comparison, annotations)."""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse

from auth import get_current_user
from collaboration import (
    fork_session, create_comparison, create_annotation,
    get_annotations, update_annotation, delete_annotation,
)

router = APIRouter()


@router.post("/api/sessions/{session_id}/fork")
async def fork_session_api(session_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    fork = fork_session(
        original_session_id=session_id,
        forked_by=current_user.get("username", ""),
        fork_point=body.get("fork_point", 0),
    )
    if not fork:
        raise HTTPException(status_code=404, detail="Session not found")
    return fork


@router.get("/api/sessions/{session_id}/forks")
async def get_forks_api(session_id: str):
    return get_forks(session_id)


@router.get("/api/sessions/{session_id}/fork-history")
async def get_fork_history_api(session_id: str):
    history = get_fork_history(session_id)
    if not history:
        raise HTTPException(status_code=404, detail="Not a forked session")
    return history


# Comparisons


@router.post("/api/collaboration/comparisons")
async def create_comparison_api(request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    comp = create_comparison(
        session_a_id=body.get("session_a_id", ""),
        session_b_id=body.get("session_b_id", ""),
        created_by=current_user.get("username", ""),
    )
    if not comp:
        raise HTTPException(status_code=404, detail="One or both sessions not found")
    return comp


@router.get("/api/collaboration/comparisons/{comparison_id}")
async def get_comparison_api(comparison_id: str):
    comp = get_comparison(comparison_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Comparison not found")
    return comp


# Annotations


@router.post("/api/sessions/{session_id}/annotations")
async def create_annotation_api(session_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    ann = create_annotation(
        session_id=session_id,
        turn_number=body.get("turn_number", 0),
        content=body.get("content", ""),
        user_id=current_user.get("username", ""),
        annotation_type=body.get("annotation_type", "comment"),
    )
    if not ann:
        raise HTTPException(status_code=404, detail="Session not found")
    return ann


@router.get("/api/sessions/{session_id}/annotations")
async def get_annotations_api(session_id: str, turn_number: int = None):
    return get_annotations(session_id, turn_number)


@router.put("/api/annotations/{annotation_id}")
async def update_annotation_api(annotation_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    updated = update_annotation(annotation_id, body.get("content", ""))
    if not updated:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"status": "ok"}


@router.delete("/api/annotations/{annotation_id}")
async def delete_annotation_api(annotation_id: str, current_user: dict = Depends(get_current_user)):
    deleted = delete_annotation(annotation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return {"status": "ok"}


@router.get("/api/sessions/{session_id}/annotation-summary")
async def get_annotation_summary_api(session_id: str):
    return get_annotation_summary(session_id)

