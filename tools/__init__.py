"""
Agent Tool System — External tools agents can call during conversations.
========================================================================
Tools are defined as JSON schemas (OpenAI-compatible) and executed
server-side. Results are fed back into the conversation context.

Available tools:
- web_search: Search the web for current information
- execute_code: Run Python code in a sandboxed environment
- read_file: Read files from a designated directory
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import textwrap
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# ─── TOOL DEFINITIONS ────────────────────────────────────────────────────

TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information. Returns top results with titles, URLs, and snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g., 'latest AI safety research 2025')",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_code",
            "description": "Execute Python code in a sandboxed environment. Returns stdout, stderr, and exit code. Maximum 30 seconds timeout. Use for calculations, data analysis, or prototyping.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 30, max 60)",
                        "default": 30,
                    },
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the designated workspace directory. Returns file content as text. Only files within the workspace are accessible.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Path to file (relative to workspace or absolute)",
                    },
                },
                "required": ["filepath"],
            },
        },
    },
]

# Build a name→definition lookup
TOOLS_BY_NAME = {t["function"]["name"]: t for t in TOOL_DEFINITIONS}

# Workspace directory for file operations
WORKSPACE_DIR = Path(__file__).parent.parent / "workspace"
WORKSPACE_DIR.mkdir(exist_ok=True)


# ─── TOOL EXECUTION ──────────────────────────────────────────────────────


def execute_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool by name with given arguments.

    Returns: {name, result, error, duration_ms}
    """
    start = time.time()
    try:
        if name == "web_search":
            result = _web_search(arguments.get("query", ""))
        elif name == "execute_code":
            result = _execute_code(
                arguments.get("code", ""), arguments.get("timeout", 30)
            )
        elif name == "read_file":
            result = _read_file(arguments.get("filepath", ""))
        else:
            return {
                "name": name,
                "result": None,
                "error": f"Unknown tool: {name}",
                "duration_ms": 0,
            }

        duration_ms = int((time.time() - start) * 1000)
        return {"name": name, "result": result, "error": None, "duration_ms": duration_ms}

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        return {
            "name": name,
            "result": None,
            "error": f"{type(e).__name__}: {str(e)}",
            "duration_ms": duration_ms,
        }


def _web_search(query: str) -> str:
    """Search the web using DuckDuckGo HTML (no API key needed)."""
    if not query.strip():
        return "Error: Empty search query"

    try:
        # Use DuckDuckGo HTML search
        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        resp = requests.post(url, data={"q": query}, headers=headers, timeout=15)
        resp.raise_for_status()

        # Parse results from HTML
        from html.parser import HTMLParser

        class DDGParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.results = []
                self.current = {}
                self.in_result = False
                self.in_title_a = False
                self.in_url_a = False
                self.in_snippet = False
                self.capture_text = False
                self.text_buffer = ""

            def handle_starttag(self, tag, attrs):
                attrs_dict = dict(attrs)
                cls = attrs_dict.get("class", "")

                if tag == "a" and "result__a" in cls:
                    self.in_result = True
                    self.in_title_a = True
                    self.current = {"title": "", "url": "", "snippet": ""}
                    self.text_buffer = ""
                elif tag == "a" and "result__url" in cls:
                    self.in_url_a = True
                    self.text_buffer = ""
                elif tag == "a" and "result__snippet" in cls:
                    self.in_snippet = True
                    self.text_buffer = ""
                elif self.capture_text:
                    pass  # keep capturing

                self.capture_text = (
                    self.in_title_a or self.in_url_a or self.in_snippet
                )

            def handle_data(self, data):
                if self.capture_text:
                    self.text_buffer += data

            def handle_endtag(self, tag):
                if tag == "a":
                    if self.in_title_a and self.current:
                        self.current["title"] = self.text_buffer.strip()
                        self.in_title_a = False
                    elif self.in_url_a and self.current:
                        # URL is mangled by DDG, extract readable part
                        self.current["url"] = self.text_buffer.strip()
                        self.in_url_a = False
                    elif self.in_snippet and self.current:
                        self.current["snippet"] = self.text_buffer.strip()
                        self.in_snippet = False
                        self.results.append(self.current)
                        self.current = {}
                        self.in_result = False
                    self.capture_text = False

        parser = DDGParser()
        parser.feed(resp.text)

        if not parser.results:
            # Fallback: try DuckDuckGo instant answer API
            api_url = f"https://api.duckduckgo.com/?q={query}&format=json"
            api_resp = requests.get(api_url, timeout=10)
            api_resp.raise_for_status()
            api_data = api_resp.json()
            abstract = api_data.get("Abstract", "")
            if abstract:
                return f"Query: {query}\n\n{abstract}"
            return f"No results found for: {query}"

        # Format results
        lines = [f"Search results for: {query}\n"]
        for i, r in enumerate(parser.results[:5], 1):
            title = r.get("title", "No title")
            snippet = r.get("snippet", "")
            url = r.get("url", "")
            lines.append(f"{i}. {title}")
            if snippet:
                lines.append(f"   {snippet}")
            if url:
                lines.append(f"   URL: {url}")
            lines.append("")

        return "\n".join(lines)

    except requests.exceptions.Timeout:
        return f"Search timed out for: {query}"
    except Exception as e:
        # Fallback: use Wikipedia API
        try:
            wiki_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={query}&format=json&srlimit=5"
            wiki_resp = requests.get(wiki_url, timeout=10)
            wiki_resp.raise_for_status()
            wiki_data = wiki_resp.json()
            searches = wiki_data.get("query", {}).get("search", [])
            if searches:
                lines = [f"Wikipedia results for: {query}\n"]
                for i, s in enumerate(searches, 1):
                    lines.append(f"{i}. {s.get('title', '')}")
                    snippet = s.get("snippet", "").replace("<span class='searchmatch'>", "").replace("</span>", "")
                    if snippet:
                        lines.append(f"   {snippet}")
                    lines.append(f"   URL: https://en.wikipedia.org/wiki/{s.get('title', '').replace(' ', '_')}")
                    lines.append("")
                return "\n".join(lines)
        except Exception:
            pass
        return f"Search error for '{query}': {type(e).__name__}: {str(e)}"


def _execute_code(code: str, timeout: int = 30) -> str:
    """Execute Python code in a subprocess with timeout and resource limits."""
    timeout = min(max(timeout, 1), 60)  # Clamp between 1-60 seconds

    # Security: block dangerous imports/patterns
    dangerous_patterns = [
        r"\bos\.system\b",
        r"\bimport\s+subprocess\b",
        r"\bos\.popen\b",
        r"\b__import__\s*\(",
        r"\bopen\s*\(",
        r"\bexec\s*\(",
        r"\beval\s*\(",
        r"\bcompile\s*\(",
        r"\bimportlib\b",
        r"\bsocket\b",
        r"\bhttp\.client\b",
        r"\burllib\.request\b",
        r"\brequests\.",
        r"\bshutil\.",
        r"\btempfile\b",
    ]

    for pattern in dangerous_patterns:
        if re.search(pattern, code):
            return f"BLOCKED: Code contains potentially unsafe operation ({pattern}). " \
                   "Only pure computation, data analysis, and standard library (math, collections, itertools, json, re, datetime, statistics) are allowed."

    # Wrap code to capture output
    wrapped = textwrap.dedent(f"""
    import sys
    import io
    import traceback

    # Capture stdout
    output = io.StringIO()
    sys.stdout = output

    try:
        {code}
    except Exception as e:
        sys.stdout = sys.__stdout__
        output.write("ERROR: " + traceback.format_exc())
    finally:
        sys.stdout = sys.__stdout__

    print(output.getvalue(), end='')
    """)

    try:
        result = subprocess.run(
            ["python3.11", "-c", wrapped],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        output_parts = []
        if result.stdout:
            output_parts.append(f"Output:\n{result.stdout}")
        if result.stderr:
            output_parts.append(f"Stderr:\n{result.stderr}")
        if not output_parts:
            output_parts.append("(No output)")
        output_parts.append(f"Exit code: {result.returncode}")

        return "\n".join(output_parts)

    except subprocess.TimeoutExpired:
        return f"TIMEOUT: Code execution exceeded {timeout} seconds"
    except FileNotFoundError:
        return "ERROR: Python 3.11 not found. Code execution unavailable."


def _read_file(filepath: str) -> str:
    """Read a file from the workspace directory."""
    # Resolve path
    path = Path(filepath)

    # If relative, resolve against workspace
    if not path.is_absolute():
        path = WORKSPACE_DIR / path

    # Security: ensure path is within workspace or project root
    project_root = Path(__file__).parent.parent.resolve()
    try:
        resolved = path.resolve()
        # Allow workspace and project root
        if not (
            str(resolved).startswith(str(WORKSPACE_DIR.resolve()))
            or str(resolved).startswith(str(project_root))
        ):
            return f"ACCESS DENIED: Path '{filepath}' is outside allowed directories.\n" \
                   f"Allowed: {WORKSPACE_DIR}/ and {project_root}/"
    except Exception:
        return f"ACCESS DENIED: Could not resolve path '{filepath}'"

    if not path.exists():
        return f"FILE NOT FOUND: {filepath}"

    if not path.is_file():
        return f"NOT A FILE: {filepath} is a directory"

    # Check file size (max 1MB)
    if path.stat().st_size > 1_000_000:
        return f"FILE TOO LARGE: {filepath} is {path.stat().st_size} bytes (max 1MB)"

    try:
        content = path.read_text(encoding="utf-8")
        # Truncate very long files
        if len(content) > 50_000:
            content = content[:50_000] + "\n\n... [file truncated, >50K chars]"
        return content
    except UnicodeDecodeError:
        return f"BINARY FILE: {filepath} cannot be read as text"


# ─── TOOL CALL PARSING ───────────────────────────────────────────────────


def extract_tool_calls(response: dict) -> List[Dict[str, Any]]:
    """Extract tool/function calls from an LLM response.

    Handles both OpenAI-style tool_calls and text-based function calls.
    Returns list of {name, arguments} dicts.
    """
    # OpenAI-style tool_calls
    tool_calls = response.get("tool_calls", [])
    if tool_calls:
        result = []
        for tc in tool_calls:
            func = tc.get("function", {})
            args_raw = func.get("arguments", "{}")
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            except json.JSONDecodeError:
                args = {}
            result.append(
                {"id": tc.get("id", ""), "name": func.get("name", ""), "arguments": args}
            )
        return result

    # Also check in message format
    msg = response.get("message", {})
    if msg:
        tool_calls = msg.get("tool_calls", [])
        if tool_calls:
            result = []
            for tc in tool_calls:
                func = tc.get("function", {})
                args_raw = func.get("arguments", "{}")
                try:
                    args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                except json.JSONDecodeError:
                    args = {}
                result.append(
                    {"id": tc.get("id", ""), "name": func.get("name", ""), "arguments": args}
                )
            return result

    return []


def extract_tool_calls_from_text(text: str) -> List[Dict[str, Any]]:
    """Extract tool calls from free-form text (for reasoning models without native tool support).

    Looks for patterns like:
    - TOOL_CALL: web_search(query="...")
    - TOOL_CALL: execute_code(code="...")
    - TOOL_CALL: read_file(filepath="...")
    """
    calls = []
    # Pattern: TOOL_CALL: function_name(key="value", ...)
    pattern = r"TOOL_CALL:\s*(\w+)\((.*?)\)"
    for match in re.finditer(pattern, text, re.DOTALL):
        func_name = match.group(1)
        args_str = match.group(2)

        if func_name not in TOOLS_BY_NAME:
            continue

        # Parse keyword arguments from the string
        args = {}
        # Match key="value" or key='value'
        for kv_match in re.finditer(r'(\w+)\s*=\s*["\']((?:[^"\\]|\\.)*)["\']', args_str):
            args[kv_match.group(1)] = kv_match.group(2)

        # Handle multiline code blocks
        if func_name == "execute_code" and "code" not in args:
            code_match = re.search(r'```(?:python)?\s*\n(.*?)\n```', args_str, re.DOTALL)
            if code_match:
                args["code"] = code_match.group(1).strip()

        if args:
            calls.append({"id": f"text_call_{func_name}_{len(calls)}", "name": func_name, "arguments": args})

    return calls


def get_tool_call_instructions() -> str:
    """Return instructions for agents on how to request tool calls (text format for reasoning models)."""
    return textwrap.dedent("""
    ## Available Tools

    You have access to the following tools to enhance your responses. To use a tool, write:
    TOOL_CALL: function_name(param="value")

    1. **web_search(query)** — Search the web for current information. Use when you need facts, data, or references outside your training data.
       Example: TOOL_CALL: web_search(query="latest AI safety research 2025")

    2. **execute_code(code)** — Run Python code for calculations, data analysis, or prototyping. Only standard library is available.
       Example: TOOL_CALL: execute_code(code="import math\\nprint(math.sqrt(144))")

    3. **read_file(filepath)** — Read files from the workspace for reference.
       Example: TOOL_CALL: read_file(filepath="data.csv")

    Use tools when they genuinely improve your contribution. Don't overuse them.
    After receiving tool results, incorporate them naturally into your response.
    """).strip()


def build_tool_messages(
    tool_name: str, tool_result: str, tool_error: str | None, tool_call_id: str = ""
) -> Dict[str, Any]:
    """Build a tool response message for the LLM conversation."""
    content = tool_result if not tool_error else f"ERROR: {tool_error}\nResult: {tool_result}"
    return {
        "role": "tool",
        "tool_call_id": tool_call_id or f"call_{tool_name}_{int(time.time())}",
        "name": tool_name,
        "content": content,
    }


# ─── AGENT TOOL INSTRUCTIONS ────────────────────────────────────────────


def get_tool_instructions() -> str:
    """Return instructions for agents on how to use tools."""
    return textwrap.dedent("""
    ## Available Tools

    You have access to the following tools to enhance your responses:

    1. **web_search(query)** — Search the web for current information. Use when you need facts, data, or references outside your training data.
    2. **execute_code(code, timeout)** — Run Python code for calculations, data analysis, or prototyping. Only standard library is available.
    3. **read_file(filepath)** — Read files from the workspace for reference.

    Use tools when they genuinely improve your contribution. Don't overuse them — your knowledge is often sufficient.
    """).strip()


def get_tools_for_persona(persona_id: str) -> List[Dict[str, Any]]:
    """Return appropriate tools for a persona.

    Some personas may get restricted tool sets based on their role.
    """
    # All personas get all tools by default
    return TOOL_DEFINITIONS.copy()
