"""Router: Research & Benchmarking."""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse

from auth import get_current_user
from research import (
    create_template, delete_template, create_ab_test,
    record_ab_result, create_comparison, record_comparison_result,
    create_reproducible, compute_ses_scores,
)
from export import embed_session

router = APIRouter()


@router.post("/api/research/templates")
async def create_template_api(request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    t = create_template(
        name=body.get("name", ""),
        description=body.get("description", ""),
        personas=body.get("personas", []),
        topic=body.get("topic", ""),
        workflow=body.get("workflow", ""),
        system_prompt=body.get("system_prompt", ""),
        max_turns=body.get("max_turns", 20),
        created_by=current_user.get("username", ""),
    )
    return t


@router.get("/api/research/templates")
async def list_templates_api(limit: int = 50):
    return list_templates(limit)


@router.get("/api/research/templates/{template_id}")
async def get_template_api(template_id: str):
    t = get_template(template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return t


@router.post("/api/research/templates/{template_id}/use")
async def use_template_api(template_id: str):
    t = use_template(template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return t


@router.delete("/api/research/templates/{template_id}")
async def delete_template_api(template_id: str, current_user: dict = Depends(get_current_user)):
    deleted = delete_template(template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"status": "ok"}


# A/B Tests


@router.post("/api/research/ab-tests")
async def create_ab_test_api(request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    test = create_ab_test(
        name=body.get("name", ""),
        description=body.get("description", ""),
        variant_a_personas=body.get("variant_a_personas", []),
        variant_b_personas=body.get("variant_b_personas", []),
        topic=body.get("topic", ""),
        seed_input=body.get("seed_input", ""),
    )
    return test


@router.get("/api/research/ab-tests/{test_id}")
async def get_ab_test_api(test_id: str):
    summary = get_ab_test_summary(test_id)
    if not summary:
        raise HTTPException(status_code=404, detail="A/B test not found")
    return summary


@router.post("/api/research/ab-tests/{test_id}/results")
async def record_ab_result_api(test_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    result = record_ab_result(
        test_id=test_id,
        variant=body.get("variant", "A"),
        session_id=body.get("session_id", ""),
        social_score=body.get("social_score", 0),
        emotional_score=body.get("emotional_score", 0),
        spiritual_score=body.get("spiritual_score", 0),
        turn_count=body.get("turn_count", 0),
        avg_response_time=body.get("avg_response_time", 0),
    )
    return result


# Provider Comparisons


@router.post("/api/research/comparisons")
async def create_comparison_api(request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    comp = create_provider_comparison(
        name=body.get("name", ""),
        prompt=body.get("prompt", ""),
    )
    return comp


@router.post("/api/research/comparisons/{comparison_id}/results")
async def record_comparison_result_api(comparison_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    result = record_provider_result(
        comparison_id=comparison_id,
        provider=body.get("provider", ""),
        model=body.get("model", ""),
        response=body.get("response", ""),
        response_time=body.get("response_time", 0),
        token_count=body.get("token_count", 0),
        social_score=body.get("social_score", 0),
        emotional_score=body.get("emotional_score", 0),
        spiritual_score=body.get("spiritual_score", 0),
    )
    return result


@router.get("/api/research/comparisons/{comparison_id}")
async def get_comparison_api(comparison_id: str):
    comp = get_provider_comparison(comparison_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Comparison not found")
    return comp


# Reproducibility


@router.post("/api/research/reproducible")
async def create_reproducible_api(request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    result = create_reproducible_session(
        session_id=body.get("session_id", ""),
        seed=body.get("seed", ""),
        prompt=body.get("prompt", ""),
        personas=body.get("personas", []),
        config=body.get("config"),
    )
    return result


@router.get("/api/research/reproducible/{seed}")
async def get_reproducible_api(seed: str):
    result = get_reproducible_session(seed)
    if not result:
        raise HTTPException(status_code=404, detail="Reproducible session not found")
    return result


# SES Scores


@router.post("/api/research/ses-scores/{session_id}")
async def compute_ses_scores_api(session_id: str, current_user: dict = Depends(get_current_user)):
    scores = compute_ses_scores(session_id)
    return scores


@router.get("/api/research/ses-scores")
async def get_ses_scores_api(session_id: str = None, limit: int = 50):
    return get_ses_scores(session_id, limit)


@router.get("/api/research/ses-scores/export/csv")
async def export_ses_csv_api():
    import csv
    import io
    from fastapi.responses import Response

    csv_content = export_ses_scores_csv()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=ses_scores.csv"}
    )

