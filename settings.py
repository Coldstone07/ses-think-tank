"""
Settings & Integrations — Phase 4.7

User-configurable API keys, LLM provider selection, tool integration management.
Supports multiple providers: LM Studio, Gemini, OpenAI, Anthropic, OpenRouter.
Keys stored encrypted at rest (Fernet symmetric encryption).
"""
import os
import json
import time
import sqlite3
import base64
from pathlib import Path
from typing import Optional, Dict, List
from cryptography.fernet import Fernet, InvalidToken

SETTINGS_DB_PATH = Path(os.environ.get("SES_SETTINGS_DB", "data/settings.db"))

# Encryption key — in production, rotate this and re-encrypt stored keys
# For self-hosted: set SES_ENCRYPTION_KEY env var (base64-encoded 32-byte key)
# For demo: auto-generate per session (keys NOT persisted across restarts)
_ENCRYPTION_KEY = os.environ.get("SES_ENCRYPTION_KEY") or Fernet.generate_key()
_cipher = Fernet(_ENCRYPTION_KEY)


def init_settings_schema():
    """Create settings tables."""
    conn = sqlite3.connect(str(SETTINGS_DB_PATH))
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id TEXT NOT NULL DEFAULT 'default',
            setting_key TEXT NOT NULL,
            setting_value TEXT DEFAULT '',
            updated_at REAL DEFAULT (julianday('now')),
            PRIMARY KEY (user_id, setting_key)
        );

        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL DEFAULT 'default',
            provider TEXT NOT NULL,
            key_name TEXT NOT NULL,
            encrypted_key TEXT NOT NULL,
            label TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            created_at REAL DEFAULT (julianday('now')),
            updated_at REAL DEFAULT (julianday('now')),
            UNIQUE(user_id, provider, key_name)
        );

        CREATE TABLE IF NOT EXISTS provider_config (
            user_id TEXT NOT NULL DEFAULT 'default',
            provider_name TEXT NOT NULL,
            config_json TEXT DEFAULT '{}',
            is_enabled INTEGER DEFAULT 1,
            is_default INTEGER DEFAULT 0,
            updated_at REAL DEFAULT (julianday('now')),
            PRIMARY KEY (user_id, provider_name)
        );

        CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);
        CREATE INDEX IF NOT EXISTS idx_api_keys_provider ON api_keys(provider);
    """)
    conn.commit()
    conn.close()


def _encrypt(value: str) -> str:
    """Encrypt a value using Fernet symmetric encryption."""
    if not value:
        return ""
    return _cipher.encrypt(value.encode()).decode()


def _decrypt(encrypted: str) -> str:
    """Decrypt a Fernet-encrypted value."""
    if not encrypted:
        return ""
    try:
        return _cipher.decrypt(encrypted.encode()).decode()
    except InvalidToken:
        return ""  # Key mismatch — return empty rather than crash


def get_available_providers() -> List[dict]:
    """Return list of available LLM providers with their config schema."""
    return [
        {
            "id": "lm_studio",
            "name": "LM Studio",
            "description": "Local LLM server (Qwen, Llama, etc.)",
            "type": "local",
            "config_schema": {
                "base_url": {"type": "string", "default": "http://localhost:1234", "label": "Server URL"},
                "model": {"type": "string", "default": "qwen/qwen3.6-27b", "label": "Model ID"},
                "max_tokens": {"type": "integer", "default": 2048, "label": "Max Tokens"},
                "temperature": {"type": "number", "default": 0.7, "label": "Temperature"},
            },
            "requires_key": False,
        },
        {
            "id": "gemini",
            "name": "Google Gemini",
            "description": "Google's Gemini models (Flash, Pro)",
            "type": "cloud",
            "config_schema": {
                "model": {"type": "string", "default": "gemini-2.5-flash", "label": "Model ID"},
                "max_tokens": {"type": "integer", "default": 2048, "label": "Max Tokens"},
                "temperature": {"type": "number", "default": 0.7, "label": "Temperature"},
            },
            "requires_key": True,
            "key_name": "GEMINI_API_KEY",
        },
        {
            "id": "openai",
            "name": "OpenAI",
            "description": "GPT-4, GPT-4o, o1, o3 models",
            "type": "cloud",
            "config_schema": {
                "base_url": {"type": "string", "default": "https://api.openai.com/v1", "label": "API URL"},
                "model": {"type": "string", "default": "gpt-4o", "label": "Model ID"},
                "max_tokens": {"type": "integer", "default": 2048, "label": "Max Tokens"},
                "temperature": {"type": "number", "default": 0.7, "label": "Temperature"},
            },
            "requires_key": True,
            "key_name": "OPENAI_API_KEY",
        },
        {
            "id": "anthropic",
            "name": "Anthropic",
            "description": "Claude models (Sonnet, Opus, Haiku)",
            "type": "cloud",
            "config_schema": {
                "base_url": {"type": "string", "default": "https://api.anthropic.com", "label": "API URL"},
                "model": {"type": "string", "default": "claude-sonnet-4-20250514", "label": "Model ID"},
                "max_tokens": {"type": "integer", "default": 2048, "label": "Max Tokens"},
                "temperature": {"type": "number", "default": 0.7, "label": "Temperature"},
                "api_version": {"type": "string", "default": "2023-06-01", "label": "API Version"},
            },
            "requires_key": True,
            "key_name": "ANTHROPIC_API_KEY",
        },
        {
            "id": "openrouter",
            "name": "OpenRouter",
            "description": "Unified API for 100+ models",
            "type": "cloud",
            "config_schema": {
                "base_url": {"type": "string", "default": "https://openrouter.ai/api/v1", "label": "API URL"},
                "model": {"type": "string", "default": "anthropic/claude-sonnet-4", "label": "Model ID"},
                "max_tokens": {"type": "integer", "default": 2048, "label": "Max Tokens"},
                "temperature": {"type": "number", "default": 0.7, "label": "Temperature"},
            },
            "requires_key": True,
            "key_name": "OPENROUTER_API_KEY",
        },
    ]


def get_available_integrations() -> List[dict]:
    """Return list of available tool integrations."""
    return [
        {
            "id": "tavily",
            "name": "Tavily Search",
            "description": "AI-optimized web search",
            "key_name": "TAVILY_API_KEY",
            "url": "https://tavily.com",
        },
        {
            "id": "serpapi",
            "name": "SerpAPI",
            "description": "Google Search API",
            "key_name": "SERPAPI_API_KEY",
            "url": "https://serpapi.com",
        },
        {
            "id": "firecrawl",
            "name": "Firecrawl",
            "description": "Web scraping and crawling",
            "key_name": "FIRECRAWL_API_KEY",
            "url": "https://firecrawl.dev",
        },
    ]


# ─── PROVIDER CONFIG ────────────────────────────────────────────────────────

def save_provider_config(user_id: str, provider_name: str, config: dict, enabled: bool = True):
    """Save provider configuration for a user."""
    conn = sqlite3.connect(str(SETTINGS_DB_PATH))
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO provider_config (user_id, provider_name, config_json, is_enabled, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(user_id, provider_name)
           DO UPDATE SET config_json = ?, is_enabled = ?, updated_at = ?""",
        (user_id, provider_name, json.dumps(config), 1 if enabled else 0, time.time(),
         json.dumps(config), 1 if enabled else 0, time.time())
    )
    conn.commit()
    conn.close()


def get_provider_config(user_id: str, provider_name: str) -> dict:
    """Get provider configuration for a user."""
    conn = sqlite3.connect(str(SETTINGS_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM provider_config WHERE user_id = ? AND provider_name = ?",
        (user_id, provider_name)
    )
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            "provider_name": provider_name,
            "config": json.loads(row["config_json"]),
            "is_enabled": bool(row["is_enabled"]),
            "is_default": bool(row["is_default"]),
        }
    return {"provider_name": provider_name, "config": {}, "is_enabled": False, "is_default": False}


def get_all_provider_configs(user_id: str) -> list:
    """Get all provider configurations for a user."""
    conn = sqlite3.connect(str(SETTINGS_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM provider_config WHERE user_id = ? ORDER BY is_default DESC", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "provider_name": row["provider_name"],
            "config": json.loads(row["config_json"]),
            "is_enabled": bool(row["is_enabled"]),
            "is_default": bool(row["is_default"]),
        }
        for row in rows
    ]


def set_default_provider(user_id: str, provider_name: str):
    """Set a provider as the default for a user."""
    conn = sqlite3.connect(str(SETTINGS_DB_PATH))
    cur = conn.cursor()
    cur.execute("UPDATE provider_config SET is_default = 0 WHERE user_id = ?", (user_id,))
    cur.execute(
        "UPDATE provider_config SET is_default = 1 WHERE user_id = ? AND provider_name = ?",
        (user_id, provider_name)
    )
    conn.commit()
    conn.close()


def get_default_provider(user_id: str) -> str:
    """Get the default provider for a user. Falls back to LM Studio."""
    conn = sqlite3.connect(str(SETTINGS_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT provider_name FROM provider_config WHERE user_id = ? AND is_default = 1 AND is_enabled = 1",
        (user_id,)
    )
    row = cur.fetchone()
    conn.close()
    if row:
        return row["provider_name"]
    # Fallback: check env, then LM Studio
    return os.environ.get("SES_DEFAULT_PROVIDER", "lm_studio")


# ─── API KEYS ────────────────────────────────────────────────────────────────

def save_api_key(user_id: str, provider: str, key_name: str, key_value: str, label: str = ""):
    """Save an API key (encrypted)."""
    encrypted = _encrypt(key_value)
    conn = sqlite3.connect(str(SETTINGS_DB_PATH))
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO api_keys (user_id, provider, key_name, encrypted_key, label, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(user_id, provider, key_name)
           DO UPDATE SET encrypted_key = ?, label = ?, updated_at = ?""",
        (user_id, provider, key_name, encrypted, label, time.time(),
         encrypted, label, time.time())
    )
    conn.commit()
    conn.close()


def get_api_key(user_id: str, provider: str, key_name: str) -> str:
    """Retrieve and decrypt an API key."""
    conn = sqlite3.connect(str(SETTINGS_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT encrypted_key FROM api_keys WHERE user_id = ? AND provider = ? AND key_name = ? AND is_active = 1",
        (user_id, provider, key_name)
    )
    row = cur.fetchone()
    conn.close()
    if row:
        return _decrypt(row["encrypted_key"])
    # Fallback: check environment variable
    env_val = os.environ.get(key_name, "")
    if env_val:
        return env_val
    return ""


def get_api_keys_list(user_id: str) -> list:
    """List all API keys (without revealing the actual keys)."""
    conn = sqlite3.connect(str(SETTINGS_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT id, provider, key_name, label, is_active, created_at, updated_at FROM api_keys WHERE user_id = ?",
        (user_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_api_key(user_id: str, key_id: int):
    """Delete (deactivate) an API key."""
    conn = sqlite3.connect(str(SETTINGS_DB_PATH))
    cur = conn.cursor()
    cur.execute("UPDATE api_keys SET is_active = 0 WHERE id = ? AND user_id = ?", (key_id, user_id))
    conn.commit()
    conn.close()


def get_environment_keys() -> dict:
    """Get which keys are already configured via environment variables."""
    env_keys = {}
    for provider in get_available_providers():
        if provider.get("requires_key"):
            key_name = provider["key_name"]
            env_keys[key_name] = bool(os.environ.get(key_name, ""))
    for integration in get_available_integrations():
        key_name = integration["key_name"]
        env_keys[key_name] = bool(os.environ.get(key_name, ""))
    return env_keys


# ─── USER SETTINGS ───────────────────────────────────────────────────────────

def save_setting(user_id: str, key: str, value: str):
    """Save a user setting."""
    conn = sqlite3.connect(str(SETTINGS_DB_PATH))
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO user_settings (user_id, setting_key, setting_value, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id, setting_key)
           DO UPDATE SET setting_value = ?, updated_at = ?""",
        (user_id, key, value, time.time(), value, time.time())
    )
    conn.commit()
    conn.close()


def get_setting(user_id: str, key: str, default: str = "") -> str:
    """Get a user setting."""
    conn = sqlite3.connect(str(SETTINGS_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT setting_value FROM user_settings WHERE user_id = ? AND setting_key = ?",
        (user_id, key)
    )
    row = cur.fetchone()
    conn.close()
    if row:
        return row["setting_value"]
    return default


def get_all_settings(user_id: str) -> dict:
    """Get all user settings."""
    conn = sqlite3.connect(str(SETTINGS_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT setting_key, setting_value FROM user_settings WHERE user_id = ?", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return {row["setting_key"]: row["setting_value"] for row in rows}


# ─── PROVIDER ROUTING ────────────────────────────────────────────────────────

def get_provider_env(user_id: str = "default") -> dict:
    """
    Get the effective provider environment for LLM calls.
    Returns {provider, base_url, model, api_key, api_version, temperature, max_tokens}.
    """
    default_provider = get_default_provider(user_id)
    config = get_provider_config(user_id, default_provider)
    provider_info = None
    for p in get_available_providers():
        if p["id"] == default_provider:
            provider_info = p
            break

    base_config = config.get("config", {})
    schema_defaults = {}
    if provider_info and provider_info.get("config_schema"):
        for k, v in provider_info["config_schema"].items():
            schema_defaults[k] = v.get("default", "")

    merged = {**schema_defaults, **base_config}

    api_key = ""
    if provider_info and provider_info.get("requires_key"):
        api_key = get_api_key(user_id, default_provider, provider_info["key_name"])

    return {
        "provider": default_provider,
        "base_url": merged.get("base_url", ""),
        "model": merged.get("model", ""),
        "api_key": api_key,
        "api_version": merged.get("api_version", ""),
        "temperature": merged.get("temperature", 0.7),
        "max_tokens": merged.get("max_tokens", 2048),
    }
