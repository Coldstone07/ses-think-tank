"""Router: Platform, Marketplace, Settings."""
from fastapi import APIRouter, Request, Request as FastAPIRequest, Depends, HTTPException
from fastapi.responses import JSONResponse

from app import (
    ConversationSession, Message, WhiteboardPin, InterventionRecord,
    active_connections, active_sessions, asdict, pin_asdict,
    broadcast_to_all, broadcast_whiteboard, calculate_synergy_metrics,
    classify_domain, extract_conversation_state, get_session,
    get_memory_suggestions, resolve_personas, resolve_workflows,
    run_conversation, save_session_to_disk, web_search,
    update_and_emit_metrics, SESSIONS_DIR, ITEMS_DIR,
)
from auth import get_current_user
from platform_scale import (
    register_plugin, install_plugin, approve_plugin, rate_plugin,
    get_plugin_reviews, get_marketplace_stats,
)
from settings import (
    set_default_provider, get_all_provider_configs, save_provider_config,
    get_default_provider, get_available_providers, get_available_integrations,
    get_all_settings, get_api_keys_list, save_api_key, delete_api_key,
    get_provider_env, get_environment_keys,
)

router = APIRouter()


@router.get("/api/platform/metrics")
async def metrics_api():
    """Get Prometheus-compatible metrics."""
    return metrics.get_prometheus_text()


@router.get("/api/platform/metrics/json")
async def metrics_json_api():
    """Get metrics as JSON."""
    return metrics.get_json()


# Structured Logging


@router.get("/api/platform/logs")
async def logs_api(lines: int = 50):
    """Get recent log entries."""
    return logger.get_recent(lines)


@router.get("/api/platform/logs/stats")
async def log_stats_api():
    """Get log statistics."""
    return logger.get_stats()


# API Router


@router.get("/api/platform/routes")
async def routes_api():
    """List all API routes."""
    return app.routes


# Plugin Marketplace


@router.post("/api/marketplace/plugins")
async def register_plugin_api(request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    plugin = register_plugin(
        name=body.get("name", ""),
        description=body.get("description", ""),
        category=body.get("category", "tool"),
        version=body.get("version", "1.0.0"),
        author=body.get("author", current_user.get("username", "")),
        download_url=body.get("download_url", ""),
        tags=body.get("tags", []),
    )
    return plugin


@router.get("/api/marketplace/plugins")
async def list_plugins_api(category: str = None, approved_only: bool = True, limit: int = 50):
    return list_plugins(category=category, approved_only=approved_only, limit=limit)


@router.get("/api/marketplace/plugins/search")
async def search_plugins_api(q: str, limit: int = 20):
    return search_plugins(q, limit)


@router.get("/api/marketplace/plugins/{plugin_id}")
async def get_plugin_api(plugin_id: str):
    plugin = get_plugin(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return plugin


@router.post("/api/marketplace/plugins/{plugin_id}/install")
async def install_plugin_api(plugin_id: str):
    plugin = install_plugin(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return plugin


@router.post("/api/marketplace/plugins/{plugin_id}/approve")
async def approve_plugin_api(plugin_id: str, current_user: dict = Depends(get_current_user)):
    approved = approve_plugin(plugin_id)
    if not approved:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return {"status": "ok"}


@router.post("/api/marketplace/plugins/{plugin_id}/rate")
async def rate_plugin_api(plugin_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    result = rate_plugin(
        plugin_id=plugin_id,
        user_id=current_user.get("user_id", ""),
        rating=body.get("rating", 0),
        review=body.get("review", ""),
    )
    if not result:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
    return result


@router.get("/api/marketplace/plugins/{plugin_id}/reviews")
async def get_plugin_reviews_api(plugin_id: str, limit: int = 20):
    return get_plugin_reviews(plugin_id, limit)


@router.get("/api/marketplace/stats")
async def marketplace_stats_api():
    return get_marketplace_stats()


@router.get("/api/settings/providers")
async def settings_providers_api():
    """Get available LLM providers."""
    return get_available_providers()


@router.get("/api/settings/integrations")
async def settings_integrations_api():
    """Get available integrations."""
    return get_available_integrations()


@router.get("/api/settings/config")
async def settings_config_api():
    """Get all provider configs + keys status for current user."""
    return {
        "providers": get_all_provider_configs("default"),
        "default_provider": get_default_provider("default"),
        "api_keys": get_api_keys_list("default"),
        "env_keys": get_environment_keys(),
        "settings": get_all_settings("default"),
        "provider_env": get_provider_env("default"),
    }


@router.post("/api/settings/provider/{provider_name}/config")
async def settings_save_provider_api(provider_name: str, request: FastAPIRequest):
    """Save provider configuration."""
    body = await request.json()
    save_provider_config("default", provider_name, body.get("config", {}), body.get("enabled", True))
    if body.get("set_default"):
        set_default_provider("default", provider_name)
    return {"status": "ok", "provider": provider_name}


@router.post("/api/settings/provider/{provider_name}/default")
async def settings_set_default_api(provider_name: str):
    """Set a provider as default."""
    set_default_provider("default", provider_name)
    return {"status": "ok", "default_provider": provider_name}


@router.post("/api/settings/api-key")
async def settings_save_api_key_api(request: FastAPIRequest):
    """Save an API key (encrypted)."""
    body = await request.json()
    save_api_key(
        "default",
        body["provider"],
        body["key_name"],
        body["key_value"],
        body.get("label", "")
    )
    return {"status": "ok"}


@router.delete("/api/settings/api-key/{key_id}")
async def settings_delete_api_key_api(key_id: int):
    """Delete an API key."""
    delete_api_key("default", int(key_id))
    return {"status": "ok"}


@router.get("/api/settings/provider-env")
async def settings_provider_env_api():
    """Get effective provider environment for LLM calls."""
    return get_provider_env("default")


@router.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    session = active_sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}
    return {
        "session_id": session.session_id,
        "topic": session.topic,
        "messages": [asdict(m) for m in session.messages],
        "started_at": session.started_at,
        "active": session.active,
        "turn_count": session.turn_count,
        "max_turns": session.max_turns,
        "evaluations": session.evaluations,
        "workflow_mode": session.workflow_mode,
        "current_phase": session.current_phase,
        "phase_history": session.phase_history,
        "deliverable": session.deliverable,
    }


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    session = active_sessions.pop(session_id, None)
    if not session:
        return {"error": "Session not found"}
    path = SESSIONS_DIR / f"{session_id}.json"
    if path.exists():
        path.unlink()
    log.info("Deleted session %s", session_id)
    return {"status": "deleted", "session_id": session_id}


@router.get("/api/sessions/{session_id}/whiteboard")
async def get_whiteboard(session_id: str):
    session = active_sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}
    return {pid: pin_asdict(pin) for pid, pin in session.whiteboard.items()}


@router.post("/api/sessions/{session_id}/whiteboard/pin")
async def create_pin(session_id: str, request: FastAPIRequest):
    session = active_sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}
    body = await request.json()
    pin = WhiteboardPin(
        id=str(uuid.uuid4())[:8],
        topic=body.get("topic", ""),
        content=body.get("content", ""),
        author=body.get("author", "unknown"),
        created_at=time.time(),
    )
    session.whiteboard[pin.id] = pin
    save_session_to_disk(session)
    await broadcast_whiteboard(session_id)
    return pin_asdict(pin)


@router.put("/api/sessions/{session_id}/whiteboard/pins/{pin_id}/vote")
async def vote_pin(session_id: str, pin_id: str, request: FastAPIRequest):
    session = active_sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}
    pin = session.whiteboard.get(pin_id)
    if not pin:
        return {"error": "Pin not found"}
    body = await request.json()
    persona_id = body.get("persona_id", "")
    vote = body.get("vote", "neutral")
    if vote not in ("approve", "reject", "neutral"):
        return {"error": "Invalid vote"}
    pin.votes[persona_id] = vote
    save_session_to_disk(session)
    await broadcast_whiteboard(session_id)
    return pin_asdict(pin)


@router.put("/api/sessions/{session_id}/whiteboard/pins/{pin_id}/comment")
async def comment_pin(session_id: str, pin_id: str, request: FastAPIRequest):
    session = active_sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}
    pin = session.whiteboard.get(pin_id)
    if not pin:
        return {"error": "Pin not found"}
    body = await request.json()
    comment = {
        "author": body.get("author", "anonymous"),
        "text": body.get("text", ""),
        "timestamp": time.time(),
    }
    pin.comments.append(comment)
    save_session_to_disk(session)
    await broadcast_whiteboard(session_id)
    return pin_asdict(pin)


@router.put("/api/sessions/{session_id}/whiteboard/pins/{pin_id}/status")
async def update_pin_status(session_id: str, pin_id: str, request: FastAPIRequest):
    session = active_sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}
    pin = session.whiteboard.get(pin_id)
    if not pin:
        return {"error": "Pin not found"}
    body = await request.json()
    status = body.get("status", "")
    if status not in ("approved", "rejected", "discussed"):
        return {"error": "Invalid status"}
    pin.status = status
    save_session_to_disk(session)
    await broadcast_whiteboard(session_id)
    return pin_asdict(pin)


@router.delete("/api/sessions/{session_id}/whiteboard/pins/{pin_id}")
async def delete_pin(session_id: str, pin_id: str):
    session = active_sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}
    pin = session.whiteboard.pop(pin_id, None)
    if not pin:
        return {"error": "Pin not found"}
    save_session_to_disk(session)
    await broadcast_whiteboard(session_id)
    return {"status": "deleted", "pin_id": pin_id}


@router.get("/api/sessions/{session_id}/metrics")
async def get_session_metrics(session_id: str):
    """Return current synergy metrics for a session."""
    session = active_sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}
    if not session.synergy_metrics:
        return calculate_synergy_metrics(session)
    return session.synergy_metrics


@router.get("/api/sessions/{session_id}/metrics/history")
async def get_session_metrics_history(session_id: str):
    """Return full turn-by-turn metrics history for a session."""
    session = active_sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}
    return session.metrics_history


@router.get("/api/sessions/{session_id}/conversation-state")
async def get_conversation_state(session_id: str):
    """Return current conversation state for a session."""
    session = active_sessions.get(session_id)
    if not session:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found")
    if session.conversation_state:
        return session.conversation_state
    return extract_conversation_state(session)


@router.get("/api/sessions/{session_id}/interventions")
async def get_interventions(session_id: str):
    """Return full intervention history for a session."""
    session = active_sessions.get(session_id)
    if not session:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "is_paused": session.is_paused,
        "interventions": [
            {"id": r.id, "mode": r.mode, "message": r.message, "target": r.target, "timestamp": r.timestamp}
            for r in session.interventions
        ],
        "total_interventions": len(session.interventions),
    }


@router.post("/api/sessions/{session_id}/intervene")
async def intervene_session(session_id: str, request: FastAPIRequest):
    """Human-in-the-Loop v2: structured intervention with modes."""
    from fastapi import HTTPException
    session = active_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    body = await request.json()
    mode = body.get("mode", "steer")  # steer, veto, amplify, pause, resume
    message = body.get("message", "")
    target = body.get("target", "")
    # Pause/resume are control actions — message is optional
    if not message.strip() and mode not in ("pause", "resume"):
        raise HTTPException(status_code=400, detail="Missing message")

    # Pause/resume are control actions
    if mode == "pause":
        session.is_paused = True
        record = InterventionRecord(
            id=str(uuid.uuid4())[:8], mode=mode, message=message,
            target=target, timestamp=time.time(),
        )
        session.interventions.append(record)
        await broadcast_to_all("intervention", {
            "type": "intervention", "mode": mode, "message": message,
            "target": target, "id": record.id, "timestamp": record.timestamp,
            "session_id": session_id,
        })
        return {"status": "paused", "mode": mode, "intervention_id": record.id}
    if mode == "resume":
        session.is_paused = False
        record = InterventionRecord(
            id=str(uuid.uuid4())[:8], mode=mode, message=message,
            target=target, timestamp=time.time(),
        )
        session.interventions.append(record)
        await broadcast_to_all("intervention", {
            "type": "intervention", "mode": mode, "message": message,
            "target": target, "id": record.id, "timestamp": record.timestamp,
            "session_id": session_id,
        })
        return {"status": "resumed", "mode": mode, "intervention_id": record.id}

    # Mode-specific prompt templates
    mode_prompts = {
        "steer": f"**[HUMAN STEER]** {message}. Please adjust the discussion accordingly.",
        "veto": f"**[HUMAN VETO]** {message}. This direction has been rejected — move on.",
        "amplify": f"**[HUMAN AMPLIFY]** {message}. Please expand on this point in detail.",
    }
    content = mode_prompts.get(mode, f"**[HUMAN INTERVENTION]** {message}")

    intervention_msg = Message(
        id=str(uuid.uuid4())[:8],
        persona_id="system",
        persona_name="Human Operator",
        icon="👤",
        color="#ffffff",
        content=content,
        timestamp=time.time(),
    )
    session.messages.append(intervention_msg)
    session.turn_count += 1
    record = InterventionRecord(
        id=str(uuid.uuid4())[:8], mode=mode, message=message,
        target=target, timestamp=time.time(),
    )
    session.interventions.append(record)
    await update_and_emit_metrics(None, session)
    save_session_to_disk(session)

    # Broadcast to all connected clients
    await broadcast_to_all("message", {"message": asdict(intervention_msg)})
    await broadcast_to_all("intervention", {
        "type": "intervention", "mode": mode, "message": message,
        "target": target, "id": record.id, "timestamp": record.timestamp,
        "session_id": session_id,
    })

    return {
        "status": "intervened",
        "mode": mode,
        "message": message,
        "turn": session.turn_count,
        "intervention_id": record.id,
    }


@router.get("/api/sessions/{session_id}/messages")
async def get_messages(session_id: str):
    """Return conversation messages for a session."""
    session = active_sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}
    return [asdict(m) for m in session.messages]


@router.get("/api/sessions")
async def get_sessions():
    return [
        {
            "session_id": s.session_id,
            "topic": s.topic,
            "turn_count": s.turn_count,
            "active": s.active,
            "started_at": s.started_at,
            "workflow_mode": s.workflow_mode,
            "current_phase": s.current_phase,
        }
        for s in active_sessions.values()
    ]


@router.post("/api/session")
async def create_session(
    topic: str, personas: str = "", max_turns: int = 20, workflow_mode: str = "salon"
):
    persona_ids = (
        [p.strip() for p in personas.split(",")]
        if personas
        else [p["id"] for p in resolve_personas()]
    )
    session_id = str(uuid.uuid4())[:8]
    wf = resolve_workflows().get(workflow_mode, resolve_workflows()["salon"])
    session = ConversationSession(
        session_id=session_id,
        topic=topic,
        started_at=time.time(),
        max_turns=max_turns,
        workflow_mode=workflow_mode,
    )
    active_sessions[session_id] = session
    save_session_to_disk(session)
    log.info(
        "Session created: id=%s topic=%s workflow=%s personas=%d",
        session_id,
        topic,
        workflow_mode,
        len(persona_ids),
    )
    return {
        "session_id": session_id,
        "topic": topic,
        "personas": persona_ids,
        "workflow": workflow_mode,
    }


@router.post("/api/sessions")
async def create_session_json(request: FastAPIRequest):
    """Create session via JSON body (test-friendly)."""
    body = await request.json()
    session_id = body.get("session_id", str(uuid.uuid4())[:8])
    topic = body.get("topic", "Discussion")
    persona_ids = body.get("persona_ids", [p["id"] for p in resolve_personas()])
    max_turns = body.get("max_turns", 20)
    workflow_mode = body.get("workflow_mode", "salon")
    personas_map = {p["id"]: p for p in resolve_personas()}
    session = ConversationSession(
        session_id=session_id,
        topic=topic,
        started_at=time.time(),
        max_turns=max_turns,
        workflow_mode=workflow_mode,
        personas=[personas_map[pid] for pid in persona_ids if pid in personas_map],
    )
    active_sessions[session_id] = session
    save_session_to_disk(session)
    return {
        "session_id": session_id,
        "topic": topic,
        "personas": persona_ids,
        "workflow": workflow_mode,
    }


@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_connections[client_id] = websocket
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            if msg.get("type") == "start_conversation":
                session_id = msg.get("session_id")
                topic = msg.get("topic")
                if not topic:
                    await websocket.send_json(
                        {"type": "error", "message": "Missing topic"}
                    )
                    continue
                persona_ids = msg.get("personas", [p["id"] for p in resolve_personas()])
                max_turns = msg.get("max_turns", 20)
                workflow_mode = msg.get("workflow_mode", "salon")
                auto_team = msg.get("auto_team", False)

                if auto_team:
                    try:
                        loop = asyncio.get_event_loop()
                        team_analysis = await loop.run_in_executor(
                            None, classify_domain, topic, workflow_mode
                        )
                        recommended = team_analysis.get("recommended_personas", [])
                        if recommended:
                            persona_ids = recommended
                            await websocket.send_json(
                                {
                                    "type": "team_recommendation",
                                    "analysis": team_analysis,
                                }
                            )
                    except Exception as e:
                        log.warning("Auto-team classification failed: %s", e)

                try:
                    loop = asyncio.get_event_loop()
                    suggestion = await loop.run_in_executor(
                        None, get_memory_suggestions, topic
                    )
                    if suggestion:
                        await websocket.send_json(
                            {"type": "memory_suggestion", **suggestion}
                        )
                except Exception as e:
                    log.warning("Memory suggestion failed: %s", e)

                try:
                    session = await run_conversation(
                        session_id,
                        topic,
                        persona_ids,
                        max_turns,
                        workflow_mode,
                        websocket,
                    )
                    active_sessions[session_id] = session
                except Exception as e:
                    await websocket.send_json(
                        {"type": "error", "message": f"Conversation failed: {str(e)}"}
                    )

            elif msg.get("type") == "pin_idea":
                ws_session_id = msg.get("session_id", "")
                ws_session = active_sessions.get(ws_session_id)
                if ws_session:
                    pin = WhiteboardPin(
                        id=str(uuid.uuid4())[:8],
                        topic=msg.get("topic", ""),
                        content=msg.get("content", ""),
                        author=msg.get("author", "unknown"),
                        created_at=time.time(),
                    )
                    ws_session.whiteboard[pin.id] = pin
                    save_session_to_disk(ws_session)
                    await broadcast_whiteboard(ws_session_id)

            elif msg.get("type") == "vote_pin":
                ws_session_id = msg.get("session_id", "")
                ws_session = active_sessions.get(ws_session_id)
                if ws_session:
                    pin_id = msg.get("pin_id", "")
                    pin = ws_session.whiteboard.get(pin_id)
                    if pin:
                        persona_id = msg.get("persona_id", "")
                        vote = msg.get("vote", "neutral")
                        if vote in ("approve", "reject", "neutral"):
                            pin.votes[persona_id] = vote
                            save_session_to_disk(ws_session)
                            await broadcast_whiteboard(ws_session_id)

            elif msg.get("type") == "comment_pin":
                ws_session_id = msg.get("session_id", "")
                ws_session = active_sessions.get(ws_session_id)
                if ws_session:
                    pin_id = msg.get("pin_id", "")
                    pin = ws_session.whiteboard.get(pin_id)
                    if pin:
                        comment = {
                            "author": msg.get("author", "anonymous"),
                            "text": msg.get("text", ""),
                            "timestamp": time.time(),
                        }
                        pin.comments.append(comment)
                        save_session_to_disk(ws_session)
                        await broadcast_whiteboard(ws_session_id)

            elif msg.get("type") == "intervene":
                ws_session_id = msg.get("session_id", "")
                ws_session = active_sessions.get(ws_session_id)
                if ws_session:
                    intervention_text = msg.get("message", "")
                    mode = msg.get("mode", "steer")
                    target = msg.get("target", "")
                    if intervention_text:
                        # Pause/resume control actions
                        if mode == "pause":
                            ws_session.is_paused = True
                            record = InterventionRecord(
                                id=str(uuid.uuid4())[:8], mode=mode, message=intervention_text,
                                target=target, timestamp=time.time(),
                            )
                            ws_session.interventions.append(record)
                            await broadcast_to_all("intervention", {
                                "type": "intervention", "mode": mode, "message": intervention_text,
                                "target": target, "id": record.id, "timestamp": record.timestamp,
                                "session_id": ws_session_id,
                            })
                            continue
                        if mode == "resume":
                            ws_session.is_paused = False
                            record = InterventionRecord(
                                id=str(uuid.uuid4())[:8], mode=mode, message=intervention_text,
                                target=target, timestamp=time.time(),
                            )
                            ws_session.interventions.append(record)
                            await broadcast_to_all("intervention", {
                                "type": "intervention", "mode": mode, "message": intervention_text,
                                "target": target, "id": record.id, "timestamp": record.timestamp,
                                "session_id": ws_session_id,
                            })
                            continue
                        # Mode-specific content
                        mode_prompts = {
                            "steer": f"**[HUMAN STEER]** {intervention_text}. Please adjust the discussion accordingly.",
                            "veto": f"**[HUMAN VETO]** {intervention_text}. This direction has been rejected — move on.",
                            "amplify": f"**[HUMAN AMPLIFY]** {intervention_text}. Please expand on this point in detail.",
                        }
                        content = mode_prompts.get(mode, f"**[HUMAN INTERVENTION]** {intervention_text}")
                        intervention_msg = Message(
                            id=str(uuid.uuid4())[:8],
                            persona_id="system",
                            persona_name="Human Operator",
                            icon="👤",
                            color="#ffffff",
                            content=content,
                            timestamp=time.time(),
                        )
                        ws_session.messages.append(intervention_msg)
                        ws_session.turn_count += 1
                        record = InterventionRecord(
                            id=str(uuid.uuid4())[:8], mode=mode, message=intervention_text,
                            target=target, timestamp=time.time(),
                        )
                        ws_session.interventions.append(record)
                        await update_and_emit_metrics(websocket, ws_session)
                        save_session_to_disk(ws_session)
                        await broadcast_to_all(
                            "message", {"message": asdict(intervention_msg)}
                        )
                        await broadcast_to_all("intervention", {
                            "type": "intervention", "mode": mode, "message": intervention_text,
                            "target": target, "id": record.id, "timestamp": record.timestamp,
                            "session_id": ws_session_id,
                        })

            elif msg.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg.get("type") == "get_state":
                ws_sid = msg.get("session_id")
                # If no session_id in message, try to find the most recent one
                if not ws_sid and active_sessions:
                    ws_sid = list(active_sessions.keys())[-1]
                if ws_sid and ws_sid in active_sessions:
                    state = extract_conversation_state(active_sessions[ws_sid])
                    await websocket.send_json({"type": "conversation_state", "state": state})
                else:
                    await websocket.send_json({"type": "error", "message": "Session not found"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.error("WebSocket error for %s: %s", client_id, e)
    finally:
        active_connections.pop(client_id, None)


@router.get("/api/search")
async def search(query: str):
    return {"query": query, "results": web_search(query)}


@router.get("/api/items")
async def get_items(pillar: str = "", limit: int = 50):
    items = []
    if ITEMS_DIR.exists():
        for yaml_path in sorted(ITEMS_DIR.rglob("*.yaml")):
            try:
                with open(yaml_path) as f:
                    raw = yaml.safe_load(f)
                if raw and "id" in raw:
                    items.append(
                        {
                            "id": raw["id"],
                            "pillar": raw.get("pillar", ""),
                            "dimension": raw.get("dimension", ""),
                            "level": raw.get("level", 1),
                            "situation": raw.get("situation", ""),
                        }
                    )
            except Exception:
                continue
    return items[:limit]

