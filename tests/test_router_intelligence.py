"""Test routers/intelligence.py endpoints."""
import pytest
import sys
import os
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Set fixed test secret BEFORE importing app (lifespan locks in the key)
os.environ["SES_JWT_SECRET"] = "test-secret-key"

from fastapi.testclient import TestClient
from app import app, init_memory_db
from session_intelligence import init_intelligence_schema
from evaluation_dashboard import init_evaluation_schema
from persona_evolution import init_evolution_schema
from intelligence import init_intelligence_schema as init_deeper_intelligence_schema
from auth import create_access_token, init_auth_schema, seed_default_user

@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "memory.db")
    os.environ["SES_MEMORY_DB"] = db_path
    # Use a fixed test secret so tokens verify consistently across module reloads
    os.environ["SES_JWT_SECRET"] = "test-secret-key"

    import importlib
    import session_intelligence
    import evaluation_dashboard
    import persona_evolution
    import intelligence
    import db
    import auth

    importlib.reload(db)
    importlib.reload(session_intelligence)
    importlib.reload(evaluation_dashboard)
    importlib.reload(persona_evolution)
    importlib.reload(intelligence)
    # Do NOT reload auth — app.py imported get_current_user at module load time.
    # Reloading auth creates a new SECRET_KEY, breaking token verification.
    
    auth.init_auth_schema()
    auth.seed_default_user()
    session_intelligence.init_intelligence_schema()
    evaluation_dashboard.init_evaluation_schema()
    persona_evolution.init_evolution_schema()
    intelligence.init_intelligence_schema()
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS memory_sessions (
            session_id TEXT PRIMARY KEY,
            topic TEXT NOT NULL,
            persona_ids TEXT DEFAULT '',
            started_at REAL DEFAULT (julianday('now')),
            ended_at REAL,
            turn_count INTEGER DEFAULT 0,
            deliverable TEXT DEFAULT '',
            summary TEXT DEFAULT ''
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS memory_messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            persona_id TEXT,
            content TEXT DEFAULT '',
            reasoning TEXT DEFAULT '',
            turn_number INTEGER DEFAULT 0,
            created_at REAL DEFAULT (julianday('now'))
        )
    """)
    cur.execute(
        "INSERT INTO memory_sessions (session_id, topic, persona_ids, turn_count) VALUES (?, ?, ?, ?)",
        ("sess-test-1", "Test Topic", "rook,elena", 5)
    )
    conn.commit()
    conn.close()
    
    with TestClient(app) as client:
        yield client

@pytest.fixture
def auth_headers(client):
    import auth
    user = auth.get_user_by_username("admin")
    if user:
        token = auth.create_access_token(user["user_id"], user["role"])
    else:
        token = auth.create_access_token("admin-id", "admin")
    return {"Authorization": f"Bearer {token}"}

def test_intelligence_summary(client):
    res = client.get("/api/intelligence/summary")
    assert res.status_code == 200

def test_get_insights_api(client):
    res = client.get("/api/intelligence/insights")
    assert res.status_code == 200
    res_sess = client.get("/api/intelligence/insights?session_id=sess-test-1")
    assert res_sess.status_code == 200

def test_get_related_sessions_api(client):
    res = client.get("/api/intelligence/related/sess-test-1")
    assert res.status_code == 200

def test_smart_recall_api(client):
    res = client.get("/api/intelligence/recall?topic=test")
    assert res.status_code == 200

def test_extract_insights_api(client):
    res = client.post("/api/intelligence/extract", json={
        "session_id": "sess-test-1",
        "messages": [{"content": "This is a key insight about artificial intelligence framework design and optimization."}]
    })
    assert res.status_code == 200

def test_rebuild_graph_api(client):
    res = client.post("/api/intelligence/graph")
    assert res.status_code == 200

def test_eval_dashboard_api(client):
    res = client.get("/api/eval/dashboard")
    assert res.status_code == 200

def test_eval_session_api(client):
    res = client.get("/api/eval/session/sess-test-1")
    assert res.status_code == 200

def test_eval_persona_api(client):
    res = client.get("/api/eval/persona/rook")
    assert res.status_code == 200

def test_eval_trend_api(client):
    res = client.get("/api/eval/trend")
    assert res.status_code == 200

def test_eval_export_api(client):
    res = client.get("/api/eval/export/sess-test-1")
    assert res.status_code == 200

def test_evolution_summary_api(client):
    res = client.get("/api/evolution/summary")
    assert res.status_code == 200

def test_evolution_persona_api(client):
    res = client.get("/api/evolution/persona/rook")
    assert res.status_code == 200

def test_search_sessions_api(client):
    res = client.get("/api/intelligence/search?q=test")
    assert res.status_code == 200

def test_synthesize_api(client):
    res = client.post("/api/intelligence/synthesize", json={"topics": ["test"]})
    assert res.status_code == 200

def test_embed_session_api(client, auth_headers):
    res = client.post("/api/intelligence/embed/sess-test-1", headers=auth_headers)
    assert res.status_code == 200

def test_persona_knowledge_api(client):
    res = client.get("/api/intelligence/knowledge/rook")
    assert res.status_code == 200

def test_generate_knowledge_api(client, auth_headers):
    res = client.post("/api/intelligence/knowledge/rook/generate", headers=auth_headers)
    assert res.status_code == 200

def test_quality_overview_api(client):
    res = client.get("/api/intelligence/quality/overview")
    assert res.status_code == 200

def test_compute_quality_api(client, auth_headers):
    res = client.post("/api/intelligence/quality/sess-test-1", headers=auth_headers)
    assert res.status_code == 200
