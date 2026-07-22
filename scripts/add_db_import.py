#!/usr/bin/env python3
"""Add 'from db import get_connection' after the last complete import block."""
import re
import os

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
files = [
    "app.py", "platform_scale.py", "auth.py", "settings.py",
    "research.py", "collaboration.py", "export.py", "intelligence.py",
    "evaluation_dashboard.py", "persona_evolution.py",
]

for fname in files:
    path = os.path.join(PROJECT, fname)
    with open(path, "r") as f:
        lines = f.readlines()

    # Find the end of the last import block
    last_import_end = -1
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        # Match top-level import (not indented)
        if re.match(r"^(?:import |from )", line):
            # Check if it's a multi-line import (ends with open paren)
            if "(" in line and not line.rstrip().endswith(")"):
                # Skip until closing paren
                i += 1
                while i < len(lines):
                    if ")" in lines[i]:
                        last_import_end = i
                        break
                    i += 1
            else:
                last_import_end = i
        i += 1

    if last_import_end >= 0:
        lines.insert(last_import_end + 1, "from db import get_connection\n")
        with open(path, "w") as f:
            f.writelines(lines)
        print(f"  OK {fname}: inserted after line {last_import_end + 1}")
    else:
        print(f"  SKIP {fname}: no import found")
