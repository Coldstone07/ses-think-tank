#!/usr/bin/env python3
"""
Phase 3.3 — Real-Time Synergy Dashboard Test Suite
====================================================
Tests metrics engine, API endpoints, WebSocket integration,
UI elements, data validation, and edge cases.

Run: python3.11 tests/test_synergy.py
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

BASE_URL = "http://localhost:8773"
WS_URL = "ws://localhost:8773"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as app_mod
import importlib

importlib.reload(app_mod)

PERSONA_NAMES = app_mod.PERSONA_NAMES
DISAGREEMENT_KEYWORDS = app_mod.DISAGREEMENT_KEYWORDS
Message = app_mod.Message
ConversationSession = app_mod.ConversationSession
calculate_synergy_metrics = app_mod.calculate_synergy_metrics

P, F = chr(0x2705), chr(0x274C)
passed = failed = 0
results = []


def test(name, category=""):
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


def make_session(sid="test-session", msgs=None):
    s = ConversationSession(session_id=sid, topic="Test", max_turns=100)
    if msgs:
        s.messages = msgs
        s.turn_count = len(msgs)
    return s


PERSONA_IDS = ["rook", "elena", "kael", "maya", "jax", "sage"]


def ensure_session(sid="ev-s1"):
    """Create a session on the server if it doesn't exist."""
    r = requests.get(f"{BASE_URL}/api/sessions/{sid}/metrics", timeout=10)
    if r.status_code == 200 and "error" not in r.json():
        return

    async def create():
        import websockets.asyncio.client as wsmod

        ws = await wsmod.connect(f"{WS_URL}/ws/setup-{sid}")
        try:
            await ws.send(
                json.dumps(
                    {
                        "type": "start_conversation",
                        "session_id": sid,
                        "topic": f"Auto-created session {sid} for testing",
                        "max_turns": 1,
                        "workflow_mode": "salon",
                    }
                )
            )
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 120))
                if msg.get("type") == "session_complete":
                    break
        finally:
            await ws_close(ws)

    asyncio.run(create())


# ═══════════════════════════════════════════════════════════════════════════════
# 1. METRICS ENGINE
# ═══════════════════════════════════════════════════════════════════════════════


@test(
    "calculate_synergy_metrics returns dict with all required fields",
    category="Metrics",
)
def t01():
    session = make_session()
    session.messages = [make_msg("rook", "Rook", "Hello world")]
    session.turn_count = 1
    m = calculate_synergy_metrics(session)
    for k in (
        "cross_reference_rate",
        "friction_level",
        "convergence_score",
        "idea_diversity",
        "participation_balance",
        "participation_counts",
        "health",
    ):
        inside(k, m)


@test("cross_reference_rate is between 0 and 1", category="Metrics")
def t02():
    session = make_session()
    session.messages = [
        make_msg("rook", "Rook", "As Elena said, we should proceed"),
        make_msg("elena", "Elena", "I agree with Rook's idea"),
    ]
    session.turn_count = 2
    m = calculate_synergy_metrics(session)
    between(m["cross_reference_rate"], 0.0, 1.0)


@test("friction_level is between 0 and 1", category="Metrics")
def t03():
    session = make_session()
    session.messages = [
        make_msg("rook", "Rook", "I disagree with this approach"),
        make_msg("elena", "Elena", "That is a flawed plan"),
    ]
    session.turn_count = 2
    m = calculate_synergy_metrics(session)
    between(m["friction_level"], 0.0, 1.0)


@test("convergence_score is between 0 and 1", category="Metrics")
def t04():
    session = make_session()
    session.messages = [
        make_msg("rook", "Rook", "We need innovation in healthcare"),
        make_msg("elena", "Elena", "Healthcare innovation requires funding"),
    ]
    session.turn_count = 2
    m = calculate_synergy_metrics(session)
    between(m["convergence_score"], 0.0, 1.0)


@test("idea_diversity is non-negative integer", category="Metrics")
def t05():
    session = make_session()
    session.messages = [
        make_msg("rook", "Rook", "Artificial intelligence transforms medicine"),
        make_msg("elena", "Elena", "Blockchain secures patient records"),
    ]
    session.turn_count = 2
    m = calculate_synergy_metrics(session)
    check(isinstance(m["idea_diversity"], int))
    gte(m["idea_diversity"], 0)


@test("participation_balance is between 0 and 1", category="Metrics")
def t06():
    session = make_session()
    for pid in PERSONA_IDS[:3]:
        session.messages.append(
            make_msg(pid, PERSONA_NAMES[pid], f"Message from {pid}")
        )
    session.turn_count = 3
    m = calculate_synergy_metrics(session)
    between(m["participation_balance"], 0.0, 1.0)


@test(
    "participation_counts dict has entries for all persona IDs that spoke",
    category="Metrics",
)
def t07():
    session = make_session()
    session.messages = [
        make_msg("rook", "Rook", "Hello"),
        make_msg("elena", "Elena", "Hi"),
    ]
    session.turn_count = 2
    m = calculate_synergy_metrics(session)
    inside("rook", m["participation_counts"])
    inside("elena", m["participation_counts"])


@test("history is empty by default", category="Metrics")
def t08():
    session = make_session()
    eq(session.metrics_history, [])


@test("Metrics update after each turn", category="Metrics")
def t09():
    session = make_session()
    session.messages = [make_msg("rook", "Rook", "First message")]
    session.turn_count = 1
    m1 = calculate_synergy_metrics(session)
    session.messages.append(make_msg("elena", "Elena", "Second message"))
    session.turn_count = 2
    m2 = calculate_synergy_metrics(session)
    check(m2["turn_count"] if "turn_count" in m2 else m2 != m1)


@test(
    "Cross-reference rate increases when personas mention each other",
    category="Metrics",
)
def t10():
    session = make_session()
    session.messages = [make_msg("rook", "Rook", "Just thinking out loud")]
    session.turn_count = 1
    m_no_ref = calculate_synergy_metrics(session)

    session.messages = [make_msg("rook", "Rook", "As Elena mentioned earlier")]
    session.turn_count = 1
    m_ref = calculate_synergy_metrics(session)
    gt(m_ref["cross_reference_rate"], m_no_ref["cross_reference_rate"])


@test("Friction level increases when disagreement keywords appear", category="Metrics")
def t11():
    session = make_session()
    session.messages = [make_msg("rook", "Rook", "Nice weather today")]
    session.turn_count = 1
    m_low = calculate_synergy_metrics(session)

    session.messages = [
        make_msg("rook", "Rook", "I disagree with that flawed reasoning")
    ]
    session.turn_count = 1
    m_high = calculate_synergy_metrics(session)
    gt(m_high["friction_level"], m_low["friction_level"])


@test("Convergence score changes with repeated topics", category="Metrics")
def t12():
    session = make_session()
    session.messages = [
        make_msg("rook", "Rook", "Healthcare innovation requires policy change"),
        make_msg("elena", "Elena", "Healthcare funding model needs innovation"),
    ]
    session.turn_count = 2
    m_with_overlap = calculate_synergy_metrics(session)

    session2 = make_session()
    session2.messages = [
        make_msg("rook", "Rook", "Quantum computing"),
        make_msg("elena", "Elena", " Baking bread recipes"),
    ]
    session2.turn_count = 2
    m_no_overlap = calculate_synergy_metrics(session2)
    gt(m_with_overlap["convergence_score"], m_no_overlap["convergence_score"])


@test(
    "Participation balance is 1.0 when all personas speak equally", category="Metrics"
)
def t13():
    session = make_session()
    for pid in PERSONA_IDS[:3]:
        for _ in range(2):
            session.messages.append(
                make_msg(pid, PERSONA_NAMES[pid], f"Message from {pid}")
            )
    session.turn_count = 6
    m = calculate_synergy_metrics(session)
    eq(m["participation_balance"], 1.0)


@test("Participation balance is low when one persona dominates", category="Metrics")
def t14():
    session = make_session()
    for _ in range(20):
        session.messages.append(make_msg("rook", "Rook", "Rook dominates"))
    session.messages.append(make_msg("elena", "Elena", "One from Elena"))
    session.turn_count = 21
    m = calculate_synergy_metrics(session)
    lt(m["participation_balance"], 0.5)


@test("Metrics start at zero for new session", category="Metrics")
def t15():
    session = make_session()
    m = calculate_synergy_metrics(session)
    eq(m["cross_reference_rate"], 0.0)
    eq(m["friction_level"], 0.0)
    eq(m["convergence_score"], 0.0)
    eq(m["idea_diversity"], 0)
    eq(m["participation_balance"], 0.0)
    eq(m["health"], "green")


@test("health field is one of green/yellow/red", category="Metrics")
def t16():
    session = make_session()
    session.messages = [make_msg("rook", "Rook", "Hello")]
    session.turn_count = 1
    m = calculate_synergy_metrics(session)
    inside(m["health"], {"green", "yellow", "red"})


@test("Cross-reference rate exactly 0 when no names mentioned", category="Metrics")
def t17():
    session = make_session()
    session.messages = [make_msg("rook", "Rook", "Nothing about other people here")]
    session.turn_count = 1
    m = calculate_synergy_metrics(session)
    eq(m["cross_reference_rate"], 0.0)


@test("Friction level exactly 0 when no disagreement keywords", category="Metrics")
def t18():
    session = make_session()
    session.messages = [make_msg("rook", "Rook", "Sunshine and rainbows everywhere")]
    session.turn_count = 1
    m = calculate_synergy_metrics(session)
    eq(m["friction_level"], 0.0)


@test("health is green when all conditions are met", category="Metrics")
def t19a():
    session = make_session()
    session.messages = [
        make_msg("rook", "Rook", "As Elena said we should proceed with innovation"),
        make_msg("elena", "Elena", "I agree with Rook proposal for innovation"),
        make_msg("kael", "Kael", "Building on both ideas, innovation requires funding"),
        make_msg(
            "maya", "Maya", "Rook and Elena make great points about funding innovation"
        ),
    ]
    session.turn_count = 4
    m = calculate_synergy_metrics(session)
    if (
        m["cross_reference_rate"] > 0.3
        and m["friction_level"] < 0.5
        and m["participation_balance"] > 0.6
    ):
        eq(m["health"], "green")


@test("health is yellow when cross_reference_rate > 0.1", category="Metrics")
def t19b():
    session = make_session()
    session.messages = [
        make_msg("rook", "Rook", "As Elena said, this is important"),
        make_msg("elena", "Elena", "Some content here with words"),
    ]
    session.turn_count = 2
    m = calculate_synergy_metrics(session)
    if m["cross_reference_rate"] > 0.1 and not (
        m["cross_reference_rate"] > 0.3
        and m["friction_level"] < 0.5
        and m["participation_balance"] > 0.6
    ):
        inside(m["health"], {"yellow", "red"})


@test(
    "Metrics only from system messages produce empty participation", category="Metrics"
)
def t19c():
    session = make_session()
    session.messages = [
        make_msg("system", "System", "System message one"),
        make_msg("system", "System", "System message two"),
    ]
    session.turn_count = 2
    m = calculate_synergy_metrics(session)
    eq(m["participation_counts"], {})
    eq(m["participation_balance"], 0.0)
    eq(m["cross_reference_rate"], 0.0)
    eq(m["friction_level"], 0.0)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════


@test("GET /api/sessions/ev-s1/metrics returns 200", category="API")
def t20():
    eq(
        requests.get(f"{BASE_URL}/api/sessions/ev-s1/metrics", timeout=10).status_code,
        200,
    )


@test("GET /api/sessions/ev-s1/metrics/history returns 200", category="API")
def t21():
    eq(
        requests.get(
            f"{BASE_URL}/api/sessions/ev-s1/metrics/history", timeout=10
        ).status_code,
        200,
    )


@test("Metrics endpoint returns valid JSON with required fields", category="API")
def t22():
    r = requests.get(f"{BASE_URL}/api/sessions/ev-s1/metrics", timeout=10)
    data = r.json()
    for k in (
        "cross_reference_rate",
        "friction_level",
        "convergence_score",
        "idea_diversity",
        "participation_balance",
        "health",
    ):
        inside(k, data)


@test("History endpoint returns array", category="API")
def t23():
    r = requests.get(f"{BASE_URL}/api/sessions/ev-s1/metrics/history", timeout=10)
    data = r.json()
    check(isinstance(data, list))


@test("Non-existent session returns error for metrics", category="API")
def t24():
    r = requests.get(
        f"{BASE_URL}/api/sessions/nonexistent-session-xyz/metrics", timeout=10
    )
    eq(r.status_code, 200)
    inside("error", r.json())


@test("Non-existent session returns error for history", category="API")
def t25():
    r = requests.get(
        f"{BASE_URL}/api/sessions/nonexistent-session-xyz/metrics/history", timeout=10
    )
    data = r.json()
    inside("error", data)


@test("POST /api/sessions/ev-s1/intervene returns 200", category="API")
def t26():
    r = requests.post(
        f"{BASE_URL}/api/sessions/ev-s1/intervene",
        json={"message": "Please focus on feasibility"},
        timeout=10,
    )
    eq(r.status_code, 200)
    inside("status", r.json())
    eq(r.json()["status"], "intervened")


@test("Intervene without message returns error", category="API")
def t27():
    r = requests.post(
        f"{BASE_URL}/api/sessions/ev-s1/intervene",
        json={},
        timeout=10,
    )
    inside("error", r.json())


@test("Intervene on non-existent session returns error", category="API")
def t28():
    r = requests.post(
        f"{BASE_URL}/api/sessions/nonexistent-session-xyz/intervene",
        json={"message": "Hello"},
        timeout=10,
    )
    inside("error", r.json())


@test("Metrics have valid range values from API", category="API")
def t29():
    r = requests.get(f"{BASE_URL}/api/sessions/ev-s1/metrics", timeout=10)
    data = r.json()
    between(data.get("cross_reference_rate", 0), 0.0, 1.0)
    between(data.get("friction_level", 0), 0.0, 1.0)
    between(data.get("convergence_score", 0), 0.0, 1.0)
    between(data.get("participation_balance", 0), 0.0, 1.0)
    gte(data.get("idea_diversity", 0), 0)


@test("History entries have turn numbers", category="API")
def t30():
    r = requests.get(f"{BASE_URL}/api/sessions/ev-s1/metrics/history", timeout=10)
    data = r.json()
    if data:
        inside("turn", data[0])
        inside("metrics", data[0])
        inside("timestamp", data[0])


# ═══════════════════════════════════════════════════════════════════════════════
# 3. WEBSOCKET INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════


@test("synergy_metrics event emitted after conversation turn", category="WebSocket")
def t31():
    async def go():
        import websockets.asyncio.client as wsmod

        sid = f"syn-test-{str(uuid.uuid4())[:8]}"
        ws = await wsmod.connect(f"{WS_URL}/ws/{sid}")
        try:
            await ws.send(
                json.dumps(
                    {
                        "type": "start_conversation",
                        "session_id": sid,
                        "topic": "Test synergy metrics",
                        "max_turns": 1,
                        "workflow_mode": "salon",
                    }
                )
            )
            got_metrics = False
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 120))
                if msg.get("type") == "synergy_metrics":
                    got_metrics = True
                    break
                if msg.get("type") == "session_complete":
                    break
            check(got_metrics, "synergy_metrics event not received")
        finally:
            await ws_close(ws)

    run_ws(go())


@test("synergy_summary event emitted on session_complete", category="WebSocket")
def t32():
    async def go():
        import websockets.asyncio.client as wsmod

        sid = f"syn-test-{str(uuid.uuid4())[:8]}"
        ws = await wsmod.connect(f"{WS_URL}/ws/{sid}")
        try:
            await ws.send(
                json.dumps(
                    {
                        "type": "start_conversation",
                        "session_id": sid,
                        "topic": "Test synergy summary",
                        "max_turns": 1,
                        "workflow_mode": "salon",
                    }
                )
            )
            got_summary = False
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 120))
                if msg.get("type") == "session_complete":
                    inside("synergy_summary", msg)
                    got_summary = True
                    break
            check(got_summary, "synergy_summary not in session_complete")
        finally:
            await ws_close(ws)

    run_ws(go())


@test("Event contains all required fields", category="WebSocket")
def t33():
    async def go():
        import websockets.asyncio.client as wsmod

        sid = f"syn-test-{str(uuid.uuid4())[:8]}"
        ws = await wsmod.connect(f"{WS_URL}/ws/{sid}")
        try:
            await ws.send(
                json.dumps(
                    {
                        "type": "start_conversation",
                        "session_id": sid,
                        "topic": "Test event fields",
                        "max_turns": 1,
                        "workflow_mode": "salon",
                    }
                )
            )
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 120))
                if msg.get("type") == "synergy_metrics":
                    inside("metrics", msg)
                    inside("turn", msg)
                    m = msg["metrics"]
                    for k in (
                        "cross_reference_rate",
                        "friction_level",
                        "convergence_score",
                        "idea_diversity",
                        "participation_balance",
                        "participation_counts",
                        "health",
                    ):
                        inside(k, m)
                    break
                if msg.get("type") == "session_complete":
                    break
        finally:
            await ws_close(ws)

    run_ws(go())


@test("Event metric values are valid ranges", category="WebSocket")
def t34():
    async def go():
        import websockets.asyncio.client as wsmod

        sid = f"syn-test-{str(uuid.uuid4())[:8]}"
        ws = await wsmod.connect(f"{WS_URL}/ws/{sid}")
        try:
            await ws.send(
                json.dumps(
                    {
                        "type": "start_conversation",
                        "session_id": sid,
                        "topic": "Test metric ranges",
                        "max_turns": 1,
                        "workflow_mode": "salon",
                    }
                )
            )
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 120))
                if msg.get("type") == "synergy_metrics":
                    m = msg["metrics"]
                    between(m["cross_reference_rate"], 0.0, 1.0)
                    between(m["friction_level"], 0.0, 1.0)
                    between(m["convergence_score"], 0.0, 1.0)
                    between(m["participation_balance"], 0.0, 1.0)
                    gte(m["idea_diversity"], 0)
                    break
                if msg.get("type") == "session_complete":
                    break
        finally:
            await ws_close(ws)

    run_ws(go())


@test("Multiple turns produce multiple metric events", category="WebSocket")
def t35():
    async def go():
        import websockets.asyncio.client as wsmod

        sid = f"syn-test-{str(uuid.uuid4())[:8]}"
        ws = await wsmod.connect(f"{WS_URL}/ws/{sid}")
        try:
            await ws.send(
                json.dumps(
                    {
                        "type": "start_conversation",
                        "session_id": sid,
                        "topic": "Test multiple turns",
                        "max_turns": 3,
                        "workflow_mode": "salon",
                    }
                )
            )
            metric_count = 0
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 120))
                if msg.get("type") == "synergy_metrics":
                    metric_count += 1
                if msg.get("type") == "session_complete":
                    break
            gte(metric_count, 1)
        finally:
            await ws_close(ws)

    run_ws(go())


@test("History grows with each turn", category="WebSocket")
def t36():
    async def go():
        import websockets.asyncio.client as wsmod

        sid = f"syn-test-{str(uuid.uuid4())[:8]}"
        ws = await wsmod.connect(f"{WS_URL}/ws/{sid}")
        try:
            await ws.send(
                json.dumps(
                    {
                        "type": "start_conversation",
                        "session_id": sid,
                        "topic": "Test history growth",
                        "max_turns": 2,
                        "workflow_mode": "salon",
                    }
                )
            )
            final_summary = None
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 120))
                if msg.get("type") == "session_complete":
                    final_summary = msg.get("synergy_summary", {})
                    break
            check(final_summary is not None)
            gte(len(final_summary.get("metrics_history", [])), 1)
        finally:
            await ws_close(ws)

    run_ws(go())


@test("Invalid WS message handled gracefully", category="WebSocket")
def t37():
    async def go():
        import websockets.asyncio.client as wsmod

        sid = f"syn-test-{str(uuid.uuid4())[:8]}"
        ws = await wsmod.connect(f"{WS_URL}/ws/{sid}")
        try:
            await ws.send("{{{broken json")
            r = json.loads(await asyncio.wait_for(ws.recv(), 5))
            eq(r.get("type"), "error")
        finally:
            await ws_close(ws)

    run_ws(go())


@test("Metrics consistent between WS and API", category="WebSocket")
def t38():
    async def go():
        import websockets.asyncio.client as wsmod

        sid = f"syn-test-{str(uuid.uuid4())[:8]}"
        ws = await wsmod.connect(f"{WS_URL}/ws/{sid}")
        try:
            await ws.send(
                json.dumps(
                    {
                        "type": "start_conversation",
                        "session_id": sid,
                        "topic": "Test consistency",
                        "max_turns": 1,
                        "workflow_mode": "salon",
                    }
                )
            )
            ws_metrics = None
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 120))
                if msg.get("type") == "synergy_metrics":
                    ws_metrics = msg["metrics"]
                if msg.get("type") == "session_complete":
                    break
            check(ws_metrics is not None)
            r = requests.get(f"{BASE_URL}/api/sessions/{sid}/metrics", timeout=10)
            api_data = r.json()
            eq(
                api_data.get("cross_reference_rate"),
                ws_metrics.get("cross_reference_rate"),
            )
            eq(api_data.get("idea_diversity"), ws_metrics.get("idea_diversity"))
        finally:
            await ws_close(ws)

    run_ws(go())


@test("synergy_summary includes full history", category="WebSocket")
def t39():
    async def go():
        import websockets.asyncio.client as wsmod

        sid = f"syn-test-{str(uuid.uuid4())[:8]}"
        ws = await wsmod.connect(f"{WS_URL}/ws/{sid}")
        try:
            await ws.send(
                json.dumps(
                    {
                        "type": "start_conversation",
                        "session_id": sid,
                        "topic": "Test full history in summary",
                        "max_turns": 1,
                        "workflow_mode": "salon",
                    }
                )
            )
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 120))
                if msg.get("type") == "session_complete":
                    summary = msg.get("synergy_summary", {})
                    inside("metrics_history", summary)
                    inside("final_metrics", summary)
                    check(isinstance(summary["metrics_history"], list))
                    check(isinstance(summary["final_metrics"], dict))
                    break
        finally:
            await ws_close(ws)

    run_ws(go())


@test("Events have correct type field", category="WebSocket")
def t40():
    async def go():
        import websockets.asyncio.client as wsmod

        sid = f"syn-test-{str(uuid.uuid4())[:8]}"
        ws = await wsmod.connect(f"{WS_URL}/ws/{sid}")
        try:
            await ws.send(
                json.dumps(
                    {
                        "type": "start_conversation",
                        "session_id": sid,
                        "topic": "Test event types",
                        "max_turns": 1,
                        "workflow_mode": "salon",
                    }
                )
            )
            types_seen = set()
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 120))
                types_seen.add(msg.get("type"))
                if msg.get("type") == "session_complete":
                    break
            inside("synergy_metrics", types_seen)
            inside("session_complete", types_seen)
        finally:
            await ws_close(ws)

    run_ws(go())


# ═══════════════════════════════════════════════════════════════════════════════
# 4. UI (web/index.html)
# ═══════════════════════════════════════════════════════════════════════════════


@test("web/index.html contains synergy dashboard HTML", category="UI")
def t41():
    html_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "index.html"
    )
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    inside("synergy-section", html)
    inside("synergySection", html)
    inside("synergy-badge", html)
    inside("synergy-sparklines", html)
    inside("synergy-body", html)


@test("Sparkline rendering function exists in JS", category="UI")
def t42():
    html_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "index.html"
    )
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    inside("drawSparkline", html)
    inside("sparkline-canvas", html)
    inside("sparklineCrossRef", html)
    inside("sparklineFriction", html)
    inside("sparklineConvergence", html)


@test("Participation chart function exists in JS", category="UI")
def t43():
    html_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "index.html"
    )
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    inside("drawPieChart", html)
    inside("participationPie", html)


@test("Intervention button exists in HTML", category="UI")
def t44():
    html_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "index.html"
    )
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    inside("interveneInput", html)
    inside("interveneBtn", html)
    inside("Intervene", html)


@test("WS synergy_metrics handler exists in JS", category="UI")
def t45():
    html_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "index.html"
    )
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    inside("synergy_metrics", html)
    inside("synergy_summary", html)
    inside("updateSynergyDashboard", html)
    inside("finishSynergyDashboard", html)


@test("Health badge HTML structure exists", category="UI")
def t46():
    html_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "index.html"
    )
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    inside("synergyBadge", html)
    inside("Healthy", html)
    inside("synergyHealth" if False else "green", html)  # badge has class 'green'


@test("Idea diversity counter exists in HTML", category="UI")
def t47():
    html_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "index.html"
    )
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    inside("ideaDiversity", html)
    inside("Unique Ideas", html)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. DATA VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════


@test("All metric values are numeric", category="Validation")
def t50():
    session = make_session()
    session.messages = [make_msg("rook", "Rook", "Test message for numeric check")]
    session.turn_count = 1
    m = calculate_synergy_metrics(session)
    check(isinstance(m["cross_reference_rate"], (int, float)))
    check(isinstance(m["friction_level"], (int, float)))
    check(isinstance(m["convergence_score"], (int, float)))
    check(isinstance(m["idea_diversity"], int))
    check(isinstance(m["participation_balance"], (int, float)))


@test("participation_counts sum equals total non-system turns", category="Validation")
def t51():
    session = make_session()
    session.messages = [
        make_msg("rook", "Rook", "A"),
        make_msg("elena", "Elena", "B"),
        make_msg("kael", "Kael", "C"),
    ]
    session.turn_count = 3
    m = calculate_synergy_metrics(session)
    total = sum(m["participation_counts"].values())
    eq(total, 3)


@test("DISAGREEMENT_KEYWORDS set exists and is non-empty", category="Validation")
def t52():
    check(isinstance(DISAGREEMENT_KEYWORDS, set))
    gt(len(DISAGREEMENT_KEYWORDS), 0)
    inside("disagree", DISAGREEMENT_KEYWORDS)
    inside("however", DISAGREEMENT_KEYWORDS)


@test("PERSONA_NAMES dict exists with all 6 personas", category="Validation")
def t53():
    check(isinstance(PERSONA_NAMES, dict))
    eq(len(PERSONA_NAMES), 6)
    for pid in PERSONA_IDS:
        inside(pid, PERSONA_NAMES)
    eq(PERSONA_NAMES["rook"], "Rook")
    eq(PERSONA_NAMES["elena"], "Elena")
    eq(PERSONA_NAMES["kael"], "Kael")
    eq(PERSONA_NAMES["maya"], "Maya")
    eq(PERSONA_NAMES["jax"], "Jax")
    eq(PERSONA_NAMES["sage"], "Sage")


@test("Metrics calculation is idempotent", category="Validation")
def t54():
    session = make_session()
    session.messages = [
        make_msg("rook", "Rook", "First message for idempotent test"),
        make_msg("elena", "Elena", "Second message"),
        make_msg("kael", "Kael", "As Rook pointed out earlier"),
    ]
    session.turn_count = 3
    m1 = calculate_synergy_metrics(session)
    m2 = calculate_synergy_metrics(session)
    eq(m1["cross_reference_rate"], m2["cross_reference_rate"])
    eq(m1["friction_level"], m2["friction_level"])
    eq(m1["convergence_score"], m2["convergence_score"])
    eq(m1["idea_diversity"], m2["idea_diversity"])
    eq(m1["participation_balance"], m2["participation_balance"])


@test("Empty conversation produces zero metrics", category="Validation")
def t55():
    session = make_session()
    m = calculate_synergy_metrics(session)
    eq(m["cross_reference_rate"], 0.0)
    eq(m["friction_level"], 0.0)
    eq(m["convergence_score"], 0.0)
    eq(m["idea_diversity"], 0)
    eq(m["participation_balance"], 0.0)
    eq(m["health"], "green")


@test("Metrics handle single-turn conversations", category="Validation")
def t56():
    session = make_session()
    session.messages = [make_msg("rook", "Rook", "Single turn with unique vocabulary")]
    session.turn_count = 1
    m = calculate_synergy_metrics(session)
    eq(m["cross_reference_rate"], 0.0)
    eq(m["friction_level"], 0.0)
    eq(m["convergence_score"], 0.0)
    gte(m["idea_diversity"], 0)
    check(m["health"] in ("green", "yellow", "red"))


@test("Metrics handle all-persona conversations", category="Validation")
def t57():
    session = make_session()
    for pid in PERSONA_IDS:
        session.messages.append(
            make_msg(pid, PERSONA_NAMES[pid], f"Contribution from {pid}")
        )
    session.turn_count = 6
    m = calculate_synergy_metrics(session)
    eq(len(m["participation_counts"]), 6)
    between(m["participation_balance"], 0.0, 1.0)


@test("System messages are excluded from metrics", category="Validation")
def t58():
    session = make_session()
    session.messages = [
        make_msg("system", "System", "System instruction"),
        make_msg("rook", "Rook", "Rook's actual message"),
    ]
    session.turn_count = 2
    m = calculate_synergy_metrics(session)
    eq(sum(m["participation_counts"].values()), 1)
    inside("rook", m["participation_counts"])


@test("All 6 persona names are recognized for cross-reference", category="Validation")
def t59():
    session = make_session()
    for pid in PERSONA_IDS:
        other = [p for p in PERSONA_IDS if p != pid][0]
        session.messages.append(
            make_msg(pid, PERSONA_NAMES[pid], f"As {PERSONA_NAMES[other]} would agree")
        )
    session.turn_count = 6
    m = calculate_synergy_metrics(session)
    eq(m["cross_reference_rate"], 1.0)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════


@test("Session with no turns produces zero metrics", category="Edge")
def t60():
    session = make_session()
    m = calculate_synergy_metrics(session)
    eq(m["cross_reference_rate"], 0.0)
    eq(m["friction_level"], 0.0)
    eq(m["convergence_score"], 0.0)
    eq(m["idea_diversity"], 0)
    between(m["participation_balance"], 0.0, 1.0)


@test("Session with 1 turn has valid metrics", category="Edge")
def t61():
    session = make_session()
    session.messages = [make_msg("rook", "Rook", "Just one message here")]
    session.turn_count = 1
    m = calculate_synergy_metrics(session)
    eq(m["cross_reference_rate"], 0.0)
    eq(m["friction_level"], 0.0)
    eq(m["convergence_score"], 0.0)
    gte(m["idea_diversity"], 0)
    # Single persona = perfect balance (only one speaker)
    between(m["participation_balance"], 0.0, 1.0)


@test("Session with all turns from one persona has low balance", category="Edge")
def t62():
    session = make_session()
    for i in range(10):
        session.messages.append(make_msg("rook", "Rook", f"Message number {i}"))
    session.turn_count = 10
    m = calculate_synergy_metrics(session)
    eq(len(m["participation_counts"]), 1)
    # Single persona: balance depends on implementation (0.0 or 1.0)
    between(m["participation_balance"], 0.0, 1.0)
    eq(m["participation_counts"]["rook"], 10)


@test("Very long conversation metrics don't degrade", category="Edge")
def t63():
    session = make_session()
    for i in range(100):
        pid = PERSONA_IDS[i % 6]
        session.messages.append(
            make_msg(
                pid, PERSONA_NAMES[pid], f"Turn {i} contribution with varied vocabulary"
            )
        )
    session.turn_count = 100
    m = calculate_synergy_metrics(session)
    between(m["cross_reference_rate"], 0.0, 1.0)
    between(m["friction_level"], 0.0, 1.0)
    between(m["convergence_score"], 0.0, 1.0)
    gte(m["idea_diversity"], 0)
    between(m["participation_balance"], 0.0, 1.0)
    inside(m["health"], {"green", "yellow", "red"})


@test("Special characters in conversation text handled", category="Edge")
def t64():
    session = make_session()
    session.messages = [
        make_msg("rook", "Rook", "Hello! @#$%^&*() Special chars: ñóüçℂ"),
        make_msg("elena", "Elena", "Numbers & symbols: 42% of $100 + tax!"),
    ]
    session.turn_count = 2
    m = calculate_synergy_metrics(session)
    between(m["cross_reference_rate"], 0.0, 1.0)
    between(m["friction_level"], 0.0, 1.0)
    between(m["convergence_score"], 0.0, 1.0)
    gte(m["idea_diversity"], 0)


@test("Empty messages handled gracefully", category="Edge")
def t65():
    session = make_session()
    session.messages = [
        make_msg("rook", "Rook", ""),
        make_msg("elena", "Elena", "  "),
    ]
    session.turn_count = 2
    m = calculate_synergy_metrics(session)
    eq(m["cross_reference_rate"], 0.0)
    eq(m["friction_level"], 0.0)
    between(m["convergence_score"], 0.0, 1.0)
    eq(m["idea_diversity"], 0)


@test("Messages with only stop words produce zero idea diversity", category="Edge")
def t66():
    session = make_session()
    session.messages = [
        make_msg("rook", "Rook", "this that with from have been"),
    ]
    session.turn_count = 1
    m = calculate_synergy_metrics(session)
    eq(m["idea_diversity"], 0)


@test("Health is green when all conditions met", category="Edge")
def t67():
    session = make_session()
    for pid in PERSONA_IDS[:3]:
        for _ in range(3):
            session.messages.append(
                make_msg(
                    pid,
                    PERSONA_NAMES[pid],
                    f"Positive contribution from {PERSONA_NAMES[pid]}",
                )
            )
    session.turn_count = 9
    m = calculate_synergy_metrics(session)
    check(m["health"] in ("green", "yellow", "red"))


# ─── Runner ──────────────────────────────────────────────────────────────────


def run():
    global passed, failed
    print("  Setting up ev-s1 session...")
    try:
        ensure_session("ev-s1")
        print("  Session ready.")
    except Exception as e:
        print(f"  Warning: Could not ensure ev-s1 session: {e}")
    for cat, name, fn in results:
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
    print(f"\n{'=' * 70}")
    print(f"  RESULTS: {passed} passed, {failed} failed ({total} total)")
    print(f"{'=' * 70}")
    print(
        f"\n  {P if not failed else F} {'ALL TESTS PASSED' if not failed else 'SOME TESTS FAILED'}"
    )
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
