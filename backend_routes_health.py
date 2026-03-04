"""
DayCare Backend — Health, Emergency Contacts & Habits Routes
=============================================================
Health Logs:
  GET  /api/health              — Today's health log (or date param)
  POST /api/health              — Upsert today's health log
  GET  /api/health/history      — Last 30 days

Emergency Contacts:
  GET    /api/contacts          — List contacts
  POST   /api/contacts          — Add contact
  PUT    /api/contacts/<id>     — Update contact
  DELETE /api/contacts/<id>     — Remove contact

Habits:
  GET   /api/habits             — 7-day view for all habits
  PATCH /api/habits             — Toggle habit completion for a date
"""

from flask import Blueprint, request
from db.schema import get_conn
from utils.helpers import (
    now_iso, today_str, new_id,
    require_auth, success, error,
    require_fields, rows_to_list, row_to_dict
)
from datetime import datetime, timedelta

health_bp   = Blueprint("health",   __name__)
contacts_bp = Blueprint("contacts", __name__)
habits_bp   = Blueprint("habits",   __name__)


# ══════════════════════════════════════════════════════════════
#  HEALTH LOGS
# ══════════════════════════════════════════════════════════════

@health_bp.route("/", methods=["GET", "OPTIONS"])
@require_auth
def get_health(user):
    if request.method == "OPTIONS":
        return success()
    date = request.args.get("date", today_str())
    conn = get_conn()
    row  = conn.execute(
        "SELECT * FROM health_logs WHERE user_id=? AND log_date=?",
        (user["id"], date)
    ).fetchone()
    conn.close()
    if not row:
        # Return empty template for the date
        return success({"log": {
            "log_date": date, "water_glasses": 0, "steps": 0,
            "bp_systolic": None, "bp_diastolic": None,
            "sleep_hours": None, "mood": None, "notes": ""
        }})
    return success({"log": row_to_dict(row)})


@health_bp.route("/", methods=["POST", "OPTIONS"])
@require_auth
def upsert_health(user):
    """Create or update today's health log (upsert)."""
    if request.method == "OPTIONS":
        return success()
    data     = request.get_json(silent=True) or {}
    log_date = data.get("date", today_str())
    ts       = now_iso()
    conn     = get_conn()

    existing = conn.execute(
        "SELECT id FROM health_logs WHERE user_id=? AND log_date=?",
        (user["id"], log_date)
    ).fetchone()

    fields   = ["water_glasses", "steps", "bp_systolic", "bp_diastolic",
                "sleep_hours", "mood", "notes"]
    updates  = {f: data[f] for f in fields if f in data}

    if existing:
        if updates:
            set_clause = ", ".join(f"{k}=?" for k in updates)
            vals       = list(updates.values()) + [ts, existing["id"]]
            conn.execute(
                f"UPDATE health_logs SET {set_clause}, updated_at=? WHERE id=?", vals
            )
    else:
        lid = new_id()
        conn.execute("""
            INSERT INTO health_logs
                (id, user_id, log_date, water_glasses, steps,
                 bp_systolic, bp_diastolic, sleep_hours, mood, notes,
                 created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            lid, user["id"], log_date,
            updates.get("water_glasses", 0),
            updates.get("steps", 0),
            updates.get("bp_systolic"),
            updates.get("bp_diastolic"),
            updates.get("sleep_hours"),
            updates.get("mood"),
            updates.get("notes", ""),
            ts, ts
        ))

    conn.commit()
    row = conn.execute(
        "SELECT * FROM health_logs WHERE user_id=? AND log_date=?",
        (user["id"], log_date)
    ).fetchone()
    conn.close()
    return success({"log": row_to_dict(row)}, "Health log saved!")


@health_bp.route("/history", methods=["GET", "OPTIONS"])
@require_auth
def health_history(user):
    if request.method == "OPTIONS":
        return success()
    days = int(request.args.get("days", 30))
    days = min(days, 90)  # cap at 90 days
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    conn  = get_conn()
    rows  = conn.execute(
        "SELECT * FROM health_logs WHERE user_id=? AND log_date >= ? ORDER BY log_date DESC",
        (user["id"], since)
    ).fetchall()
    conn.close()
    logs = rows_to_list(rows)
    # Compute averages
    if logs:
        avg_water = round(sum(l["water_glasses"] for l in logs) / len(logs), 1)
        avg_steps = round(sum(l["steps"] or 0 for l in logs) / len(logs))
        avg_sleep = round(sum(l["sleep_hours"] or 0 for l in logs if l["sleep_hours"]) /
                          max(1, sum(1 for l in logs if l["sleep_hours"])), 1)
    else:
        avg_water = avg_steps = avg_sleep = 0

    return success({
        "logs": logs,
        "averages": {
            "water_glasses": avg_water,
            "steps":         avg_steps,
            "sleep_hours":   avg_sleep,
        }
    })


# ══════════════════════════════════════════════════════════════
#  EMERGENCY CONTACTS
# ══════════════════════════════════════════════════════════════

@contacts_bp.route("/", methods=["GET", "OPTIONS"])
@require_auth
def list_contacts(user):
    if request.method == "OPTIONS":
        return success()
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM emergency_contacts WHERE user_id=? ORDER BY sort_order ASC",
        (user["id"],)
    ).fetchall()
    conn.close()
    return success({"contacts": rows_to_list(rows)})


@contacts_bp.route("/", methods=["POST", "OPTIONS"])
@require_auth
def add_contact(user):
    if request.method == "OPTIONS":
        return success()
    data    = request.get_json(silent=True) or {}
    missing = require_fields(data, ["name", "phone"])
    if missing:
        return error(f"Missing fields: {', '.join(missing)}")

    # Max 10 contacts
    conn = get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM emergency_contacts WHERE user_id=?", (user["id"],)
    ).fetchone()[0]
    if count >= 10:
        conn.close()
        return error("Maximum 10 emergency contacts allowed")

    rel_emoji = {
        "Son": "👨", "Daughter": "👩", "Spouse": "💑", "Sibling": "🧑",
        "Friend": "😊", "Doctor": "👩‍⚕️", "Neighbour": "🏠",
        "Caregiver": "🤝", "Ambulance": "🚑"
    }
    relation = data.get("relation", "")
    avatar   = data.get("avatar", rel_emoji.get(relation, "👤"))

    cid = new_id()
    conn.execute("""
        INSERT INTO emergency_contacts
            (id, user_id, name, phone, relation, avatar, sort_order, created_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, (cid, user["id"], data["name"].strip(), data["phone"].strip(),
          relation, avatar, count, now_iso()))
    conn.commit()
    row = conn.execute("SELECT * FROM emergency_contacts WHERE id=?", (cid,)).fetchone()
    conn.close()
    return success({"contact": row_to_dict(row)}, f"{data['name']} added to emergency contacts!", 201)


@contacts_bp.route("/<cid>", methods=["PUT", "PATCH", "OPTIONS"])
@require_auth
def update_contact(user, cid):
    if request.method == "OPTIONS":
        return success()
    data = request.get_json(silent=True) or {}
    conn = get_conn()
    existing = conn.execute(
        "SELECT id FROM emergency_contacts WHERE id=? AND user_id=?", (cid, user["id"])
    ).fetchone()
    if not existing:
        conn.close()
        return error("Contact not found", 404)

    allowed = ["name", "phone", "relation", "avatar"]
    updates = {k: data[k] for k in allowed if k in data}
    if not updates:
        conn.close()
        return error("No valid fields to update")

    set_clause = ", ".join(f"{k}=?" for k in updates)
    vals       = list(updates.values()) + [cid, user["id"]]
    conn.execute(f"UPDATE emergency_contacts SET {set_clause} WHERE id=? AND user_id=?", vals)
    conn.commit()
    row = conn.execute("SELECT * FROM emergency_contacts WHERE id=?", (cid,)).fetchone()
    conn.close()
    return success({"contact": row_to_dict(row)}, "Contact updated!")


@contacts_bp.route("/<cid>", methods=["DELETE", "OPTIONS"])
@require_auth
def delete_contact(user, cid):
    if request.method == "OPTIONS":
        return success()
    conn = get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM emergency_contacts WHERE user_id=?", (user["id"],)
    ).fetchone()[0]
    if count <= 1:
        conn.close()
        return error("Keep at least one emergency contact!")

    conn.execute(
        "DELETE FROM emergency_contacts WHERE id=? AND user_id=?", (cid, user["id"])
    )
    conn.commit()
    conn.close()
    return success(message="Contact removed.")


# ══════════════════════════════════════════════════════════════
#  HABITS
# ══════════════════════════════════════════════════════════════

DEFAULT_HABITS = [
    {"name": "Morning Walk",        "icon": "🌅"},
    {"name": "Medicine on Time",    "icon": "💊"},
    {"name": "Daily Reading",       "icon": "📖"},
    {"name": "Breathing Exercise",  "icon": "🧘"},
]


@habits_bp.route("/", methods=["GET", "OPTIONS"])
@require_auth
def get_habits(user):
    """Return 7-day completion view for all habits."""
    if request.method == "OPTIONS":
        return success()

    days  = 7
    dates = [(datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
             for i in range(days - 1, -1, -1)]
    conn  = get_conn()
    rows  = conn.execute(
        "SELECT * FROM habit_logs WHERE user_id=? AND log_date >= ?",
        (user["id"], dates[0])
    ).fetchall()
    conn.close()

    logs_by_key = {f"{r['habit_name']}_{r['log_date']}": r["completed"] for r in rows}

    result = []
    for h in DEFAULT_HABITS:
        week   = [logs_by_key.get(f"{h['name']}_{d}", 0) for d in dates]
        streak = 0
        for d in reversed(dates):
            if logs_by_key.get(f"{h['name']}_{d}", 0):
                streak += 1
            else:
                break
        result.append({
            "name":   h["name"],
            "icon":   h["icon"],
            "week":   week,
            "dates":  dates,
            "streak": streak,
        })

    return success({"habits": result, "dates": dates})


@habits_bp.route("/", methods=["PATCH", "OPTIONS"])
@require_auth
def toggle_habit(user):
    """Toggle a habit on/off for a given date."""
    if request.method == "OPTIONS":
        return success()
    data    = request.get_json(silent=True) or {}
    missing = require_fields(data, ["habit_name", "date"])
    if missing:
        return error(f"Missing fields: {', '.join(missing)}")

    habit_name = data["habit_name"]
    log_date   = data["date"]
    ts         = now_iso()

    # Find icon for this habit
    icon = next((h["icon"] for h in DEFAULT_HABITS if h["name"] == habit_name), "✅")

    conn = get_conn()
    existing = conn.execute(
        "SELECT * FROM habit_logs WHERE user_id=? AND habit_name=? AND log_date=?",
        (user["id"], habit_name, log_date)
    ).fetchone()

    if existing:
        new_val = 0 if existing["completed"] else 1
        conn.execute(
            "UPDATE habit_logs SET completed=? WHERE id=?",
            (new_val, existing["id"])
        )
    else:
        conn.execute("""
            INSERT INTO habit_logs (id, user_id, habit_name, habit_icon, log_date, completed, created_at)
            VALUES (?,?,?,?,?,1,?)
        """, (new_id(), user["id"], habit_name, icon, log_date, ts))
        new_val = 1

    conn.commit()
    conn.close()
    msg = f"🔥 {habit_name} marked complete!" if new_val else f"↩ {habit_name} unmarked"
    return success({"completed": bool(new_val), "date": log_date}, msg)
