"""
Shared SQLite connection helper.

Enables WAL mode, proper timeouts, and thread-safe connections.
Use this instead of raw sqlite3.connect() everywhere.
"""
import sqlite3
import threading
from pathlib import Path
from typing import Optional

# Global connection pool per database path
_pool: dict[str, sqlite3.Connection] = {}
_pool_lock = threading.Lock()


def get_connection(db_path: str | Path, wal: bool = True, timeout: float = 30.0) -> sqlite3.Connection:
    """Get a thread-safe SQLite connection with WAL mode enabled.

    Returns a cached connection per thread to avoid concurrent access issues.
    """
    db_path = str(db_path)
    thread_id = threading.get_ident()
    key = f"{db_path}:{thread_id}"

    with _pool_lock:
        if key in _pool:
            conn = _pool[key]
            # Verify connection is still alive
            try:
                if not conn.in_transaction and conn.execute("SELECT 1").fetchone():
                    return conn
                del _pool[key]
            except (sqlite3.Error, AttributeError):
                del _pool[key]

    # Create new connection
    conn = sqlite3.connect(
        db_path,
        check_same_thread=False,  # Allow sharing across threads
        timeout=timeout,
    )
    conn.row_factory = sqlite3.Row

    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")  # Faster writes, still durable
        conn.execute("PRAGMA busy_timeout=30000")  # 30s busy timeout
        conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        # Note: foreign_keys=ON disabled — some tables reference cross-DB FKs
        # (e.g., session_shares → memory_sessions in different DB) which SQLite
        # cannot enforce. Enable per-connection when needed.

    with _pool_lock:
        _pool[key] = conn

    return conn


def close_all():
    """Close all pooled connections."""
    with _pool_lock:
        for conn in _pool.values():
            try:
                conn.close()
            except sqlite3.Error:
                pass
        _pool.clear()


def reset_pool():
    """Reset the connection pool (useful for tests)."""
    close_all()
