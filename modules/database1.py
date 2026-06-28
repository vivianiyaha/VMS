"""
Database module for Smart Visitor Management System.
Handles all SQLite operations, schema creation, and data access.
"""

import sqlite3
import os
import bcrypt
import pytz
from datetime import datetime
from pathlib import Path

DB_PATH = "data/vms.db"
LAGOS_TZ = pytz.timezone("Africa/Lagos")


def get_connection():
    """Return a SQLite connection with row factory."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def lagos_now():
    """Return current datetime in Africa/Lagos timezone."""
    return datetime.now(LAGOS_TZ)


def init_db():
    """Create all tables and seed default data on first run."""
    os.makedirs("data/visitors", exist_ok=True)
    os.makedirs("data/photos", exist_ok=True)
    os.makedirs("data/logs", exist_ok=True)
    os.makedirs("data/approvals", exist_ok=True)
    os.makedirs("data/exports", exist_ok=True)
    os.makedirs("data/backups", exist_ok=True)

    conn = get_connection()
    c = conn.cursor()

    # ── Visitors ────────────────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS visitors (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        visitor_number   TEXT    UNIQUE NOT NULL,
        barcode_id       TEXT    UNIQUE NOT NULL,
        full_name        TEXT    NOT NULL,
        phone            TEXT,
        email            TEXT,
        gender           TEXT,
        company          TEXT,
        address          TEXT,
        person_to_visit  TEXT,
        department       TEXT,
        purpose          TEXT,
        expected_duration TEXT,
        vehicle_reg      TEXT,
        id_type          TEXT,
        id_number        TEXT,
        photo_path       TEXT,
        items_carried    TEXT,
        emergency_name   TEXT,
        emergency_phone  TEXT,
        status           TEXT    DEFAULT 'Pending',
        entry_date       TEXT,
        entry_time       TEXT,
        entry_timestamp  TEXT,
        exit_date        TEXT,
        exit_time        TEXT,
        exit_timestamp   TEXT,
        visit_duration   TEXT,
        created_at       TEXT    DEFAULT CURRENT_TIMESTAMP
    )""")

    # ── Approvals ───────────────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS approvals (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        visitor_id      INTEGER REFERENCES visitors(id),
        visitor_number  TEXT,
        approver_name   TEXT,
        approver_role   TEXT,
        action          TEXT,
        comments        TEXT,
        action_date     TEXT,
        action_time     TEXT,
        created_at      TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    # ── Departments ─────────────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS departments (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    )""")

    # ── Hosts ───────────────────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS hosts (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT NOT NULL,
        department TEXT,
        phone      TEXT,
        email      TEXT
    )""")

    # ── Admins ──────────────────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        username         TEXT    UNIQUE NOT NULL,
        password_hash    TEXT    NOT NULL,
        full_name        TEXT,
        role             TEXT    DEFAULT 'Receptionist',
        email            TEXT,
        must_change_pw   INTEGER DEFAULT 1,
        is_active        INTEGER DEFAULT 1,
        created_at       TEXT    DEFAULT CURRENT_TIMESTAMP,
        last_login       TEXT
    )""")

    # ── Audit Logs ──────────────────────────────────────────────────────────
    c.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        username    TEXT,
        action      TEXT,
        details     TEXT,
        ip_address  TEXT,
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    )""")

    # ── Seed default departments ─────────────────────────────────────────────
    default_depts = [
        "Administration", "Finance", "Human Resources", "Information Technology",
        "Operations", "Sales & Marketing", "Procurement", "Legal",
        "Security", "Customer Service", "Production", "Logistics"
    ]
    for dept in default_depts:
        c.execute("INSERT OR IGNORE INTO departments(name) VALUES (?)", (dept,))

    # ── Seed default admin ───────────────────────────────────────────────────
    existing = c.execute("SELECT id FROM admins WHERE username='admin'").fetchone()
    if not existing:
        pw_hash = bcrypt.hashpw("Admin@123".encode(), bcrypt.gensalt()).decode()
        c.execute("""
            INSERT INTO admins(username, password_hash, full_name, role, must_change_pw)
            VALUES (?, ?, ?, ?, ?)
        """, ("admin", pw_hash, "System Administrator", "Super Admin", 1))

    # ── Seed sample hosts ────────────────────────────────────────────────────
    sample_hosts = [
        ("Mrs. Adaeze Okonkwo", "Human Resources"),
        ("Mr. Chukwuemeka Eze", "Information Technology"),
        ("Mrs. Ngozi Adeyemi", "Finance"),
        ("Mr. Babatunde Olatunji", "Operations"),
        ("Mrs. Fatima Abdullahi", "Administration"),
        ("Mr. Emeka Nwosu", "Sales & Marketing"),
    ]
    for name, dept in sample_hosts:
        c.execute("INSERT OR IGNORE INTO hosts(name, department) VALUES (?, ?)", (name, dept))

    conn.commit()
    conn.close()


# ── Visitor CRUD ─────────────────────────────────────────────────────────────

def get_next_visitor_number():
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) as cnt FROM visitors").fetchone()
    conn.close()
    return f"VIS-{(row['cnt'] + 1):05d}"


def create_visitor(data: dict) -> int:
    conn = get_connection()
    now = lagos_now()
    c = conn.cursor()
    c.execute("""
        INSERT INTO visitors (
            visitor_number, barcode_id, full_name, phone, email, gender,
            company, address, person_to_visit, department, purpose,
            expected_duration, vehicle_reg, id_type, id_number, photo_path,
            items_carried, emergency_name, emergency_phone,
            status, entry_date, entry_time, entry_timestamp
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        data["visitor_number"], data["barcode_id"],
        data["full_name"], data.get("phone"), data.get("email"),
        data.get("gender"), data.get("company"), data.get("address"),
        data.get("person_to_visit"), data.get("department"), data.get("purpose"),
        data.get("expected_duration"), data.get("vehicle_reg"),
        data.get("id_type"), data.get("id_number"), data.get("photo_path"),
        data.get("items_carried"), data.get("emergency_name"), data.get("emergency_phone"),
        "Pending",
        now.strftime("%Y-%m-%d"),
        now.strftime("%H:%M:%S"),
        now.isoformat()
    ))
    visitor_id = c.lastrowid
    conn.commit()
    conn.close()
    return visitor_id


def get_visitor_by_barcode(barcode_id: str):
    conn = get_connection()
    row = conn.execute("SELECT * FROM visitors WHERE barcode_id=?", (barcode_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_visitor_by_number(visitor_number: str):
    conn = get_connection()
    row = conn.execute("SELECT * FROM visitors WHERE visitor_number=?", (visitor_number,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_visitors(status=None, date=None, department=None, search=None):
    conn = get_connection()
    query = "SELECT * FROM visitors WHERE 1=1"
    params = []
    if status:
        query += " AND status=?"
        params.append(status)
    if date:
        query += " AND entry_date=?"
        params.append(date)
    if department:
        query += " AND department=?"
        params.append(department)
    if search:
        query += " AND (full_name LIKE ? OR visitor_number LIKE ? OR phone LIKE ? OR barcode_id LIKE ?)"
        params += [f"%{search}%"] * 4
    query += " ORDER BY created_at DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_visitor_status(visitor_id: int, status: str):
    conn = get_connection()
    conn.execute("UPDATE visitors SET status=? WHERE id=?", (status, visitor_id))
    conn.commit()
    conn.close()


def record_exit(visitor_id: int):
    now = lagos_now()
    conn = get_connection()
    visitor = conn.execute("SELECT * FROM visitors WHERE id=?", (visitor_id,)).fetchone()
    visitor = dict(visitor)
    duration = ""
    if visitor.get("entry_timestamp"):
        try:
            entry_dt = datetime.fromisoformat(visitor["entry_timestamp"])
            if entry_dt.tzinfo is None:
                entry_dt = LAGOS_TZ.localize(entry_dt)
            delta = now - entry_dt
            hours, rem = divmod(int(delta.total_seconds()), 3600)
            mins = rem // 60
            duration = f"{hours}h {mins}m"
        except Exception:
            duration = "N/A"
    conn.execute("""
        UPDATE visitors SET
            status='Checked Out',
            exit_date=?, exit_time=?, exit_timestamp=?, visit_duration=?
        WHERE id=?
    """, (now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"), now.isoformat(), duration, visitor_id))
    conn.commit()
    conn.close()
    return duration


# ── Approval CRUD ────────────────────────────────────────────────────────────

def create_approval(data: dict):
    now = lagos_now()
    conn = get_connection()
    conn.execute("""
        INSERT INTO approvals(visitor_id, visitor_number, approver_name, approver_role,
            action, comments, action_date, action_time)
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        data["visitor_id"], data["visitor_number"],
        data["approver_name"], data.get("approver_role", ""),
        data["action"], data.get("comments", ""),
        now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")
    ))
    conn.commit()
    conn.close()


def get_approvals(visitor_id=None):
    conn = get_connection()
    if visitor_id:
        rows = conn.execute("SELECT * FROM approvals WHERE visitor_id=? ORDER BY created_at DESC", (visitor_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM approvals ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Dashboard stats ──────────────────────────────────────────────────────────

def get_dashboard_stats():
    conn = get_connection()
    today = lagos_now().strftime("%Y-%m-%d")
    stats = {}
    stats["total_today"] = conn.execute(
        "SELECT COUNT(*) FROM visitors WHERE entry_date=?", (today,)).fetchone()[0]
    stats["inside"] = conn.execute(
        "SELECT COUNT(*) FROM visitors WHERE status='Approved' AND entry_date=?", (today,)).fetchone()[0]
    stats["approved"] = conn.execute(
        "SELECT COUNT(*) FROM visitors WHERE status='Approved'").fetchone()[0]
    stats["rejected"] = conn.execute(
        "SELECT COUNT(*) FROM visitors WHERE status='Rejected'").fetchone()[0]
    stats["checked_out"] = conn.execute(
        "SELECT COUNT(*) FROM visitors WHERE status='Checked Out' AND entry_date=?", (today,)).fetchone()[0]
    stats["pending"] = conn.execute(
        "SELECT COUNT(*) FROM visitors WHERE status='Pending'").fetchone()[0]
    conn.close()
    return stats


def get_daily_visits(days=30):
    conn = get_connection()
    rows = conn.execute("""
        SELECT entry_date, COUNT(*) as count FROM visitors
        WHERE entry_date IS NOT NULL
        GROUP BY entry_date ORDER BY entry_date DESC LIMIT ?
    """, (days,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_department_visits():
    conn = get_connection()
    rows = conn.execute("""
        SELECT department, COUNT(*) as count FROM visitors
        WHERE department IS NOT NULL AND department != ''
        GROUP BY department ORDER BY count DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_hourly_visits():
    conn = get_connection()
    today = lagos_now().strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT substr(entry_time,1,2) as hour, COUNT(*) as count
        FROM visitors WHERE entry_date=?
        GROUP BY hour ORDER BY hour
    """, (today,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Admin auth ────────────────────────────────────────────────────────────────

def verify_admin(username: str, password: str):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM admins WHERE username=? AND is_active=1", (username,)).fetchone()
    conn.close()
    if row and bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
        return dict(row)
    return None


def update_admin_password(username: str, new_password: str):
    pw_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    conn = get_connection()
    conn.execute(
        "UPDATE admins SET password_hash=?, must_change_pw=0 WHERE username=?",
        (pw_hash, username))
    conn.commit()
    conn.close()


def update_last_login(username: str):
    now = lagos_now().isoformat()
    conn = get_connection()
    conn.execute("UPDATE admins SET last_login=? WHERE username=?", (now, username))
    conn.commit()
    conn.close()


# ── Audit ────────────────────────────────────────────────────────────────────

def log_audit(username: str, action: str, details: str = "", ip: str = "127.0.0.1"):
    conn = get_connection()
    conn.execute(
        "INSERT INTO audit_logs(username, action, details, ip_address) VALUES (?,?,?,?)",
        (username, action, details, ip))
    conn.commit()
    conn.close()


def get_audit_logs(limit=200):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Departments & Hosts ───────────────────────────────────────────────────────

def get_departments():
    conn = get_connection()
    rows = conn.execute("SELECT name FROM departments ORDER BY name").fetchall()
    conn.close()
    return [r["name"] for r in rows]


def get_hosts(department=None):
    conn = get_connection()
    if department:
        rows = conn.execute(
            "SELECT * FROM hosts WHERE department=? ORDER BY name", (department,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM hosts ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_admins():
    conn = get_connection()
    rows = conn.execute("SELECT id, username, full_name, role, email, is_active, last_login FROM admins").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_admin(username, password, full_name, role, email):
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO admins(username, password_hash, full_name, role, email) VALUES (?,?,?,?,?)",
            (username, pw_hash, full_name, role, email))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()
