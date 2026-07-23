"""
Authentication & Authorization — Phase 5.1

JWT-based auth with login/register/token refresh.
Per-user session isolation, rate limiting, and quotas.
"""

import os
import time
import uuid
import secrets
import hashlib
import hmac
import sqlite3
import json
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from db import get_connection

AUTH_DB_PATH = Path(os.environ.get("SES_AUTH_DB", "data/auth.db"))

_JWT_SECRET_FILE = Path("data/.jwt_secret")


def _load_or_create_jwt_secret():
    env_key = os.environ.get("SES_JWT_SECRET")
    if env_key:
        return env_key
    _JWT_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _JWT_SECRET_FILE.exists():
        return _JWT_SECRET_FILE.read_text().strip()
    secret = secrets.token_urlsafe(32)
    _JWT_SECRET_FILE.write_text(secret)
    return secret


SECRET_KEY = _load_or_create_jwt_secret()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.environ.get("SES_TOKEN_EXPIRE_MINUTES", "1440")
)  # 24h
REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("SES_REFRESH_EXPIRE_DAYS", "30"))

security = HTTPBearer(auto_error=False)


def init_auth_schema():
    """Create auth tables."""
    conn = get_connection(str(AUTH_DB_PATH))
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE,
            hashed_password TEXT NOT NULL,
            display_name TEXT DEFAULT '',
            role TEXT DEFAULT 'user',
            is_active INTEGER DEFAULT 1,
            is_public INTEGER DEFAULT 0,
            created_at REAL DEFAULT (julianday('now')),
            updated_at REAL DEFAULT (julianday('now')),
            last_login REAL
        );

        CREATE TABLE IF NOT EXISTS refresh_tokens (
            token_hash TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            expires_at REAL NOT NULL,
            created_at REAL DEFAULT (julianday('now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS user_quotas (
            user_id TEXT PRIMARY KEY,
            monthly_token_budget INTEGER DEFAULT 1000000,
            tokens_used_this_month INTEGER DEFAULT 0,
            monthly_session_budget INTEGER DEFAULT 100,
            sessions_this_month INTEGER DEFAULT 0,
            reset_date TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS rate_limits (
            user_id TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            request_count INTEGER DEFAULT 0,
            window_start REAL DEFAULT 0,
            PRIMARY KEY (user_id, endpoint)
        );

        CREATE TABLE IF NOT EXISTS session_shares (
            share_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            is_public INTEGER DEFAULT 0,
            created_at REAL DEFAULT (strftime('%s', 'now'))
        );

        CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
        CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
        CREATE INDEX IF NOT EXISTS idx_session_shares_session ON session_shares(session_id);
        CREATE INDEX IF NOT EXISTS idx_session_shares_share ON session_shares(share_id);
    """)
    conn.commit()


# ─── PASSWORD HASHING (PBKDF2-SHA256) ────────────────────────────────────────


def hash_password(password: str) -> str:
    """Hash password with PBKDF2-SHA256 + random salt."""
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 100000
    ).hex()
    return f"{salt}:{hashed}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against stored hash."""
    salt, stored_hash = hashed.split(":")
    computed = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 100000
    ).hex()
    return hmac.compare_digest(computed, stored_hash)


# ─── JWT TOKENS ──────────────────────────────────────────────────────────────


def create_access_token(user_id: str, role: str = "user") -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "role": role,
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access",
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh",
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    # Store hash of refresh token
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn = get_connection(str(AUTH_DB_PATH))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO refresh_tokens (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
        (token_hash, user_id, expire.timestamp()),
    )
    conn.commit()
    return token


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # Manual expiration check (python-jose doesn't always enforce it)
        if "exp" in payload:
            import time

            if payload["exp"] < time.time():
                raise HTTPException(status_code=401, detail="Token has expired")
        if payload.get("type") not in ("access", "refresh"):
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def verify_refresh_token(token: str) -> dict:
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")
    # Verify token hash exists and isn't expired
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    conn = get_connection(str(AUTH_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM refresh_tokens WHERE token_hash = ? AND expires_at > ?",
        (token_hash, time.time()),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Refresh token expired or revoked")
    return payload


# ─── USER CRUD ───────────────────────────────────────────────────────────────


def register_user(
    username: str, password: str, email: str = "", display_name: str = ""
) -> dict:
    """Register a new user. Returns user dict."""
    if len(username) < 3:
        raise HTTPException(
            status_code=400, detail="Username must be at least 3 characters"
        )
    if len(password) < 6:
        raise HTTPException(
            status_code=400, detail="Password must be at least 6 characters"
        )

    user_id = str(uuid.uuid4())
    hashed = hash_password(password)

    conn = get_connection(str(AUTH_DB_PATH))
    cur = conn.cursor()
    try:
        cur.execute(
            """INSERT INTO users (user_id, username, email, hashed_password, display_name)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, username, email or None, hashed, display_name or username),
        )
        # Initialize quotas
        cur.execute("INSERT INTO user_quotas (user_id) VALUES (?)", (user_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Username or email already exists")

    return {
        "user_id": user_id,
        "username": username,
        "display_name": display_name or username,
        "email": email,
        "role": "user",
    }


def authenticate_user(username: str, password: str) -> dict:
    """Authenticate and return user dict + tokens."""
    conn = get_connection(str(AUTH_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (username,))
    user = cur.fetchone()

    if not user or not verify_password(password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Update last login
    conn = get_connection(str(AUTH_DB_PATH))
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET last_login = ? WHERE user_id = ?",
        (time.time(), user["user_id"]),
    )
    conn.commit()

    access_token = create_access_token(user["user_id"], user["role"])
    refresh_token = create_refresh_token(user["user_id"])

    return {
        "user": {
            "user_id": user["user_id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "email": user["email"],
            "role": user["role"],
        },
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


def get_user_by_id(user_id: str) -> Optional[dict]:
    conn = get_connection(str(AUTH_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ? AND is_active = 1", (user_id,))
    row = cur.fetchone()
    if row:
        return dict(row)
    return None


def get_user_by_username(username: str) -> Optional[dict]:
    conn = get_connection(str(AUTH_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (username,))
    row = cur.fetchone()
    if row:
        return dict(row)
    return None


# ─── DEPENDENCIES ────────────────────────────────────────────────────────────


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """FastAPI dependency to get current user from JWT."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(credentials.credentials)
    user = get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[dict]:
    """FastAPI dependency that returns user if authenticated, None otherwise."""
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials)
        return get_user_by_id(payload["sub"])
    except HTTPException:
        return None


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency that requires admin role."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# ─── RATE LIMITING ───────────────────────────────────────────────────────────


def check_rate_limit(
    user_id: str, endpoint: str, max_requests: int = 60, window_seconds: int = 60
) -> bool:
    """Check if a user has exceeded rate limits. Returns True if allowed."""
    conn = get_connection(str(AUTH_DB_PATH))
    cur = conn.cursor()
    now = time.time()
    window_start = now - window_seconds

    cur.execute(
        "SELECT request_count, window_start FROM rate_limits WHERE user_id = ? AND endpoint = ?",
        (user_id, endpoint),
    )
    row = cur.fetchone()

    if row is None or row[1] < window_start:
        # New window
        cur.execute(
            """INSERT INTO rate_limits (user_id, endpoint, request_count, window_start)
               VALUES (?, ?, 1, ?)
               ON CONFLICT(user_id, endpoint) DO UPDATE SET request_count = 1, window_start = ?""",
            (user_id, endpoint, now, now),
        )
        conn.commit()
        return True
    elif row[0] >= max_requests:
        return False
    else:
        cur.execute(
            "UPDATE rate_limits SET request_count = request_count + 1 WHERE user_id = ? AND endpoint = ?",
            (user_id, endpoint),
        )
        conn.commit()
        return True


# ─── QUOTAS ──────────────────────────────────────────────────────────────────


def reset_monthly_quotas():
    """Reset monthly quotas for all users (call this via cron on 1st of month)."""
    now = datetime.utcnow()
    reset_date = now.strftime("%Y-%m")
    conn = get_connection(str(AUTH_DB_PATH))
    cur = conn.cursor()
    cur.execute(
        "UPDATE user_quotas SET tokens_used_this_month = 0, sessions_this_month = 0, reset_date = ?",
        (reset_date,),
    )
    conn.commit()


def check_quota(user_id: str, quota_type: str = "session") -> bool:
    """Check if user has quota remaining. Returns True if allowed."""
    conn = get_connection(str(AUTH_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM user_quotas WHERE user_id = ?", (user_id,))
    row = cur.fetchone()

    if not row:
        return True  # No quota set = unlimited

    now = datetime.utcnow()
    reset_date = now.strftime("%Y-%m")

    # Reset if new month
    if row["reset_date"] != reset_date:
        conn = get_connection(str(AUTH_DB_PATH))
        cur = conn.cursor()
        cur.execute(
            "UPDATE user_quotas SET tokens_used_this_month = 0, sessions_this_month = 0, reset_date = ?",
            (reset_date,),
        )
        conn.commit()
        return True

    if quota_type == "session":
        return row["sessions_this_month"] < row["monthly_session_budget"]
    elif quota_type == "tokens":
        return row["tokens_used_this_month"] < row["monthly_token_budget"]
    return True


def increment_quota(user_id: str, quota_type: str = "session", amount: int = 1):
    """Increment quota usage."""
    conn = get_connection(str(AUTH_DB_PATH))
    cur = conn.cursor()
    if quota_type == "session":
        cur.execute(
            "UPDATE user_quotas SET sessions_this_month = sessions_this_month + ? WHERE user_id = ?",
            (amount, user_id),
        )
    elif quota_type == "tokens":
        cur.execute(
            "UPDATE user_quotas SET tokens_used_this_month = tokens_used_this_month + ? WHERE user_id = ?",
            (amount, user_id),
        )
    conn.commit()


def get_quota_status(user_id: str) -> dict:
    """Get current quota status for a user."""
    conn = get_connection(str(AUTH_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM user_quotas WHERE user_id = ?", (user_id,))
    row = cur.fetchone()

    if not row:
        return {
            "tokens_used": 0,
            "token_budget": "unlimited",
            "sessions_used": 0,
            "session_budget": "unlimited",
        }

    return {
        "tokens_used": row["tokens_used_this_month"],
        "token_budget": row["monthly_token_budget"],
        "sessions_used": row["sessions_this_month"],
        "session_budget": row["monthly_session_budget"],
        "reset_date": row["reset_date"],
    }


# ─── SESSION SHARING ─────────────────────────────────────────────────────────


def create_session_share(
    session_id: str, owner_id: str, is_public: bool = False
) -> str:
    """Create a shareable link for a session."""
    share_id = secrets.token_urlsafe(16)
    conn = get_connection(str(AUTH_DB_PATH))
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO session_shares (share_id, session_id, owner_id, is_public) VALUES (?, ?, ?, ?)",
        (share_id, session_id, owner_id, 1 if is_public else 0),
    )
    conn.commit()
    return share_id


def get_shared_session(share_id: str) -> Optional[dict]:
    """Get a shared session by share ID."""
    conn = get_connection(str(AUTH_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM session_shares WHERE share_id = ?", (share_id,))
    row = cur.fetchone()
    if row:
        return dict(row)
    return None


def revoke_session_share(share_id: str, owner_id: str):
    """Revoke a session share."""
    conn = get_connection(str(AUTH_DB_PATH))
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM session_shares WHERE share_id = ? AND owner_id = ?",
        (share_id, owner_id),
    )
    conn.commit()


def get_user_shares(user_id: str) -> list:
    """Get all shares for a user."""
    conn = get_connection(str(AUTH_DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """SELECT ss.* FROM session_shares ss
           WHERE ss.owner_id = ?
           ORDER BY ss.created_at DESC""",
        (user_id,),
    )
    rows = cur.fetchall()
    return [dict(row) for row in rows]


# ─── SEED DEFAULT USER ──────────────────────────────────────────────────────


def seed_default_user():
    """Create a default 'admin' user if none exist. Password from env or auto-generated."""
    conn = get_connection(str(AUTH_DB_PATH))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as c FROM users")
    count = cur.fetchone()[0]

    if count == 0:
        default_password = secrets.token_urlsafe(16)
        try:
            user = register_user("admin", default_password, "", "Admin")
            # Make admin
            conn = get_connection(str(AUTH_DB_PATH))
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET role = 'admin' WHERE user_id = ?", (user["user_id"],)
            )
            conn.commit()
            print(f"[auth] Default admin user created. Password: {default_password}")
        except HTTPException:
            pass  # Already exists
