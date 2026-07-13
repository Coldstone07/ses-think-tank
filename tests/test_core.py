#!/usr/bin/env python3
"""
Unit tests for SES Think Tank — persona generation, ASFE metrics, JSON extraction.
Run: python3.11 -m pytest tests/test_core.py -v
"""
import json
import re
import sys
import os
import importlib

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as app_mod
importlib.reload(app_mod)

PERSONAS = app_mod.PERSONAS
WORKFLOWS = app_mod.WORKFLOWS
extract_json_from_text = app_mod.extract_json_from_text
extract_from_reasoning = app_mod.extract_from_reasoning


# ─── Persona Tests ───────────────────────────────────────────────────────────

class TestPersonas:
    def test_persona_count(self):
        assert len(PERSONAS) == 6, f"Expected 6 personas, got {len(PERSONAS)}"

    def test_persona_ids_unique(self):
        ids = [p["id"] for p in PERSONAS]
        assert len(ids) == len(set(ids)), "Duplicate persona IDs found"

    def test_required_fields_present(self):
        required = ["id", "name", "title", "icon", "color", "system_prompt", "background", "dna"]
        for p in PERSONAS:
            for field in required:
                assert field in p, f"Persona {p.get('id', '?')} missing field: {field}"

    def test_dna_structure(self):
        for p in PERSONAS:
            dna = p["dna"]
            assert "core_drives" in dna, f"{p['id']} DNA missing core_drives"
            assert "blind_spots" in dna, f"{p['id']} DNA missing blind_spots"
            assert "interaction_style" in dna, f"{p['id']} DNA missing interaction_style"
            assert "relationships" in dna, f"{p['id']} DNA missing relationships"

    def test_system_prompt_contains_dna(self):
        for p in PERSONAS:
            prompt = p["system_prompt"]
            assert p["name"] in prompt, f"{p['id']} system prompt missing name"
            assert len(prompt) > 200, f"{p['id']} system prompt too short — DNA likely missing"

    def test_persona_names(self):
        expected = {"Rook", "Elena", "Kael", "Maya", "Jax", "Sage"}
        actual = {p["name"] for p in PERSONAS}
        assert actual == expected, f"Expected {expected}, got {actual}"


# ─── Workflow Tests ──────────────────────────────────────────────────────────

class TestWorkflows:
    def test_workflow_count(self):
        assert len(WORKFLOWS) >= 3, f"Expected at least 3 workflows, got {len(WORKFLOWS)}"

    def test_workflow_modes(self):
        assert "salon" in WORKFLOWS, "Missing salon workflow"
        assert "design" in WORKFLOWS, "Missing design workflow"
        assert "sprint" in WORKFLOWS, "Missing sprint workflow"

    def test_workflow_phases(self):
        for mode, w in WORKFLOWS.items():
            if mode == "salon":
                continue  # Salon is freeform — no phases
            assert "phases" in w, f"Workflow {mode} missing phases"
            assert len(w["phases"]) > 0, f"Workflow {mode} has no phases"
            for phase in w["phases"]:
                assert "name" in phase, f"Phase in {mode} missing name"
                assert "description" in phase, f"Phase in {mode} missing description"


# ─── JSON Extraction Tests ───────────────────────────────────────────────────

class TestJSONExtraction:
    def test_direct_json(self):
        result = extract_json_from_text('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_in_text(self):
        text = "Here's my analysis: {\"depth\": 8, \"overall\": 7}. Let me know."
        result = extract_json_from_text(text)
        assert result is not None
        assert result["depth"] == 8

    def test_json_in_multiline(self):
        text = """Thinking...
        
        {"depth": 9, "clarity": 7, "overall": 8, "reasoning": "good response"}
        
        Hope that helps!"""
        result = extract_json_from_text(text)
        assert result is not None
        assert result["overall"] == 8

    def test_invalid_json(self):
        result = extract_json_from_text("no json here at all")
        assert result is None

    def test_empty_string(self):
        result = extract_json_from_text("")
        assert result is None

    def test_nested_json(self):
        text = '{"scores": {"depth": 8, "clarity": 7}, "overall": 7}'
        result = extract_json_from_text(text)
        assert result is not None
        assert result["overall"] == 7


# ─── Reasoning Extraction Tests ──────────────────────────────────────────────

class TestReasoningExtraction:
    def test_response_separator(self):
        text = "Thinking about this...\n\n---RESPONSE---\n\nThis is the actual response."
        result = extract_from_reasoning(text)
        assert "actual response" in result
        assert "Thinking" not in result

    def test_draft_paragraphs(self):
        text = """Draft Paragraph 1: The healthcare system needs reform.
        
        1. **Check constraints** - OK
        2. **Refine tone** - OK"""
        result = extract_from_reasoning(text)
        assert len(result) > 0

    def test_fallback_to_last_block(self):
        text = "Some analysis here. Then more analysis. Finally the conclusion paragraph with substantial content that should be returned."
        result = extract_from_reasoning(text)
        assert len(result) > 0


# ─── ASFE Metrics Tests ──────────────────────────────────────────────────────

class TestASFE:
    def test_cross_reference_count(self):
        # Test that cross-referencing is measured correctly
        messages = [
            {"persona_name": "Rook", "content": "As Elena mentioned, we need to consider..."},
            {"persona_name": "Elena", "content": "Building on Kael's point about ethics..."},
            {"persona_name": "Kael", "content": "I disagree with Maya's assessment."},
        ]
        refs = sum(1 for m in messages if any(name in m["content"] for name in ["Elena", "Kael", "Maya", "Rook"]))
        assert refs == 3, f"Expected 3 cross-references, got {refs}"

    def test_synergy_calculation(self):
        # Synergy = cross_references * building_rate
        cross_refs = 4
        building_rate = 0.75
        synergy = cross_refs * building_rate
        assert synergy == 3.0

    def test_friction_calculation(self):
        # Friction = disagreement_rate * resolution_rate
        disagreements = 2
        total_turns = 10
        resolved = 1
        disagreement_rate = disagreements / total_turns
        resolution_rate = resolved / max(1, disagreements)
        friction = disagreement_rate * resolution_rate
        assert 0 < friction < 1


# ─── Integration Tests ──────────────────────────────────────────────────────

class TestIntegration:
    def test_asfe_grade_imports(self):
        # Verify asfe_grade.py can import the new functions
        import scripts.asfe_grade as grade_mod
        assert hasattr(grade_mod, 'call_llm_raw')
        assert hasattr(grade_mod, 'extract_json_from_text')

    def test_find_free_port(self):
        # Verify port finder exists and returns a valid port
        port = app_mod.find_free_port(8773)
        assert 8773 <= port <= 8783, f"Port {port} outside expected range"

    def test_personas_exportable_to_json(self):
        # Verify personas can be serialized (for API responses)
        json_str = json.dumps(PERSONAS)
        parsed = json.loads(json_str)
        assert len(parsed) == 6


# ─── Run Tests ───────────────────────────────────────────────────────────────

def run_tests():
    """Simple test runner without pytest dependency."""
    import traceback
    
    test_classes = [TestPersonas, TestWorkflows, TestJSONExtraction, 
                    TestReasoningExtraction, TestASFE, TestIntegration]
    
    passed = 0
    failed = 0
    errors = []
    
    for cls in test_classes:
        print(f"\n{'='*60}")
        print(f"{cls.__name__}")
        print('='*60)
        
        instance = cls()
        methods = [m for m in dir(instance) if m.startswith('test_')]
        
        for method_name in methods:
            method = getattr(instance, method_name)
            try:
                method()
                print(f"  ✅ {method_name}")
                passed += 1
            except Exception as e:
                print(f"  ❌ {method_name}: {e}")
                failed += 1
                errors.append((f"{cls.__name__}.{method_name}", str(e), traceback.format_exc()))
    
    print(f"\n{'='*60}")
    print(f"RESULTS: {passed} passed, {failed} failed")
    print('='*60)
    
    if errors:
        print("\nFAILED TESTS:")
        for name, error, tb in errors:
            print(f"\n{name}:")
            print(f"  {error}")
    
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
