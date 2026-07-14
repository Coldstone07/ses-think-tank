"""Phase 4.3: Human-in-the-Loop v2 — Intervention Modes, Pause/Resume, History

Tests cover:
- POST /api/sessions/{id}/intervene (all modes)
- GET /api/sessions/{id}/interventions
- GET /api/sessions/{id}/conversation-state (pause flag)
- Pause/resume state management
- Edge cases (invalid modes, session not found, empty message)
"""
import pytest
import requests
import time

BASE = "http://localhost:8773"


def create_session(topic="Test topic", max_turns=10, workflow_mode="salon"):
    """Create a session via REST and return session_id."""
    sid = f"hitl-{int(time.time() * 1000000)}"
    r = requests.post(f"{BASE}/api/sessions", json={
        "session_id": sid,
        "topic": topic,
        "max_turns": max_turns,
        "workflow_mode": workflow_mode,
    })
    r.raise_for_status()
    return sid


# ─── Steer Mode (1-10) ───

def test_01_intervene_steer_basic():
    """POST intervene with mode=steer returns 200."""
    sid = create_session()
    r = requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "steer", "message": "Focus on economics"
    })
    assert r.status_code == 200
    data = r.json()
    assert data["mode"] == "steer"
    assert "intervention_id" in data


def test_02_intervene_steer_adds_message():
    """Steer intervention adds a message to the session."""
    sid = create_session()
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "steer", "message": "Let's discuss pricing"
    })
    r = requests.get(f"{BASE}/api/sessions/{sid}/messages")
    assert r.status_code == 200
    msgs = r.json()
    assert any("[HUMAN STEER]" in m.get("content", "") for m in msgs)


def test_03_intervene_steer_content_format():
    """Steer message contains the custom steer text."""
    sid = create_session()
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "steer", "message": "Custom steer text"
    })
    r = requests.get(f"{BASE}/api/sessions/{sid}/messages")
    msgs = r.json()
    steer_msgs = [m for m in msgs if "[HUMAN STEER]" in m.get("content", "")]
    assert len(steer_msgs) >= 1
    assert "Custom steer text" in steer_msgs[-1]["content"]


def test_04_intervene_steer_increases_turn_count():
    """Steer intervention increments turn_count."""
    sid = create_session()
    r1 = requests.get(f"{BASE}/api/sessions/{sid}/conversation-state")
    turns_before = r1.json().get("total_turns", 0)
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "steer", "message": "test"
    })
    r2 = requests.get(f"{BASE}/api/sessions/{sid}/conversation-state")
    turns_after = r2.json().get("total_turns", 0)
    assert turns_after > turns_before


def test_05_intervene_steer_with_target():
    """Steer intervention accepts a target persona."""
    sid = create_session()
    r = requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "steer", "message": "Rook, expand", "target": "rook"
    })
    assert r.status_code == 200


def test_06_intervene_steer_multiple():
    """Multiple steer interventions are all recorded."""
    sid = create_session()
    for i in range(3):
        requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
            "mode": "steer", "message": f"Steer {i}"
        })
    r = requests.get(f"{BASE}/api/sessions/{sid}/interventions")
    assert r.status_code == 200
    data = r.json()
    steer_count = sum(1 for inv in data["interventions"] if inv["mode"] == "steer")
    assert steer_count >= 3


def test_07_intervene_steer_persona_name():
    """Steer intervention message has persona_name 'Human Operator'."""
    sid = create_session()
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "steer", "message": "test"
    })
    r = requests.get(f"{BASE}/api/sessions/{sid}/messages")
    msgs = r.json()
    human_msgs = [m for m in msgs if m.get("persona_name") == "Human Operator"]
    assert len(human_msgs) >= 1


def test_08_intervene_steer_returns_status():
    """Steer intervention returns status 'intervened'."""
    sid = create_session()
    r = requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "steer", "message": "test"
    })
    assert r.json()["status"] == "intervened"


def test_09_intervene_steer_turn_in_response():
    """Steer intervention returns turn number in response."""
    sid = create_session()
    r = requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "steer", "message": "test"
    })
    data = r.json()
    assert "turn" in data
    assert data["turn"] >= 1


def test_10_intervene_steer_id_format():
    """Intervention ID is a hex string."""
    sid = create_session()
    r = requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "steer", "message": "test"
    })
    iid = r.json()["intervention_id"]
    assert isinstance(iid, str)
    assert len(iid) > 0


# ─── Veto Mode (11-16) ───

def test_11_intervene_veto_basic():
    """Veto intervention creates a record with veto mode."""
    sid = create_session()
    r = requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "veto", "message": "Stop discussing this"
    })
    assert r.status_code == 200
    assert r.json()["mode"] == "veto"


def test_12_intervene_veto_content_format():
    """Veto message contains VETO prefix."""
    sid = create_session()
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "veto", "message": "Wrong direction"
    })
    r = requests.get(f"{BASE}/api/sessions/{sid}/messages")
    msgs = r.json()
    assert any("[HUMAN VETO]" in m.get("content", "") for m in msgs)


def test_13_intervene_veto_rejected_text():
    """Veto message includes 'rejected' instruction."""
    sid = create_session()
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "veto", "message": "Drop this"
    })
    r = requests.get(f"{BASE}/api/sessions/{sid}/messages")
    msgs = r.json()
    veto_msgs = [m for m in msgs if "[HUMAN VETO]" in m.get("content", "")]
    assert any("rejected" in m["content"] for m in veto_msgs)


def test_14_intervene_veto_increases_turn_count():
    """Veto intervention increments turn count."""
    sid = create_session()
    r1 = requests.get(f"{BASE}/api/sessions/{sid}/conversation-state")
    before = r1.json().get("total_turns", 0)
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "veto", "message": "stop"
    })
    r2 = requests.get(f"{BASE}/api/sessions/{sid}/conversation-state")
    after = r2.json().get("total_turns", 0)
    assert after > before


def test_15_intervene_veto_in_history():
    """Veto appears in intervention history."""
    sid = create_session()
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "veto", "message": "no"
    })
    r = requests.get(f"{BASE}/api/sessions/{sid}/interventions")
    assert r.status_code == 200
    history = r.json()["interventions"]
    assert any(h["mode"] == "veto" for h in history)


def test_16_intervene_veto_status():
    """Veto intervention returns status 'intervened'."""
    sid = create_session()
    r = requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "veto", "message": "stop"
    })
    assert r.json()["status"] == "intervened"


# ─── Amplify Mode (17-22) ───

def test_17_intervene_amplify_basic():
    """Amplify intervention creates a record."""
    sid = create_session()
    r = requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "amplify", "message": "Expand on cultural impact"
    })
    assert r.status_code == 200
    assert r.json()["mode"] == "amplify"


def test_18_intervene_amplify_content_format():
    """Amplify message contains AMPLIFY prefix."""
    sid = create_session()
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "amplify", "message": "More detail"
    })
    r = requests.get(f"{BASE}/api/sessions/{sid}/messages")
    msgs = r.json()
    assert any("[HUMAN AMPLIFY]" in m.get("content", "") for m in msgs)


def test_19_intervene_amplify_expand_text():
    """Amplify message includes 'expand' instruction."""
    sid = create_session()
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "amplify", "message": "this point"
    })
    r = requests.get(f"{BASE}/api/sessions/{sid}/messages")
    msgs = r.json()
    amp_msgs = [m for m in msgs if "[HUMAN AMPLIFY]" in m.get("content", "")]
    assert any("expand" in m["content"].lower() for m in amp_msgs)


def test_20_intervene_amplify_in_history():
    """Amplify appears in intervention history."""
    sid = create_session()
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "amplify", "message": "go deeper"
    })
    r = requests.get(f"{BASE}/api/sessions/{sid}/interventions")
    history = r.json()["interventions"]
    assert any(h["mode"] == "amplify" for h in history)


def test_21_intervene_amplify_increases_turn_count():
    """Amplify intervention increments turn count."""
    sid = create_session()
    r1 = requests.get(f"{BASE}/api/sessions/{sid}/conversation-state")
    before = r1.json().get("total_turns", 0)
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "amplify", "message": "more"
    })
    r2 = requests.get(f"{BASE}/api/sessions/{sid}/conversation-state")
    after = r2.json().get("total_turns", 0)
    assert after > before


def test_22_intervene_amplify_status():
    """Amplify returns status 'intervened'."""
    sid = create_session()
    r = requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "amplify", "message": "expand"
    })
    assert r.json()["status"] == "intervened"


# ─── Pause Mode (23-28) ───

def test_23_intervene_pause_sets_flag():
    """Pause intervention sets is_paused=True."""
    sid = create_session()
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "pause", "message": "Hold on"
    })
    r = requests.get(f"{BASE}/api/sessions/{sid}/conversation-state")
    assert r.json().get("is_paused") is True


def test_24_intervene_pause_in_history():
    """Pause appears in intervention history."""
    sid = create_session()
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "pause", "message": "stop"
    })
    r = requests.get(f"{BASE}/api/sessions/{sid}/interventions")
    history = r.json()["interventions"]
    assert any(h["mode"] == "pause" for h in history)


def test_25_intervene_pause_does_not_add_message():
    """Pause does NOT add a conversation message."""
    sid = create_session()
    r1 = requests.get(f"{BASE}/api/sessions/{sid}/messages")
    count_before = len(r1.json())
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "pause", "message": "freeze"
    })
    r2 = requests.get(f"{BASE}/api/sessions/{sid}/messages")
    count_after = len(r2.json())
    assert count_after == count_before


def test_26_intervene_pause_returns_status():
    """Pause returns status 'paused'."""
    sid = create_session()
    r = requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "pause", "message": "stop"
    })
    assert r.json()["status"] == "paused"


def test_27_intervene_pause_multiple():
    """Multiple pauses are all recorded in history."""
    sid = create_session()
    for i in range(3):
        requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
            "mode": "pause", "message": f"pause {i}"
        })
    r = requests.get(f"{BASE}/api/sessions/{sid}/interventions")
    history = r.json()["interventions"]
    pause_count = sum(1 for h in history if h["mode"] == "pause")
    assert pause_count >= 3


def test_28_intervene_pause_state_reflects():
    """State endpoint shows is_paused after pause intervention."""
    sid = create_session()
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "pause", "message": "halt"
    })
    r = requests.get(f"{BASE}/api/sessions/{sid}/conversation-state")
    assert r.json().get("is_paused") is True


# ─── Resume Mode (29-34) ───

def test_29_intervene_resume_clears_pause():
    """Resume intervention sets is_paused=False."""
    sid = create_session()
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "pause", "message": "stop"
    })
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "resume", "message": "go again"
    })
    r = requests.get(f"{BASE}/api/sessions/{sid}/conversation-state")
    assert r.json().get("is_paused") is False


def test_30_intervene_resume_in_history():
    """Resume appears in intervention history."""
    sid = create_session()
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "resume", "message": "continue"
    })
    r = requests.get(f"{BASE}/api/sessions/{sid}/interventions")
    history = r.json()["interventions"]
    assert any(h["mode"] == "resume" for h in history)


def test_31_intervene_resume_does_not_add_message():
    """Resume does NOT add a conversation message."""
    sid = create_session()
    r1 = requests.get(f"{BASE}/api/sessions/{sid}/messages")
    count_before = len(r1.json())
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "resume", "message": "go"
    })
    r2 = requests.get(f"{BASE}/api/sessions/{sid}/messages")
    count_after = len(r2.json())
    assert count_after == count_before


def test_32_intervene_resume_without_prior_pause():
    """Resume works even if session was never paused."""
    sid = create_session()
    r = requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "resume", "message": "start"
    })
    assert r.status_code == 200
    assert r.json()["mode"] == "resume"


def test_33_intervene_pause_resume_cycle():
    """Multiple pause/resume cycles work correctly."""
    sid = create_session()
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={"mode": "pause", "message": "p1"})
    assert requests.get(f"{BASE}/api/sessions/{sid}/conversation-state").json().get("is_paused") is True
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={"mode": "resume", "message": "r1"})
    assert requests.get(f"{BASE}/api/sessions/{sid}/conversation-state").json().get("is_paused") is False
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={"mode": "pause", "message": "p2"})
    assert requests.get(f"{BASE}/api/sessions/{sid}/conversation-state").json().get("is_paused") is True
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={"mode": "resume", "message": "r2"})
    assert requests.get(f"{BASE}/api/sessions/{sid}/conversation-state").json().get("is_paused") is False


def test_34_intervene_resume_status():
    """Resume returns status 'resumed'."""
    sid = create_session()
    r = requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "resume", "message": "go"
    })
    assert r.json()["status"] == "resumed"


# ─── GET /api/sessions/{id}/interventions (35-40) ───

def test_35_get_interventions_empty():
    """New session has empty intervention history."""
    sid = create_session()
    r = requests.get(f"{BASE}/api/sessions/{sid}/interventions")
    assert r.status_code == 200
    data = r.json()
    assert data["interventions"] == []
    assert data["total_interventions"] == 0


def test_36_get_interventions_after_intervention():
    """Intervention history contains records after interventions."""
    sid = create_session()
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "steer", "message": "test"
    })
    r = requests.get(f"{BASE}/api/sessions/{sid}/interventions")
    assert r.status_code == 200
    data = r.json()
    assert len(data["interventions"]) >= 1
    assert data["total_interventions"] >= 1


def test_37_get_interventions_not_found():
    """GET interventions for non-existent session returns 404."""
    r = requests.get(f"{BASE}/api/sessions/nonexistent-xyz/interventions")
    assert r.status_code == 404


def test_38_get_interventions_returns_fields():
    """Intervention records contain expected fields."""
    sid = create_session()
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "steer", "message": "check fields"
    })
    r = requests.get(f"{BASE}/api/sessions/{sid}/interventions")
    record = r.json()["interventions"][-1]
    assert "id" in record
    assert "mode" in record
    assert "message" in record
    assert "timestamp" in record


def test_39_get_interventions_multiple_modes():
    """Intervention history preserves all modes correctly."""
    sid = create_session()
    for mode in ["steer", "veto", "amplify", "pause"]:
        requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
            "mode": mode, "message": f"{mode} msg"
        })
    r = requests.get(f"{BASE}/api/sessions/{sid}/interventions")
    history = r.json()["interventions"]
    modes = [h["mode"] for h in history]
    for mode in ["steer", "veto", "amplify", "pause"]:
        assert mode in modes


def test_40_get_interventions_ordered():
    """Interventions are returned in chronological order."""
    sid = create_session()
    for i in range(3):
        requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
            "mode": "steer", "message": f"msg {i}"
        })
        time.sleep(0.1)
    r = requests.get(f"{BASE}/api/sessions/{sid}/interventions")
    history = r.json()["interventions"]
    steer_history = [h for h in history if h["mode"] == "steer"]
    assert len(steer_history) >= 3
    for i in range(len(steer_history) - 1):
        assert steer_history[i]["timestamp"] <= steer_history[i + 1]["timestamp"]


# ─── Persistence (41-44) ───

def test_41_intervention_persistence():
    """Interventions are saved and retrievable."""
    sid = create_session()
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "steer", "message": "persist test"
    })
    r = requests.get(f"{BASE}/api/sessions/{sid}/interventions")
    history = r.json()["interventions"]
    assert any(h["message"] == "persist test" for h in history)


def test_42_pause_state_persistence():
    """Pause state is saved to session."""
    sid = create_session()
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "pause", "message": "persist pause"
    })
    r = requests.get(f"{BASE}/api/sessions/{sid}/conversation-state")
    assert r.json().get("is_paused") is True


def test_43_intervention_target_persistence():
    """Intervention target is saved."""
    sid = create_session()
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "steer", "message": "targeted", "target": "maya"
    })
    r = requests.get(f"{BASE}/api/sessions/{sid}/interventions")
    history = r.json()["interventions"]
    targeted = [h for h in history if h.get("target") == "maya"]
    assert len(targeted) >= 1


def test_44_intervention_timestamp_persistence():
    """Intervention timestamps are saved as numbers."""
    sid = create_session()
    requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "steer", "message": "time test"
    })
    r = requests.get(f"{BASE}/api/sessions/{sid}/interventions")
    history = r.json()["interventions"]
    assert any(isinstance(h["timestamp"], (int, float)) for h in history)


# ─── Edge Cases (45-52) ───

def test_45_intervene_session_not_found():
    """Intervening on non-existent session returns 404."""
    r = requests.post(f"{BASE}/api/sessions/does-not-exist/intervene", json={
        "mode": "steer", "message": "test"
    })
    assert r.status_code == 404


def test_46_intervene_empty_message():
    """Empty message returns error."""
    sid = create_session()
    r = requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "steer", "message": ""
    })
    assert r.status_code == 400


def test_47_intervene_whitespace_only_message():
    """Whitespace-only message returns error."""
    sid = create_session()
    r = requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "steer", "message": "   "
    })
    assert r.status_code == 400


def test_48_intervene_missing_mode_defaults_to_steer():
    """Missing mode defaults to steer."""
    sid = create_session()
    r = requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "message": "default mode test"
    })
    assert r.status_code == 200
    assert r.json().get("mode") == "steer"


def test_49_intervene_unknown_mode():
    """Unknown mode is accepted and recorded as-is."""
    sid = create_session()
    r = requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "custom_mode", "message": "custom"
    })
    assert r.status_code == 200
    assert r.json()["mode"] == "custom_mode"


def test_50_intervene_missing_message_field():
    """Missing message field returns 400."""
    sid = create_session()
    r = requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "steer"
    })
    assert r.status_code == 400


def test_51_intervene_long_message():
    """Long intervention messages are handled."""
    sid = create_session()
    long_msg = "A " * 500
    r = requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "steer", "message": long_msg
    })
    assert r.status_code == 200


def test_52_intervene_unicode_message():
    """Unicode characters in intervention messages work."""
    sid = create_session()
    r = requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
        "mode": "steer", "message": "🎯 Focus 🔑"
    })
    assert r.status_code == 200
    assert "🎯" in r.json()["message"]


# ─── Combined Scenarios (53-55) ───

def test_53_mixed_interventions_sequence():
    """Mixed sequence of interventions is recorded correctly."""
    sid = create_session()
    sequence = [
        ("steer", "first steer"),
        ("veto", "reject that"),
        ("pause", "hold"),
        ("amplify", "expand"),
        ("resume", "go"),
    ]
    for mode, msg in sequence:
        requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
            "mode": mode, "message": msg
        })
    r = requests.get(f"{BASE}/api/sessions/{sid}/interventions")
    history = r.json()["interventions"]
    modes = [h["mode"] for h in history]
    for expected_mode, _ in sequence:
        assert expected_mode in modes


def test_54_intervention_count_matches():
    """Intervention count matches number of interventions sent."""
    sid = create_session()
    num_interventions = 5
    for i in range(num_interventions):
        requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={
            "mode": "steer", "message": f"msg {i}"
        })
    r = requests.get(f"{BASE}/api/sessions/{sid}/interventions")
    assert r.json()["total_interventions"] == num_interventions


def test_55_pause_resume_doesnt_affect_message_count():
    """Pause/resume cycles don't add conversation messages."""
    sid = create_session()
    r = requests.get(f"{BASE}/api/sessions/{sid}/messages")
    msg_count = len(r.json())
    for _ in range(3):
        requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={"mode": "pause", "message": "p"})
        requests.post(f"{BASE}/api/sessions/{sid}/intervene", json={"mode": "resume", "message": "r"})
    r = requests.get(f"{BASE}/api/sessions/{sid}/messages")
    assert len(r.json()) == msg_count


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
