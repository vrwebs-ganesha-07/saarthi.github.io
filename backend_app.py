"""
DayCare Backend — Main Flask Application
=========================================
Run with:
    python app.py

The server starts at http://localhost:5000

API Base URL: http://localhost:5000/api

All endpoints return JSON:
  { "success": true/false, "message": "...", "data": {...} }

Authentication:
  Include header:  X-Auth-Token: <your_token>
  Obtain token via POST /api/auth/login or /api/auth/register
"""

import sys
import os

# Make subpackages importable
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, jsonify, request
from db.schema import init_db
from routes.users            import auth_bp, users_bp
from routes.reminders        import reminders_bp
from routes.health_contacts  import health_bp, contacts_bp, habits_bp

# ── APP SETUP ──────────────────────────────────────────────────────
app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False


# ── CORS (manual, no flask-cors needed) ───────────────────────────
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Auth-Token"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
    return response

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        from flask import make_response
        resp = make_response()
        resp.headers["Access-Control-Allow-Origin"]  = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Auth-Token"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        return resp, 200


# ── REGISTER BLUEPRINTS ────────────────────────────────────────────
app.register_blueprint(auth_bp,       url_prefix="/api/auth")
app.register_blueprint(users_bp,      url_prefix="/api/users")
app.register_blueprint(reminders_bp,  url_prefix="/api/reminders")
app.register_blueprint(health_bp,     url_prefix="/api/health")
app.register_blueprint(contacts_bp,   url_prefix="/api/contacts")
app.register_blueprint(habits_bp,     url_prefix="/api/habits")


# ── ROOT & HEALTH CHECK ────────────────────────────────────────────
@app.route("/")
def root():
    return jsonify({
        "app":     "DayCare Backend API",
        "version": "1.0.0",
        "status":  "running ☀️",
        "docs":    "See /api/routes for all endpoints"
    })

@app.route("/api/routes")
def list_routes():
    """List all registered API routes."""
    routes = []
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        if rule.rule.startswith("/api"):
            routes.append({
                "endpoint": rule.rule,
                "methods":  sorted(m for m in rule.methods if m not in ("HEAD","OPTIONS"))
            })
    return jsonify({"routes": routes, "total": len(routes)})

@app.route("/api/ping")
def ping():
    return jsonify({"pong": True, "message": "DayCare server is healthy ✅"})


# ── ERROR HANDLERS ─────────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return jsonify({"success": False, "message": "Endpoint not found. Check /api/routes"}), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"success": False, "message": "Method not allowed for this endpoint"}), 405

@app.errorhandler(500)
def server_error(e):
    return jsonify({"success": False, "message": "Internal server error", "error": str(e)}), 500


# ── STARTUP ────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "═"*52)
    print("  ☀️  DayCare Backend Server")
    print("═"*52)
    init_db()
    print("📡  Starting on http://localhost:5000")
    print("📚  API docs at  http://localhost:5000/api/routes")
    print("═"*52 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
