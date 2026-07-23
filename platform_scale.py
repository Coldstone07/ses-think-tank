"""
Platform & Scale — Phase 5.6

Prometheus metrics, structured logging, API-first headless mode,
and plugin marketplace registry.
"""
import os
import time
import json
import secrets
import sqlite3
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
from collections import defaultdict
from db import get_connection

MEMORY_DB_PATH = Path(os.environ.get("SES_MEMORY_DB", "data/memory.db"))
MARKETPLACE_DB_PATH = Path(os.environ.get("SES_MARKETPLACE_DB", "data/marketplace.db"))


def _memory_db_path() -> Path:
    return Path(os.environ.get("SES_MEMORY_DB", "data/memory.db"))


def _marketplace_db_path() -> Path:
    return Path(os.environ.get("SES_MARKETPLACE_DB", "data/marketplace.db"))


# ─── PROMETHEUS METRICS ─────────────────────────────────────────────────────

class MetricsCollector:
    """In-process metrics collector with Prometheus-compatible output."""

    def __init__(self):
        self._counters = defaultdict(int)
        self._gauges = defaultdict(float)
        self._histograms = defaultdict(list)
        self._labels = defaultdict(dict)
        self._lock = threading.Lock()
        self._start_time = time.time()

    def increment_counter(self, name: str, value: int = 1, labels: dict = None):
        """Increment a counter metric."""
        with self._lock:
            key = self._make_key(name, labels)
            self._counters[key] += value
            if labels:
                self._labels[key] = labels

    def set_gauge(self, name: str, value: float, labels: dict = None):
        """Set a gauge metric."""
        with self._lock:
            key = self._make_key(name, labels)
            self._gauges[key] = value
            if labels:
                self._labels[key] = labels

    def observe_histogram(self, name: str, value: float, labels: dict = None):
        """Record a histogram observation."""
        with self._lock:
            key = self._make_key(name, labels)
            self._histograms[key].append(value)
            if labels:
                self._labels[key] = labels

    def _make_key(self, name: str, labels: dict = None) -> str:
        if not labels:
            return name
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def get_prometheus_text(self) -> str:
        """Export metrics in Prometheus text format."""
        lines = []
        uptime = time.time() - self._start_time

        # Uptime gauge
        lines.append("# HELP ses_uptime_seconds Application uptime in seconds")
        lines.append("# TYPE ses_uptime_seconds gauge")
        lines.append(f"ses_uptime_seconds {uptime:.2f}")
        lines.append("")

        # Counters
        counter_names = set(k.split("{")[0] for k in self._counters)
        for name in counter_names:
            lines.append(f"# HELP ses_{name}_total Counter for {name}")
            lines.append(f"# TYPE ses_{name}_total counter")
            for key, value in self._counters.items():
                if key.startswith(name):
                    lines.append(f"ses_{key}_total {value}")
            lines.append("")

        # Gauges
        gauge_names = set(k.split("{")[0] for k in self._gauges)
        for name in gauge_names:
            lines.append(f"# HELP ses_{name} Gauge for {name}")
            lines.append(f"# TYPE ses_{name} gauge")
            for key, value in self._gauges.items():
                if key.startswith(name):
                    lines.append(f"ses_{key} {value:.4f}")
            lines.append("")

        # Histograms (summary stats)
        hist_names = set(k.split("{")[0] for k in self._histograms)
        for name in hist_names:
            lines.append(f"# HELP ses_{name}_seconds Histogram for {name}")
            lines.append(f"# TYPE ses_{name}_seconds histogram")
            for key, values in self._histograms.items():
                if key.startswith(name):
                    if values:
                        count = len(values)
                        total = sum(values)
                        avg = total / count
                        lines.append(f"ses_{key}_count {count}")
                        lines.append(f"ses_{key}_sum {total:.4f}")
                        lines.append(f"ses_{key}_avg {avg:.4f}")
            lines.append("")

        return "\n".join(lines)

    def get_json(self) -> dict:
        """Export metrics as JSON."""
        return {
            "uptime": round(time.time() - self._start_time, 2),
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {
                k: {
                    "count": len(v),
                    "sum": round(sum(v), 4),
                    "avg": round(sum(v) / len(v), 4) if v else 0,
                    "min": round(min(v), 4) if v else 0,
                    "max": round(max(v), 4) if v else 0,
                }
                for k, v in self._histograms.items()
            },
        }


# Global metrics instance
metrics = MetricsCollector()


# ─── STRUCTURED LOGGING ─────────────────────────────────────────────────────

class StructuredLogger:
    """Structured JSON logger with levels and rotation."""

    def __init__(self, log_file: str = "data/app.log", max_size: int = 10 * 1024 * 1024):
        self.log_file = log_file
        self.max_size = max_size
        self._lock = threading.Lock()
        # Ensure directory exists
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

    def log(self, level: str, message: str, **kwargs):
        """Write a structured log entry."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message,
            **kwargs,
        }
        with self._lock:
            # Rotate if needed
            self._rotate()
            with open(self.log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")

    def _rotate(self):
        """Rotate log file if it exceeds max size."""
        try:
            if os.path.exists(self.log_file) and os.path.getsize(self.log_file) > self.max_size:
                backup = f"{self.log_file}.1"
                os.replace(self.log_file, backup)
        except Exception:
            pass

    def info(self, message: str, **kwargs):
        self.log("INFO", message, **kwargs)

    def warn(self, message: str, **kwargs):
        self.log("WARN", message, **kwargs)

    def error(self, message: str, **kwargs):
        self.log("ERROR", message, **kwargs)

    def debug(self, message: str, **kwargs):
        self.log("DEBUG", message, **kwargs)

    def get_recent(self, lines: int = 100) -> List[dict]:
        """Get recent log entries."""
        if not os.path.exists(self.log_file):
            return []
        with open(self.log_file, "r") as f:
            all_lines = f.readlines()
        entries = []
        for line in all_lines[-lines:]:
            try:
                entries.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                pass
        return entries

    def get_stats(self) -> dict:
        """Get log statistics."""
        entries = self.get_recent(10000)
        stats = {"total": len(entries), "levels": defaultdict(int)}
        for e in entries:
            stats["levels"][e.get("level", "UNKNOWN")] += 1
        stats["levels"] = dict(stats["levels"])
        return stats


# Global logger
logger = StructuredLogger()


# ─── API-FIRST MODE (HEADLESS REST) ─────────────────────────────────────────

class APIRouter:
    """API-first router for headless REST operations."""

    def __init__(self):
        self._routes = {}
        self._middleware = []

    def use(self, middleware):
        """Add middleware."""
        self._middleware.append(middleware)

    def route(self, method: str, path: str):
        """Decorator to register a route."""
        def decorator(func):
            key = f"{method}:{path}"
            self._routes[key] = func
            return func
        return decorator

    def handle(self, method: str, path: str, body: dict = None) -> dict:
        """Handle a request through the router."""
        key = f"{method}:{path}"
        handler = self._routes.get(key)
        if not handler:
            return {"status": 404, "error": f"No handler for {method} {path}"}

        # Run middleware
        for mw in self._middleware:
            result = mw(method, path, body)
            if result:
                return result

        # Call handler
        try:
            return handler(body or {})
        except Exception as e:
            return {"status": 500, "error": str(e)}

    def get_routes(self) -> List[dict]:
        """List all registered routes."""
        return [{"method": k.split(":")[0], "path": k.split(":")[1], "key": k}
                for k in sorted(self._routes.keys())]


# ─── PLUGIN MARKETPLACE ─────────────────────────────────────────────────────

def init_marketplace_schema():
    """Create marketplace tables."""
    conn = get_connection(str(_marketplace_db_path()))
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS plugin_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plugin_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            category TEXT DEFAULT 'tool',
            version TEXT DEFAULT '1.0.0',
            author TEXT DEFAULT '',
            download_url TEXT DEFAULT '',
            install_count INTEGER DEFAULT 0,
            rating REAL DEFAULT 0,
            rating_count INTEGER DEFAULT 0,
            tags TEXT DEFAULT '[]',
            created_at REAL DEFAULT (julianday('now')),
            approved INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS plugin_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id TEXT UNIQUE NOT NULL,
            plugin_id TEXT NOT NULL,
            user_id TEXT DEFAULT '',
            rating INTEGER DEFAULT 0 CHECK(rating >= 1 AND rating <= 5),
            review TEXT DEFAULT '',
            created_at REAL DEFAULT (julianday('now')),
            FOREIGN KEY (plugin_id) REFERENCES plugin_registry(plugin_id)
        );

        CREATE INDEX IF NOT EXISTS idx_plugins_category ON plugin_registry(category);
        CREATE INDEX IF NOT EXISTS idx_plugins_name ON plugin_registry(name);
        CREATE INDEX IF NOT EXISTS idx_plugins_approved ON plugin_registry(approved);
        CREATE INDEX IF NOT EXISTS idx_reviews_plugin ON plugin_reviews(plugin_id);
    """)
    conn.commit()


def register_plugin(name: str, description: str, category: str = "tool",
                     version: str = "1.0.0", author: str = "",
                     download_url: str = "", tags: List[str] = None) -> dict:
    """Register a plugin in the marketplace."""
    plugin_id = f"plugin_{secrets.token_urlsafe(8)}"

    conn = get_connection(str(_marketplace_db_path()))
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO plugin_registry
           (plugin_id, name, description, category, version, author,
            download_url, tags)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (plugin_id, name, description, category, version, author,
         download_url, json.dumps(tags or []))
    )
    conn.commit()

    return get_plugin(plugin_id)


def get_plugin(plugin_id: str) -> Optional[dict]:
    """Get a plugin by ID."""
    conn = get_connection(str(_marketplace_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM plugin_registry WHERE plugin_id = ?", (plugin_id,))
    row = cur.fetchone()

    if not row:
        return None

    plugin = dict(row)
    plugin["tags"] = json.loads(plugin.get("tags", "[]"))
    return plugin


def list_plugins(category: str = None, approved_only: bool = True,
                  limit: int = 50) -> List[dict]:
    """List plugins, optionally filtered by category."""
    conn = get_connection(str(_marketplace_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if category and approved_only:
        cur.execute(
            "SELECT * FROM plugin_registry WHERE category = ? AND approved = 1 ORDER BY rating DESC, install_count DESC LIMIT ?",
            (category, limit)
        )
    elif approved_only:
        cur.execute(
            "SELECT * FROM plugin_registry WHERE approved = 1 ORDER BY rating DESC, install_count DESC LIMIT ?",
            (limit,)
        )
    elif category:
        cur.execute(
            "SELECT * FROM plugin_registry WHERE category = ? ORDER BY rating DESC, install_count DESC LIMIT ?",
            (category, limit)
        )
    else:
        cur.execute(
            "SELECT * FROM plugin_registry ORDER BY rating DESC, install_count DESC LIMIT ?",
            (limit,)
        )

    rows = cur.fetchall()

    result = []
    for row in rows:
        p = dict(row)
        p["tags"] = json.loads(p.get("tags", "[]"))
        result.append(p)
    return result


def search_plugins(query: str, limit: int = 20) -> List[dict]:
    """Search plugins by name or description."""
    conn = get_connection(str(_marketplace_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """SELECT * FROM plugin_registry
           WHERE (name LIKE ? OR description LIKE ?)
           AND approved = 1
           ORDER BY rating DESC LIMIT ?""",
        (f"%{query}%", f"%{query}%", limit)
    )
    rows = cur.fetchall()

    result = []
    for row in rows:
        p = dict(row)
        p["tags"] = json.loads(p.get("tags", "[]"))
        result.append(p)
    return result


def install_plugin(plugin_id: str) -> Optional[dict]:
    """Increment install count for a plugin."""
    conn = get_connection(str(_marketplace_db_path()))
    cur = conn.cursor()
    cur.execute(
        "UPDATE plugin_registry SET install_count = install_count + 1 WHERE plugin_id = ?",
        (plugin_id,)
    )
    conn.commit()

    return get_plugin(plugin_id)


def approve_plugin(plugin_id: str) -> bool:
    """Approve a plugin for the marketplace."""
    conn = get_connection(str(_marketplace_db_path()))
    cur = conn.cursor()
    cur.execute(
        "UPDATE plugin_registry SET approved = 1 WHERE plugin_id = ?",
        (plugin_id,)
    )
    approved = cur.rowcount > 0
    conn.commit()
    return approved


def rate_plugin(plugin_id: str, user_id: str, rating: int,
                 review: str = "") -> Optional[dict]:
    """Submit a rating/review for a plugin."""
    if rating < 1 or rating > 5:
        return None

    review_id = f"rev_{secrets.token_urlsafe(8)}"

    conn = get_connection(str(_marketplace_db_path()))
    cur = conn.cursor()

    # Insert review
    cur.execute(
        """INSERT INTO plugin_reviews (review_id, plugin_id, user_id, rating, review)
           VALUES (?, ?, ?, ?, ?)""",
        (review_id, plugin_id, user_id, rating, review)
    )

    # Update plugin rating
    cur.execute(
        """SELECT rating, rating_count FROM plugin_registry WHERE plugin_id = ?""",
        (plugin_id,)
    )
    row = cur.fetchone()
    if row:
        old_rating = row[0] or 0
        old_count = row[1] or 0
        new_count = old_count + 1
        new_rating = ((old_rating * old_count) + rating) / new_count
        cur.execute(
            """UPDATE plugin_registry SET rating = ?, rating_count = ?
               WHERE plugin_id = ?""",
            (round(new_rating, 2), new_count, plugin_id)
        )

    conn.commit()

    return {"review_id": review_id, "plugin_id": plugin_id, "rating": rating}


def get_plugin_reviews(plugin_id: str, limit: int = 20) -> List[dict]:
    """Get reviews for a plugin."""
    conn = get_connection(str(_marketplace_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM plugin_reviews WHERE plugin_id = ? ORDER BY created_at DESC LIMIT ?",
        (plugin_id, limit)
    )
    rows = cur.fetchall()

    return [dict(row) for row in rows]


def get_marketplace_stats() -> dict:
    """Get marketplace statistics."""
    conn = get_connection(str(_marketplace_db_path()))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) as total FROM plugin_registry")
    total = cur.fetchone()["total"]

    cur.execute("SELECT COUNT(*) as approved FROM plugin_registry WHERE approved = 1")
    approved = cur.fetchone()["approved"]

    cur.execute("SELECT SUM(install_count) as installs FROM plugin_registry")
    installs = cur.fetchone()["installs"] or 0

    cur.execute("SELECT AVG(rating) as avg_rating FROM plugin_registry WHERE rating > 0")
    avg_rating = cur.fetchone()["avg_rating"]

    cur.execute("SELECT category, COUNT(*) as count FROM plugin_registry GROUP BY category")
    categories = {row["category"]: row["count"] for row in cur.fetchall()}


    return {
        "total_plugins": total,
        "approved_plugins": approved,
        "total_installs": installs,
        "average_rating": round(avg_rating, 2) if avg_rating else 0,
        "categories": categories,
    }
