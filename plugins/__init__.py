"""
Phase 4.1: YAML Plugin System

Load custom personas, workflows, and memory rules from YAML files in the
`plugins/` directory. Plugins are merged with built-in definitions at
runtime and support hot-reloading.

Directory structure:
    plugins/
        personas/     — custom persona YAML files
        workflows/    — custom workflow YAML files
        memory/       — cross-session memory rule YAML files
"""

import os
import time
import yaml
from pathlib import Path

# ─── VALIDATION ────────────────────────────────────────────────────────────────

PERSONA_REQUIRED = {"id", "name", "title", "system_prompt"}
PERSONA_OPTIONAL = {"icon", "color", "accent", "background", "dna"}

WORKFLOW_REQUIRED = {"id", "name", "description", "phases"}

PLUGIN_DIRS = {
    "personas": "plugins/personas",
    "workflows": "plugins/workflows",
    "memory": "plugins/memory",
    "tools": "plugins/tools",
}

# Import tool plugin system
from plugins.tools import (
    tool_store, validate_tool, tool_to_openai_schema,
    execute_tool_plugin, TOOL_REQUIRED, EXECUTION_TYPES,
)

# Import knowledge system
from plugins.knowledge import (
    load_knowledge, add_memory, extract_memories_from_conversation,
    list_personas_with_knowledge,
)


def validate_persona(data: dict) -> list[str]:
    """Validate a persona YAML dict. Returns list of errors (empty = valid)."""
    errors = []
    for field in PERSONA_REQUIRED:
        if field not in data or not data[field]:
            errors.append(f"Missing required field: {field}")
    if "id" in data and not isinstance(data["id"], str):
        errors.append("id must be a string")
    if "dna" in data and isinstance(data["dna"], dict):
        dna = data["dna"]
        if "core_drives" in dna and not isinstance(dna["core_drives"], list):
            errors.append("dna.core_drives must be a list")
        if "blind_spots" in dna and not isinstance(dna["blind_spots"], list):
            errors.append("dna.blind_spots must be a list")
        if "relationships" in dna and not isinstance(dna["relationships"], dict):
            errors.append("dna.relationships must be a dict")
    return errors


def validate_workflow(data: dict) -> list[str]:
    """Validate a workflow YAML dict. Returns list of errors."""
    errors = []
    for field in WORKFLOW_REQUIRED:
        if field not in data or not data[field]:
            errors.append(f"Missing required field: {field}")
    if "phases" in data and not isinstance(data["phases"], list):
        errors.append("phases must be a list")
    return errors


# ─── PLUGIN STORE ──────────────────────────────────────────────────────────────

class PluginStore:
    """In-memory store for loaded plugins with file metadata."""

    def __init__(self):
        self.personas = []      # list of persona dicts
        self.workflows = []     # list of workflow dicts
        self.memory_rules = []  # list of memory rule dicts
        self.files = {}         # filepath -> {type, loaded_at, hash}
        self.errors = []        # list of {file, error} during last load

    def load_all(self, base_dir: str = ".") -> dict:
        """Scan all plugin directories and load YAML files.

        Returns summary: {loaded: int, errors: int, files: [path], ...}
        """
        self.personas = []
        self.workflows = []
        self.memory_rules = []
        self.files = {}
        self.errors = []

        for plugin_type, rel_dir in PLUGIN_DIRS.items():
            dir_path = Path(base_dir) / Path(*rel_dir.split("/"))
            if not dir_path.is_dir():
                continue
            for fname in sorted(os.listdir(str(dir_path))):
                if not fname.endswith((".yaml", ".yml")):
                    continue
                fpath = str(dir_path / fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        raw = f.read()
                    data = yaml.safe_load(raw)
                    if not isinstance(data, dict):
                        self.errors.append({"file": fpath, "error": "YAML root must be a mapping"})
                        continue

                    # Compute file hash for change detection
                    file_hash = hash(raw)

                    if plugin_type == "personas":
                        errs = validate_persona(data)
                        if errs:
                            self.errors.append({"file": fpath, "error": "; ".join(errs)})
                        else:
                            self.personas.append(data)
                            self.files[fpath] = {"type": "persona", "loaded_at": time.time(), "hash": file_hash}
                    elif plugin_type == "workflows":
                        errs = validate_workflow(data)
                        if errs:
                            self.errors.append({"file": fpath, "error": "; ".join(errs)})
                        else:
                            self.workflows.append(data)
                            self.files[fpath] = {"type": "workflow", "loaded_at": time.time(), "hash": file_hash}
                    elif plugin_type == "memory":
                        self.memory_rules.append(data)
                        self.files[fpath] = {"type": "memory", "loaded_at": time.time(), "hash": file_hash}

                except yaml.YAMLError as e:
                    self.errors.append({"file": fpath, "error": f"YAML parse error: {e}"})
                except Exception as e:
                    self.errors.append({"file": fpath, "error": str(e)})

        return {
            "loaded": len(self.files),
            "errors": len(self.errors),
            "persona_count": len(self.personas),
            "workflow_count": len(self.workflows),
            "memory_count": len(self.memory_rules),
            "files": list(self.files.keys()),
            "errors_detail": self.errors,
        }

    def needs_reload(self, base_dir: str = ".") -> bool:
        """Check if any plugin file has changed since last load."""
        for plugin_type, rel_dir in PLUGIN_DIRS.items():
            dir_path = Path(base_dir) / Path(*rel_dir.split("/"))
            if not dir_path.is_dir():
                continue
            for fname in os.listdir(str(dir_path)):
                if not fname.endswith((".yaml", ".yml")):
                    continue
                fpath = str(dir_path / fname)
                if fpath not in self.files:
                    return True  # new file
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        raw = f.read()
                    if hash(raw) != self.files[fpath]["hash"]:
                        return True  # content changed
                except Exception:
                    pass
        # Check for deleted files
        for fpath in list(self.files.keys()):
            if not os.path.exists(fpath):
                return True
        return False

    def info(self) -> dict:
        """Return plugin store info."""
        return {
            "personas": [{"id": p.get("id"), "name": p.get("name"), "title": p.get("title")} for p in self.personas],
            "workflows": [{"id": w.get("id"), "name": w.get("name")} for w in self.workflows],
            "memory_rules": len(self.memory_rules),
            "total_loaded": len(self.files),
            "errors": self.errors,
        }


# ─── GLOBAL STORE ──────────────────────────────────────────────────────────────

plugin_store = PluginStore()


def get_all_personas(built_in_personas: list) -> list:
    """Merge built-in personas with plugin personas. Plugins override built-ins by id."""
    result = list(built_in_personas)
    plugin_ids = {p["id"] for p in plugin_store.personas}
    # Remove built-in personas that are overridden by plugins
    result = [p for p in result if p["id"] not in plugin_ids]
    # Add plugin personas
    result.extend(plugin_store.personas)
    return result


def get_all_workflows(built_in_workflows: dict) -> dict:
    """Merge built-in workflows with plugin workflows. Plugins add new entries."""
    result = dict(built_in_workflows)
    for w in plugin_store.workflows:
        result[w["id"]] = w
    return result
