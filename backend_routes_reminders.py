"""
DayCare Backend — Reminders / Tasks Routes
===========================================
GET    /api/reminders           — List all reminders for user
GET    /api/reminders?date=today — Filter by today's done status
POST   /api/reminders           — Create new reminder
PUT    /api/reminders/<id>      — Update reminder (name, time, etc.)
PATCH  /api/reminders/<id>/done — Toggle done/undone
DELETE /api/reminders/<id>      — Delete reminder
DELETE /api/reminders/done/clear — Clear all done reminders for today
"""

from flask import Blueprint, request
from db.schema import get_conn
from utils.helpers import (
    now_iso, today_str, new_id,
    require_auth, success, error,
    require_fields, rows_to_list, row_to_dict
)

reminders_bp = Blueprint("reminders", __name__)


# ── LIST REMINDERS ─────────────────────────────────────────────────
@reminders_bp.route("/", methods=["GET", "OPTIONS"])
@require_auth
def list_reminders(user):
    if request.method == "OPTIONS":
        return success()

    category = request.args.get("category")      # filter by category
    date     = request.args.get("date", today_str())  # "today" = default

    conn = get_conn()
    query  = "SELECT * FROM reminders WHERE user_id=?"
    params = [user["id"]]

    if category:
        query  += " AND category=?"
        params.append(category)

    query += " ORDER BY time ASC"
    rows   = conn.execute(query, params).fetchall()
    conn.close()

    items = rows_to_list(rows)

    # Annotate with status
    from datetime import datetime
    now_min = datetime.utcnow().hour * 60 + datetime.utcnow().minute
    for item in items:
        h, m   = map(int, item["time"].split(":"))
        task_m = h * 60 + m
        if item["done"]:
            item["status"] = "done"
        elif now_min > task_m + 15:
            item["status"] = "overdue"
        elif now_min < task_m - 30:
            item["status"] = "upcoming"
        else:
            item["status"] = "pending"

    summary = {
        "total":    len(items),
        "done":     sum(1 for i in items if i["done"]),
        "overdue":  sum(1 for i in items if i.get("status") == "overdue"),
        "upcoming": sum(1 for i in items if i.get("status") == "upcoming"),
    }
    return success({"reminders": items, "summary": summary})


# ── CREATE REMINDER ────────────────────────────────────────────────
@reminders_bp.route("/", methods=["POST", "OPTIONS"])
@require_auth
def create_reminder(user):
    if request.method == "OPTIONS":
        return success()
    data    = request.get_json(silent=True) or {}
    missing = require_fields(data, ["name", "time"])
    if missing:
        return error(f"Missing fields: {', '.join(missing)}")

    # Validate time format HH:MM
    try:
        h, m = map(int, data["time"].split(":"))
        assert 0 <= h <= 23 and 0 <= m <= 59
    except Exception:
        return error("Invalid time format. Use HH:MM (e.g. 08:30)")

    rid = new_id()
    ts  = now_iso()
    conn = get_conn()
    conn.execute("""
        INSERT INTO reminders
            (id, user_id, name, time, icon, category, repeat, priority, done, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,0,?,?)
    """, (
        rid, user["id"],
        data["name"].strip(),
        data["time"],
        data.get("icon", "📋"),
        data.get("category", "other"),
        data.get("repeat", "daily"),
        data.get("priority", "normal"),
        ts, ts
    ))
    conn.commit()
    row = conn.execute("SELECT * FROM reminders WHERE id=?", (rid,)).fetchone()
    conn.close()
    return success({"reminder": row_to_dict(row)}, "Reminder created!", 201)


# ── UPDATE REMINDER ────────────────────────────────────────────────
@reminders_bp.route("/<rid>", methods=["PUT", "PATCH", "OPTIONS"])
@require_auth
def update_reminder(user, rid):
    if request.method == "OPTIONS":
        return success()
    data = request.get_json(silent=True) or {}

    conn = get_conn()
    existing = conn.execute(
        "SELECT * FROM reminders WHERE id=? AND user_id=?", (rid, user["id"])
    ).fetchone()
    if not existing:
        conn.close()
        return error("Reminder not found", 404)

    allowed = ["name", "time", "icon", "category", "repeat", "priority"]
    updates = {k: data[k] for k in allowed if k in data}
    if not updates:
        conn.close()
        return error("No valid fields to update")

    set_clause = ", ".join(f"{k}=?" for k in updates)
    values     = list(updates.values()) + [now_iso(), rid, user["id"]]
    conn.execute(
        f"UPDATE reminders SET {set_clause}, updated_at=? WHERE id=? AND user_id=?",
        values
    )
    conn.commit()
    row = conn.execute("SELECT * FROM reminders WHERE id=?", (rid,)).fetchone()
    conn.close()
    return success({"reminder": row_to_dict(row)}, "Reminder updated!")


# ── TOGGLE DONE ────────────────────────────────────────────────────
@reminders_bp.route("/<rid>/done", methods=["PATCH", "OPTIONS"])
@require_auth
def toggle_done(user, rid):
    if request.method == "OPTIONS":
        return success()
    conn = get_conn()
    row  = conn.execute(
        "SELECT * FROM reminders WHERE id=? AND user_id=?", (rid, user["id"])
    ).fetchone()
    if not row:
        conn.close()
        return error("Reminder not found", 404)

    new_done = 0 if row["done"] else 1
    done_date = today_str() if new_done else None
    conn.execute(
        "UPDATE reminders SET done=?, done_date=?, updated_at=? WHERE id=?",
        (new_done, done_date, now_iso(), rid)
    )
    conn.commit()
    updated = conn.execute("SELECT * FROM reminders WHERE id=?", (rid,)).fetchone()
    conn.close()
    msg = "✅ Marked as done! Great job!" if new_done else "↩ Marked as not done"
    return success({"reminder": row_to_dict(updated)}, msg)


# ── DELETE REMINDER ────────────────────────────────────────────────
@reminders_bp.route("/<rid>", methods=["DELETE", "OPTIONS"])
@require_auth
def delete_reminder(user, rid):
    if request.method == "OPTIONS":
        return success()
    conn = get_conn()
    row  = conn.execute(
        "SELECT id FROM reminders WHERE id=? AND user_id=?", (rid, user["id"])
    ).fetchone()
    if not row:
        conn.close()
        return error("Reminder not found", 404)
    conn.execute("DELETE FROM reminders WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    return success(message="Reminder deleted.")


# ── CLEAR ALL DONE ─────────────────────────────────────────────────
@reminders_bp.route("/done/clear", methods=["DELETE", "OPTIONS"])
@require_auth
def clear_done(user):
    if request.method == "OPTIONS":
        return success()
    conn = get_conn()
    # Only reset daily ones — permanent "once" tasks get deleted
    conn.execute(
        "UPDATE reminders SET done=0, done_date=NULL, updated_at=? WHERE user_id=? AND done=1 AND repeat='daily'",
        (now_iso(), user["id"])
    )
    conn.execute(
        "DELETE FROM reminders WHERE user_id=? AND done=1 AND repeat='once'",
        (user["id"],)
    )
    conn.commit()
    conn.close()
    return success(message="Done reminders reset for new day!")
