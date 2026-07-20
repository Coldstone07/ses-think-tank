"""Phase 5.1: Auth Tests"""
import pytest
import sys
import os
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from auth import (
    init_auth_schema, seed_default_user,
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token, verify_refresh_token,
    register_user, authenticate_user, get_user_by_id, get_user_by_username,
    check_rate_limit, check_quota, increment_quota, get_quota_status,
    create_session_share, get_shared_session, revoke_session_share, get_user_shares,
    HTTPException,
)


@pytest.fixture
def tmp_auth_db(tmp_path):
    """Create a temporary auth DB."""
    os.environ["SES_AUTH_DB"] = str(tmp_path / "auth.db")
    os.environ["SES_JWT_SECRET"] = "test-secret-key-for-testing-only-1234567890"
    import importlib
    import auth
    importlib.reload(auth)
    auth.init_auth_schema()
    return tmp_path


def test_hash_and_verify_password():
    hashed = hash_password("mypassword123")
    assert hashed != "mypassword123"
    assert verify_password("mypassword123", hashed)
    assert not verify_password("wrongpassword", hashed)


def test_register_user(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    user = auth.register_user("testuser", "password123", "test@example.com", "Test User")
    assert user["username"] == "testuser"
    assert user["email"] == "test@example.com"
    assert user["display_name"] == "Test User"
    assert "user_id" in user
    assert len(user["user_id"]) == 36  # UUID


def test_register_user_short_username(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    with pytest.raises(HTTPException) as exc:
        auth.register_user("ab", "password123")
    assert exc.value.status_code == 400


def test_register_user_short_password(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    with pytest.raises(HTTPException) as exc:
        auth.register_user("validuser", "abc")
    assert exc.value.status_code == 400


def test_register_duplicate_username(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    auth.register_user("dupuser", "password123")
    with pytest.raises(HTTPException) as exc:
        auth.register_user("dupuser", "password456")
    assert exc.value.status_code == 409


def test_authenticate_user(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    auth.register_user("loginuser", "password123", "login@test.com")
    result = auth.authenticate_user("loginuser", "password123")
    assert "user" in result
    assert result["user"]["username"] == "loginuser"
    assert "access_token" in result
    assert "refresh_token" in result
    assert result["token_type"] == "bearer"


def test_authenticate_wrong_password(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    auth.register_user("wrongpass", "password123")
    with pytest.raises(HTTPException) as exc:
        auth.authenticate_user("wrongpass", "wrongpassword")
    assert exc.value.status_code == 401


def test_authenticate_nonexistent_user(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    with pytest.raises(HTTPException) as exc:
        auth.authenticate_user("nonexistent", "password123")
    assert exc.value.status_code == 401


def test_create_and_decode_access_token(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    token = auth.create_access_token("user-123", "admin")
    payload = auth.decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["role"] == "admin"
    assert payload["type"] == "access"


def test_refresh_token(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    auth.register_user("refreshtest", "password123")
    refresh = auth.create_refresh_token("refreshtest-id")
    payload = auth.verify_refresh_token(refresh)
    assert payload["sub"] == "refreshtest-id"
    assert payload["type"] == "refresh"


def test_get_user_by_id(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    user = auth.register_user("findme", "password123")
    found = auth.get_user_by_id(user["user_id"])
    assert found is not None
    assert found["username"] == "findme"


def test_get_user_by_username(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    auth.register_user("findbyname", "password123")
    found = auth.get_user_by_username("findbyname")
    assert found is not None
    assert found["username"] == "findbyname"


def test_get_nonexistent_user(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    assert auth.get_user_by_id("nonexistent-id") is None
    assert auth.get_user_by_username("nonexistent") is None


def test_rate_limiting(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    # Allow first 5 requests
    for i in range(5):
        assert auth.check_rate_limit("user1", "/api/test", max_requests=5, window_seconds=60)

    # 6th should be blocked
    assert not auth.check_rate_limit("user1", "/api/test", max_requests=5, window_seconds=60)


def test_rate_limit_new_window(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    # Different endpoint = different limit
    assert auth.check_rate_limit("user1", "/api/endpoint_a", max_requests=2, window_seconds=60)
    assert auth.check_rate_limit("user1", "/api/endpoint_a", max_requests=2, window_seconds=60)
    assert not auth.check_rate_limit("user1", "/api/endpoint_a", max_requests=2, window_seconds=60)
    # Different endpoint still allowed
    assert auth.check_rate_limit("user1", "/api/endpoint_b", max_requests=2, window_seconds=60)


def test_quota_check_and_increment(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    auth.register_user("quotauser", "password123")
    user = auth.get_user_by_username("quotauser")

    # Default quota: 100 sessions/month
    assert auth.check_quota(user["user_id"], "session")

    # Increment 100 times
    for _ in range(100):
        auth.increment_quota(user["user_id"], "session")

    # Should be over quota
    assert not auth.check_quota(user["user_id"], "session")


def test_quota_status(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    auth.register_user("statususer", "password123")
    user = auth.get_user_by_username("statususer")

    status = auth.get_quota_status(user["user_id"])
    assert "tokens_used" in status
    assert "token_budget" in status
    assert "sessions_used" in status
    assert "session_budget" in status


def test_session_share(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    auth.register_user("shareuser", "password123")
    user = auth.get_user_by_username("shareuser")

    share_id = auth.create_session_share("session-123", user["user_id"])
    assert len(share_id) > 0

    share = auth.get_shared_session(share_id)
    assert share is not None
    assert share["session_id"] == "session-123"
    assert share["owner_id"] == user["user_id"]


def test_revoke_session_share(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    auth.register_user("revokeuser", "password123")
    user = auth.get_user_by_username("revokeuser")

    share_id = auth.create_session_share("session-456", user["user_id"])
    auth.revoke_session_share(share_id, user["user_id"])

    share = auth.get_shared_session(share_id)
    assert share is None


def test_get_user_shares(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    auth.register_user("sharesuser", "password123")
    user = auth.get_user_by_username("sharesuser")

    auth.create_session_share("session-a", user["user_id"])
    auth.create_session_share("session-b", user["user_id"])

    shares = auth.get_user_shares(user["user_id"])
    assert len(shares) == 2


def test_seed_default_user(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    auth.seed_default_user()
    admin = auth.get_user_by_username("admin")
    assert admin is not None
    assert admin["role"] == "admin"


def test_seed_default_user_idempotent(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    auth.seed_default_user()
    auth.seed_default_user()  # Should not fail
    admin = auth.get_user_by_username("admin")
    assert admin is not None


def test_expired_refresh_token(tmp_auth_db):
    import importlib
    import auth
    importlib.reload(auth)

    # Manually insert expired token
    import hashlib
    import sqlite3
    from jose import jwt

    # Use time.time() directly to avoid UTC/local clock mismatch
    past_time = time.time() - 3600  # 1 hour ago

    payload = {
        "sub": "expired-user",
        "exp": past_time,
        "type": "refresh",
    }
    token = jwt.encode(payload, os.environ["SES_JWT_SECRET"], algorithm="HS256")
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    conn = sqlite3.connect(str(auth.AUTH_DB_PATH))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO refresh_tokens (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
        (token_hash, "expired-user", past_time)
    )
    conn.commit()
    conn.close()

    with pytest.raises(HTTPException) as exc:
        auth.verify_refresh_token(token)
    assert exc.value.status_code == 401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
