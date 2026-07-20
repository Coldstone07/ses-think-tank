"""Phase 4.7: Settings & Integrations Tests"""
import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from settings import (
    init_settings_schema, get_available_providers, get_available_integrations,
    save_provider_config, get_provider_config, get_all_provider_configs,
    set_default_provider, get_default_provider,
    save_api_key, get_api_key, get_api_keys_list, delete_api_key,
    get_environment_keys,
    save_setting, get_setting, get_all_settings,
    get_provider_env,
    _encrypt, _decrypt,
)


@pytest.fixture
def tmp_settings_db(tmp_path):
    """Create a temporary settings DB."""
    os.environ["SES_SETTINGS_DB"] = str(tmp_path / "settings.db")
    import importlib
    import settings
    importlib.reload(settings)
    settings.init_settings_schema()
    return tmp_path


def test_encrypt_decrypt():
    original = "sk-test-1234567890"
    encrypted = _encrypt(original)
    assert encrypted != original
    decrypted = _decrypt(encrypted)
    assert decrypted == original


def test_encrypt_empty():
    assert _encrypt("") == ""
    assert _decrypt("") == ""


def test_decrypt_invalid():
    assert _decrypt("not-valid-token") == ""


def test_get_available_providers():
    providers = get_available_providers()
    assert len(providers) >= 4
    provider_ids = [p["id"] for p in providers]
    assert "lm_studio" in provider_ids
    assert "gemini" in provider_ids
    assert "openai" in provider_ids
    assert "anthropic" in provider_ids


def test_provider_has_config_schema():
    providers = get_available_providers()
    for p in providers:
        assert "config_schema" in p
        assert "name" in p
        assert "description" in p
        assert "type" in p
        if p.get("requires_key"):
            assert "key_name" in p


def test_get_available_integrations():
    integrations = get_available_integrations()
    assert len(integrations) >= 2
    for i in integrations:
        assert "id" in i
        assert "name" in i
        assert "key_name" in i
        assert "url" in i


def test_save_and_get_provider_config(tmp_settings_db):
    import importlib
    import settings
    importlib.reload(settings)

    settings.save_provider_config("user1", "openai", {
        "model": "gpt-4o",
        "max_tokens": 4096,
    }, enabled=True)

    config = settings.get_provider_config("user1", "openai")
    assert config["provider_name"] == "openai"
    assert config["config"]["model"] == "gpt-4o"
    assert config["is_enabled"]


def test_provider_config_defaults():
    import importlib
    import settings
    importlib.reload(settings)

    config = settings.get_provider_config("user1", "nonexistent")
    assert config["provider_name"] == "nonexistent"
    assert config["config"] == {}
    assert not config["is_enabled"]


def test_save_and_get_api_key(tmp_settings_db):
    import importlib
    import settings
    importlib.reload(settings)

    settings.save_api_key("user1", "gemini", "GEMINI_API_KEY", "sk-test-key-123", "My key")

    key = settings.get_api_key("user1", "gemini", "GEMINI_API_KEY")
    assert key == "sk-test-key-123"


def test_api_key_not_stored_in_plain_text(tmp_settings_db):
    import importlib
    import settings
    importlib.reload(settings)

    settings.save_api_key("user1", "openai", "OPENAI_API_KEY", "secret-key", "")

    # Check DB directly
    import sqlite3
    conn = sqlite3.connect(str(settings.SETTINGS_DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT encrypted_key FROM api_keys WHERE provider = 'openai'")
    row = cur.fetchone()
    assert row[0] != "secret-key"  # Should be encrypted
    conn.close()


def test_api_keys_list_does_not_reveal_keys(tmp_settings_db):
    import importlib
    import settings
    importlib.reload(settings)

    settings.save_api_key("user1", "gemini", "GEMINI_API_KEY", "my-secret", "Test key")

    keys = settings.get_api_keys_list("user1")
    assert len(keys) == 1
    assert keys[0]["provider"] == "gemini"
    assert keys[0]["key_name"] == "GEMINI_API_KEY"
    assert keys[0]["label"] == "Test key"
    # Key value should NOT be in the list
    assert "encrypted_key" not in keys[0]
    assert "key_value" not in keys[0]


def test_delete_api_key(tmp_settings_db):
    import importlib
    import settings
    importlib.reload(settings)

    settings.save_api_key("user1", "openai", "OPENAI_API_KEY", "key123", "")

    keys = settings.get_api_keys_list("user1")
    assert len(keys) == 1
    key_id = keys[0]["id"]

    settings.delete_api_key("user1", key_id)

    # Key should be deactivated
    key = settings.get_api_key("user1", "openai", "OPENAI_API_KEY")
    assert key == ""


def test_api_key_fallback_to_env(tmp_settings_db):
    import importlib
    import settings
    importlib.reload(settings)

    os.environ["TEST_API_KEY"] = "env-key-value"
    try:
        # Key not in DB, should fall back to env
        key = settings.get_api_key("user1", "test", "TEST_API_KEY")
        assert key == "env-key-value"
    finally:
        del os.environ["TEST_API_KEY"]


def test_set_default_provider(tmp_settings_db):
    import importlib
    import settings
    importlib.reload(settings)

    settings.save_provider_config("user1", "openai", {"model": "gpt-4o"}, enabled=True)
    settings.save_provider_config("user1", "anthropic", {"model": "claude-sonnet-4"}, enabled=True)

    settings.set_default_provider("user1", "anthropic")

    default = settings.get_default_provider("user1")
    assert default == "anthropic"


def test_default_provider_fallback(tmp_settings_db):
    import importlib
    import settings
    importlib.reload(settings)

    # No providers configured — should fall back to LM Studio
    default = settings.get_default_provider("empty_user")
    assert default == "lm_studio"


def test_get_all_provider_configs(tmp_settings_db):
    import importlib
    import settings
    importlib.reload(settings)

    settings.save_provider_config("user1", "openai", {"model": "gpt-4o"}, enabled=True)
    settings.save_provider_config("user1", "gemini", {"model": "gemini-2.5-flash"}, enabled=True)
    settings.set_default_provider("user1", "openai")

    configs = settings.get_all_provider_configs("user1")
    assert len(configs) == 2
    # Default should come first
    assert configs[0]["provider_name"] == "openai"
    assert configs[0]["is_default"]


def test_save_and_get_setting(tmp_settings_db):
    import importlib
    import settings
    importlib.reload(settings)

    settings.save_setting("user1", "theme", "dark")
    settings.save_setting("user1", "language", "en")

    assert settings.get_setting("user1", "theme") == "dark"
    assert settings.get_setting("user1", "language") == "en"
    assert settings.get_setting("user1", "nonexistent", "default") == "default"


def test_get_all_settings(tmp_settings_db):
    import importlib
    import settings
    importlib.reload(settings)

    settings.save_setting("user1", "theme", "dark")
    settings.save_setting("user1", "notifications", "true")

    all_settings = settings.get_all_settings("user1")
    assert all_settings["theme"] == "dark"
    assert all_settings["notifications"] == "true"


def test_get_environment_keys():
    import importlib
    import settings
    importlib.reload(settings)

    os.environ["GEMINI_API_KEY"] = "test"
    os.environ["TAVILY_API_KEY"] = "test"
    try:
        env_keys = settings.get_environment_keys()
        assert env_keys["GEMINI_API_KEY"] is True
        assert env_keys["TAVILY_API_KEY"] is True
    finally:
        del os.environ["GEMINI_API_KEY"]
        del os.environ["TAVILY_API_KEY"]


def test_get_provider_env(tmp_settings_db):
    import importlib
    import settings
    importlib.reload(settings)

    settings.save_provider_config("default", "openai", {
        "model": "gpt-4o",
        "base_url": "https://api.openai.com/v1",
        "max_tokens": 4096,
        "temperature": 0.8,
    }, enabled=True)
    settings.set_default_provider("default", "openai")
    settings.save_api_key("default", "openai", "OPENAI_API_KEY", "sk-test-key", "")

    env = settings.get_provider_env("default")
    assert env["provider"] == "openai"
    assert env["model"] == "gpt-4o"
    assert env["api_key"] == "sk-test-key"
    assert env["max_tokens"] == 4096
    assert env["temperature"] == 0.8


def test_provider_env_with_schema_defaults(tmp_settings_db):
    import importlib
    import settings
    importlib.reload(settings)

    # Save minimal config — should merge with schema defaults
    settings.save_provider_config("default", "openai", {
        "model": "gpt-4o-mini",
    }, enabled=True)
    settings.set_default_provider("default", "openai")

    env = settings.get_provider_env("default")
    assert env["model"] == "gpt-4o-mini"  # User override
    assert env["base_url"] == "https://api.openai.com/v1"  # Schema default


def test_provider_config_update(tmp_settings_db):
    import importlib
    import settings
    importlib.reload(settings)

    # Initial config
    settings.save_provider_config("user1", "openai", {"model": "gpt-4"}, enabled=True)
    assert settings.get_provider_config("user1", "openai")["config"]["model"] == "gpt-4"

    # Update
    settings.save_provider_config("user1", "openai", {"model": "gpt-4o", "max_tokens": 4096}, enabled=True)
    config = settings.get_provider_config("user1", "openai")
    assert config["config"]["model"] == "gpt-4o"
    assert config["config"]["max_tokens"] == 4096


def test_multiple_users_isolation(tmp_settings_db):
    import importlib
    import settings
    importlib.reload(settings)

    settings.save_api_key("user1", "openai", "OPENAI_API_KEY", "key1", "")
    settings.save_api_key("user2", "openai", "OPENAI_API_KEY", "key2", "")

    assert settings.get_api_key("user1", "openai", "OPENAI_API_KEY") == "key1"
    assert settings.get_api_key("user2", "openai", "OPENAI_API_KEY") == "key2"


def test_lm_studio_no_key_required():
    providers = get_available_providers()
    lm_studio = next(p for p in providers if p["id"] == "lm_studio")
    assert not lm_studio["requires_key"]
    assert lm_studio["type"] == "local"


def test_cloud_providers_require_keys():
    providers = get_available_providers()
    cloud_providers = [p for p in providers if p["type"] == "cloud"]
    for p in cloud_providers:
        assert p["requires_key"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
