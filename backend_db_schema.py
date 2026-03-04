"""
DayCare Backend — Database Schema & Connection
================================================
SQLite database with tables for:
  - users          : profile info, preferences, accessibility settings
  - reminders      : daily tasks/reminders per user
  - health_logs    : daily water, steps, BP, sleep tracking
  - emergency_contacts : per-user emergency contacts
  - habit_logs     : 7-day habit streak tracking
  - sessions       : user auth sessions (token-based)
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "daycare.db")


def get_conn():
    """Return a database connection with row_factory for dict-like access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all tables if they don't already exist."""
    conn = get_conn()
    cur = conn.cursor()

    # ── USERS ─────────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            age           INTEGER,
            city          TEXT,
            gender        TEXT,
            blood_group   TEXT,
            health_notes  TEXT,
            doctor_name   TEXT,
            language      TEXT DEFAULT 'English',
            avatar        TEXT DEFAULT '👴',
            font_size     TEXT DEFAULT 'medium',
            high_contrast INTEGER DEFAULT 0,
            password_hash TEXT NOT NULL,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        )
    """)

    # ── SESSIONS (token auth) ──────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token      TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # ── REMINDERS ─────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id         TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL,
            name       TEXT NOT NULL,
            time       TEXT NOT NULL,
            icon       TEXT DEFAULT '📋',
            category   TEXT DEFAULT 'other',
            repeat     TEXT DEFAULT 'daily',
            priority   TEXT DEFAULT 'normal',
            done       INTEGER DEFAULT 0,
            done_date  TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # ── HEALTH LOGS (one row per user per day) ────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS health_logs (
            id            TEXT PRIMARY KEY,
            user_id       TEXT NOT NULL,
            log_date      TEXT NOT NULL,
            water_glasses INTEGER DEFAULT 0,
            steps         INTEGER DEFAULT 0,
            bp_systolic   INTEGER,
            bp_diastolic  INTEGER,
            sleep_hours   REAL,
            mood          TEXT,
            notes         TEXT,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            UNIQUE(user_id, log_date),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # ── EMERGENCY CONTACTS ─────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS emergency_contacts (
            id         TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL,
            name       TEXT NOT NULL,
            phone      TEXT NOT NULL,
            relation   TEXT,
            avatar     TEXT DEFAULT '👤',
            sort_order INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # ── HABIT LOGS ─────────────────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS habit_logs (
            id         TEXT PRIMARY KEY,
            user_id    TEXT NOT NULL,
            habit_name TEXT NOT NULL,
            habit_icon TEXT DEFAULT '✅',
            log_date   TEXT NOT NULL,
            completed  INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, habit_name, log_date),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # ── NOTIFICATION SETTINGS ──────────────────────────────────────
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notification_settings (
            id                  TEXT PRIMARY KEY,
            user_id             TEXT NOT NULL UNIQUE,
            medicine_reminders  INTEGER DEFAULT 1,
            exercise_reminder   INTEGER DEFAULT 1,
            water_reminder      INTEGER DEFAULT 0,
            activity_reminder   INTEGER DEFAULT 1,
            daily_quote         INTEGER DEFAULT 1,
            spiritual_reminder  INTEGER DEFAULT 0,
            updated_at          TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Database initialised:", DB_PATH)
