"""Tool Plugin System - YAML-based tool definitions with python/shell/http execution."""

import os, time, yaml, json, subprocess, textwrap
from pathlib import Path

TOOL_REQUIRED = {"name", "description", "parameters", "execution"}
EXECUTION_TYPES = {"python", "shell", "http"}


def validate_tool(data):
    errors = []
    for field in TOOL_REQUIRED:
        if field not in data:
            errors.append(f"Missing required field: {field}")
        elif field == "parameters":
            if not isinstance(data[field], list):
                errors.append("parameters must be a list")
        elif not data[field]:
            errors.append(f"Missing required field: {field}")
    if "parameters" in data and isinstance(data["parameters"], list):
        for p in data["parameters"]:
            if not isinstance(p, dict) or "name" not in p:
                errors.append("each parameter must have a name field")
    if "execution" in data:
        ec = data["execution"]
        if not isinstance(ec, dict):
            errors.append("execution must be a mapping")
        elif "type" not in ec:
            errors.append("execution.type is required")
        elif ec["type"] not in EXECUTION_TYPES:
            errors.append(f"execution.type must be one of {EXECUTION_TYPES}")
        else:
            t = ec["type"]
            if t == "python" and "code" not in ec:
                errors.append("execution.code required for python type")
            elif t == "shell" and "command" not in ec:
                errors.append("execution.command required for shell type")
            elif t == "http" and "url" not in ec:
                errors.append("execution.url required for http type")
    return errors


def tool_to_openai_schema(td):
    params = td.get("parameters", [])
    props, req = {}, []
    for p in params:
        prop = {"type": p.get("type", "string")}
        if "description" in p:
            prop["description"] = p["description"]
        if "default" in p:
            prop["default"] = p["default"]
        props[p["name"]] = prop
        if p.get("required", False):
            req.append(p["name"])
    return {
        "type": "function",
        "function": {
            "name": td["name"],
            "description": td["description"],
            "parameters": {"type": "object", "properties": props, "required": req},
        },
    }


def execute_tool_plugin(td, args, base_dir="."):
    ec = td.get("execution", {})
    et = ec.get("type", "python")
    timeout = td.get("timeout", 30)
    sandbox = td.get("sandbox", True)
    try:
        if et == "python":
            return _exec_python(ec, args, base_dir, timeout, sandbox)
        elif et == "shell":
            return _exec_shell(ec, args, base_dir, timeout)
        elif et == "http":
            return _exec_http(ec, args, timeout)
        return {"result": None, "error": f"Unknown type: {et}"}
    except Exception as e:
        return {"result": None, "error": "Execution error"}


def _exec_python(ec, args, base_dir, timeout, sandbox):
    code = ec.get("code", "")
    # Safe argument substitution — raw strings inline, repr for numbers/booleans
    for k, v in args.items():
        if isinstance(v, str):
            code = code.replace("{{" + k + "}}", v)
        else:
            code = code.replace("{{" + k + "}}", repr(v))
    workspace = Path(base_dir).resolve() / "workspace"
    workspace.mkdir(exist_ok=True)
    # Build wrapper script — write errors to stderr so they're detected
    lines = [
        "import sys, io",
        "safe_builtins = dict(print=print, len=len, str=str, int=int, float=float, list=list, dict=dict, tuple=tuple, set=set, bool=bool, range=range, enumerate=enumerate, zip=zip, map=map, filter=filter, sorted=sorted, reversed=reversed, any=any, all=all, sum=sum, min=min, max=max, abs=abs, round=round, eval=eval)",
    ]
    if sandbox:
        lines.append(f'import os; os.chdir({str(workspace)!r})')
    lines += [
        "output = io.StringIO()",
        "errout = io.StringIO()",
        "sys.stdout = output",
        "try:",
        f"    exec({code!r}, dict(__builtins__=safe_builtins))",
        "except Exception as e:",
        "    sys.stdout = sys.__stdout__",
        "    import traceback; traceback.print_exc(file=errout)",
        "finally:",
        "    sys.stdout = sys.__stdout__",
        "result = output.getvalue()",
        "err = errout.getvalue()",
        "if result: sys.stdout.write(result)",
        "if err: sys.stderr.write(err)",
    ]
    wrapper = "\n".join(lines)
    env = {**os.environ, "BASE_DIR": str(Path(base_dir).resolve())}
    try:
        r = subprocess.run(
            ["python", "-c", wrapper],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(workspace),
        )
    except subprocess.TimeoutExpired:
        return {"result": None, "error": f"Execution timed out after {timeout}s"}
    if r.stderr.strip():
        return {"result": r.stdout.strip()[:4000] if r.stdout.strip() else None, "error": r.stderr.strip()[-500:]}
    out = r.stdout.strip()
    return {"result": out[:4000] if out else "(no output)", "error": None}


def _exec_shell(ec, args, base_dir, timeout):
    import shlex

    cmd = ec.get("command", "")
    for k, v in args.items():
        cmd = cmd.replace("{{" + k + "}}", shlex.quote(str(v)))
    workspace = Path(base_dir).resolve() / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    shell_cmd = ["cmd", "/c", cmd] if os.name == "nt" else ["sh", "-c", cmd]
    r = subprocess.run(
        shell_cmd,
        shell=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(workspace),
    )
    if r.returncode != 0:
        return {"result": None, "error": r.stderr.strip()[-500:]}
    out = r.stdout.strip()
    return {"result": out[:4000] if out else "(no output)", "error": None}


def _exec_http(ec, args, timeout):
    import requests as req

    url = ec.get("url", "")
    method = ec.get("method", "GET").upper()
    headers = ec.get("headers", {})
    body = ec.get("body")
    try:
        url = url.format(**args)
    except KeyError as e:
        return {"result": None, "error": f"Missing argument: {e}"}
    if body:
        try:
            body = body.format(**args)
        except KeyError:
            pass
    try:
        resp = req.request(
            method,
            url,
            headers=headers,
            timeout=timeout,
            json=json.loads(body)
            if (body and method in ("POST", "PUT", "PATCH"))
            else None,
        )
        resp.raise_for_status()
        return {"result": resp.text[:4000], "error": None}
    except req.RequestException as e:
        return {"result": None, "error": "HTTP error"}


class ToolStore:
    def __init__(self):
        self.tools = {}
        self.files = {}
        self.errors = []

    def load_all(self, base_dir=".", tools_dir=None):
        self.tools = {}
        self.files = {}
        self.errors = []
        td = Path(tools_dir) if tools_dir else (Path(base_dir) / "plugins" / "tools")
        if not td.is_dir():
            return {"loaded": 0, "errors": 0, "tools": [], "errors_detail": []}
        for fn in sorted(os.listdir(str(td))):
            if not fn.endswith((".yaml", ".yml")):
                continue
            fp = str(td / fn)
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    raw = f.read()
                data = yaml.safe_load(raw)
                if not isinstance(data, dict):
                    self.errors.append(
                        {"file": fp, "error": "YAML root must be a mapping"}
                    )
                    continue
                errs = validate_tool(data)
                if errs:
                    self.errors.append({"file": fp, "error": "; ".join(errs)})
                    continue
                self.tools[data["name"]] = data
                self.files[fp] = {"loaded_at": time.time(), "hash": hash(raw)}
            except yaml.YAMLError as e:
                self.errors.append({"file": fp, "error": f"YAML parse: {e}"})
            except Exception as e:
                self.errors.append({"file": fp, "error": "Load failed"})
        return {
            "loaded": len(self.tools),
            "errors": len(self.errors),
            "tools": list(self.tools.keys()),
            "errors_detail": self.errors,
        }

    def needs_reload(self, base_dir="."):
        td = Path(base_dir) / "plugins" / "tools"
        if not td.is_dir():
            return False
        for fn in os.listdir(str(td)):
            if not fn.endswith((".yaml", ".yml")) or fn.startswith("__"):
                continue
            fp = str(td / fn)
            if fp not in self.files:
                return True
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    if hash(f.read()) != self.files[fp]["hash"]:
                        return True
            except Exception:
                pass
        for fp in self.files:
            if not os.path.exists(fp):
                return True
        return False

    def get_openai_schemas(self):
        return [tool_to_openai_schema(t) for t in self.tools.values()]

    def info(self):
        return {
            "tools": [
                {
                    "name": n,
                    "description": t["description"],
                    "execution_type": t.get("execution", {}).get("type"),
                    "parameters": [p["name"] for p in t.get("parameters", [])],
                }
                for n, t in self.tools.items()
            ],
            "total": len(self.tools),
            "errors": self.errors,
        }


tool_store = ToolStore()
