"""Phase 4.3: Tool Plugins + Knowledge System Tests"""
import pytest
import json
import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from plugins.tools import (
    validate_tool, tool_to_openai_schema, execute_tool_plugin,
    tool_store, ToolStore, EXECUTION_TYPES,
)
from plugins.knowledge import (
    load_knowledge, add_memory, extract_memories_from_conversation,
    list_personas_with_knowledge,
)


# ─── Tool Validation ──────────────────────────────────────────────────────

class TestValidateTool:
    def test_valid_python_tool(self):
        tool = {
            "name": "test_tool",
            "description": "A test tool",
            "parameters": [{"name": "x", "type": "string", "required": True}],
            "execution": {"type": "python", "code": "print('hello')"},
        }
        assert validate_tool(tool) == []

    def test_valid_shell_tool(self):
        tool = {
            "name": "shell_tool",
            "description": "A shell tool",
            "parameters": [],
            "execution": {"type": "shell", "command": "echo hello"},
        }
        assert validate_tool(tool) == []

    def test_valid_http_tool(self):
        tool = {
            "name": "http_tool",
            "description": "An HTTP tool",
            "parameters": [],
            "execution": {"type": "http", "url": "http://example.com"},
        }
        assert validate_tool(tool) == []

    def test_missing_name(self):
        tool = {"description": "test", "parameters": [], "execution": {"type": "python", "code": "x"}}
        errs = validate_tool(tool)
        assert any("name" in e for e in errs)

    def test_missing_execution(self):
        tool = {"name": "t", "description": "d", "parameters": []}
        errs = validate_tool(tool)
        assert any("execution" in e for e in errs)

    def test_invalid_execution_type(self):
        tool = {
            "name": "t", "description": "d", "parameters": [],
            "execution": {"type": "invalid"},
        }
        errs = validate_tool(tool)
        assert any("execution.type" in e for e in errs)

    def test_python_without_code(self):
        tool = {
            "name": "t", "description": "d", "parameters": [],
            "execution": {"type": "python"},
        }
        errs = validate_tool(tool)
        assert any("code" in e for e in errs)

    def test_shell_without_command(self):
        tool = {
            "name": "t", "description": "d", "parameters": [],
            "execution": {"type": "shell"},
        }
        errs = validate_tool(tool)
        assert any("command" in e for e in errs)

    def test_http_without_url(self):
        tool = {
            "name": "t", "description": "d", "parameters": [],
            "execution": {"type": "http"},
        }
        errs = validate_tool(tool)
        assert any("url" in e for e in errs)


# ─── OpenAI Schema Conversion ─────────────────────────────────────────────

class TestToolToOpenAISchema:
    def test_basic_conversion(self):
        tool = {
            "name": "search",
            "description": "Search things",
            "parameters": [
                {"name": "query", "type": "string", "required": True, "description": "Search query"},
                {"name": "limit", "type": "integer", "default": 5},
            ],
        }
        schema = tool_to_openai_schema(tool)
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "search"
        assert "query" in schema["function"]["parameters"]["required"]
        assert "limit" not in schema["function"]["parameters"]["required"]

    def test_empty_parameters(self):
        tool = {"name": "ping", "description": "Ping", "parameters": []}
        schema = tool_to_openai_schema(tool)
        assert schema["function"]["parameters"]["properties"] == {}
        assert schema["function"]["parameters"]["required"] == []


# ─── Tool Execution ───────────────────────────────────────────────────────

class TestToolExecution:
    def test_python_execution(self):
        tool = {
            "name": "add",
            "execution": {"type": "python", "code": 'print(2 + 3)'},
            "timeout": 10,
            "sandbox": True,
        }
        result = execute_tool_plugin(tool, {}, ".")
        assert result["error"] is None
        assert "5" in result["result"]

    def test_python_with_format_args(self):
        tool = {
            "name": "greet",
            "execution": {"type": "python", "code": 'print("Hello {{name}}")'},
            "timeout": 10,
            "sandbox": True,
        }
        result = execute_tool_plugin(tool, {"name": "World"}, ".")
        assert result["error"] is None
        assert "Hello World" in result["result"]

    def test_shell_execution(self):
        tool = {
            "name": "echo_test",
            "execution": {"type": "shell", "command": "echo {{msg}}"},
            "timeout": 10,
        }
        result = execute_tool_plugin(tool, {"msg": "hello"}, ".")
        assert result["error"] is None
        assert "hello" in result["result"]

    def test_missing_argument(self):
        tool = {
            "name": "test",
            "execution": {"type": "python", "code": 'x = int("{{missing_num}}")'},
            "timeout": 10,
            "sandbox": True,
        }
        result = execute_tool_plugin(tool, {}, ".")
        # Missing arg leaves {{missing_num}} as literal string → int() fails
        assert result["error"] is not None

    def test_timeout(self):
        tool = {
            "name": "slow",
            "execution": {"type": "python", "code": "import time; time.sleep(60)"},
            "timeout": 1,
            "sandbox": True,
        }
        result = execute_tool_plugin(tool, {}, ".")
        assert result["error"] is not None


# ─── ToolStore ────────────────────────────────────────────────────────────

class TestToolStore:
    def test_load_from_directory(self, tmp_path):
        tools_dir = tmp_path / "plugins" / "tools"
        tools_dir.mkdir(parents=True)
        (tools_dir / "test.yaml").write_text("""
name: test_tool
description: A test tool
parameters:
  - name: x
    type: string
    required: true
execution:
  type: python
  code: |
    print("hello {{x}}")
timeout: 10
sandbox: true
""")
        store = ToolStore()
        result = store.load_all(str(tmp_path))
        assert result["loaded"] == 1
        assert "test_tool" in result["tools"]

    def test_ignores_invalid_yaml(self, tmp_path):
        tools_dir = tmp_path / "plugins" / "tools"
        tools_dir.mkdir(parents=True)
        (tools_dir / "bad.yaml").write_text("not: valid: yaml: [")
        store = ToolStore()
        result = store.load_all(str(tmp_path))
        assert result["loaded"] == 0
        assert result["errors"] == 1

    def test_ignores_non_yaml_files(self, tmp_path):
        tools_dir = tmp_path / "plugins" / "tools"
        tools_dir.mkdir(parents=True)
        (tools_dir / "readme.md").write_text("docs")
        (tools_dir / "__init__.py").write_text("")
        store = ToolStore()
        result = store.load_all(str(tmp_path))
        assert result["loaded"] == 0

    def test_needs_reload_on_new_file(self, tmp_path):
        tools_dir = tmp_path / "plugins" / "tools"
        tools_dir.mkdir(parents=True)
        store = ToolStore()
        store.load_all(str(tmp_path))
        assert not store.needs_reload(str(tmp_path))
        (tools_dir / "new.yaml").write_text("name: new\ndescription: d\nparameters: []\nexecution:\n  type: python\n  code: pass\n")
        assert store.needs_reload(str(tmp_path))

    def test_needs_reload_on_modified_file(self, tmp_path):
        tools_dir = tmp_path / "plugins" / "tools"
        tools_dir.mkdir(parents=True)
        f = tools_dir / "t.yaml"
        f.write_text("name: t\ndescription: d\nparameters: []\nexecution:\n  type: python\n  code: pass\n")
        store = ToolStore()
        store.load_all(str(tmp_path))
        assert not store.needs_reload(str(tmp_path))
        f.write_text("name: t\ndescription: modified\nparameters: []\nexecution:\n  type: python\n  code: pass\n")
        assert store.needs_reload(str(tmp_path))

    def test_get_openai_schemas(self, tmp_path):
        tools_dir = tmp_path / "plugins" / "tools"
        tools_dir.mkdir(parents=True)
        (tools_dir / "t.yaml").write_text("name: my_tool\ndescription: desc\nparameters:\n  - name: q\n    type: string\n    required: true\nexecution:\n  type: python\n  code: pass\n")
        store = ToolStore()
        store.load_all(str(tmp_path))
        schemas = store.get_openai_schemas()
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "my_tool"


# ─── Knowledge System ─────────────────────────────────────────────────────

class TestKnowledgeSystem:
    def test_load_knowledge_no_dir(self):
        result = load_knowledge("nonexistent", "/tmp/nonexistent_base")
        assert result["books"] == []
        assert result["memories"] == []
        assert result["knowledge_prompt"] == ""

    def test_load_knowledge_with_books(self, tmp_path):
        books_dir = tmp_path / "plugins" / "knowledge" / "test_persona" / "books"
        books_dir.mkdir(parents=True)
        (books_dir / "test_book.yaml").write_text("""
title: "Test Book"
authors: ["Author"]
key_insights:
  - "First insight"
  - "Second insight"
""")
        result = load_knowledge("test_persona", str(tmp_path))
        assert len(result["books"]) == 1
        assert result["books"][0]["title"] == "Test Book"
        assert len(result["books"][0]["key_insights"]) == 2
        assert "[KNOWLEDGE BASE]" in result["knowledge_prompt"]

    def test_add_memory(self, tmp_path):
        knowledge_dir = tmp_path / "plugins" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        mem = add_memory("test_persona", "I learned something", "session 123", str(tmp_path))
        assert mem["insight"] == "I learned something"
        assert mem["source"] == "session 123"
        # Verify it was saved
        result = load_knowledge("test_persona", str(tmp_path))
        assert len(result["memories"]) == 1
        assert "[CONVERSATION MEMORIES]" in result["knowledge_prompt"]

    def test_add_multiple_memories(self, tmp_path):
        knowledge_dir = tmp_path / "plugins" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        add_memory("p1", "Insight 1", "s1", str(tmp_path))
        add_memory("p1", "Insight 2", "s2", str(tmp_path))
        result = load_knowledge("p1", str(tmp_path))
        assert len(result["memories"]) == 2

    def test_memory_cap_at_50(self, tmp_path):
        knowledge_dir = tmp_path / "plugins" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        for i in range(60):
            add_memory("p1", f"Insight {i}", source="", base_dir=str(tmp_path))
        result = load_knowledge("p1", str(tmp_path))
        assert len(result["memories"]) == 50

    def test_extract_memories_from_conversation(self, tmp_path):
        knowledge_dir = tmp_path / "plugins" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        messages = [
            {"persona_id": "rook", "persona_name": "Rook", "content": "I realize that composition is more flexible than inheritance."},
            {"persona_id": "elena", "persona_name": "Elena", "content": "That's an interesting point."},
            {"persona_id": "rook", "persona_name": "Rook", "content": "Regular message without insight patterns."},
        ]
        added = extract_memories_from_conversation("rook", messages, str(tmp_path))
        assert len(added) >= 1  # At least the "I realize" message

    def test_list_personas_with_knowledge(self, tmp_path):
        knowledge_dir = tmp_path / "plugins" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        (knowledge_dir / "rook" / "books").mkdir(parents=True)
        (knowledge_dir / "elena" / "books").mkdir(parents=True)
        result = list_personas_with_knowledge(str(tmp_path))
        persona_ids = [p["persona_id"] for p in result]
        assert "rook" in persona_ids
        assert "elena" in persona_ids
        # Should not include __pycache__
        assert "__pycache__" not in persona_ids

    def test_knowledge_prompt_format(self, tmp_path):
        books_dir = tmp_path / "plugins" / "knowledge" / "p1" / "books"
        books_dir.mkdir(parents=True)
        (books_dir / "book.yaml").write_text("""
title: "Sample Book"
key_insights:
  - "Key idea one"
  - "Key idea two"
""")
        add_memory("p1", "I learned from experience", "session", str(tmp_path))
        result = load_knowledge("p1", str(tmp_path))
        prompt = result["knowledge_prompt"]
        assert "[KNOWLEDGE BASE]" in prompt
        assert "[CONVERSATION MEMORIES]" in prompt
        assert "Sample Book" in prompt
        assert "I learned from experience" in prompt


# ─── Integration ──────────────────────────────────────────────────────────

class TestIntegration:
    def test_tool_load_and_execute(self, tmp_path):
        """Full cycle: load tool from YAML -> execute -> get result"""
        tools_dir = tmp_path / "plugins" / "tools"
        tools_dir.mkdir(parents=True)
        (tools_dir / "calculator.yaml").write_text("""
name: calculator
description: Simple calculator
parameters:
  - name: expr
    type: string
    required: true
execution:
  type: python
  code: |
    print(eval("{{expr}}"))
timeout: 10
sandbox: true
""")
        store = ToolStore()
        store.load_all(str(tmp_path))
        assert "calculator" in store.tools
        result = execute_tool_plugin(store.tools["calculator"], {"expr": "2 + 3"}, str(tmp_path))
        assert result["error"] is None
        assert "5" in result["result"]

    def test_knowledge_augments_prompt(self, tmp_path):
        """Books + memories produce a valid knowledge prompt"""
        books_dir = tmp_path / "plugins" / "knowledge" / "test" / "books"
        books_dir.mkdir(parents=True)
        (books_dir / "insights.yaml").write_text("""
title: "Deep Insights"
key_insights:
  - "Think in systems"
""")
        add_memory("test", "Systems thinking matters", "workshop", str(tmp_path))
        persona = {"id": "test", "system_prompt": "You are a thinker."}
        knowledge = load_knowledge("test", str(tmp_path))
        augmented = persona["system_prompt"] + "\n\n" + knowledge["knowledge_prompt"]
        assert "Deep Insights" in augmented
        assert "Think in systems" in augmented
        assert "Systems thinking matters" in augmented
