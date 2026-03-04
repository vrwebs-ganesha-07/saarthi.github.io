"""
DayCare Backend — User & Auth Routes
======================================
POST /api/auth/register   — Create new account
POST /api/auth/login      — Login, receive token
POST /api/auth/logout     — Invalidate token
GET  /api/users/me        — Get own profile
PUT  /api/users/me        — Update profile
PUT  /api/users/me/settings — Update accessibility settings
DELETE /api/users/me      — Delete account
"""

from flask import Blueprint, request
from db.schema import get_conn
from utils.helpers import (
    now_iso, new_id, hash_password, verify_password,
    create_session, delete_session, require_auth,
    success, error, require_fields, safe_user, row_to_dict
)

auth_bp  = Blueprint("auth",  __name__)
users_bp = Blueprint("users", __name__)


# ── REGISTER ───────────────────────────────────────────────────────
@auth_bp.route("/register", methods=["POST", "OPTIONS"])
def register():
    if request.method == "OPTIONS":
        return success()
    data = request.get_json(silent=True) or {}
    missing = require_fields(data, ["name", "password"])
    if missing:
        return error(f"Missing required fields: {', '.join(missing)}")

    name     = data["name"].strip()
    password = data["password"]

    if len(password) < 4:
        return error("Password must be at least 4 characters")

    conn = get_conn()
    # Check duplicate name (simple — real app would use email/phone)
    existing = conn.execute(
        "SELECT id FROM users WHERE LOWER(name) = LOWER(?)", (name,)
    ).fetchone()
    if existing:
        conn.close()
        return error("A user with this name already exists. Try a different name or add your city (e.g. Ramesh Mumbai)")

    uid = new_id()
    ts  = now_iso()
    conn.execute("""
        INSERT INTO users
            (id, name, age, city, gender, blood_group, health_notes,
             doctor_name, language, avatar, font_size, high_contrast,
             password_hash, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        uid,
        name,
        data.get("age"),
        data.get("city", ""),
        data.get("gender", ""),
        data.get("blood_group", ""),
        data.get("health_notes", ""),
        data.get("doctor_name", ""),
        data.get("language", "English"),
        data.get("avatar", "👴"),
        data.get("font_size", "medium"),
        0,
        hash_password(password),
        ts, ts
    ))

    # Create default notification settings
    conn.execute("""
        INSERT INTO notification_settings
            (id, user_id, medicine_reminders, exercise_reminder,
             water_reminder, activity_reminder, daily_quote,
             spiritual_reminder, updated_at)
        VALUES (?,?,1,1,0,1,1,0,?)
    """, (new_id(), uid, ts))

    # Seed default emergency contacts
    default_contacts = [
        (new_id(), uid, "Emergency Services", "112",       "Ambulance",  "🚑", 0, ts),
        (new_id(), uid, "Family Member",       "",          "Son",        "👨", 1, ts),
        (new_id(), uid, "My Doctor",           "",          "Doctor",     "👩‍⚕️", 2, ts),
    ]
    conn.executemany("""
        INSERT INTO emergency_contacts
            (id, user_id, name, phone, relation, avatar, sort_order, created_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, default_contacts)

    # Seed default reminders
    default_reminders = [
        (new_id(), uid, "Morning Medicine",   "07:00", "💊", "medicine", "daily",  "high",   ts, ts),
        (new_id(), uid, "Morning Walk",       "07:30", "🚶", "exercise", "daily",  "normal", ts, ts),
        (new_id(), uid, "Breakfast",          "08:30", "🍳", "meal",     "daily",  "normal", ts, ts),
        (new_id(), uid, "Drink Water",        "10:00", "💧", "water",    "daily",  "low",    ts, ts),
        (new_id(), uid, "Afternoon Medicine", "13:00", "💊", "medicine", "daily",  "high",   ts, ts),
        (new_id(), uid, "Lunch",              "13:30", "🍱", "meal",     "daily",  "normal", ts, ts),
        (new_id(), uid, "Evening Walk",       "17:00", "🌅", "exercise", "daily",  "normal", ts, ts),
        (new_id(), uid, "Evening Medicine",   "19:00", "💊", "medicine", "daily",  "high",   ts, ts),
        (new_id(), uid, "Dinner",             "20:00", "🍽", "meal",     "daily",  "normal", ts, ts),
    ]
    conn.executemany("""
        INSERT INTO reminders
            (id, user_id, name, time, icon, category, repeat, priority, done, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,0,?,?)
    """, default_reminders)

    conn.commit()
    conn.close()

    token = create_session(uid)
    user  = get_conn().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return success({
        "token": token,
        "user":  safe_user(user)
    }, "Account created successfully! Welcome to DayCare.", 201)


# ── LOGIN ──────────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["POST", "OPTIONS"])
def login():
    if request.method == "OPTIONS":
        return success()
    data = request.get_json(silent=True) or {}
    missing = require_fields(data, ["name", "password"])
    if missing:
        return error(f"Missing fields: {', '.join(missing)}")

    conn = get_conn()
    user = conn.execute(
        "SELECT * FROM users WHERE LOWER(name) = LOWER(?)", (data["name"].strip(),)
    ).fetchone()
    conn.close()

    if not user or not verify_password(data["password"], user["password_hash"]):
        return error("Incorrect name or password. Please try again.", 401)

    token = create_session(user["id"])
    return success({
        "token": token,
        "user":  safe_user(user)
    }, f"Welcome back, {user['name']}!")


# ── LOGOUT ─────────────────────────────────────────────────────────
@auth_bp.route("/logout", methods=["POST", "OPTIONS"])
@require_auth
def logout(user):
    if request.method == "OPTIONS":
        return success()
    token = request.headers.get("X-Auth-Token") or request.args.get("token")
    delete_session(token)
    return success(message="Logged out successfully.")


# ── GET PROFILE ────────────────────────────────────────────────────
@users_bp.route("/me", methods=["GET", "OPTIONS"])
@require_auth
def get_profile(user):
    if request.method == "OPTIONS":
        return success()
    conn = get_conn()
    notif = conn.execute(
        "SELECT * FROM notification_settings WHERE user_id=?", (user["id"],)
    ).fetchone()
    conn.close()
    return success({
        "user":                  safe_user(user),
        "notification_settings": row_to_dict(notif)
    })


# ── UPDATE PROFILE ─────────────────────────────────────────────────
@users_bp.route("/me", methods=["PUT", "PATCH", "OPTIONS"])
@require_auth
def update_profile(user):
    if request.method == "OPTIONS":
        return success()
    data  = request.get_json(silent=True) or {}
    allowed = ["name","age","city","gender","blood_group","health_notes",
               "doctor_name","language","avatar","font_size"]
    updates = {k: data[k] for k in allowed if k in data}
    if not updates:
        return error("No valid fields to update")

    conn = get_conn()
    # Check name uniqueness if being changed
    if "name" in updates and updates["name"].lower() != user["name"].lower():
        dup = conn.execute(
            "SELECT id FROM users WHERE LOWER(name)=LOWER(?) AND id!=?",
            (updates["name"], user["id"])
        ).fetchone()
        if dup:
            conn.close()
            return error("That name is already taken by another user")

    set_clause = ", ".join(f"{k}=?" for k in updates)
    values     = list(updates.values()) + [now_iso(), user["id"]]
    conn.execute(f"UPDATE users SET {set_clause}, updated_at=? WHERE id=?", values)
    conn.commit()
    updated = conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
    conn.close()
    return success({"user": safe_user(updated)}, "Profile updated!")


# ── UPDATE ACCESSIBILITY SETTINGS ──────────────────────────────────
@users_bp.route("/me/settings", methods=["PUT", "PATCH", "OPTIONS"])
@require_auth
def update_settings(user):
    if request.method == "OPTIONS":
        return success()
    data    = request.get_json(silent=True) or {}
    allowed = ["font_size", "high_contrast", "language", "avatar"]
    updates = {k: data[k] for k in allowed if k in data}
    if not updates:
        return error("No valid settings fields provided")

    conn = get_conn()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values     = list(updates.values()) + [now_iso(), user["id"]]
    conn.execute(f"UPDATE users SET {set_clause}, updated_at=? WHERE id=?", values)
    conn.commit()
    updated = conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
    conn.close()
    return success({"user": safe_user(updated)}, "Settings saved!")


# ── UPDATE NOTIFICATIONS ───────────────────────────────────────────
@users_bp.route("/me/notifications", methods=["PUT", "PATCH", "OPTIONS"])
@require_auth
def update_notifications(user):
    if request.method == "OPTIONS":
        return success()
    data    = request.get_json(silent=True) or {}
    allowed = ["medicine_reminders","exercise_reminder","water_reminder",
               "activity_reminder","daily_quote","spiritual_reminder"]
    updates = {k: (1 if data[k] else 0) for k in allowed if k in data}
    if not updates:
        return error("No notification fields provided")

    conn = get_conn()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values     = list(updates.values()) + [now_iso(), user["id"]]
    conn.execute(
        f"UPDATE notification_settings SET {set_clause}, updated_at=? WHERE user_id=?",
        values
    )
    conn.commit()
    notif = conn.execute(
        "SELECT * FROM notification_settings WHERE user_id=?", (user["id"],)
    ).fetchone()
    conn.close()
    return success({"notification_settings": row_to_dict(notif)}, "Notification settings updated!")


# ── DELETE ACCOUNT ─────────────────────────────────────────────────
@users_bp.route("/me", methods=["DELETE", "OPTIONS"])
@require_auth
def delete_account(user):
    if request.method == "OPTIONS":
        return success()
    conn = get_conn()
    conn.execute("DELETE FROM users WHERE id=?", (user["id"],))
    conn.commit()
    conn.close()
    return success(message="Account deleted. We will miss you!")
