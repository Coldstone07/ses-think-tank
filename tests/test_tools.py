"""Phase 4.2: External Tool Integration Tests"""
import pytest
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tools import (
    TOOL_DEFINITIONS,
    TOOLS_BY_NAME,
    execute_tool,
    extract_tool_calls,
    extract_tool_calls_from_text,
    build_tool_messages,
    get_tool_instructions,
    get_tool_call_instructions,
)

# ─── Tool definitions ────────────────────────────────────────────────────

class TestToolDefinitions:
    def test_tool_definitions_exist(self):
        assert len(TOOL_DEFINITIONS) == 3

    def test_web_search_definition(self):
        ws = next(t for t in TOOL_DEFINITIONS if t['function']['name'] == 'web_search')
        assert 'description' in ws['function']
        assert 'query' in ws['function']['parameters']['properties']

    def test_read_file_definition(self):
        rf = next(t for t in TOOL_DEFINITIONS if t['function']['name'] == 'read_file')
        assert 'filepath' in rf['function']['parameters']['properties']

    def test_execute_code_definition(self):
        ec = next(t for t in TOOL_DEFINITIONS if t['function']['name'] == 'execute_code')
        assert 'code' in ec['function']['parameters']['properties']

    def test_tools_by_name_lookup(self):
        assert 'web_search' in TOOLS_BY_NAME
        assert 'read_file' in TOOLS_BY_NAME
        assert 'execute_code' in TOOLS_BY_NAME

# ─── execute_tool() ──────────────────────────────────────────────────────

class TestExecuteTool:
    def test_web_search_returns_string(self):
        result = execute_tool('web_search', {'query': 'python asyncio'})
        # Result is a formatted string, not a dict
        assert isinstance(result['result'], str)
        assert len(result['result']) > 0

    def test_web_search_empty_query(self):
        result = execute_tool('web_search', {'query': ''})
        assert 'Empty' in result['result'] or 'error' in result['result'].lower()

    def test_read_file_success(self):
        # Create a temp file in the workspace
        workspace = os.path.join(os.path.dirname(__file__), '..', 'workspace')
        os.makedirs(workspace, exist_ok=True)
        path = os.path.join(workspace, 'test_tool_file.txt')
        with open(path, 'w') as f:
            f.write('hello world\nline 2')
        result = execute_tool('read_file', {'filepath': path})
        assert 'hello world' in result['result']

    def test_read_file_not_found(self):
        result = execute_tool('read_file', {'filepath': '/nonexistent/file.txt'})
        # Path outside workspace is denied, not "not found"
        assert 'DENIED' in result['result'] or 'not found' in result['result'].lower()

    def test_execute_code_returns_string(self):
        result = execute_tool('execute_code', {'code': 'print(2 + 2)'})
        assert isinstance(result['result'], str)

    def test_unknown_tool(self):
        result = execute_tool('nonexistent_tool', {})
        assert result['error'] is not None
        assert 'Unknown tool' in result['error']

# ─── extract_tool_calls() ────────────────────────────────────────────────

class TestExtractToolCalls:
    def test_native_tool_calls(self):
        # extract_tool_calls works on the 'message' dict, not the full response
        message = {
            'tool_calls': [{
                'id': 'call_1',
                'function': {
                    'name': 'web_search',
                    'arguments': json.dumps({'query': 'test'})
                }
            }]
        }
        calls = extract_tool_calls(message)
        assert len(calls) == 1
        assert calls[0]['name'] == 'web_search'
        assert calls[0]['arguments']['query'] == 'test'

    def test_no_tool_calls(self):
        calls = extract_tool_calls({'content': 'hello'})
        assert len(calls) == 0

# ─── extract_tool_calls_from_text() ──────────────────────────────────────

class TestExtractToolCallsFromText:
    def test_single_tool_call(self):
        text = 'Some text\n\nTOOL_CALL: web_search(query="python")\n\nMore text'
        calls = extract_tool_calls_from_text(text)
        assert len(calls) == 1
        assert calls[0]['name'] == 'web_search'
        assert calls[0]['arguments']['query'] == 'python'

    def test_multiple_tool_calls(self):
        text = '''First thought
TOOL_CALL: web_search(query="AI trends")

Second thought
TOOL_CALL: execute_code(code="print('hello')")
'''
        calls = extract_tool_calls_from_text(text)
        assert len(calls) == 2
        assert calls[0]['name'] == 'web_search'
        assert calls[1]['name'] == 'execute_code'

    def test_no_tool_calls_in_text(self):
        text = 'This is just a normal response with no tools.'
        calls = extract_tool_calls_from_text(text)
        assert len(calls) == 0

# ─── build_tool_messages() ───────────────────────────────────────────────

class TestBuildToolMessages:
    def test_build_tool_messages(self):
        msg = build_tool_messages(
            tool_name='web_search',
            tool_result='Search results...',
            tool_error=None,
            tool_call_id='call_1',
        )
        assert msg['role'] == 'tool'
        assert msg['tool_call_id'] == 'call_1'
        assert msg['name'] == 'web_search'

    def test_build_tool_messages_with_error(self):
        msg = build_tool_messages(
            tool_name='read_file',
            tool_result='',
            tool_error='File not found',
            tool_call_id='call_2',
        )
        assert 'ERROR' in msg['content']

# ─── Tool instructions ───────────────────────────────────────────────────

class TestToolInstructions:
    def test_get_tool_instructions(self):
        instructions = get_tool_instructions()
        assert 'web_search' in instructions
        assert 'execute_code' in instructions
        assert 'read_file' in instructions

    def test_get_tool_call_instructions(self):
        instructions = get_tool_call_instructions()
        assert 'TOOL_CALL:' in instructions
        # Contains usage examples
        assert 'web_search(query=' in instructions

# ─── Integration ─────────────────────────────────────────────────────────

class TestIntegration:
    """End-to-end: text extraction -> execute -> result formatting"""
    def test_full_tool_cycle(self):
        llm_text = '''Based on the conversation, let me search for current information.

TOOL_CALL: web_search(query="latest AI research 2025")

I'll also check a file for reference data.

TOOL_CALL: read_file(filepath="workspace/test.txt")
'''
        calls = extract_tool_calls_from_text(llm_text)
        assert len(calls) == 2

        results = []
        for call in calls:
            result = execute_tool(call['name'], call['arguments'])
            results.append(result)

        for call, result in zip(calls, results):
            msg = build_tool_messages(
                tool_name=call['name'],
                tool_result=str(result.get('result', '')),
                tool_error=result.get('error'),
                tool_call_id=call.get('id', ''),
            )
            assert msg['role'] == 'tool'
            assert msg['name'] == call['name']
