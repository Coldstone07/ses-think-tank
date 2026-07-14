"""Tests for Phase 4.1: YAML Plugin System."""
import os
import sys
import tempfile
import time
import yaml
import pytest

from plugins import (
    PluginStore, plugin_store,
    validate_persona, validate_workflow,
    get_all_personas, get_all_workflows,
    PERSONA_REQUIRED, WORKFLOW_REQUIRED,
    PLUGIN_DIRS,
)


# ─── FIXTURES ──────────────────────────────────────────────────────────────

VALID_PERSONA = {
    "id": "test_persona",
    "name": "TestBot",
    "title": "The Tester",
    "system_prompt": "You are a test persona.",
    "icon": "🧪",
    "dna": {
        "core_drives": ["test things"],
        "blind_spots": ["nothing"],
        "relationships": {"rook": "colleague"},
    },
}

VALID_WORKFLOW = {
    "id": "test_wf",
    "name": "Test Workflow",
    "description": "A test workflow",
    "phases": [{"name": "Phase 1", "turns": 3}],
}

BUILTIN_PERSONAS = [
    {"id": "rook", "name": "Rook", "title": "The Architect"},
    {"id": "elena", "name": "Elena", "title": "The Empath"},
]

BUILTIN_WORKFLOWS = {
    "salon": {"id": "salon", "name": "Salon"},
}


# ─── VALIDATION ────────────────────────────────────────────────────────────

class TestValidatePersona:
    def test_valid_persona(self):
        assert validate_persona(VALID_PERSONA) == []

    def test_missing_id(self):
        p = dict(VALID_PERSONA)
        del p["id"]
        errs = validate_persona(p)
        assert any("id" in e for e in errs)

    def test_missing_name(self):
        p = dict(VALID_PERSONA)
        del p["name"]
        errs = validate_persona(p)
        assert any("name" in e for e in errs)

    def test_missing_title(self):
        p = dict(VALID_PERSONA)
        del p["title"]
        errs = validate_persona(p)
        assert any("title" in e for e in errs)

    def test_missing_system_prompt(self):
        p = dict(VALID_PERSONA)
        del p["system_prompt"]
        errs = validate_persona(p)
        assert any("system_prompt" in e for e in errs)

    def test_empty_system_prompt(self):
        p = dict(VALID_PERSONA)
        p["system_prompt"] = ""
        errs = validate_persona(p)
        assert any("system_prompt" in e for e in errs)

    def test_id_not_string(self):
        p = dict(VALID_PERSONA)
        p["id"] = 123
        errs = validate_persona(p)
        assert any("string" in e for e in errs)

    def test_dna_core_drives_not_list(self):
        import copy
        p = copy.deepcopy(VALID_PERSONA)
        p["dna"]["core_drives"] = "not a list"
        errs = validate_persona(p)
        assert any("core_drives" in e for e in errs)

    def test_dna_blind_spots_not_list(self):
        import copy
        p = copy.deepcopy(VALID_PERSONA)
        p["dna"]["blind_spots"] = "not a list"
        errs = validate_persona(p)
        assert any("blind_spots" in e for e in errs)

    def test_dna_relationships_not_dict(self):
        import copy
        p = copy.deepcopy(VALID_PERSONA)
        p["dna"]["relationships"] = ["not a dict"]
        errs = validate_persona(p)
        assert any("relationships" in e for e in errs)

    def test_all_required_missing(self):
        errs = validate_persona({})
        assert len(errs) == len(PERSONA_REQUIRED)


class TestValidateWorkflow:
    def test_valid_workflow(self):
        assert validate_workflow(VALID_WORKFLOW) == []

    def test_missing_id(self):
        w = dict(VALID_WORKFLOW)
        del w["id"]
        errs = validate_workflow(w)
        assert any("id" in e for e in errs)

    def test_missing_phases(self):
        w = dict(VALID_WORKFLOW)
        del w["phases"]
        errs = validate_workflow(w)
        assert any("phases" in e for e in errs)

    def test_phases_not_list(self):
        w = dict(VALID_WORKFLOW)
        w["phases"] = "not a list"
        errs = validate_workflow(w)
        assert any("phases must be a list" in e for e in errs)

    def test_all_required_missing(self):
        errs = validate_workflow({})
        assert len(errs) == len(WORKFLOW_REQUIRED)


# ─── PLUGIN STORE ──────────────────────────────────────────────────────────

class TestPluginStore:
    def test_initial_state(self):
        store = PluginStore()
        assert store.personas == []
        assert store.workflows == []
        assert store.memory_rules == []
        assert store.files == {}
        assert store.errors == []

    def test_load_valid_persona(self, tmp_path):
        store = PluginStore()
        personas_dir = tmp_path / "plugins" / "personas"
        personas_dir.mkdir(parents=True)
        (personas_dir / "test.yaml").write_text(yaml.dump(VALID_PERSONA))
        summary = store.load_all(str(tmp_path))
        assert summary["loaded"] == 1
        assert summary["errors"] == 0
        assert len(store.personas) == 1
        assert store.personas[0]["id"] == "test_persona"

    def test_load_valid_workflow(self, tmp_path):
        store = PluginStore()
        workflows_dir = tmp_path / "plugins" / "workflows"
        workflows_dir.mkdir(parents=True)
        (workflows_dir / "test.yaml").write_text(yaml.dump(VALID_WORKFLOW))
        summary = store.load_all(str(tmp_path))
        assert summary["loaded"] == 1
        assert len(store.workflows) == 1
        assert store.workflows[0]["id"] == "test_wf"

    def test_load_invalid_persona(self, tmp_path):
        store = PluginStore()
        personas_dir = tmp_path / "plugins" / "personas"
        personas_dir.mkdir(parents=True)
        (personas_dir / "bad.yaml").write_text(yaml.dump({"id": "bad"}))
        summary = store.load_all(str(tmp_path))
        assert summary["loaded"] == 0
        assert summary["errors"] == 1
        assert len(store.personas) == 0

    def test_load_invalid_yaml(self, tmp_path):
        store = PluginStore()
        personas_dir = tmp_path / "plugins" / "personas"
        personas_dir.mkdir(parents=True)
        (personas_dir / "broken.yaml").write_text("{{invalid: yaml: [}")
        summary = store.load_all(str(tmp_path))
        assert summary["errors"] == 1
        assert "YAML parse error" in store.errors[0]["error"]

    def test_load_yaml_not_mapping(self, tmp_path):
        store = PluginStore()
        personas_dir = tmp_path / "plugins" / "personas"
        personas_dir.mkdir(parents=True)
        (personas_dir / "list.yaml").write_text("- just a list")
        summary = store.load_all(str(tmp_path))
        assert summary["errors"] == 1
        assert "mapping" in store.errors[0]["error"].lower()

    def test_load_ignores_non_yaml(self, tmp_path):
        store = PluginStore()
        personas_dir = tmp_path / "plugins" / "personas"
        personas_dir.mkdir(parents=True)
        (personas_dir / "test.txt").write_text("not yaml")
        (personas_dir / "test.md").write_text("# readme")
        summary = store.load_all(str(tmp_path))
        assert summary["loaded"] == 0
        assert summary["errors"] == 0

    def test_load_missing_directory_is_ok(self, tmp_path):
        store = PluginStore()
        summary = store.load_all(str(tmp_path))
        assert summary["loaded"] == 0
        assert summary["errors"] == 0

    def test_load_multiple_plugins(self, tmp_path):
        store = PluginStore()
        personas_dir = tmp_path / "plugins" / "personas"
        personas_dir.mkdir(parents=True)
        p1 = dict(VALID_PERSONA)
        p1["id"] = "persona_a"
        p1["name"] = "Persona A"
        (personas_dir / "a.yaml").write_text(yaml.dump(p1))
        p2 = dict(VALID_PERSONA)
        p2["id"] = "persona_b"
        p2["name"] = "Persona B"
        (personas_dir / "b.yaml").write_text(yaml.dump(p2))
        workflows_dir = tmp_path / "plugins" / "workflows"
        workflows_dir.mkdir(parents=True)
        (workflows_dir / "wf.yaml").write_text(yaml.dump(VALID_WORKFLOW))
        summary = store.load_all(str(tmp_path))
        assert summary["loaded"] == 3
        assert summary["persona_count"] == 2
        assert summary["workflow_count"] == 1

    def test_load_memory_rules(self, tmp_path):
        store = PluginStore()
        memory_dir = tmp_path / "plugins" / "memory"
        memory_dir.mkdir(parents=True)
        (memory_dir / "rule.yaml").write_text(yaml.dump({
            "name": "test rule",
            "pattern": "test",
        }))
        summary = store.load_all(str(tmp_path))
        assert summary["memory_count"] == 1

    def test_load_resets_previous_state(self, tmp_path):
        store = PluginStore()
        personas_dir = tmp_path / "plugins" / "personas"
        personas_dir.mkdir(parents=True)
        p = dict(VALID_PERSONA)
        p["id"] = "first"
        (personas_dir / "first.yaml").write_text(yaml.dump(p))
        store.load_all(str(tmp_path))
        assert len(store.personas) == 1
        # Remove file and reload
        (personas_dir / "first.yaml").unlink()
        store.load_all(str(tmp_path))
        assert len(store.personas) == 0

    def test_load_yml_extension(self, tmp_path):
        store = PluginStore()
        personas_dir = tmp_path / "plugins" / "personas"
        personas_dir.mkdir(parents=True)
        (personas_dir / "test.yml").write_text(yaml.dump(VALID_PERSONA))
        summary = store.load_all(str(tmp_path))
        assert summary["loaded"] == 1

    def test_file_metadata(self, tmp_path):
        store = PluginStore()
        personas_dir = tmp_path / "plugins" / "personas"
        personas_dir.mkdir(parents=True)
        (personas_dir / "test.yaml").write_text(yaml.dump(VALID_PERSONA))
        store.load_all(str(tmp_path))
        fpath = str(personas_dir / "test.yaml")
        assert fpath in store.files
        meta = store.files[fpath]
        assert meta["type"] == "persona"
        assert "loaded_at" in meta
        assert "hash" in meta


# ─── NEEDS RELOAD ──────────────────────────────────────────────────────────

class TestNeedsReload:
    def test_no_change(self, tmp_path):
        import copy
        store = PluginStore()
        personas_dir = tmp_path / "plugins" / "personas"
        personas_dir.mkdir(parents=True)
        (personas_dir / "test.yaml").write_text(yaml.dump(copy.deepcopy(VALID_PERSONA)))
        store.load_all(str(tmp_path))
        assert not store.needs_reload(str(tmp_path))

    def test_new_file(self, tmp_path):
        import copy
        store = PluginStore()
        personas_dir = tmp_path / "plugins" / "personas"
        personas_dir.mkdir(parents=True)
        (personas_dir / "test.yaml").write_text(yaml.dump(copy.deepcopy(VALID_PERSONA)))
        store.load_all(str(tmp_path))
        p = copy.deepcopy(VALID_PERSONA)
        p["id"] = "new_persona"
        (personas_dir / "new.yaml").write_text(yaml.dump(p))
        assert store.needs_reload(str(tmp_path))

    def test_modified_file(self, tmp_path):
        import copy
        store = PluginStore()
        personas_dir = tmp_path / "plugins" / "personas"
        personas_dir.mkdir(parents=True)
        (personas_dir / "test.yaml").write_text(yaml.dump(copy.deepcopy(VALID_PERSONA)))
        store.load_all(str(tmp_path))
        time.sleep(0.01)
        (personas_dir / "test.yaml").write_text(yaml.dump({
            **VALID_PERSONA,
            "name": "Modified Name",
        }))
        assert store.needs_reload(str(tmp_path))

    def test_deleted_file(self, tmp_path):
        import copy
        store = PluginStore()
        personas_dir = tmp_path / "plugins" / "personas"
        personas_dir.mkdir(parents=True)
        (personas_dir / "test.yaml").write_text(yaml.dump(copy.deepcopy(VALID_PERSONA)))
        store.load_all(str(tmp_path))
        (personas_dir / "test.yaml").unlink()
        assert store.needs_reload(str(tmp_path))

    def test_empty_store_no_files(self, tmp_path):
        store = PluginStore()
        # No plugin dirs exist
        assert not store.needs_reload(str(tmp_path))


# ─── INFO ──────────────────────────────────────────────────────────────────

class TestInfo:
    def test_empty_info(self):
        store = PluginStore()
        info = store.info()
        assert info["total_loaded"] == 0
        assert info["personas"] == []
        assert info["workflows"] == []
        assert info["memory_rules"] == 0
        assert info["errors"] == []

    def test_info_with_plugins(self, tmp_path):
        store = PluginStore()
        personas_dir = tmp_path / "plugins" / "personas"
        personas_dir.mkdir(parents=True)
        (personas_dir / "test.yaml").write_text(yaml.dump(VALID_PERSONA))
        store.load_all(str(tmp_path))
        info = store.info()
        assert info["total_loaded"] == 1
        assert len(info["personas"]) == 1
        assert info["personas"][0]["id"] == "test_persona"


# ─── MERGE FUNCTIONS ──────────────────────────────────────────────────────

class TestMergePersonas:
    def test_no_plugins(self):
        plugin_store.personas = []
        result = get_all_personas(BUILTIN_PERSONAS)
        assert len(result) == 2
        assert [p["id"] for p in result] == ["rook", "elena"]

    def test_adds_plugin_persona(self):
        plugin_store.personas = [VALID_PERSONA]
        result = get_all_personas(BUILTIN_PERSONAS)
        ids = [p["id"] for p in result]
        assert "rook" in ids
        assert "test_persona" in ids
        assert len(result) == 3

    def test_plugin_overrides_builtin(self):
        override = dict(VALID_PERSONA)
        override["id"] = "rook"
        override["name"] = "Rook Override"
        plugin_store.personas = [override]
        result = get_all_personas(BUILTIN_PERSONAS)
        rook = next(p for p in result if p["id"] == "rook")
        assert rook["name"] == "Rook Override"
        assert len(result) == 2  # override replaces, doesn't add

    def test_multiple_plugins_added(self):
        p1 = dict(VALID_PERSONA)
        p1["id"] = "extra_a"
        p2 = dict(VALID_PERSONA)
        p2["id"] = "extra_b"
        plugin_store.personas = [p1, p2]
        result = get_all_personas(BUILTIN_PERSONAS)
        assert len(result) == 4
        ids = [p["id"] for p in result]
        assert "extra_a" in ids
        assert "extra_b" in ids

    def test_built_ins_not_mutated(self):
        plugin_store.personas = [VALID_PERSONA]
        original_len = len(BUILTIN_PERSONAS)
        get_all_personas(BUILTIN_PERSONAS)
        assert len(BUILTIN_PERSONAS) == original_len


class TestMergeWorkflows:
    def test_no_plugins(self):
        plugin_store.workflows = []
        result = get_all_workflows(BUILTIN_WORKFLOWS)
        assert "salon" in result
        assert len(result) == 1

    def test_adds_plugin_workflow(self):
        plugin_store.workflows = [VALID_WORKFLOW]
        result = get_all_workflows(BUILTIN_WORKFLOWS)
        assert "salon" in result
        assert "test_wf" in result
        assert len(result) == 2

    def test_plugin_overrides_builtin_workflow(self):
        override = dict(VALID_WORKFLOW)
        override["id"] = "salon"
        override["name"] = "Salon Override"
        plugin_store.workflows = [override]
        result = get_all_workflows(BUILTIN_WORKFLOWS)
        assert result["salon"]["name"] == "Salon Override"
        assert len(result) == 1

    def test_built_ins_not_mutated(self):
        plugin_store.workflows = [VALID_WORKFLOW]
        original_keys = set(BUILTIN_WORKFLOWS.keys())
        get_all_workflows(BUILTIN_WORKFLOWS)
        assert set(BUILTIN_WORKFLOWS.keys()) == original_keys


# ─── CONSTANTS ─────────────────────────────────────────────────────────────

class TestConstants:
    def test_persona_required_fields(self):
        assert PERSONA_REQUIRED == {"id", "name", "title", "system_prompt"}

    def test_workflow_required_fields(self):
        assert WORKFLOW_REQUIRED == {"id", "name", "description", "phases"}

    def test_plugin_dirs(self):
        assert "personas" in PLUGIN_DIRS
        assert "workflows" in PLUGIN_DIRS
        assert "memory" in PLUGIN_DIRS
        assert PLUGIN_DIRS["personas"] == "plugins/personas"


# ─── GLOBAL STORE ──────────────────────────────────────────────────────────

class TestGlobalStore:
    def test_plugin_store_exists(self):
        assert isinstance(plugin_store, PluginStore)

    def test_plugin_store_is_singleton(self):
        from plugins import plugin_store as ps2
        assert ps2 is plugin_store
