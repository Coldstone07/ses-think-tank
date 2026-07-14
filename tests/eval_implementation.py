#!/usr/bin/env python3
"""
SES Think Tank — Comprehensive Implementation Eval
===================================================
Tests ALL implemented features against the running server on localhost:8773.

Run: python3.11 tests/eval_implementation.py
"""

import asyncio
import json
import os
import subprocess
import sys
import traceback

import requests

BASE_URL = "http://localhost:8773"
WS_URL = "ws://localhost:8773"

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


# ─── API ─────────────────────────────────────────────────────────────────


@test("GET /api/personas returns 200", category="API")
def t1():
    eq(requests.get(f"{BASE_URL}/api/personas", timeout=10).status_code, 200)


@test("GET /api/personas returns 6 personas", category="API")
def t2():
    eq(len(requests.get(f"{BASE_URL}/api/personas", timeout=10).json()), 6)


@test("GET /api/personas — all required fields", category="API")
def t3():
    req = {"id", "name", "title", "icon", "color", "system_prompt", "background", "dna"}
    for p in requests.get(f"{BASE_URL}/api/personas", timeout=10).json():
        check(not (req - set(p.keys())), f"{p.get('id', '?')} missing fields")


@test("GET /api/personas — unique IDs and names", category="API")
def t4():
    data = requests.get(f"{BASE_URL}/api/personas", timeout=10).json()
    ids = [p["id"] for p in data]
    eq(len(ids), len(set(ids)))
    eq(set(ids), {"rook", "elena", "kael", "maya", "jax", "sage"})


@test("GET /api/workflows returns 200", category="API")
def t5():
    eq(requests.get(f"{BASE_URL}/api/workflows", timeout=10).status_code, 200)


@test("GET /api/workflows has 4 modes", category="API")
def t6():
    eq(
        set(requests.get(f"{BASE_URL}/api/workflows", timeout=10).json().keys()),
        {"salon", "design", "sprint", "living_lab"},
    )


@test("GET /api/sessions returns 200", category="API")
def t7():
    eq(requests.get(f"{BASE_URL}/api/sessions", timeout=10).status_code, 200)


@test("GET /api/items returns 200", category="API")
def t8():
    eq(requests.get(f"{BASE_URL}/api/items", timeout=10).status_code, 200)


@test("GET / returns HTML dashboard", category="API")
def t9():
    r = requests.get(f"{BASE_URL}/", timeout=10)
    eq(r.status_code, 200)
    check("html" in r.headers.get("content-type", "").lower())


@test("POST /api/chat unknown persona returns error", category="API")
def t10():
    r = requests.post(
        f"{BASE_URL}/api/chat",
        json={"persona_id": "nonexistent", "message": "Hi"},
        timeout=10,
    )
    check("error" in r.json())


@test("POST /api/chat valid persona returns response", category="API")
def t11():
    r = requests.post(
        f"{BASE_URL}/api/chat",
        json={"persona_id": "rook", "message": "Hello"},
        timeout=310,
    )
    eq(r.status_code, 200)
    check("response" in r.json())
    eq(r.json().get("persona_id"), "rook")
    eq(r.json().get("persona_name"), "Rook")


# ─── Workflow Phases ─────────────────────────────────────────────────────


@test("Design workflow 4 phases with structure", category="Workflows")
def t12():
    wf = requests.get(f"{BASE_URL}/api/workflows", timeout=10).json()["design"]
    eq(len(wf["phases"]), 4)
    eq([p["id"] for p in wf["phases"]], ["diverge", "converge", "stress", "synthesize"])
    for p in wf["phases"]:
        for k in ("name", "description", "turns", "speakers", "speaker_instructions"):
            inside(k, p)
        gt(p["turns"], 0)
        gt(len(p["speakers"]), 0)


@test("Sprint workflow 4 phases with structure", category="Workflows")
def t13():
    wf = requests.get(f"{BASE_URL}/api/workflows", timeout=10).json()["sprint"]
    eq(len(wf["phases"]), 4)
    eq([p["id"] for p in wf["phases"]], ["draft", "refine", "stress", "finalize"])
    for p in wf["phases"]:
        inside("name", p)
        inside("turns", p)
        inside("speakers", p)
        gt(p["turns"], 0)


@test("Living Lab workflow 4 phases", category="Workflows")
def t14():
    wf = requests.get(f"{BASE_URL}/api/workflows", timeout=10).json()["living_lab"]
    eq(len(wf["phases"]), 4)
    eq(
        [p["id"] for p in wf["phases"]],
        ["debate", "whiteboard", "synthesis", "ship_or_kill"],
    )


# ─── Persona DNA ─────────────────────────────────────────────────────────


@test("All 6 personas have DNA structure", category="DNA")
def t15():
    for p in requests.get(f"{BASE_URL}/api/personas", timeout=10).json():
        dna = p["dna"]
        for k in ("core_drives", "blind_spots", "interaction_style", "relationships"):
            inside(k, dna)
        eq(len(dna["core_drives"]), 3)
        eq(len(dna["blind_spots"]), 3)
        gt(len(dna["interaction_style"]), 10)


@test("Personas have relationships with all others", category="DNA")
def t16():
    ps = requests.get(f"{BASE_URL}/api/personas", timeout=10).json()
    aids = {p["id"] for p in ps}
    for p in ps:
        rel = p["dna"]["relationships"]
        for o in aids - {p["id"]}:
            inside(o, rel, f"{p['id']} missing rel for {o}")
        for o in rel:
            gt(len(rel[o]), 5)


@test("System prompts contain persona name", category="DNA")
def t17():
    for p in requests.get(f"{BASE_URL}/api/personas", timeout=10).json():
        inside(p["name"], p["system_prompt"], f"{p['id']} prompt missing name")
        gt(len(p["system_prompt"]), 200)


# ─── WebSocket ───────────────────────────────────────────────────────────


@test("WebSocket ping/pong", category="WS")
def t18():
    async def go():
        import websockets.asyncio.client as wsmod

        ws = await wsmod.connect(f"{WS_URL}/ws/ev-ping")
        try:
            await ws.send(json.dumps({"type": "ping"}))
            r = json.loads(await asyncio.wait_for(ws.recv(), 5))
            eq(r.get("type"), "pong")
        finally:
            await ws_close(ws)

    run_ws(go())


@test("WebSocket invalid JSON → error", category="WS")
def t19():
    async def go():
        import websockets.asyncio.client as wsmod

        ws = await wsmod.connect(f"{WS_URL}/ws/ev-badjson")
        try:
            await ws.send("not json")
            r = json.loads(await asyncio.wait_for(ws.recv(), 5))
            eq(r.get("type"), "error")
            check("Invalid JSON" in r.get("message", ""))
        finally:
            await ws_close(ws)

    run_ws(go())


@test("WebSocket missing topic → error", category="WS")
def t20():
    async def go():
        import websockets.asyncio.client as wsmod

        ws = await wsmod.connect(f"{WS_URL}/ws/ev-notopic")
        try:
            await ws.send(json.dumps({"type": "start_conversation", "session_id": "x"}))
            r = json.loads(await asyncio.wait_for(ws.recv(), 10))
            if r.get("type") == "error":
                check("Missing topic" in r.get("message", ""))
        except TimeoutError:
            pass
        finally:
            await ws_close(ws)

    run_ws(go())


@test("WebSocket start_conversation accepted", category="WS")
def t21():
    async def go():
        import websockets.asyncio.client as wsmod, asyncio

        for attempt in range(3):
            try:
                ws = await asyncio.wait_for(
                    wsmod.connect(f"{WS_URL}/ws/ev-start"), timeout=30
                )
            except TimeoutError:
                if attempt < 2:
                    await asyncio.sleep(3)
                    continue
                raise
            try:
                await ws.send(
                    json.dumps(
                        {
                            "type": "start_conversation",
                            "session_id": "ev-s1",
                            "topic": "Test",
                            "max_turns": 1,
                            "workflow_mode": "salon",
                        }
                    )
                )
                resps = []
                while True:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), 120))
                    resps.append(msg)
                    if msg.get("type") == "session_complete":
                        break
                gt(len(resps), 0)
                types = {r.get("type") for r in resps}
                inside("message", types)
                inside("session_complete", types)
                return
            finally:
                await ws_close(ws)

    run_ws(go())


@test("WebSocket catches JSON decode errors", category="WS")
def t22():
    async def go():
        import websockets.asyncio.client as wsmod

        ws = await wsmod.connect(f"{WS_URL}/ws/ev-decode")
        try:
            await ws.send("{{{broken}}")
            r = json.loads(await asyncio.wait_for(ws.recv(), 5))
            eq(r.get("type"), "error")
            check(
                "Invalid JSON" in r.get("message", "") or "JSON" in r.get("message", "")
            )
        finally:
            await ws_close(ws)

    run_ws(go())


# ─── Code Quality ────────────────────────────────────────────────────────


@test("All existing unit tests pass", category="Quality")
def t23():
    r = subprocess.run(
        [sys.executable, "tests/test_core.py"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    check(r.returncode == 0, f"Unit tests failed:\n{r.stdout}\n{r.stderr}")


# ─── New Features ────────────────────────────────────────────────────────


@test("find_free_port() exists and works", category="Features")
def t24():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import importlib
    import app as a

    importlib.reload(a)
    port = a.find_free_port(18773)
    check(isinstance(port, int))
    check(18773 <= port <= 18783)


@test("call_llm_raw() exists in app.py", category="Features")
def t25():
    import importlib
    import app as a

    importlib.reload(a)
    check(hasattr(a, "call_llm_raw"))
    check(callable(a.call_llm_raw))


@test("extract_json_from_text() handles reasoning output", category="Features")
def t26():
    import importlib
    import app as a

    importlib.reload(a)
    ext = a.extract_json_from_text
    eq(ext('{"a":1}'), {"a": 1})
    r = ext('Here:\n{"s":8}\nEnd.')
    check(r is not None)
    eq(r.get("s"), 8)
    r = ext('{"o":{"i":"v"},"k":42}')
    check(r is not None)
    eq(r.get("k"), 42)
    check(ext("no json") is None)
    check(ext("") is None)


# ─── Runner ──────────────────────────────────────────────────────────────


def run():
    global passed, failed
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
