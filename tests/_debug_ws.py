#!/usr/bin/env python3
"""Debug: run all WS tests in a single event loop."""

import asyncio, json, requests, uuid
import websockets.asyncio.client as wsmod

BASE_URL = "http://localhost:8773"
WS_URL = "ws://localhost:8773"
SID = "ev-s1"


def cleanup():
    r = requests.get(f"{BASE_URL}/api/sessions/{SID}/whiteboard", timeout=10)
    for pid in list(r.json().keys()):
        try:
            requests.delete(
                f"{BASE_URL}/api/sessions/{SID}/whiteboard/pins/{pid}", timeout=10
            )
        except:
            pass


async def drain(ws):
    while True:
        try:
            await asyncio.wait_for(ws.recv(), 0.3)
        except (asyncio.TimeoutError, TimeoutError):
            break


async def run_all():
    cleanup()
    cid = lambda: f"dbg-{uuid.uuid4().hex[:4]}"

    for name, coro in [
        ("t29 WS pin_idea creates pin", t29(cid())),
        ("t30 WS vote_pin works", t30(cid())),
        ("t31 WS comment_pin works", t31(cid())),
        ("t32 WS whiteboard_update on pin_idea", t32(cid())),
        ("t33 WS whiteboard_update on vote", t33(cid())),
        ("t34 WS whiteboard_update on comment", t34(cid())),
        ("t35 WS pin_idea missing topic creates pin", t35(cid())),
        ("t36 WS vote_pin missing pin_id does nothing", t36(cid())),
        ("t37 WS comment_pin missing text adds empty", t37(cid())),
        ("t38 WS state consistent after multiple actions", t38(cid())),
    ]:
        try:
            await coro
            print(f"  PASS: {name}")
        except Exception as e:
            print(f"  FAIL: {name}: {e}")
            import traceback

            traceback.print_exc()
            break

    print("WS DEBUG DONE")


async def t29(c):
    cleanup()
    pin = requests.post(
        f"{BASE_URL}/api/sessions/{SID}/whiteboard/pin",
        json={
            "topic": "WS Pin Idea",
            "content": "Created via WebSocket",
            "author": "rook",
        },
        timeout=10,
    ).json()
    ws = await wsmod.connect(f"{WS_URL}/ws/{c}")
    try:
        await ws.send(
            json.dumps(
                {
                    "type": "pin_idea",
                    "session_id": SID,
                    "topic": "WS Pin Idea",
                    "content": "Created via WebSocket",
                    "author": "rook",
                }
            )
        )
        await asyncio.sleep(0.3)
        wb = requests.get(
            f"{BASE_URL}/api/sessions/{SID}/whiteboard", timeout=10
        ).json()
        matches = [p for p in wb.values() if p["topic"] == "WS Pin Idea"]
        assert len(matches) > 0
    finally:
        await ws.close()


async def t30(c):
    cleanup()
    pin = requests.post(
        f"{BASE_URL}/api/sessions/{SID}/whiteboard/pin",
        json={"topic": "WS Vote Test", "content": "test", "author": "test"},
        timeout=10,
    ).json()
    ws = await wsmod.connect(f"{WS_URL}/ws/{c}")
    try:
        await ws.send(
            json.dumps(
                {
                    "type": "vote_pin",
                    "session_id": SID,
                    "pin_id": pin["id"],
                    "persona_id": "sage",
                    "vote": "approve",
                }
            )
        )
        await asyncio.sleep(0.3)
        wb = requests.get(
            f"{BASE_URL}/api/sessions/{SID}/whiteboard", timeout=10
        ).json()
        assert wb[pin["id"]]["votes"].get("sage") == "approve"
    finally:
        await ws.close()


async def t31(c):
    cleanup()
    pin = requests.post(
        f"{BASE_URL}/api/sessions/{SID}/whiteboard/pin",
        json={"topic": "WS Comment Test", "content": "test", "author": "test"},
        timeout=10,
    ).json()
    ws = await wsmod.connect(f"{WS_URL}/ws/{c}")
    try:
        await ws.send(
            json.dumps(
                {
                    "type": "comment_pin",
                    "session_id": SID,
                    "pin_id": pin["id"],
                    "author": "jax",
                    "text": "Comment from WebSocket",
                }
            )
        )
        await asyncio.sleep(0.3)
        wb = requests.get(
            f"{BASE_URL}/api/sessions/{SID}/whiteboard", timeout=10
        ).json()
        assert len(wb[pin["id"]]["comments"]) == 1
    finally:
        await ws.close()


async def t32(c):
    cleanup()
    ws = await wsmod.connect(f"{WS_URL}/ws/{c}")
    try:
        await drain(ws)
        await ws.send(
            json.dumps(
                {
                    "type": "pin_idea",
                    "session_id": SID,
                    "topic": "WB Update Test",
                    "content": "test",
                    "author": "rook",
                }
            )
        )
        msg = json.loads(await asyncio.wait_for(ws.recv(), 5))
        assert msg.get("type") == "whiteboard_update"
    finally:
        await ws.close()


async def t33(c):
    cleanup()
    pin = requests.post(
        f"{BASE_URL}/api/sessions/{SID}/whiteboard/pin",
        json={"topic": "WB Vote Event", "content": "test", "author": "test"},
        timeout=10,
    ).json()
    ws = await wsmod.connect(f"{WS_URL}/ws/{c}")
    try:
        await drain(ws)
        await ws.send(
            json.dumps(
                {
                    "type": "vote_pin",
                    "session_id": SID,
                    "pin_id": pin["id"],
                    "persona_id": "rook",
                    "vote": "reject",
                }
            )
        )
        msg = json.loads(await asyncio.wait_for(ws.recv(), 5))
        assert msg.get("type") == "whiteboard_update"
    finally:
        await ws.close()


async def t34(c):
    print("  [t34 start]")
    cleanup()
    print("  [t34 cleanup done]")
    pin = requests.post(
        f"{BASE_URL}/api/sessions/{SID}/whiteboard/pin",
        json={"topic": "WB Comment Event", "content": "test", "author": "test"},
        timeout=10,
    ).json()
    print(f"  [t34 pin created: {pin['id']}]")
    ws = await wsmod.connect(f"{WS_URL}/ws/{c}")
    print("  [t34 connected]")
    try:
        await ws.send(
            json.dumps(
                {
                    "type": "comment_pin",
                    "session_id": SID,
                    "pin_id": pin["id"],
                    "author": "elena",
                    "text": "Event test comment",
                }
            )
        )
        print("  [t34 sent]")
        msg = json.loads(await asyncio.wait_for(ws.recv(), 5))
        print(f"  [t34 recv: {msg.get('type')}]")
        assert msg.get("type") == "whiteboard_update", (
            f"Expected whiteboard_update, got {msg.get('type')}"
        )
        assert len(msg["whiteboard"][pin["id"]]["comments"]) == 1
        print("  [t34 assertions passed]")
        await asyncio.sleep(0.3)
        wb = requests.get(
            f"{BASE_URL}/api/sessions/{SID}/whiteboard", timeout=10
        ).json()
        assert len(wb[pin["id"]]["comments"]) == 1
        print(f"  [t34 API check passed: {wb[pin['id']]['comments'][0]['text']!r}]")
    finally:
        print("  [t34 closing]")
        await ws.close()
        print("  [t34 closed]")


async def t35(c):
    cleanup()
    ws = await wsmod.connect(f"{WS_URL}/ws/{c}")
    try:
        await ws.send(
            json.dumps(
                {
                    "type": "pin_idea",
                    "session_id": SID,
                    "content": "no topic provided",
                    "author": "test",
                }
            )
        )
        await asyncio.sleep(0.3)
        wb = requests.get(
            f"{BASE_URL}/api/sessions/{SID}/whiteboard", timeout=10
        ).json()
        matches = [p for p in wb.values() if p["content"] == "no topic provided"]
        assert len(matches) > 0
        assert matches[0]["topic"] == ""
    finally:
        await ws.close()


async def t36(c):
    cleanup()
    pin = requests.post(
        f"{BASE_URL}/api/sessions/{SID}/whiteboard/pin",
        json={"topic": "WS No-op Vote", "content": "test", "author": "test"},
        timeout=10,
    ).json()
    ws = await wsmod.connect(f"{WS_URL}/ws/{c}")
    try:
        initial = requests.get(
            f"{BASE_URL}/api/sessions/{SID}/whiteboard", timeout=10
        ).json()
        await ws.send(
            json.dumps(
                {
                    "type": "vote_pin",
                    "session_id": SID,
                    "persona_id": "rook",
                    "vote": "approve",
                }
            )
        )
        await asyncio.sleep(0.3)
        after = requests.get(
            f"{BASE_URL}/api/sessions/{SID}/whiteboard", timeout=10
        ).json()
        assert len(after[pin["id"]]["votes"]) == len(initial[pin["id"]]["votes"])
    finally:
        await ws.close()


async def t37(c):
    cleanup()
    pin = requests.post(
        f"{BASE_URL}/api/sessions/{SID}/whiteboard/pin",
        json={"topic": "WS Empty Comment", "content": "test", "author": "test"},
        timeout=10,
    ).json()
    ws = await wsmod.connect(f"{WS_URL}/ws/{c}")
    try:
        await ws.send(
            json.dumps(
                {
                    "type": "comment_pin",
                    "session_id": SID,
                    "pin_id": pin["id"],
                    "author": "test",
                }
            )
        )
        await asyncio.sleep(0.3)
        wb = requests.get(
            f"{BASE_URL}/api/sessions/{SID}/whiteboard", timeout=10
        ).json()
        assert len(wb[pin["id"]]["comments"]) == 1
        assert wb[pin["id"]]["comments"][0]["text"] == ""
    finally:
        await ws.close()


async def t38(c):
    cleanup()
    pin = requests.post(
        f"{BASE_URL}/api/sessions/{SID}/whiteboard/pin",
        json={"topic": "WS Multi Action", "content": "original", "author": "test"},
        timeout=10,
    ).json()
    ws = await wsmod.connect(f"{WS_URL}/ws/{c}")
    try:
        await ws.send(
            json.dumps(
                {
                    "type": "vote_pin",
                    "session_id": SID,
                    "pin_id": pin["id"],
                    "persona_id": "rook",
                    "vote": "approve",
                }
            )
        )
        await ws.send(
            json.dumps(
                {
                    "type": "vote_pin",
                    "session_id": SID,
                    "pin_id": pin["id"],
                    "persona_id": "elena",
                    "vote": "reject",
                }
            )
        )
        await ws.send(
            json.dumps(
                {
                    "type": "comment_pin",
                    "session_id": SID,
                    "pin_id": pin["id"],
                    "author": "kael",
                    "text": "First comment",
                }
            )
        )
        await ws.send(
            json.dumps(
                {
                    "type": "comment_pin",
                    "session_id": SID,
                    "pin_id": pin["id"],
                    "author": "maya",
                    "text": "Second comment",
                }
            )
        )
        await asyncio.sleep(0.5)
        wb = requests.get(
            f"{BASE_URL}/api/sessions/{SID}/whiteboard", timeout=10
        ).json()
        assert wb[pin["id"]]["votes"]["rook"] == "approve"
        assert wb[pin["id"]]["votes"]["elena"] == "reject"
        assert len(wb[pin["id"]]["comments"]) == 2
        assert wb[pin["id"]]["comments"][0]["text"] == "First comment"
        assert wb[pin["id"]]["comments"][1]["text"] == "Second comment"
    finally:
        await ws.close()


if __name__ == "__main__":
    asyncio.run(run_all())
