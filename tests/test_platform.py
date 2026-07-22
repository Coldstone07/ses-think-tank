"""Phase 5.6: Platform & Scale Tests"""
import pytest
import sys
import os
import tempfile
import time
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from platform_scale import (
    MetricsCollector, StructuredLogger, APIRouter,
    init_marketplace_schema, register_plugin, get_plugin, list_plugins,
    search_plugins, install_plugin, approve_plugin, rate_plugin,
    get_plugin_reviews, get_marketplace_stats,
)


# ─── METRICS TESTS ──────────────────────────────────────────────────────────

def test_metrics_counter():
    m = MetricsCollector()
    m.increment_counter("requests_total")
    m.increment_counter("requests_total", 5)
    data = m.get_json()
    assert data["counters"]["requests_total"] == 6


def test_metrics_counter_with_labels():
    m = MetricsCollector()
    m.increment_counter("requests", 1, {"method": "GET", "path": "/api"})
    m.increment_counter("requests", 1, {"method": "POST", "path": "/api"})
    data = m.get_json()
    assert len([k for k in data["counters"] if k.startswith("requests")]) == 2


def test_metrics_gauge():
    m = MetricsCollector()
    m.set_gauge("active_users", 42)
    m.set_gauge("active_users", 50)
    data = m.get_json()
    assert data["gauges"]["active_users"] == 50.0


def test_metrics_histogram():
    m = MetricsCollector()
    m.observe_histogram("response_time", 0.1)
    m.observe_histogram("response_time", 0.3)
    m.observe_histogram("response_time", 0.6)
    data = m.get_json()
    assert data["histograms"]["response_time"]["count"] == 3
    assert data["histograms"]["response_time"]["min"] == 0.1
    assert data["histograms"]["response_time"]["max"] == 0.6


def test_metrics_prometheus_text():
    m = MetricsCollector()
    m.increment_counter("api_calls", 10)
    m.set_gauge("memory_usage", 0.75)
    text = m.get_prometheus_text()
    assert "# HELP" in text
    assert "# TYPE" in text
    assert "ses_uptime_seconds" in text
    assert "ses_api_calls_total" in text
    assert "ses_memory_usage" in text


def test_metrics_uptime():
    m = MetricsCollector()
    time.sleep(0.1)
    data = m.get_json()
    assert data["uptime"] > 0


# ─── STRUCTURED LOGGING TESTS ───────────────────────────────────────────────

def test_structured_logger(tmp_path):
    log_file = str(tmp_path / "test.log")
    log = StructuredLogger(log_file=log_file)

    log.info("Test message", user="testuser", action="login")
    log.warn("Warning message", code=400)
    log.error("Error message", error="timeout")

    entries = log.get_recent()
    assert len(entries) == 3
    assert entries[0]["level"] == "INFO"
    assert entries[1]["level"] == "WARN"
    assert entries[2]["level"] == "ERROR"
    assert entries[0]["user"] == "testuser"


def test_structured_logger_stats(tmp_path):
    log_file = str(tmp_path / "test.log")
    log = StructuredLogger(log_file=log_file)

    log.info("Info 1")
    log.info("Info 2")
    log.error("Error 1")

    stats = log.get_stats()
    assert stats["total"] == 3
    assert stats["levels"]["INFO"] == 2
    assert stats["levels"]["ERROR"] == 1


def test_structured_logger_empty(tmp_path):
    log_file = str(tmp_path / "nonexistent.log")
    log = StructuredLogger(log_file=log_file)
    entries = log.get_recent()
    assert entries == []


# ─── API ROUTER TESTS ───────────────────────────────────────────────────────

def test_api_router_basic():
    router = APIRouter()

    @router.route("GET", "/api/hello")
    def hello(body):
        return {"message": "Hello, World!"}

    result = router.handle("GET", "/api/hello")
    assert result["message"] == "Hello, World!"


def test_api_router_not_found():
    router = APIRouter()
    result = router.handle("GET", "/nonexistent")
    assert result["status"] == 404


def test_api_router_middleware():
    router = APIRouter()

    def auth_mw(method, path, body):
        if path == "/protected":
            return {"status": 401, "error": "Unauthorized"}
        return None

    router.use(auth_mw)

    @router.route("GET", "/protected")
    def protected(body):
        return {"data": "secret"}

    result = router.handle("GET", "/protected")
    assert result["status"] == 401


def test_api_router_list_routes():
    router = APIRouter()

    @router.route("GET", "/a")
    def a(body):
        return {}

    @router.route("POST", "/b")
    def b(body):
        return {}

    routes = router.get_routes()
    assert len(routes) == 2
    methods = [r["method"] for r in routes]
    assert "GET" in methods
    assert "POST" in methods


# ─── MARKETPLACE TESTS ──────────────────────────────────────────────────────

@pytest.fixture
def tmp_marketplace_db(tmp_path):
    """Create temp DB with marketplace schema."""
    os.environ["SES_MARKETPLACE_DB"] = str(tmp_path / "marketplace.db")

    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "marketplace.db"))
    cur = conn.cursor()
    init_marketplace_schema()
    conn.commit()
    conn.close()

    yield tmp_path

    os.environ.pop("SES_MARKETPLACE_DB", None)
    from db import reset_pool
    reset_pool()  # Release pooled connections before deleting temp DB
    try:
        (tmp_path / "marketplace.db").unlink(missing_ok=True)
    except PermissionError:
        pass  # Windows may still hold handle briefly


def test_register_plugin(tmp_marketplace_db):
    plugin = register_plugin(
        name="Web Search Pro",
        description="Advanced web search with filtering",
        category="tool",
        version="2.0.0",
        author="dev1",
        download_url="https://example.com/web-search",
        tags=["search", "web"],
    )
    assert plugin["name"] == "Web Search Pro"
    assert plugin["category"] == "tool"
    assert plugin["install_count"] == 0
    assert plugin["approved"] == 0


def test_get_plugin(tmp_marketplace_db):
    plugin = register_plugin("Test Plugin", "desc", author="dev1")
    fetched = get_plugin(plugin["plugin_id"])
    assert fetched is not None
    assert fetched["name"] == "Test Plugin"


def test_get_plugin_not_found(tmp_marketplace_db):
    assert get_plugin("nonexistent") is None


def test_list_plugins(tmp_marketplace_db):
    register_plugin("Plugin A", "a", category="tool", author="dev1")
    register_plugin("Plugin B", "b", category="knowledge", author="dev1")
    approve_plugin(register_plugin("Plugin C", "c", category="tool", author="dev1")["plugin_id"])

    all_plugins = list_plugins(approved_only=False)
    assert len(all_plugins) == 3

    approved_only = list_plugins(approved_only=True)
    assert len(approved_only) == 1


def test_list_plugins_by_category(tmp_marketplace_db):
    register_plugin("Tool A", "a", category="tool", author="dev1")
    approve_plugin(register_plugin("Tool B", "b", category="tool", author="dev1")["plugin_id"])
    approve_plugin(register_plugin("Knowledge A", "a", category="knowledge", author="dev1")["plugin_id"])

    tools = list_plugins(category="tool", approved_only=True)
    assert len(tools) == 1


def test_search_plugins(tmp_marketplace_db):
    register_plugin("Web Search", "Search the web", category="tool", author="dev1")
    approve_plugin(register_plugin("Data Analyzer", "Analyze data", category="tool", author="dev1")["plugin_id"])

    results = search_plugins("search")
    assert len(results) >= 1


def test_install_plugin(tmp_marketplace_db):
    plugin = register_plugin("Installable", "desc", author="dev1")
    installed = install_plugin(plugin["plugin_id"])
    assert installed["install_count"] == 1

    installed2 = install_plugin(plugin["plugin_id"])
    assert installed2["install_count"] == 2


def test_approve_plugin(tmp_marketplace_db):
    plugin = register_plugin("To Approve", "desc", author="dev1")
    assert plugin["approved"] == 0
    assert approve_plugin(plugin["plugin_id"]) is True

    approved = get_plugin(plugin["plugin_id"])
    assert approved["approved"] == 1


def test_approve_plugin_not_found(tmp_marketplace_db):
    assert approve_plugin("nonexistent") is False


def test_rate_plugin(tmp_marketplace_db):
    plugin = register_plugin("Ratable", "desc", author="dev1")
    result = rate_plugin(plugin["plugin_id"], "user1", 5, "Great plugin!")
    assert result["rating"] == 5

    plugin_after = get_plugin(plugin["plugin_id"])
    assert plugin_after["rating"] == 5.0
    assert plugin_after["rating_count"] == 1


def test_rate_plugin_multiple(tmp_marketplace_db):
    plugin = register_plugin("Multi Rate", "desc", author="dev1")
    rate_plugin(plugin["plugin_id"], "user1", 5)
    rate_plugin(plugin["plugin_id"], "user2", 3)

    plugin_after = get_plugin(plugin["plugin_id"])
    assert plugin_after["rating"] == pytest.approx(4.0, abs=0.01)
    assert plugin_after["rating_count"] == 2


def test_rate_plugin_invalid(tmp_marketplace_db):
    plugin = register_plugin("Invalid Rate", "desc", author="dev1")
    result = rate_plugin(plugin["plugin_id"], "user1", 0)
    assert result is None

    result2 = rate_plugin(plugin["plugin_id"], "user1", 6)
    assert result2 is None


def test_get_plugin_reviews(tmp_marketplace_db):
    plugin = register_plugin("Reviewed", "desc", author="dev1")
    rate_plugin(plugin["plugin_id"], "user1", 5, "Excellent!")
    rate_plugin(plugin["plugin_id"], "user2", 4, "Very good")

    reviews = get_plugin_reviews(plugin["plugin_id"])
    assert len(reviews) == 2


def test_marketplace_stats(tmp_marketplace_db):
    p1 = register_plugin("Stats A", "a", category="tool", author="dev1")
    p2 = register_plugin("Stats B", "b", category="knowledge", author="dev1")
    approve_plugin(p1["plugin_id"])
    install_plugin(p1["plugin_id"])
    rate_plugin(p1["plugin_id"], "user1", 5)

    stats = get_marketplace_stats()
    assert stats["total_plugins"] == 2
    assert stats["approved_plugins"] == 1
    assert stats["total_installs"] == 1
    assert stats["average_rating"] == 5.0
    assert "tool" in stats["categories"]


def test_init_marketplace_schema(tmp_marketplace_db):
    """Verify all marketplace tables exist."""
    import sqlite3
    conn = sqlite3.connect(str(tmp_marketplace_db / "marketplace.db"))
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cur.fetchall()]
    conn.close()

    assert "plugin_registry" in tables
    assert "plugin_reviews" in tables


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
