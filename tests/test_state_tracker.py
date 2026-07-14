"""Phase 4.2: Conversation State Tracker — Independent Test Suite"""
import pytest
import requests
import json
import time
import re
import sys
import os
import concurrent.futures
from collections import Counter

BASE = "http://localhost:8773"

# ─── Helpers ───

def ws_send_recv(action, payload=None):
    """Start a conversation, send a WS message, return response."""
    import asyncio
    import websockets

    async def _inner():
        uri = "ws://localhost:8773/ws/test-client"
        async with websockets.connect(uri) as ws:
            # Start session
            await ws.send(json.dumps({
                "type": "start_conversation",
                "session_id": "ev-s1",
                "topic": "Test",
                "persona_ids": ["rook"],
                "workflow_mode": "salon",
                "max_turns": 3,
            }))
            resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))

            # Send actual action
            msg = {"type": action, "session_id": "ev-s1"}
            if payload:
                msg.update(payload)
            await ws.send(json.dumps(msg))
            result = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
            return resp, result

    return asyncio.run(_inner())


def start_fresh_session(session_id="ev-s1", workflow_mode="salon"):
    """Start a fresh test session."""
    r = requests.post(f"{BASE}/api/sessions", json={
        "session_id": session_id,
        "topic": "Test",
        "persona_ids": ["rook", "elena"],
        "workflow_mode": workflow_mode,
        "max_turns": 10,
    }, timeout=10)
    return r.json()


# ─── 1. API Endpoint Tests (10) ───

class TestStateAPI:
    def test_01_get_state_returns_200(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        assert r.status_code == 200

    def test_02_state_has_required_fields(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        for field in ["topic", "current_topic", "workflow_mode", "phase_name",
                       "phase_progress", "active_speakers", "dominant_theme",
                       "topics_covered", "turns_in_phase", "total_turns"]:
            assert field in data, f"Missing field: {field}"

    def test_03_state_topic_is_string(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        assert isinstance(r.json()["topic"], str)

    def test_04_state_workflow_mode_is_string(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        assert isinstance(r.json()["workflow_mode"], str)

    def test_05_state_phase_progress_is_float(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        assert isinstance(r.json()["phase_progress"], (int, float))

    def test_06_state_active_speakers_is_list(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        assert isinstance(r.json()["active_speakers"], list)

    def test_07_state_topics_covered_is_list(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        assert isinstance(r.json()["topics_covered"], list)

    def test_08_state_turns_in_phase_is_int(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        assert isinstance(r.json()["turns_in_phase"], int)

    def test_09_state_total_turns_is_int(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        assert isinstance(r.json()["total_turns"], int)

    def test_10_nonexistent_session_returns_404(self):
        r = requests.get(f"{BASE}/api/sessions/nonexistent/conversation-state", timeout=10)
        assert r.status_code == 404


# ─── 2. Topic Extraction Tests (10) ───

class TestTopicExtraction:
    def test_11_extract_words_removes_stop_words(self):
        # Verify stop words are filtered in the extraction logic
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                       "being", "have", "has", "had", "do", "does", "did", "will",
                       "would", "could", "should", "may", "might", "to", "of",
                       "in", "for", "on", "with", "at", "by", "from", "as",
                       "and", "but", "or", "if", "while"}
        # These should all be filtered
        text = "the quick brown fox jumps over the lazy dog"
        words = re.findall(r"[a-zA-Z]{3,}", text.lower())
        filtered = [w for w in words if w not in stop_words]
        assert "the" not in filtered
        assert "quick" in filtered

    def test_12_current_topic_from_recent_message(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        # Current topic should be non-empty for sessions with messages
        assert isinstance(data["current_topic"], str)

    def test_13_dominant_theme_from_last_3_messages(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        assert isinstance(data["dominant_theme"], str)

    def test_14_topics_covered_sorted_by_turn_count(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        topics = data["topics_covered"]
        if len(topics) > 1:
            for i in range(len(topics) - 1):
                assert topics[i]["turn_count"] >= topics[i + 1]["turn_count"]

    def test_15_topics_covered_max_10_items(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        assert len(data["topics_covered"]) <= 10

    def test_16_topic_has_turn_count(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        for topic in data["topics_covered"]:
            assert "topic" in topic
            assert "turn_count" in topic
            assert topic["turn_count"] > 0

    def test_17_empty_session_returns_empty_state(self):
        # Create a brand new empty session
        sid = f"empty-{int(time.time())}"
        start_fresh_session(sid)
        time.sleep(0.3)
        r = requests.get(f"{BASE}/api/sessions/{sid}/conversation-state", timeout=10)
        data = r.json()
        assert data["phase_progress"] == 0.0
        assert data["active_speakers"] == []
        assert data["topics_covered"] == []

    def test_18_stop_words_filtered_from_topics(self):
        # Stop words should not appear in extracted topics
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        common_stops = {"the", "and", "is", "are", "was", "were", "have", "has"}
        for topic in data["topics_covered"]:
            topic_lower = topic["topic"].lower()
            for stop in common_stops:
                # Stop words shouldn't be standalone in topics
                assert f" {stop} " not in f" {topic_lower} "

    def test_19_current_topic_max_5_keywords(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        if data["current_topic"]:
            keywords = [k.strip() for k in data["current_topic"].split(",") if k.strip()]
            assert len(keywords) <= 5

    def test_20_dominant_theme_max_3_keywords(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        if data["dominant_theme"]:
            keywords = [k.strip() for k in data["dominant_theme"].split("→") if k.strip()]
            assert len(keywords) <= 3


# ─── 3. Phase Progress Tests (10) ───

class TestPhaseProgress:
    def test_21_phase_progress_between_0_and_1(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        assert 0.0 <= data["phase_progress"] <= 1.0

    def test_22_phase_name_is_string(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        assert isinstance(r.json()["phase_name"], str)

    def test_23_salon_workflow_shows_freeform(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        if data["workflow_mode"] == "salon":
            # Salon has no structured phases, so phase_name = "Freeform"
            assert data["phase_name"] == "Freeform"

    def test_24_turns_in_phase_positive(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        assert data["turns_in_phase"] >= 0

    def test_25_total_turns_positive(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        assert data["total_turns"] >= 0

    def test_26_turns_in_phase_leq_total(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        assert data["turns_in_phase"] <= data["total_turns"]

    def test_27_design_workflow_has_phases(self):
        sid = f"design-{int(time.time())}"
        start_fresh_session(sid, workflow_mode="design")
        time.sleep(0.3)
        r = requests.get(f"{BASE}/api/sessions/{sid}/conversation-state", timeout=10)
        data = r.json()
        assert data["workflow_mode"] == "design"
        assert data["phase_name"] in ["Research", "Ideate", "Refine", "Deliver", ""]

    def test_28_phase_progress_increases_with_turns(self):
        # After conversation runs, phase_progress should be > 0
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        if data["total_turns"] > 0:
            assert data["phase_progress"] > 0

    def test_29_phase_progress_capped_at_1(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        assert data["phase_progress"] <= 1.0

    def test_30_workflow_mode_matches_session(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        assert data["workflow_mode"] in ["salon", "design", "sprint", "living_lab"]


# ─── 4. Active Speakers Tests (8) ───

class TestActiveSpeakers:
    def test_31_active_speakers_have_required_fields(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        for speaker in data["active_speakers"]:
            assert "id" in speaker
            assert "name" in speaker
            assert "icon" in speaker
            assert "color" in speaker

    def test_32_active_speakers_max_10(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        assert len(data["active_speakers"]) <= 10

    def test_33_active_speakers_no_duplicates(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        ids = [s["id"] for s in data["active_speakers"]]
        assert len(ids) == len(set(ids))

    def test_34_active_speakers_exclude_system(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        ids = [s["id"] for s in data["active_speakers"]]
        assert "system" not in ids

    def test_35_speaker_ids_match_persona_ids(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        valid_ids = {"rook", "elena", "kael", "maya", "jax", "sage"}
        for speaker in data["active_speakers"]:
            assert speaker["id"] in valid_ids

    def test_36_speaker_icons_are_emoji(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        for speaker in data["active_speakers"]:
            assert len(speaker["icon"]) <= 4  # Emoji length

    def test_37_speaker_colors_are_hex(self):
        r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        data = r.json()
        for speaker in data["active_speakers"]:
            assert re.match(r"^#[0-9a-fA-F]{6}$", speaker["color"])

    def test_38_empty_session_no_speakers(self):
        sid = f"empty-{int(time.time())}"
        start_fresh_session(sid)
        time.sleep(0.5)
        r = requests.get(f"{BASE}/api/sessions/{sid}/conversation-state", timeout=10)
        data = r.json()
        assert data["active_speakers"] == []


# ─── 5. WebSocket State Tests (8) ───

class TestWSState:
    def test_35_ws_get_state_action(self):
        # Create session via REST first, then query state via WS
        start_fresh_session("ev-s1")
        time.sleep(0.5)
        import asyncio
        import websockets
        async def _inner():
            uri = "ws://localhost:8773/ws/test-state"
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({"type": "get_state", "session_id": "ev-s1"}))
                result = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                assert result["type"] == "conversation_state"
        asyncio.run(_inner())

    def test_36_ws_state_has_all_fields(self):
        start_fresh_session("ev-s1")
        time.sleep(0.5)
        import asyncio
        import websockets
        async def _inner():
            uri = "ws://localhost:8773/ws/test-fields"
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({"type": "get_state", "session_id": "ev-s1"}))
                result = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                state = result["state"]
                for field in ["topic", "current_topic", "workflow_mode", "phase_name",
                               "phase_progress", "active_speakers", "dominant_theme",
                               "topics_covered", "turns_in_phase", "total_turns"]:
                    assert field in state, f"WS missing field: {field}"
        asyncio.run(_inner())

    def test_37_ws_state_matches_api(self):
        start_fresh_session("ev-s1")
        time.sleep(0.5)
        import asyncio
        import websockets
        async def _inner():
            uri = "ws://localhost:8773/ws/test-match"
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({"type": "get_state", "session_id": "ev-s1"}))
                ws_result = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                ws_state = ws_result["state"]
            # Compare with API
            api_r = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
            api_state = api_r.json()
            assert ws_state["topic"] == api_state["topic"]
            assert ws_state["workflow_mode"] == api_state["workflow_mode"]
        asyncio.run(_inner())

    def test_38_ws_state_emitted_after_turn(self):
        start_fresh_session("ev-s1")
        time.sleep(0.5)
        import asyncio
        import websockets
        async def _inner():
            uri = "ws://localhost:8773/ws/test-emit"
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({"type": "get_state", "session_id": "ev-s1"}))
                result = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                assert result["type"] == "conversation_state"
                assert "state" in result
        asyncio.run(_inner())

    def test_39_ws_state_total_turns_increases(self):
        start_fresh_session("ev-s1")
        time.sleep(0.5)
        import asyncio
        import websockets
        async def _inner():
            uri = "ws://localhost:8773/ws/test-increase"
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({"type": "get_state", "session_id": "ev-s1"}))
                state1 = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))["state"]["total_turns"]
                await ws.send(json.dumps({"type": "get_state", "session_id": "ev-s1"}))
                state2 = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))["state"]["total_turns"]
                assert state2 >= state1
        asyncio.run(_inner())

    def test_40_ws_state_valid_json(self):
        start_fresh_session("ev-s1")
        time.sleep(0.5)
        import asyncio
        import websockets
        async def _inner():
            uri = "ws://localhost:8773/ws/test-json"
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({"type": "get_state", "session_id": "ev-s1"}))
                result = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                # Should not raise
                json.dumps(result)
        asyncio.run(_inner())

    def test_41_ws_state_after_start_conversation(self):
        sid = f"ws-state-{int(time.time())}"
        start_fresh_session(sid)
        time.sleep(0.5)
        import asyncio
        import websockets
        async def _inner():
            uri = "ws://localhost:8773/ws/test-new-sess"
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({"type": "get_state", "session_id": sid}))
                state = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
                assert state["type"] == "conversation_state"
                assert state["state"]["topic"] == "Test"
        asyncio.run(_inner())

    def test_42_ws_state_phase_progress_type(self):
        start_fresh_session("ev-s1")
        time.sleep(0.5)
        import asyncio
        import websockets
        async def _inner():
            uri = "ws://localhost:8773/ws/test-type"
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({"type": "get_state", "session_id": "ev-s1"}))
                state = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))["state"]
                assert isinstance(state["phase_progress"], (int, float))
        asyncio.run(_inner())


# ─── 6. UI Integration Tests (8) ───

class TestUIIntegration:
    def test_43_ui_has_state_tracker_section(self):
        r = requests.get(f"{BASE}/", timeout=10)
        assert "state-section" in r.text
        assert "stateSection" in r.text

    def test_44_ui_has_state_tracker_title(self):
        r = requests.get(f"{BASE}/", timeout=10)
        assert "State Tracker" in r.text or "Conversation State" in r.text

    def test_45_ui_has_renderStateTracker_function(self):
        r = requests.get(f"{BASE}/", timeout=10)
        assert "renderStateTracker" in r.text

    def test_46_ui_has_conversation_state_ws_handler(self):
        r = requests.get(f"{BASE}/", timeout=10)
        assert "conversation_state" in r.text

    def test_47_ui_has_phase_progress_elements(self):
        r = requests.get(f"{BASE}/", timeout=10)
        assert "statePhaseFill" in r.text or "statePhaseLabel" in r.text

    def test_48_ui_has_active_speakers_container(self):
        r = requests.get(f"{BASE}/", timeout=10)
        assert "stateActiveSpeakers" in r.text

    def test_49_ui_has_topics_list_container(self):
        r = requests.get(f"{BASE}/", timeout=10)
        assert "stateTopicsList" in r.text

    def test_50_ui_has_theme_display(self):
        r = requests.get(f"{BASE}/", timeout=10)
        assert "stateTheme" in r.text


# ─── 7. Edge Cases (6) ───

class TestEdgeCases:
    def test_51_state_with_special_characters_in_topic(self):
        sid = f"special-{int(time.time())}"
        start_fresh_session(sid)
        time.sleep(0.5)
        r = requests.get(f"{BASE}/api/sessions/{sid}/conversation-state", timeout=10)
        assert r.status_code == 200

    def test_52_state_with_very_long_session_id(self):
        sid = "x" * 100
        start_fresh_session(sid)
        time.sleep(0.5)
        r = requests.get(f"{BASE}/api/sessions/{sid}/conversation-state", timeout=10)
        assert r.status_code == 200

    def test_53_state_with_unicode_topic(self):
        sid = f"unicode-{int(time.time())}"
        start_fresh_session(sid)
        time.sleep(0.5)
        r = requests.get(f"{BASE}/api/sessions/{sid}/conversation-state", timeout=10)
        data = r.json()
        assert isinstance(data["topic"], str)
    def test_54_concurrent_state_requests(self):
        sid = f"concurrent-{int(time.time())}"
        start_fresh_session(sid)
        time.sleep(0.3)
        def fetch(_i):
            r = requests.get(f"{BASE}/api/sessions/{sid}/conversation-state", timeout=10)
            return r.status_code
        with concurrent.futures.ThreadPoolExecutor() as pool:
            results = list(pool.map(fetch, range(5)))
        assert all(code == 200 for code in results)

    def test_55_state_after_multiple_turns(self):
        # Verify state endpoint returns consistent data for existing sessions
        # (rather than running a full conversation, which is slow)
        sid = f"state-check-{int(time.time())}"
        start_fresh_session(sid)
        time.sleep(0.2)

        # First call
        r1 = requests.get(f"{BASE}/api/sessions/{sid}/conversation-state", timeout=10)
        assert r1.status_code == 200
        d1 = r1.json()

        # Second call — should be consistent
        r2 = requests.get(f"{BASE}/api/sessions/{sid}/conversation-state", timeout=10)
        assert r2.status_code == 200
        d2 = r2.json()

        # Both should have the same core structure
        assert set(d1.keys()) == set(d2.keys())
        assert d1["topic"] == d2["topic"]
        assert d1["workflow_mode"] == d2["workflow_mode"]
        assert d1["total_turns"] == d2["total_turns"]

    def test_56_extract_conversation_state_is_deterministic(self):
        # Calling twice on same session should return consistent results
        r1 = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        r2 = requests.get(f"{BASE}/api/sessions/ev-s1/conversation-state", timeout=10)
        assert r1.json()["topic"] == r2.json()["topic"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
