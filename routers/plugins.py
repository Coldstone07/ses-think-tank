"""Router: Plugin API, Tool API, Knowledge API."""
from fastapi import APIRouter, Request, Request as FastAPIRequest, Depends, HTTPException
from fastapi.responses import JSONResponse

from app import (
    BASE_DIR, resolve_personas, reload_plugins,
    get_plugin_personas, add_plugin_persona, delete_plugin_persona,
    check_plugins_need_reload, reload_tools, get_tools,
    register_tool, delete_tool, get_knowledge,
)

router = APIRouter()


@router.get("/api/plugins")
async def get_plugins():
    """List all loaded plugins with metadata."""
    return plugin_store.info()


@router.post("/api/plugins/reload")
async def reload_plugins():
    """Hot-reload all plugins from disk."""
    summary = plugin_store.load_all(str(BASE_DIR))
    log.info(f"Plugins reloaded: {summary['loaded']} files, {summary['errors']} errors")
    # Update PERSONA_NAMES with merged personas
    global PERSONA_NAMES
    PERSONA_NAMES = {p["id"]: p["name"] for p in resolve_personas()}
    return summary


@router.get("/api/plugins/personas")
async def get_plugin_personas():
    """List plugin-defined personas only."""
    return plugin_store.personas


@router.get("/api/plugins/memory")
async def get_plugin_memory():
    """List plugin-defined memory rules."""
    return plugin_store.memory_rules


@router.post("/api/plugins/personas")
async def create_plugin_persona(request: FastAPIRequest):
    """Create a new persona plugin YAML file."""
    body = await request.json()
    errors = []
    for field in PERSONA_REQUIRED:
        if field not in body or not body[field]:
            errors.append(f"Missing required field: {field}")
    if errors:
        return JSONResponse(status_code=400, content={"error": "; ".join(errors)})

    persona_id = body["id"]
    if not isinstance(persona_id, str) or not persona_id.replace("-", "").replace("_", "").isalnum():
        return JSONResponse(status_code=400, content={"error": "Invalid persona id"})

    fname = f"plugins/personas/{persona_id}.yaml"
    fpath = str(BASE_DIR / fname)
    try:
        os.makedirs(str(BASE_DIR / "plugins/personas"), exist_ok=True)
        with open(fpath, "w", encoding="utf-8") as f:
            yaml.dump(body, f, default_flow_style=False, allow_unicode=True)
        # Reload to pick up new persona
        summary = plugin_store.load_all(str(BASE_DIR))
        global PERSONA_NAMES
        PERSONA_NAMES = {p["id"]: p["name"] for p in resolve_personas()}
        return {"created": fpath, "reloaded": True, "summary": summary}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.delete("/api/plugins/personas/{persona_id}")
async def delete_plugin_persona(persona_id: str):
    """Delete a plugin persona YAML file."""
    fpath = str(BASE_DIR / f"plugins/personas/{persona_id}.yaml")
    if not os.path.exists(fpath):
        return JSONResponse(status_code=404, content={"error": f"Persona plugin not found: {persona_id}"})
    try:
        os.remove(fpath)
        summary = plugin_store.load_all(str(BASE_DIR))
        global PERSONA_NAMES
        PERSONA_NAMES = {p["id"]: p["name"] for p in resolve_personas()}
        return {"deleted": fpath, "reloaded": True, "summary": summary}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/api/plugins/needs-reload")
async def check_plugin_reload():
    """Check if any plugin files have changed since last load."""
    return {"needs_reload": plugin_store.needs_reload(str(BASE_DIR))}


@router.get("/api/tools")
async def list_tools():
    """List all available tools (built-in + plugins)."""
    return tool_store.info()


@router.post("/api/tools/reload")
async def reload_tools():
    """Reload tool plugins from disk."""
    summary = tool_store.load_all(str(BASE_DIR))
    log.info(f"Tools reloaded: {summary['loaded']} tools, {summary['errors']} errors")
    return {"reloaded": True, "summary": summary}


@router.post("/api/tools")
async def create_tool():
    """Create a new tool plugin YAML file."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    errors = validate_tool(body)
    if errors:
        return JSONResponse(status_code=400, content={"error": "; ".join(errors)})

    tool_name = body["name"]
    fname = f"plugins/tools/{tool_name}.yaml"
    fpath = str(BASE_DIR / fname)
    try:
        os.makedirs(str(BASE_DIR / "plugins/tools"), exist_ok=True)
        with open(fpath, "w", encoding="utf-8") as f:
            yaml.dump(body, f, default_flow_style=False, allow_unicode=True)
        summary = tool_store.load_all(str(BASE_DIR))
        return {"created": fpath, "reloaded": True, "summary": summary}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.delete("/api/tools/{tool_name}")
async def delete_tool(tool_name: str):
    """Delete a tool plugin YAML file."""
    fpath = str(BASE_DIR / f"plugins/tools/{tool_name}.yaml")
    if not os.path.exists(fpath):
        return JSONResponse(status_code=404, content={"error": f"Tool plugin not found: {tool_name}"})
    try:
        os.remove(fpath)
        summary = tool_store.load_all(str(BASE_DIR))
        return {"deleted": fpath, "reloaded": True, "summary": summary}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/api/knowledge")
async def list_knowledge():
    """List all personas with knowledge."""
    return list_personas_with_knowledge(str(BASE_DIR))


@router.get("/api/knowledge/{persona_id}")
async def get_knowledge(persona_id: str):
    """Get knowledge for a specific persona."""
    return load_knowledge(persona_id, str(BASE_DIR))


@router.post("/api/knowledge/{persona_id}/memory")
async def add_persona_memory(persona_id: str):
    """Add a memory to a persona's knowledge."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    insight = body.get("insight", "")
    source = body.get("source", "")
    if not insight:
        return JSONResponse(status_code=400, content={"error": "insight is required"})

    memory = add_memory(persona_id, insight, source, str(BASE_DIR))
    return {"added": memory}


@router.post("/api/knowledge/{persona_id}/extract-memories")
async def extract_persona_memories(persona_id: str):
    """Extract memories from recent conversation messages for a persona."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    messages = body.get("messages", [])
    added = extract_memories_from_conversation(persona_id, messages, str(BASE_DIR))
    return {"extracted": len(added), "memories": added}

