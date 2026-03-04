"""
DayCare Backend — Utility Helpers
===================================
Auth (password hashing, token generation),
response helpers, validation, CORS headers.
"""

import hashlib
import uuid
import json
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify
from db.schema import get_conn


# ── DATETIME ───────────────────────────────────────────────────────
def now_iso():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def today_str():
    return datetime.utcnow().strftime("%Y-%m-%d")

def new_id():
    return str(uuid.uuid4())


# ── PASSWORD ───────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    """SHA-256 hash with a fixed salt prefix."""
    salted = f"daycare_2024_{password}_secure"
    return hashlib.sha256(salted.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed


# ── SESSION TOKENS ─────────────────────────────────────────────────
def create_session(user_id: str) -> str:
    """Generate and store a 30-day session token."""
    token   = str(uuid.uuid4()).replace("-", "")
    expires = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = get_conn()
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
        (token, user_id, now_iso(), expires)
    )
    conn.commit()
    conn.close()
    return token

def get_user_from_token(token: str):
    """Return user row for a valid, unexpired token, or None."""
    if not token:
        return None
    conn  = get_conn()
    row   = conn.execute(
        """SELECT u.* FROM users u
           JOIN sessions s ON s.user_id = u.id
           WHERE s.token = ? AND s.expires_at > ?""",
        (token, now_iso())
    ).fetchone()
    conn.close()
    return row

def delete_session(token: str):
    conn = get_conn()
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()


# ── AUTH DECORATOR ─────────────────────────────────────────────────
def require_auth(f):
    """Decorator: inject current_user or return 401."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-Auth-Token") or request.args.get("token")
        user  = get_user_from_token(token)
        if not user:
            return error("Unauthorised — please log in", 401)
        return f(*args, user=user, **kwargs)
    return decorated


# ── RESPONSE HELPERS ───────────────────────────────────────────────
def success(data=None, message="OK", status=200):
    resp = {"success": True, "message": message}
    if data is not None:
        resp["data"] = data
    response = jsonify(resp)
    _add_cors(response)
    return response, status

def error(message="Error", status=400, details=None):
    resp = {"success": False, "message": message}
    if details:
        resp["details"] = details
    response = jsonify(resp)
    _add_cors(response)
    return response, status

def _add_cors(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Auth-Token"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"


# ── VALIDATION ─────────────────────────────────────────────────────
def require_fields(data: dict, fields: list):
    """Return list of missing required fields."""
    return [f for f in fields if not data.get(f)]

def row_to_dict(row):
    """Convert sqlite3.Row to plain dict."""
    if row is None:
        return None
    return dict(row)

def rows_to_list(rows):
    return [dict(r) for r in rows]


# ── USER SAFE DICT (strip password) ───────────────────────────────
def safe_user(user):
    d = dict(user)
    d.pop("password_hash", None)
    return d
