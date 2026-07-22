#!/usr/bin/env python3
"""Replace sqlite3.connect() with db.get_connection() across the codebase."""
import re
import os

PROJECT = os.path.dirname(os.path.abspath(__file__))
files = [
    "app.py", "platform_scale.py", "auth.py", "settings.py",
    "research.py", "collaboration.py", "export.py", "intelligence.py",
    "evaluation_dashboard.py", "persona_evolution.py",
]

for fname in files:
    path = os.path.join(PROJECT, fname)
    if not os.path.exists(path):
        continue

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace sqlite3.connect(str(X)) with db.get_connection(X)
    # Pattern: sqlite3.connect(str(SOME_PATH))
    content_new = re.sub(
        r'sqlite3\.connect\(str\(([^)]+)\)\)',
        r'db.get_connection(\1)',
        content
    )

    # Also handle: sqlite3.connect(SOME_PATH) without str()
    content_new = re.sub(
        r'sqlite3\.connect\(([^)]+)\)',
        r'db.get_connection(\1)',
        content_new
    )

    if content_new != content:
        # Add import if not present
        if "from db import" not in content_new and "import db" not in content_new:
            # Add after existing imports
            lines = content_new.split("\n")
            insert_idx = 0
            for i, line in enumerate(lines):
                if line.startswith("import ") or line.startswith("from "):
                    insert_idx = i + 1
                else:
                    break
            lines.insert(insert_idx, "from db import get_connection")
            content_new = "\n".join(lines)

        changes = content.count("sqlite3.connect") - content_new.count("sqlite3.connect")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content_new)
        print(f"✓ {fname}: replaced {changes} sqlite3.connect calls")
    else:
        print(f"  {fname}: no changes needed")

print("\nDone!")
