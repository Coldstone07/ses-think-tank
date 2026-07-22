"""Router: Core: index, health, personas, chat, workflows."""
from fastapi import APIRouter, Request, Request as FastAPIRequest, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index():
    from app import BASE_DIR
    with open(BASE_DIR / "web" / "index.html") as f:
        return f.read()


@router.get("/api/personas")
async def get_personas():
    from app import resolve_personas
    return resolve_personas()


@router.get("/health")
async def health_check():
    import time
    from app import START_TIME, active_sessions, _get_memory_mb
    return {
        "status": "ok",
        "uptime": round(time.time() - START_TIME, 1),
        "memory_mb": _get_memory_mb(),
        "active_sessions": len(active_sessions),
    }


@router.post("/api/chat")
async def chat_with_persona(request: FastAPIRequest):
    """Chat with a single persona directly."""
    from app import resolve_personas, call_llm
    body = await request.json()
    persona_id = body.get("persona_id")
    message = body.get("message")

    persona = next((p for p in resolve_personas() if p["id"] == persona_id), None)
    if not persona:
        return {"error": f"Unknown persona: {persona_id}"}

    messages = [
        {"role": "system", "content": persona["system_prompt"]},
        {"role": "user", "content": message},
    ]

    response = call_llm(messages, temperature=0.85, max_tokens=1024)

    return {
        "persona_id": persona_id,
        "persona_name": persona["name"],
        "icon": persona["icon"],
        "response": response,
    }


@router.post("/api/teams/analyze")
async def teams_analyze(request: FastAPIRequest):
    """Analyze a topic and recommend optimal team composition."""
    import asyncio
    from app import classify_domain
    body = await request.json()
    topic = body.get("topic", "")
    workflow_mode = body.get("workflow_mode", "auto")
    if not topic:
        return {
            "error": "Missing topic",
            "domain": "",
            "complexity": "",
            "recommended_personas": [],
            "excluded_personas": [],
            "reasoning": "",
        }
    result = await asyncio.get_event_loop().run_in_executor(
        None, classify_domain, topic, workflow_mode
    )
    return result


@router.get("/api/workflows")
async def get_workflows():
    from app import resolve_workflows
    return resolve_workflows()
