"""
Knowledge System — personas read books, build memories, and develop organic personality.

Directory structure:
    plugins/knowledge/
        rook/
            books/
                design-patterns.txt
                clean-architecture.md
            memories.yaml          # organic memories from conversations
        elena/
            books/
                empathy-in-design.txt
            memories.yaml
        ...

Knowledge flows into the persona system prompt as:
[KNOWLEDGE BASE]
Books read: ...
Key insights: ...
[CONVERSATION MEMORIES]
From session X: ...
"""
import os
import yaml
import uuid
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_knowledge(persona_id: str, base_dir: str = ".") -> dict:
    """Load knowledge for a persona: books + memories.

    Returns:
        {
            books: [{title, path, key_insights: [...]}],
            memories: [{date, session_id, insight, source}],
            knowledge_prompt: str  # ready-to-inject text block
        }
    """
    knowledge_dir = Path(base_dir) / "plugins" / "knowledge" / persona_id
    books = _load_books(knowledge_dir)
    memories = _load_memories(knowledge_dir)
    return {
        "books": books,
        "memories": memories,
        "knowledge_prompt": _build_knowledge_prompt(books, memories),
    }


def _load_books(knowledge_dir: Path) -> list:
    """Load books from plugins/knowledge/<persona>/books/."""
    books_dir = knowledge_dir / "books"
    if not books_dir.is_dir():
        return []

    books = []
    for fn in sorted(os.listdir(str(books_dir))):
        if not fn.endswith((".txt", ".md", ".yaml", ".yml")):
            continue
        fpath = books_dir / fn
        try:
            with open(str(fpath), "r", encoding="utf-8") as f:
                content = f.read()

            # For YAML files, extract structured data
            if fn.endswith((".yaml", ".yml")):
                data = yaml.safe_load(content)
                if isinstance(data, dict):
                    title = data.get("title", fn)
                    insights = data.get("key_insights", [])
                    books.append({
                        "title": title,
                        "path": str(fpath),
                        "key_insights": insights,
                        "content_summary": content[:2000],
                    })
                continue

            # For text/markdown, extract title from first line and summarize
            lines = content.strip().split("\n")
            title = lines[0].replace("#", "").strip() if lines else fn
            # Take first 500 chars as summary for the prompt
            summary = content[:500].strip()

            books.append({
                "title": title,
                "path": str(fpath),
                "key_insights": [],
                "content_summary": summary,
            })
        except Exception:
            pass

    return books


def _load_memories(knowledge_dir: Path) -> list:
    """Load memories from plugins/knowledge/<persona>/memories.yaml."""
    mem_file = knowledge_dir / "memories.yaml"
    if not mem_file.is_file():
        return []

    try:
        with open(str(mem_file), "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return data.get("memories", [])
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _build_knowledge_prompt(books: list, memories: list) -> str:
    """Build a knowledge block to inject into the system prompt."""
    if not books and not memories:
        return ""

    parts = []

    if books:
        parts.append("[KNOWLEDGE BASE]")
        parts.append("You have studied the following works and internalized their key ideas:")
        for book in books:
            parts.append(f"\n- \"{book['title']}\"")
            if book.get("key_insights"):
                for insight in book["key_insights"][:3]:
                    parts.append(f"  * {insight}")
            elif book.get("content_summary"):
                summary = book["content_summary"][:200]
                parts.append(f"  * Key takeaway: {summary}...")
        parts.append("")

    if memories:
        parts.append("[CONVERSATION MEMORIES]")
        parts.append("From past conversations, you've learned:")
        for mem in memories[-10:]:  # last 10 memories
            date = mem.get("date", "")
            insight = mem.get("insight", "")
            source = mem.get("source", "")
            if date and insight:
                parts.append(f"- {date}: {insight}" + (f" (from {source})" if source else ""))
        parts.append("")

    parts.append("Use these experiences to inform your thinking, but don't just repeat them mechanically. Let them shape how you approach problems organically.")

    return "\n".join(parts)


def add_memory(persona_id: str, insight: str, source: str = "", base_dir: str = ".") -> dict:
    """Add a memory to a persona's memories.yaml."""
    knowledge_dir = Path(base_dir) / "plugins" / "knowledge" / persona_id
    mem_file = knowledge_dir / "memories.yaml"
    knowledge_dir.mkdir(parents=True, exist_ok=True)

    # Load existing
    memories = []
    if mem_file.is_file():
        try:
            with open(str(mem_file), "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                memories = data.get("memories", [])
            elif isinstance(data, list):
                memories = data
        except Exception:
            pass

    # Add new memory
    memory = {
        "id": uuid.uuid4().hex[:8],
        "date": time.strftime("%Y-%m-%d"),
        "insight": insight,
        "source": source,
        "timestamp": time.time(),
    }
    memories.append(memory)

    # Cap at 50 memories
    if len(memories) > 50:
        memories = memories[-50:]

    # Save
    with open(str(mem_file), "w", encoding="utf-8") as f:
        yaml.dump({"memories": memories}, f, default_flow_style=False, sort_keys=False)

    return memory


def extract_memories_from_conversation(persona_id: str, messages: list, base_dir: str = ".") -> list:
    """Extract meaningful memories from a conversation for a persona.

    Looks for: key decisions, insights gained, corrections received, strong opinions formed.
    Returns list of added memories.
    """
    # Simple heuristic: look for messages from this persona that contain
    # insight-like patterns (I realize, I've learned, this changes my view, etc.)
    insight_patterns = [
        "i realize", "i've learned", "i didn't consider", "that's a good point",
        "i hadn't thought", "this changes", "upon reflection", "i see now",
        "you're right", "i agree", "that makes sense", "i hadn't considered",
    ]

    added = []
    for msg in messages:
        if msg.get("persona_id") != persona_id:
            continue
        content = msg.get("content", "").lower()
        if any(p in content for p in insight_patterns):
            # Extract the insight (first 200 chars of the message)
            insight = msg.get("content", "")[:200].strip()
            source = f"session with {', '.join(set(m.get('persona_name', '') for m in messages if m.get('persona_id') != persona_id))}"
            mem = add_memory(persona_id, insight, source, base_dir)
            added.append(mem)

    return added


def list_personas_with_knowledge(base_dir="."):
    """List all personas that have knowledge directories."""
    knowledge_dir = Path(base_dir).resolve() / "plugins" / "knowledge"
    if not knowledge_dir.is_dir():
        return []

    personas = []
    for entry in sorted(os.listdir(str(knowledge_dir))):
        ep = knowledge_dir / entry
        if not ep.is_dir() or entry.startswith("__"):
            continue
        books_dir = ep / "books"
        mem_file = ep / "memories.yaml"
        personas.append({
            "persona_id": entry,
            "book_count": len(list(books_dir.glob("*"))) if books_dir.is_dir() else 0,
            "has_memories": mem_file.is_file(),
        })

    return personas
