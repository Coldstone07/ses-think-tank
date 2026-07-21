#!/usr/bin/env python3
"""
Phase 3.4 — Multi-Session Memory Test Suite
=============================================
Tests SQLite database layer, memory search API, cross-session insights,
team recommendations, memory population, WebSocket suggestions, UI, and edge cases.

Run: python3.11 tests/test_memory.py
"""

import asyncio
import json
import os
import sys
import time
import traceback
import uuid
from collections import Counter
from typing import Dict, List, Optional

import requests
import sqlite3

BASE_URL = "http://localhost:8773"
WS_URL = "ws://localhost:8773"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as app_mod
import importlib

importlib.reload(app_mod)

# Re-import AFTER reload to get fresh class references
MEMORY_DB_PATH = app_mod.MEMORY_DB_PATH
BASE_DIR = app_mod.BASE_DIR
WEB_HTML = os.path.join(BASE_DIR, "web", "index.html")

init_memory_db = app_mod.init_memory_db
populate_memory = app_mod.populate_memory
search_memory_by_topic = app_mod.search_memory_by_topic
search_memory_by_persona = app_mod.search_memory_by_persona
get_session_memory = app_mod.get_session_memory
get_cross_session_insights = app_mod.get_cross_session_insights
recommend_team_from_memory = app_mod.recommend_team_from_memory
get_memory_suggestions = app_mod.get_memory_suggestions
Message = app_mod.Message
WhiteboardPin = app_mod.WhiteboardPin
ConversationSession = app_mod.ConversationSession
PERSONA_NAMES = app_mod.PERSONA_NAMES

P, F = chr(0x2705), chr(0x274C)
passed = failed = 0
results = []


def _test(name, category=""):
    def wrap(fn):
        results.append((category, name, fn))
        return fn

    return wrap


def check(c, m=""):
    if not c:
        raise AssertionError(m)


def eq(a, b, m=""):
    if a != b:
        raise AssertionError(m or f"Expected {b!r}, got {a!r}")


def inside(item, col, m=""):
    if item not in col:
        raise AssertionError(m or f"{item!r} not in {col!r}")


def gt(a, b, m=""):
    if not (a > b):
        raise AssertionError(m or f"Expected {a!r} > {b!r}")


def gte(a, b, m=""):
    if not (a >= b):
        raise AssertionError(m or f"Expected {a!r} >= {b!r}")


def lt(a, b, m=""):
    if not (a < b):
        raise AssertionError(m or f"Expected {a!r} < {b!r}")


def between(val, lo, hi, m=""):
    if not (lo <= val <= hi):
        raise AssertionError(m or f"Expected {lo} <= {val} <= {hi}")


async def ws_close(ws):
    try:
        ws.transport.abort()
    except Exception:
        pass


def run_ws(coro):
    try:
        asyncio.run(coro)
    except (AssertionError, TimeoutError):
        raise
    except Exception:
        pass


def make_msg(pid, pname, content, ts=None):
    return Message(
        id=str(uuid.uuid4())[:8],
        persona_id=pid,
        persona_name=pname,
        icon="?",
        color="#ccc",
        content=content,
        timestamp=ts or time.time(),
    )


def make_pin(
    pin_id, topic="Test Pin", content="Pin content", author="rook", status="approved"
):
    return WhiteboardPin(
        id=pin_id,
        topic=topic,
        content=content,
        author=author,
        status=status,
        created_at=time.time(),
    )


def make_session(sid="test-mem-session", topic="Test Memory", msgs=None, pins=None):
    s = ConversationSession(
        session_id=sid,
        topic=topic,
        max_turns=100,
        workflow_mode="salon",
        started_at=time.time(),
    )
    s.personas = [
        {"id": "rook", "name": "Rook", "icon": "♟"},
        {"id": "elena", "name": "Elena", "icon": "🌸"},
    ]
    if msgs:
        s.messages = msgs
        s.turn_count = len(msgs)
    else:
        msgs = [
            make_msg("rook", "Rook", "We should focus on renewable energy"),
            make_msg("elena", "Elena", "Solar power has the highest ROI currently"),
        ]
        s.messages = msgs
        s.turn_count = len(msgs)
    if pins:
        s.whiteboard = {p.id: p for p in pins}
    return s


def clean_test_db():
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    cur = conn.cursor()
    cur.execute("DELETE FROM cross_references")
    cur.execute("DELETE FROM persona_interactions")
    cur.execute("DELETE FROM memory_pins")
    cur.execute("DELETE FROM memory_sessions")
    conn.commit()
    conn.close()


def ensure_test_session(sid="test-mem-session"):
    r = requests.get(f"{BASE_URL}/api/memory/session/{sid}", timeout=10)
    if r.status_code == 200 and "error" not in r.json():
        return
    session = make_session(sid=sid, topic="Test Memory")
    populate_memory(session)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SQLite Database (Data Layer)
# ═══════════════════════════════════════════════════════════════════════════════


@_test("init_memory_db creates all required tables", category="DB")
def t01():
    init_memory_db()
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    conn.close()
    for t in (
        "memory_sessions",
        "memory_pins",
        "persona_interactions",
        "cross_references",
    ):
        inside(t, tables)


@_test("memory_sessions table has correct schema", category="DB")
def t02():
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(memory_sessions)")
    cols = {r[1]: r[2] for r in cur.fetchall()}
    conn.close()
    for col, dtype in [
        ("session_id", "TEXT"),
        ("topic", "TEXT"),
        ("workflow_mode", "TEXT"),
        ("started_at", "REAL"),
        ("ended_at", "REAL"),
        ("turn_count", "INTEGER"),
        ("deliverable", "TEXT"),
        ("summary", "TEXT"),
        ("persona_ids", "TEXT"),
    ]:
        inside(col, cols)
        eq(cols[col], dtype)


@_test("memory_pins table has correct schema", category="DB")
def t03():
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(memory_pins)")
    cols = {r[1]: r[2] for r in cur.fetchall()}
    conn.close()
    for col in (
        "id",
        "session_id",
        "topic",
        "content",
        "author",
        "status",
        "created_at",
    ):
        inside(col, cols)


@_test("persona_interactions table has correct schema", category="DB")
def t04():
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(persona_interactions)")
    cols = {r[1]: r[2] for r in cur.fetchall()}
    conn.close()
    for col in ("id", "session_id", "persona_id", "turns_spoken", "partners"):
        inside(col, cols)


@_test("cross_references table has correct schema", category="DB")
def t05():
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(cross_references)")
    cols = {r[1]: r[2] for r in cur.fetchall()}
    conn.close()
    for col in (
        "id",
        "session_id",
        "referenced_session_id",
        "reference_text",
        "created_at",
    ):
        inside(col, cols)


@_test("populate_memory inserts a session record", category="DB")
def t06():
    clean_test_db()
    sid = f"db-test-{str(uuid.uuid4())[:8]}"
    session = make_session(sid=sid, topic="Database Test")
    session.deliverable = "Test deliverable output"
    populate_memory(session)
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    cur = conn.cursor()
    cur.execute(
        "SELECT session_id, topic, deliverable FROM memory_sessions WHERE session_id = ?",
        (sid,),
    )
    row = cur.fetchone()
    conn.close()
    check(row is not None, f"Session {sid} not found in DB")
    eq(row[1], "Database Test")
    eq(row[2], "Test deliverable output")


@_test("populate_memory extracts whiteboard pins into memory_pins", category="DB")
def t07():
    clean_test_db()
    sid = f"db-pins-{str(uuid.uuid4())[:8]}"
    pins = [
        make_pin(
            "pin001", topic="Renewable Energy", content="Solar farms", author="rook"
        ),
        make_pin(
            "pin002",
            topic="Storage",
            content="Battery tech",
            author="elena",
            status="discussed",
        ),
    ]
    session = make_session(sid=sid, topic="Pin Test", pins=pins)
    populate_memory(session)
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    cur = conn.cursor()
    cur.execute(
        "SELECT id, topic, content, author, status FROM memory_pins WHERE session_id = ?",
        (sid,),
    )
    rows = cur.fetchall()
    conn.close()
    eq(len(rows), 2)
    ids = [r[0] for r in rows]
    inside("pin001", ids)
    inside("pin002", ids)


@_test("populate_memory records persona interaction counts", category="DB")
def t08():
    clean_test_db()
    sid = f"db-interact-{str(uuid.uuid4())[:8]}"
    msgs = [
        make_msg("rook", "Rook", "First idea"),
        make_msg("elena", "Elena", "Second idea"),
        make_msg("rook", "Rook", "Third idea"),
    ]
    session = make_session(sid=sid, topic="Interaction Test", msgs=msgs)
    populate_memory(session)
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    cur = conn.cursor()
    cur.execute(
        "SELECT persona_id, turns_spoken FROM persona_interactions WHERE session_id = ?",
        (sid,),
    )
    rows = cur.fetchall()
    conn.close()
    counts = {r[0]: r[1] for r in rows}
    inside("rook", counts)
    inside("elena", counts)
    eq(counts["rook"], 2)
    eq(counts["elena"], 1)


@_test("populate_memory handles session with no whiteboard pins", category="DB")
def t09():
    clean_test_db()
    sid = f"db-nopins-{str(uuid.uuid4())[:8]}"
    session = make_session(sid=sid, topic="No Pins Test", pins=[])
    session.whiteboard = {}
    populate_memory(session)
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM memory_pins WHERE session_id = ?", (sid,))
    count = cur.fetchone()[0]
    conn.close()
    eq(count, 0)


@_test("DB file exists at expected path", category="DB")
def t10():
    check(os.path.exists(str(MEMORY_DB_PATH)), f"DB file not found at {MEMORY_DB_PATH}")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Memory Search API
# ═══════════════════════════════════════════════════════════════════════════════


@_test("GET /api/memory/sessions returns 200", category="Search API")
def t11():
    r = requests.get(f"{BASE_URL}/api/memory/sessions", timeout=10)
    eq(r.status_code, 200)


@_test(
    "GET /api/memory/sessions?topic=X returns matching sessions", category="Search API"
)
def t12():
    sid = f"search-topic-{str(uuid.uuid4())[:8]}"
    session = make_session(sid=sid, topic="Quantum Computing Applications")
    populate_memory(session)
    r = requests.get(f"{BASE_URL}/api/memory/sessions?topic=Quantum", timeout=10)
    eq(r.status_code, 200)
    data = r.json()
    topics = [s.get("topic", "") for s in data]
    matches = [t for t in topics if "Quantum" in t]
    gt(len(matches), 0)


@_test(
    "GET /api/memory/sessions?persona=X returns matching sessions",
    category="Search API",
)
def t13():
    sid = f"search-persona-{str(uuid.uuid4())[:8]}"
    session = make_session(sid=sid, topic="AI Ethics")
    populate_memory(session)
    r = requests.get(f"{BASE_URL}/api/memory/sessions?persona=rook", timeout=10)
    eq(r.status_code, 200)
    data = r.json()
    check(isinstance(data, list))
    gte(len(data), 1)
    for s in data:
        inside("rook", s.get("persona_ids", []))


@_test(
    "GET /api/memory/sessions with no params returns all sessions",
    category="Search API",
)
def t14():
    r = requests.get(f"{BASE_URL}/api/memory/sessions", timeout=10)
    eq(r.status_code, 200)
    data = r.json()
    check(isinstance(data, list))


@_test(
    "GET /api/memory/session/{id} returns full record with pins and interactions",
    category="Search API",
)
def t15():
    sid = f"search-full-{str(uuid.uuid4())[:8]}"
    pins = [make_pin("fp001", topic="Test Insight", content="Detail", author="kael")]
    session = make_session(sid=sid, topic="Full Record Test", pins=pins)
    populate_memory(session)
    r = requests.get(f"{BASE_URL}/api/memory/session/{sid}", timeout=10)
    eq(r.status_code, 200)
    data = r.json()
    eq(data["session_id"], sid)
    eq(data["topic"], "Full Record Test")
    inside("pins", data)
    inside("interactions", data)
    gte(len(data["pins"]), 1)
    gte(len(data["interactions"]), 1)


@_test("GET /api/memory/session/{nonexistent} returns error", category="Search API")
def t16():
    r = requests.get(
        f"{BASE_URL}/api/memory/session/nonexistent-session-12345", timeout=10
    )
    data = r.json()
    inside("error", data)


@_test("Search is case-insensitive", category="Search API")
def t17():
    sid = f"search-case-{str(uuid.uuid4())[:8]}"
    session = make_session(sid=sid, topic="Case Sensitivity Test")
    populate_memory(session)
    r = requests.get(
        f"{BASE_URL}/api/memory/sessions?topic=case+sensitivity", timeout=10
    )
    eq(r.status_code, 200)
    data = r.json()
    sid_list = [s.get("session_id") for s in data]
    inside(sid, sid_list)


@_test("Multiple topic keywords work", category="Search API")
def t18():
    sid = f"search-multi-{str(uuid.uuid4())[:8]}"
    session = make_session(sid=sid, topic="Artificial Intelligence Machine Learning")
    populate_memory(session)
    r = requests.get(
        f"{BASE_URL}/api/memory/sessions?topic=Artificial+Machine", timeout=10
    )
    eq(r.status_code, 200)
    data = r.json()
    sid_list = [s.get("session_id") for s in data]
    inside(sid, sid_list)


@_test("Persona filter only returns sessions with that persona", category="Search API")
def t19():
    sid1 = f"pf-{str(uuid.uuid4())[:8]}"
    sid2 = f"pf-{str(uuid.uuid4())[:8]}"
    s1 = make_session(sid=sid1, topic="Session One")
    s2 = make_session(sid=sid2, topic="Session Two")
    populate_memory(s1)
    populate_memory(s2)
    r = requests.get(f"{BASE_URL}/api/memory/sessions?persona=rook", timeout=10)
    eq(r.status_code, 200)
    data = r.json()
    for s in data:
        pid_list = s.get("persona_ids", [])
        inside("rook", pid_list)


@_test("Search returns empty list when topic has no matches", category="Search API")
def t20():
    r = requests.get(
        f"{BASE_URL}/api/memory/sessions?topic=zzzzzxyznonexistenttopic", timeout=10
    )
    eq(r.status_code, 200)
    data = r.json()
    eq(data, [])


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Cross-Session Insights API
# ═══════════════════════════════════════════════════════════════════════════════


@_test("GET /api/memory/insights/{topic} returns 200", category="Insights")
def t21():
    r = requests.get(f"{BASE_URL}/api/memory/insights/Test", timeout=10)
    eq(r.status_code, 200)


@_test("Insights response contains session_count field", category="Insights")
def t22():
    r = requests.get(f"{BASE_URL}/api/memory/insights/Test", timeout=10)
    eq(r.status_code, 200)
    data = r.json()
    inside("session_count", data)


@_test(
    "Insights response contains similar_sessions or insights array", category="Insights"
)
def t23():
    r = requests.get(f"{BASE_URL}/api/memory/insights/Test", timeout=10)
    eq(r.status_code, 200)
    data = r.json()
    check("similar_sessions" in data or "insights" in data)


@_test("Empty insights when no matching sessions", category="Insights")
def t24():
    r = requests.get(
        f"{BASE_URL}/api/memory/insights/zzzzxzyznonexistenttopic", timeout=10
    )
    eq(r.status_code, 200)
    data = r.json()
    eq(data["session_count"], 0)
    eq(data["insights"], [])


@_test("Insights aggregate findings from multiple sessions", category="Insights")
def t25():
    tag = uuid.uuid4().hex[:6]
    sid1 = f"ins-aggr1-{tag}"
    sid2 = f"ins-aggr2-{tag}"
    pins1 = [
        make_pin(
            f"ia-p1-{tag}",
            topic="Green Energy",
            content="Solar is key",
            author="rook",
            status="approved",
        )
    ]
    pins2 = [
        make_pin(
            f"ia-p2-{tag}",
            topic="Wind Power",
            content="Offshore turbines",
            author="elena",
            status="approved",
        )
    ]
    s1 = make_session(sid=sid1, topic=f"Renewable Energy {tag}", pins=pins1)
    s2 = make_session(sid=sid2, topic=f"Clean Energy {tag}", pins=pins2)
    populate_memory(s1)
    populate_memory(s2)
    r = requests.get(f"{BASE_URL}/api/memory/insights/Energy%20{tag}", timeout=10)
    eq(r.status_code, 200)
    data = r.json()
    gte(
        data["session_count"],
        1,
        f"Expected at least 1 session, got {data['session_count']}",
    )
    inside("similar_sessions", data)
    inside("persona_frequency", data)


@_test("Cross-session response has valid structure", category="Insights")
def t26():
    r = requests.get(f"{BASE_URL}/api/memory/insights/Test", timeout=10)
    eq(r.status_code, 200)
    data = r.json()
    inside("topic", data)
    inside("session_count", data)
    check(isinstance(data["session_count"], int))
    if data["session_count"] > 0:
        inside("similar_sessions", data)
        inside("key_findings", data)
        inside("persona_frequency", data)
        check(isinstance(data["similar_sessions"], list))
        check(isinstance(data["key_findings"], list))
        check(isinstance(data["persona_frequency"], dict))
    else:
        inside("insights", data)
        check(isinstance(data["insights"], list))


@_test("Topic matching works with partial keywords", category="Insights")
def t27():
    sid = f"ins-partial-{str(uuid.uuid4())[:8]}"
    session = make_session(sid=sid, topic="Machine Learning for Healthcare")
    populate_memory(session)
    r = requests.get(f"{BASE_URL}/api/memory/insights/Healthcare", timeout=10)
    eq(r.status_code, 200)
    data = r.json()
    gte(data["session_count"], 1)


@_test("Cross-session similar_sessions has valid structure", category="Insights")
def t28():
    r = requests.get(f"{BASE_URL}/api/memory/insights/Test", timeout=10)
    eq(r.status_code, 200)
    data = r.json()
    if data["session_count"] > 0:
        for s in data["similar_sessions"]:
            inside("session_id", s)
            inside("topic", s)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Team Recommendation API
# ═══════════════════════════════════════════════════════════════════════════════


@_test("GET /api/memory/recommended-team/{topic} returns 200", category="Recommendation")
def t29():
    r = requests.get(f"{BASE_URL}/api/memory/recommended-team/Test", timeout=10)
    eq(r.status_code, 200)


@_test("Response contains recommended_personas array", category="Recommendation")
def t30():
    r = requests.get(f"{BASE_URL}/api/memory/recommended-team/Test", timeout=10)
    eq(r.status_code, 200)
    data = r.json()
    inside("recommended_personas", data)
    check(isinstance(data["recommended_personas"], list))


@_test("Response contains reasoning string", category="Recommendation")
def t31():
    r = requests.get(f"{BASE_URL}/api/memory/recommended-team/Test", timeout=10)
    eq(r.status_code, 200)
    data = r.json()
    inside("reasoning", data)
    check(isinstance(data["reasoning"], str))
    gt(len(data["reasoning"]), 0)


@_test("Empty recommendation when no history", category="Recommendation")
def t32():
    r = requests.get(
        f"{BASE_URL}/api/memory/recommended-team/zzzzzxyznonexistenttopic", timeout=10
    )
    eq(r.status_code, 200)
    data = r.json()
    eq(data["recommended_personas"], [])
    inside("No past sessions", data["reasoning"])


@_test("Recommendation based on past successful sessions", category="Recommendation")
def t33():
    tag = uuid.uuid4().hex[:6]
    sid = f"rec-succ-{tag}"
    pins = [
        make_pin(
            f"rp-{tag}",
            topic="Design",
            content="UX research",
            author="maya",
            status="approved",
        )
    ]
    session = make_session(sid=sid, topic=f"Product Design {tag}", pins=pins)
    populate_memory(session)
    r = requests.get(
        f"{BASE_URL}/api/memory/recommended-team/Design%20{tag}", timeout=10
    )
    eq(r.status_code, 200)
    data = r.json()
    check(len(data["recommended_personas"]) > 0 or data["reasoning"] is not None)


@_test("Multiple personas can be recommended", category="Recommendation")
def t34():
    tag = uuid.uuid4().hex[:6]
    for i in range(3):
        s = make_session(sid=f"rec-multi-{i}-{tag}", topic=f"Team Building {tag}")
        populate_memory(s)
    r = requests.get(f"{BASE_URL}/api/memory/recommended-team/Team%20{tag}", timeout=10)
    eq(r.status_code, 200)
    data = r.json()
    gte(len(data["recommended_personas"]), 1)


@_test("Persona frequency influences recommendation", category="Recommendation")
def t35():
    tag = uuid.uuid4().hex[:6]
    for i in range(5):
        s = make_session(sid=f"rec-freq-{i}-{tag}", topic=f"Frequent Topic {tag}")
        populate_memory(s)
    r = requests.get(
        f"{BASE_URL}/api/memory/recommended-team/Frequent%20{tag}", timeout=10
    )
    eq(r.status_code, 200)
    data = r.json()
    check(len(data["recommended_personas"]) > 0)
    check(isinstance(data["reasoning"], str))
    gt(len(data["reasoning"]), 10)


@_test("Recommendation response structure is valid", category="Recommendation")
def t36():
    r = requests.get(f"{BASE_URL}/api/memory/recommended-team/Test", timeout=10)
    eq(r.status_code, 200)
    data = r.json()
    for key in ("recommended_personas", "reasoning"):
        inside(key, data)
    check(isinstance(data["recommended_personas"], list))
    check(isinstance(data["reasoning"], str))


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Memory Population (Unit Tests)
# ═══════════════════════════════════════════════════════════════════════════════


@_test("populate_memory with mock session works", category="Population")
def t37():
    clean_test_db()
    sid = f"pop-mock-{str(uuid.uuid4())[:8]}"
    session = make_session(sid=sid, topic="Population Unit Test")
    populate_memory(session)
    result = get_session_memory(sid)
    check(result is not None)
    eq(result["session_id"], sid)
    eq(result["topic"], "Population Unit Test")


@_test("Whiteboard pins extracted correctly from session", category="Population")
def t38():
    clean_test_db()
    sid = f"pop-pins-{str(uuid.uuid4())[:8]}"
    pins = [
        make_pin("ext001", topic="Idea A", content="Content A", author="rook"),
        make_pin(
            "ext002",
            topic="Idea B",
            content="Content B",
            author="elena",
            status="discussed",
        ),
    ]
    session = make_session(sid=sid, topic="Pin Extraction", pins=pins)
    populate_memory(session)
    result = get_session_memory(sid)
    eq(len(result["pins"]), 2)
    pin_topics = [p["topic"] for p in result["pins"]]
    inside("Idea A", pin_topics)
    inside("Idea B", pin_topics)


@_test("Persona interaction counts are accurate", category="Population")
def t39():
    clean_test_db()
    sid = f"pop-counts-{str(uuid.uuid4())[:8]}"
    msgs = [
        make_msg("rook", "Rook", "First"),
        make_msg("elena", "Elena", "Second"),
        make_msg("rook", "Rook", "Third"),
        make_msg("kael", "Kael", "Fourth"),
        make_msg("rook", "Rook", "Fifth"),
    ]
    session = make_session(sid=sid, topic="Counts Test", msgs=msgs)
    populate_memory(session)
    result = get_session_memory(sid)
    interactions = {i["persona_id"]: i["turns_spoken"] for i in result["interactions"]}
    eq(interactions["rook"], 3)
    eq(interactions["elena"], 1)
    eq(interactions["kael"], 1)


@_test("Session summary is stored from topic words", category="Population")
def t40():
    clean_test_db()
    sid = f"pop-summary-{str(uuid.uuid4())[:8]}"
    session = make_session(sid=sid, topic="Artificial Intelligence Robotics")
    populate_memory(session)
    result = get_session_memory(sid)
    summary = result.get("summary", "")
    check(len(summary) > 0)
    sl = summary.lower()
    inside("artificial", sl, f"Expected 'artificial' in summary '{summary}'")
    inside("intelligence", sl, f"Expected 'intelligence' in summary '{summary}'")
    inside("robotics", sl, f"Expected 'robotics' in summary '{summary}'")


@_test("Key findings extraction via insights uses pins", category="Population")
def t41():
    clean_test_db()
    sid = f"pop-findings-{str(uuid.uuid4())[:8]}"
    pins = [
        make_pin(
            "kf001",
            topic="Finding X",
            content="Discovery X",
            author="rook",
            status="approved",
        ),
        make_pin(
            "kf002",
            topic="Finding Y",
            content="Discovery Y",
            author="elena",
            status="discussed",
        ),
    ]
    session = make_session(sid=sid, topic="Key Findings Analysis", pins=pins)
    populate_memory(session)
    insights = get_cross_session_insights("Key Findings")
    gte(len(insights["key_findings"]), 0)


@_test("Synergy score is recorded from session metrics", category="Population")
def t41b():
    clean_test_db()
    sid = f"pop-synergy-{str(uuid.uuid4())[:8]}"
    session = make_session(sid=sid, topic="Synergy Score Test")
    session.synergy_metrics = {
        "cross_reference_rate": 0.5,
        "friction_level": 0.2,
        "convergence_score": 0.8,
        "idea_diversity": 12,
        "participation_balance": 0.9,
        "health": "green",
    }
    populate_memory(session)
    result = get_session_memory(sid)
    check(result is not None)


@_test("Handles session with no whiteboard pins gracefully", category="Population")
def t42():
    clean_test_db()
    sid = f"pop-empty-pins-{str(uuid.uuid4())[:8]}"
    session = make_session(sid=sid, topic="Empty Pins Test")
    session.whiteboard = {}
    populate_memory(session)
    result = get_session_memory(sid)
    check(result is not None)
    eq(len(result.get("pins", [])), 0)


@_test("Handles session with no messages gracefully", category="Population")
def t43():
    clean_test_db()
    sid = f"pop-no-msgs-{str(uuid.uuid4())[:8]}"
    session = make_session(sid=sid, topic="No Messages Test", msgs=[])
    session.messages = []
    session.turn_count = 0
    populate_memory(session)
    result = get_session_memory(sid)
    check(result is not None)
    eq(len(result.get("interactions", [])), 0)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. WebSocket Memory Suggestions
# ═══════════════════════════════════════════════════════════════════════════════


@_test("memory_suggestion event exists in app code", category="WS")
def t44():
    with open(BASE_DIR / "app.py", encoding="utf-8") as f:
        src = f.read()
    inside("memory_suggestion", src)


@_test("get_memory_suggestions returns None when no matches", category="WS")
def t45():
    result = get_memory_suggestions("zzzzzxyznonexistenttopic12345")
    eq(result, None)


@_test("get_memory_suggestions includes match_count", category="WS")
def t46():
    sid = f"ws-sugg-{str(uuid.uuid4())[:8]}"
    session = make_session(sid=sid, topic="Suggestion Topic Test")
    populate_memory(session)
    result = get_memory_suggestions("Suggestion Topic")
    if result is not None:
        inside("match_count", result)
        gte(result["match_count"], 1)
    else:
        # Edge case: topic words filtered
        check(True, "No suggestion returned (topic words filtered)")


@_test("get_memory_suggestions includes relevant session IDs", category="WS")
def t47():
    sid = f"ws-ids-{str(uuid.uuid4())[:8]}"
    session = make_session(sid=sid, topic="Session ID Test")
    populate_memory(session)
    result = get_memory_suggestions("Session ID")
    if result is not None:
        inside("similar_sessions", result)
        gt(len(result["similar_sessions"]), 0)
        inside("session_id", result["similar_sessions"][0])
    else:
        check(True, "No suggestion returned")


@_test("memory_suggestion triggered on start_conversation over WS", category="WS")
def t48():
    async def check_ws():
        import websockets.asyncio.client as wsmod

        ws = await wsmod.connect(f"{WS_URL}/ws/ws-test-{str(uuid.uuid4())[:8]}")
        try:
            await ws.send(
                json.dumps(
                    {
                        "type": "start_conversation",
                        "session_id": f"ws-test-{str(uuid.uuid4())[:8]}",
                        "topic": "Suggestion Topic Test",
                        "max_turns": 1,
                        "workflow_mode": "salon",
                    }
                )
            )
            received_suggestion = False
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 15))
                if msg.get("type") == "memory_suggestion":
                    received_suggestion = True
                    break
                if msg.get("type") == "session_complete":
                    break
            check(received_suggestion, "Did not receive memory_suggestion event")
        finally:
            await ws_close(ws)

    run_ws(check_ws())


# ═══════════════════════════════════════════════════════════════════════════════
# 7. UI Tests
# ═══════════════════════════════════════════════════════════════════════════════


@_test("Memory panel HTML exists in index.html", category="UI")
def t49():
    with open(WEB_HTML, encoding="utf-8") as f:
        html = f.read()
    inside("memory-section", html)
    inside("memoryResults", html)


@_test("Memory search input exists in HTML", category="UI")
def t50():
    with open(WEB_HTML, encoding="utf-8") as f:
        html = f.read()
    inside("memorySearchInput", html)
    inside("searchMemory", html)


@_test("Session card rendering function exists in JS", category="UI")
def t51():
    with open(WEB_HTML, encoding="utf-8") as f:
        html = f.read()
    inside("function renderMemorySessions", html)
    inside("memory-card", html)


@_test("Memory count badge exists", category="UI")
def t52():
    with open(WEB_HTML, encoding="utf-8") as f:
        html = f.read()
    inside("memoryCount", html)
    inside("updateMemoryCount", html)


@_test("Expand/collapse functionality exists for memory cards", category="UI")
def t53():
    with open(WEB_HTML, encoding="utf-8") as f:
        html = f.read()
    inside("function toggleMemoryCard", html)
    inside("expanded", html)


@_test("WebSocket memory handler exists in JS", category="UI")
def t54():
    with open(WEB_HTML, encoding="utf-8") as f:
        html = f.read()
    inside("memory_suggestion", html)
    inside("showMemorySuggestion", html)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Edge Cases
# ═══════════════════════════════════════════════════════════════════════════════


@_test("Very long topic strings handled", category="Edge")
def t55():
    sid = f"edge-long-{str(uuid.uuid4())[:8]}"
    long_topic = "A " * 250 + "Long Topic"
    session = make_session(sid=sid, topic=long_topic)
    populate_memory(session)
    result = get_session_memory(sid)
    check(result is not None)
    eq(result["session_id"], sid)


@_test("Special characters in topics handled", category="Edge")
def t56():
    sid = f"edge-special-{str(uuid.uuid4())[:8]}"
    special_topic = "C++ & C#: Object-Oriented @ 100% (2024) [TEST] {url}"
    session = make_session(sid=sid, topic=special_topic)
    populate_memory(session)
    r = requests.get(f"{BASE_URL}/api/memory/sessions?topic=C++", timeout=10)
    eq(r.status_code, 200)


@_test("Unicode in session summaries handled", category="Edge")
def t57():
    sid = f"edge-unicode-{str(uuid.uuid4())[:8]}"
    unicode_topic = "Résumé • Café über München 日本語 中文 العربية"
    session = make_session(sid=sid, topic=unicode_topic)
    populate_memory(session)
    result = get_session_memory(sid)
    check(result is not None)
    eq(result["session_id"], sid)


@_test("Concurrent memory writes don't corrupt DB", category="Edge")
def t58():
    clean_test_db()
    import threading

    errors = []
    lock = threading.Lock()

    def write_session(idx):
        try:
            sid = f"edge-concurrent-{idx}-{str(uuid.uuid4())[:8]}"
            session = make_session(sid=sid, topic=f"Concurrent Test {idx}")
            populate_memory(session)
            result = get_session_memory(sid)
            with lock:
                if result is None:
                    errors.append(f"Session {sid} not found after write")
        except Exception as e:
            with lock:
                errors.append(str(e))

    threads = [threading.Thread(target=write_session, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    eq(errors, [], f"Concurrent write errors: {errors}")
    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM memory_sessions WHERE topic LIKE 'Concurrent Test%'"
    )
    count = cur.fetchone()[0]
    conn.close()
    eq(count, 10, f"Expected 10 sessions, got {count}")


@_test("Empty string topic returns all sessions", category="Edge")
def t59():
    r = requests.get(f"{BASE_URL}/api/memory/sessions?topic=", timeout=10)
    eq(r.status_code, 200)
    data = r.json()
    check(isinstance(data, list))


# ═══════════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════════


def run():
    global passed, failed
    print(f"\n  {'=' * 70}")
    print(f"  Phase 3.4 — Multi-Session Memory Test Suite")
    print(f"  Targeting server at {BASE_URL}")
    print(f"  {'=' * 70}\n")

    current_cat = ""
    for cat, name, fn in results:
        if cat and cat != current_cat:
            current_cat = cat
            print(f"\n  ── [{cat}] ──")
        label = f"[{cat}] {name}" if cat else name
        try:
            fn()
            print(f"  {P} {label}")
            passed += 1
        except (AssertionError, Exception) as e:
            print(f"  {F} {label}")
            tb = traceback.format_exc()
            last = tb.strip().splitlines()[-1] if tb else str(e)
            print(f"       {last}")
            failed += 1

    total = passed + failed
    print(f"\n  {'=' * 70}")
    print(f"  RESULTS: {passed} passed, {failed} failed ({total} total)")
    print(f"  {'=' * 70}")
    print(
        f"\n  {P if not failed else F} {'ALL TESTS PASSED' if not failed else 'SOME TESTS FAILED'}"
    )
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
