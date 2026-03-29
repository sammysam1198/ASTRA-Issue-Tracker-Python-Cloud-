import os
import uuid
import json
import bcrypt
import psycopg2
from flask import Flask, jsonify, request
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone, timedelta
import logging 


app = Flask(__name__)

TRUSTED_ADMINS = {
    "Sammi.fishbein@jtax.com",
    "John.Maron@jtax.com",
    "Dominique.Smith@jtax.com"
}


# --- File paths for stores.json (store metadata only) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORES_PATH = os.path.join(BASE_DIR, "Stores.json")

# --- Database connection ---
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_user_by_email(conn, email: str):
    """
    Return a single user row (dict) by email, or None if not found.
    Email is normalized to lowercase.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            id,
            email,
            username,
            password_hash,
            pin_hash,
            has_password,
            has_pin,
            last_login_at,
            created_at,
            updated_at
        FROM users
        WHERE email = %s;
        """,
        (email.lower(),),
    )
    return cur.fetchone()

def is_trusted_admin_email(email: str | None) -> bool:
    if not email:
        return False
    email = email.strip().lower()
    return email in {e.lower() for e in TRUSTED_ADMINS}
    

def get_db_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db():
    """Create/upgrade tables (issues, users, stores) and ensure new columns exist."""
    conn = get_db_conn()
    cur = conn.cursor()

    # =========================
    # ISSUES TABLE
    # =========================
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS issues (
            id SERIAL PRIMARY KEY,
            store_name TEXT NOT NULL,
            store_number INTEGER,
            issue_name TEXT,
            priority TEXT,
            computer_number TEXT,
            device_type TEXT,
            category TEXT,
            description TEXT,
            narrative TEXT,
            replicable TEXT,
            status TEXT,
            resolution TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            global_issue BOOLEAN NOT NULL DEFAULT FALSE,
            global_num INTEGER
        );
        """
    )

    
    # =========================
    # USERS TABLE
    # =========================
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            username TEXT NOT NULL,
            password_hash TEXT,
            pin_hash TEXT,
            has_password BOOLEAN NOT NULL DEFAULT FALSE,
            has_pin BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            last_login_at TIMESTAMPTZ
        );
        """
    )

    # =======================
    # Tech Table
    # =======================
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS store_devices (
            id SERIAL PRIMARY KEY,
            device_uid TEXT UNIQUE NOT NULL,
            store_number INTEGER NOT NULL REFERENCES stores(store_number),
            device_type TEXT NOT NULL,
            device_number TEXT,
            manufacturer TEXT,
            model TEXT,
            device_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_store_devices_store_number
            ON store_devices(store_number);
        """
    )
    # ====================================================
    # Rules for importing new rows into the tech info table
    # ====================================================
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_store_devices_phone
        ON store_devices (store_number, device_number)
        WHERE device_type = 'Phone';
    """)

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_store_devices_computer
        ON store_devices (store_number, device_number)
        WHERE device_type = 'Computer';
    """)

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_store_devices_printer_cradlepoint
        ON store_devices (store_number, device_type)
        WHERE device_type IN ('Printer', 'CradlePoint');
    """)
    
    

# (207) 300-3096 Lilly evans


    # =========================
    # STORES TABLE
    # =========================
    # Base definition (in case table doesn't exist yet)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS stores (
            id SERIAL PRIMARY KEY,
            store_number INTEGER UNIQUE NOT NULL,
            store_name TEXT NOT NULL,
            type TEXT,
            state TEXT,
            num_comp INTEGER,
            address TEXT,
            city TEXT,
            zip TEXT,
            phone TEXT,
            kiosk TEXT
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_employees (
            id SERIAL PRIMARY KEY,
            employee_uid TEXT UNIQUE NOT NULL,
            store_number INTEGER NOT NULL,
            full_name TEXT NOT NULL,
            role_title TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            archived_until TIMESTAMP NULL,
            archive_reason TEXT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_availability (
            id SERIAL PRIMARY KEY,
            store_number INTEGER NOT NULL,
            day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),

            status TEXT NOT NULL DEFAULT 'STANDARD',
            -- allowed: STANDARD, CUSTOM, OFF, BLOCK

            start_time TIME NULL,
            end_time TIME NULL,

            source TEXT NOT NULL DEFAULT 'manual',
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

            UNIQUE (store_number, day_of_week)

        );
        """
    )
    cur.execute(
       """ 
        CREATE TABLE IF NOT EXISTS schedule_standard_hours (
            day_of_week INTEGER PRIMARY KEY CHECK (day_of_week BETWEEN 0 AND 6),
            start_time TIME NOT NULL,
            end_time TIME NOT NULL
        );
        """
    )


    

    # ======================
    # One Time Updates
    # ======================

    cur.execute(
        """
        INSERT INTO schedule_standard_hours (day_of_week, start_time, end_time) VALUES
            (0, '12:00', '16:00'),
            (1, '11:00', '19:00'),
            (2, '11:00', '19:00'),
            (3, '11:00', '19:00'),
            (4, '11:00', '19:00'),
            (5, '11:00', '19:00'),
            (6, '11:00', '19:00')
            ON CONFLICT (day_of_week) DO NOTHING;
        """
    )
        
    



    conn.commit()
    cur.close()
    conn.close()

# ------------------------
# PASSWORD HASHING
# ------------------------
def hash_secret(plain: str) -> str:
    """Hash a password or PIN using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(plain.encode("utf-8"), salt)
    return hashed.decode("utf-8")
#SECRET MEANS LIKE A PASSWORD OR PIN IT'S LIKE AN AUTH KEY

def verify_secret(plain: str, stored_hash: str) -> bool:
    """Check if plain password/PIN matches stored bcrypt hash."""
    if not stored_hash:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), stored_hash.encode("utf-8"))
    except ValueError:
        return False


SPECIAL_CHARS = set('!@#$%^&*":><')


def check_password_policy(password: str, username: str):
    """Return (ok: bool, errors: list[str]) based on your rules."""
    errors = []

    if len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    if password.lower() == username.lower():
        errors.append("Password cannot be the same as your username.")
    if not any(ch.isupper() for ch in password):
        errors.append("Password must contain at least one uppercase letter.")
    if not any(ch.islower() for ch in password):
        errors.append("Password must contain at least one lowercase letter.")
    if not any(ch.isdigit() for ch in password):
        errors.append("Password must contain at least one number.")
    if not any(ch in SPECIAL_CHARS for ch in password):
        errors.append("Password must contain at least one special character (! @ # $ % ^&*\":><).")

    return len(errors) == 0, errors


def check_pin_policy(pin: str):
    """Simple PIN rule: 4–6 digits only."""
    if not pin.isdigit():
        return False, "PIN must contain only digits."
    if not (4 <= len(pin) <= 6):
        return False, "PIN must be between 4 and 6 digits."
    if len(set(pin)) == 1:
        return False, "PIN cannot be all one digit (e.g., 0000, 1111)."

        
    return True, None


def load_stores():
    """
    Load store metadata from the Postgres `stores` table and return it in the
    legacy Stores.json structure, keyed by store name.
    """
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            store_number,
            store_name,
            type,
            state,
            num_comp,
            address,
            city,
            zip,
            phone,
            kiosk
        FROM stores
        ORDER BY store_number;
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    stores_legacy = {}
    for row in rows:
        legacy = db_store_row_to_legacy(row)
        # Legacy structure used store name as the key
        stores_legacy[legacy["Store Name"]] = legacy

    return stores_legacy



def db_store_row_to_legacy(row):
    """
    Adapt a row from the `stores` DB table into the legacy Stores.json structure.
    This keeps older client code working without caring that the backend changed.
    """
    return {
        "Store Number": row["store_number"],
        "Store Name": row["store_name"],
        "State": row.get("state"),
        "Type": row.get("type"),
        "Computers": row.get("num_comp"),
        "Address": row.get("address"),
        "City": row.get("city"),
        "ZIP": row.get("zip"),
        "Phone": row.get("phone"),
        "Kiosk Type": row.get("kiosk"),
        # Legacy structure kept issues inside each store; issues now live in a
        # separate table, so this is left as an empty list for compatibility.
        "Known Issues": row.get("Known Issues", []),
    }


# -----------------------------------------
#             ENDPOINTS
# -----------------------------------------


@app.get("/")
def home():
    return jsonify({"status": "ok", "message": "Issue Tracker API is running"})


@app.get("/stores")
def get_stores():
    """
    Return store metadata in the *legacy* Stores.json structure,
    but backed by the Postgres `stores` table.

    Shape:
    {
      "Some Store Name": {
        "Store Number": 123,
        "Store Name": "Some Store Name",
        "State": "MA",
        "Type": "Brick & Mortar",
        "Computers": 5,
        "Address": "...",
        "City": "...",
        "ZIP": "...",
        "Phone": "...",
        "Kiosk Type": "...",
        "Known Issues": []
      },
      ...
    }
    """
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            store_number,
            store_name,
            type,
            state,
            num_comp,
            address,
            city,
            zip,
            phone,
            kiosk
        FROM stores
        ORDER BY store_number;
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    stores_legacy = {}
    for row in rows:
        legacy = db_store_row_to_legacy(row)
        # Legacy structure keyed by store name, just like Stores.json was
        stores_legacy[legacy["Store Name"]] = legacy

    return jsonify(stores_legacy)

@app.post("/auth/register")
def auth_register():
    """
    Create or update a user with hashed password and PIN.

    Expected JSON body:
    {
      "email": "Sammi.Fishbein@jtax.com",
      "username": "FishbeinS",
      "password": "MyNewPassword123!",
      "pin": "1234"
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    email = data.get("email", "").strip()
    username = data.get("username", "").strip()
    password = data.get("password", "")
    pin = data.get("pin", "")

    if not email or not username or not password or not pin:
        return jsonify({"error": "email, username, password, and pin are required"}), 400

    # Optional: enforce corporate domains here
    lowered = email.lower()
    if not (lowered.endswith("@jtax.com") or lowered.endswith("@jacksonhewittcoo.com")):
        return jsonify({"error": "Email domain not allowed"}), 403

    # Normalize username for policy
    username_norm = username

    # Check password + PIN rules
    ok_pw, pw_errors = check_password_policy(password, username_norm)
    if not ok_pw:
        return jsonify({"error": "Password does not meet requirements", "details": pw_errors}), 400

    ok_pin, pin_error = check_pin_policy(pin)
    if not ok_pin:
        return jsonify({"error": "PIN does not meet requirements", "details": [pin_error]}), 400

    pw_hash = hash_secret(password)
    pin_hash = hash_secret(pin)

    conn = get_db_conn()
    cur = conn.cursor()

    # Upsert-like behavior: if email exists, update; otherwise insert.
    cur.execute(
        """
        INSERT INTO users (email, username, password_hash, pin_hash, has_password, has_pin)
        VALUES (%s, %s, %s, %s, TRUE, TRUE)
        ON CONFLICT (email)
        DO UPDATE SET
            username = EXCLUDED.username,
            password_hash = EXCLUDED.password_hash,
            pin_hash = EXCLUDED.pin_hash,
            has_password = TRUE,
            has_pin = TRUE,
            updated_at = NOW();
        """,
        (email.lower(), username_norm, pw_hash, pin_hash),
    )

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": "User registered/updated successfully."}), 200


@app.post("/auth/login")
def auth_login():
    """
    Verify email + username + password + PIN.

    Expected JSON:
    {
      "email": "Sammi.Fishbein@jtax.com",
      "username": "FishbeinS",
      "password": "MyNewPassword123!",
      "pin": "1234"
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    email = data.get("email", "").strip().lower()
    username = data.get("username", "").strip()   # <-- FIX
    password = data.get("password", "")
    pin = data.get("pin", "").strip()             # <-- FIX

    if not email or not username or not password or not pin:
        return jsonify({"error": "email, username, password, and pin are required"}), 400


    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT email, username, password_hash, pin_hash, has_password, has_pin
        FROM users
        WHERE email = %s;
        """,
        (email,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return jsonify({"error": "No user found with that email"}), 404

    if row["username"] != username:
        return jsonify({"error": "Unable to log in at this time"}), 401

    if not row["has_password"] or not row["password_hash"]:
        return jsonify({"error": "Password not set! Contact Admin"}), 403

    if not verify_secret(password, row["password_hash"]):
        return jsonify({"error": "Unable to log in at this time"}), 401

    if not row["has_pin"] or not row["pin_hash"]:
        return jsonify({"error": "PIN not set! Contact Admin"}), 403

    if not verify_secret(pin, row["pin_hash"]):
        return jsonify({"error": "Unable to log in at this time"}), 401

    #update last_login_at
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE users
        SET last_login_at = NOW(),
            updated_at = NOW()
        WHERE email = %s;
        """,
        (email,),
    )
    conn.commit()
    cur.close()
    conn.close()

    # If we get here, everything is good
    return jsonify({"message": "Login successful"}), 200



@app.post("/auth/quick-login")
def auth_quick_login():
    """
    Quick login with username + password ONLY if last_login_at is within 156 hours.

    Expected JSON:
    {
      "username": "ExactCaseUsername",
      "password": "CurrentPassword123!"
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT email, username, password_hash, has_password, last_login_at
        FROM users
        WHERE username = %s;
        """,
        (username,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    # Generic failure message to not leak info
    generic_error = {"error": "Unable to log in at this time", "require_full": True}

    if not row:
        return jsonify(generic_error), 401

    # Username is exact (case sensitive) by query, so no extra check needed
    if not row["has_password"] or not row["password_hash"]:
        return jsonify(generic_error), 401

    if not verify_secret(password, row["password_hash"]):
        return jsonify(generic_error), 401

    last_login_at = row["last_login_at"]
    if last_login_at is None:
        # Never logged in before with full protocol
        return jsonify(generic_error), 401

    # Check if last_login_at is within the last 156 hours
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=156)
    if last_login_at < cutoff:
        # Too old, require full login
        return jsonify(generic_error), 401

    # Quick login OK – refresh last_login_at
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE users
        SET last_login_at = NOW(),
            updated_at = NOW()
        WHERE username = %s;
        """,
        (username,),
    )
    conn.commit()
    cur.close()
    conn.close()

    is_admin = is_trusted_admin_email(row["email"])

    return jsonify({
        "message": "Quick login successful.",
        "email": row["email"],
        "is_admin": is_admin
    }), 200



@app.post("/auth/change-password")
def auth_change_password():
    """
    Change a user's password.

    Expected JSON:
    {
      "email": "user@jtax.com",
      "username": "ExactCaseUsername",
      "current_password": "OldPass123!",
      "new_password": "NewPass123!",
      "pin": "1234"
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    email = data.get("email", "").strip().lower()
    username = data.get("username", "").strip()
    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")
    pin = data.get("pin", "")

    if not email or not username or not current_password or not new_password or not pin:
        return jsonify(
            {"error": "email, username, current_password, new_password, and pin are required"}
        ), 400

    # Look up user
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT email, username, password_hash, pin_hash, has_password, has_pin
        FROM users
        WHERE email = %s;
        """,
        (email,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return jsonify({"error": "Unable to change password at this time"}), 401

    # Username must match EXACTLY (case-sensitive)
    if row["username"] != username:
        return jsonify({"error": "Unable to change password at this time"}), 401

    # Must have password/PIN set
    if not row["has_password"] or not row["password_hash"]:
        return jsonify({"error": "Password not set! Contact Admin"}), 403
    if not row["has_pin"] or not row["pin_hash"]:
        return jsonify({"error": "PIN not set! Contact Admin"}), 403

    # Verify current password + PIN
    if not verify_secret(current_password, row["password_hash"]):
        return jsonify({"error": "Unable to change password at this time"}), 401
    if not verify_secret(pin, row["pin_hash"]):
        return jsonify({"error": "Unable to change password at this time"}), 401

    # Check new password policy
    ok_pw, pw_errors = check_password_policy(new_password, username)
    if not ok_pw:
        return jsonify(
            {"error": "New password does not meet requirements", "details": pw_errors}
        ), 400

    # Hash and update
    new_pw_hash = hash_secret(new_password)

    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE users
        SET password_hash = %s,
            has_password = TRUE,
            updated_at = NOW()
        WHERE email = %s;
        """,
        (new_pw_hash, email),
    )
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": "Password changed successfully"}), 200




@app.post("/auth/change-pin")
def auth_change_pin():
    """
    Change a user's PIN.

    Expected JSON:
    {
      "email": "user@jtax.com",
      "username": "ExactCaseUsername",
      "password": "CurrentPassword123!",
      "current_pin": "1234",
      "new_pin": "5678"
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    email = data.get("email", "").strip().lower()
    username = data.get("username", "").strip()
    password = data.get("password", "")
    current_pin = data.get("current_pin", "")
    new_pin = data.get("new_pin", "")

    if not email or not username or not password or not current_pin or not new_pin:
        return jsonify(
            {"error": "email, username, password, current_pin, and new_pin are required"}
        ), 400

    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT email, username, password_hash, pin_hash, has_password, has_pin
        FROM users
        WHERE email = %s;
        """,
        (email,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return jsonify({"error": "Unable to change PIN at this time"}), 401

    if row["username"] != username:
        return jsonify({"error": "Unable to change PIN at this time"}), 401

    if not row["has_password"] or not row["password_hash"]:
        return jsonify({"error": "Password not set! Contact Admin"}), 403
    if not row["has_pin"] or not row["pin_hash"]:
        return jsonify({"error": "PIN not set! Contact Admin"}), 403

    # Verify current password + current PIN
    if not verify_secret(password, row["password_hash"]):
        return jsonify({"error": "Unable to change PIN at this time"}), 401
    if not verify_secret(current_pin, row["pin_hash"]):
        return jsonify({"error": "Unable to change PIN at this time"}), 401

    # Check new PIN policy
    ok_pin, pin_error = check_pin_policy(new_pin)
    if not ok_pin:
        return jsonify(
            {"error": "New PIN does not meet requirements", "details": [pin_error]}
        ), 400

    # Hash and update
    new_pin_hash = hash_secret(new_pin)

    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE users
        SET pin_hash = %s,
            has_pin = TRUE,
            updated_at = NOW()
        WHERE email = %s;
        """,
        (new_pin_hash, email),
    )
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": "PIN changed successfully"}), 200

ADMIN_EMAIL = "sammi.fishbein@jtax.com".lower()

@app.post("/admin/verify")
def admin_verify():
    """
    Verify that:
    - email is a trusted admin
    - password and PIN match that user's stored hashes

    Expected JSON:
    {
      "email": "admin@jtax.com",
      "password": "CurrentPassword123!",
      "pin": "1234"
    }
    """
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    pin = data.get("pin", "")

    if not email or not password or not pin:
        return jsonify({"ok": False, "error": "Missing email, password, or PIN."}), 400

    if not is_trusted_admin_email(email):
        return jsonify({"ok": False, "error": "Email is not a trusted admin."}), 403

    try:
        conn = get_db_conn()
    except Exception as e:
        return jsonify({"ok": False, "error": f"Database error: {e}"}), 500

    try:
        user = get_user_by_email(conn, email)
        if not user:
            return jsonify({"ok": False, "error": "Admin user not found."}), 404

        if not user.get("has_password") or not user.get("password_hash"):
            return jsonify({"ok": False, "error": "Admin password not set."}), 403
        if not user.get("has_pin") or not user.get("pin_hash"):
            return jsonify({"ok": False, "error": "Admin PIN not set."}), 403

        if not verify_secret(password, user["password_hash"]):
            return jsonify({"ok": False, "error": "Invalid password."}), 403
        if not verify_secret(pin, user["pin_hash"]):
            return jsonify({"ok": False, "error": "Invalid PIN."}), 403

        return jsonify({"ok": True, "message": "Admin verified."}), 200
    finally:
        conn.close()


@app.post("/admin/users")
def admin_users():
    """
    List all users. Admin credentials required.

    Expected JSON:
    {
      "admin_email": "admin@jtax.com",
      "admin_password": "CurrentPassword123!",
      "admin_pin": "1234"
    }
    """
    data = request.get_json(silent=True) or {}
    admin_email = data.get("admin_email", "").strip().lower()
    admin_password = data.get("admin_password", "")
    admin_pin = data.get("admin_pin", "")

    if not admin_email or not admin_password or not admin_pin:
        return jsonify({"error": "Missing admin credentials."}), 400

    if not is_trusted_admin_email(admin_email):
        return jsonify({"error": "Email is not a trusted admin."}), 403

    try:
        conn = get_db_conn()
    except Exception as e:
        return jsonify({"error": f"Database error: {e}"}), 500

    try:
        admin_user = get_user_by_email(conn, admin_email)
        if not admin_user:
            return jsonify({"error": "Admin user not found."}), 404

        if not admin_user.get("has_password") or not admin_user.get("password_hash"):
            return jsonify({"error": "Admin password not set."}), 403
        if not admin_user.get("has_pin") or not admin_user.get("pin_hash"):
            return jsonify({"error": "Admin PIN not set."}), 403

        if not verify_secret(admin_password, admin_user["password_hash"]):
            return jsonify({"error": "Invalid admin password."}), 403
        if not verify_secret(admin_pin, admin_user["pin_hash"]):
            return jsonify({"error": "Invalid admin PIN."}), 403

        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                id,
                username,
                email,
                has_password,
                has_pin,
                last_login_at
            FROM users
            ORDER BY email ASC;
            """
        )
        users = cur.fetchall()

        return jsonify({"users": users}), 200
    finally:
        conn.close()


@app.post("/admin/change-user-password")
def admin_change_user_password():
    """
    Admin-only: change another user's password.

    Expected JSON:
    {
      "admin_email": "admin@jtax.com",
      "admin_password": "AdminPass123!",
      "admin_pin": "1234",
      "target_email": "user@jtax.com",
      "new_password": "NewPass123!"
    }
    """
    data = request.get_json(silent=True) or {}
    admin_email = data.get("admin_email", "").strip().lower()
    admin_password = data.get("admin_password", "")
    admin_pin = data.get("admin_pin", "")
    target_email = data.get("target_email", "").strip().lower()
    new_password = data.get("new_password", "")

    if not all([admin_email, admin_password, admin_pin, target_email, new_password]):
        return jsonify({"error": "Missing required fields."}), 400

    if not is_trusted_admin_email(admin_email):
        return jsonify({"error": "Email is not a trusted admin."}), 403

    try:
        conn = get_db_conn()
    except Exception as e:
        return jsonify({"error": f"Database error: {e}"}), 500

    try:
        # Verify admin
        admin_user = get_user_by_email(conn, admin_email)
        if not admin_user:
            return jsonify({"error": "Admin user not found."}), 404

        if not admin_user.get("has_password") or not admin_user.get("password_hash"):
            return jsonify({"error": "Admin password not set."}), 403
        if not admin_user.get("has_pin") or not admin_user.get("pin_hash"):
            return jsonify({"error": "Admin PIN not set."}), 403

        if not verify_secret(admin_password, admin_user["password_hash"]):
            return jsonify({"error": "Invalid admin password."}), 403
        if not verify_secret(admin_pin, admin_user["pin_hash"]):
            return jsonify({"error": "Invalid admin PIN."}), 403

        # Get target user
        target_user = get_user_by_email(conn, target_email)
        if not target_user:
            return jsonify({"error": "Target user not found."}), 404

        # Check password policy using target's username
        ok_pw, pw_errors = check_password_policy(
            new_password, target_user["username"]
        )
        if not ok_pw:
            return jsonify(
                {
                    "error": "New password does not meet requirements",
                    "details": pw_errors,
                }
            ), 400

        new_pw_hash = hash_secret(new_password)

        cur = conn.cursor()
        cur.execute(
            """
            UPDATE users
            SET password_hash = %s,
                has_password = TRUE,
                updated_at = NOW()
            WHERE email = %s;
            """,
            (new_pw_hash, target_email),
        )
        conn.commit()

        return jsonify(
            {"message": f"Password updated for {target_email}."}
        ), 200
    finally:
        conn.close()


@app.post("/admin/change-user-pin")
def admin_change_user_pin():
    """
    Admin-only: change another user's PIN.

    Expected JSON:
    {
      "admin_email": "admin@jtax.com",
      "admin_password": "AdminPass123!",
      "admin_pin": "1234",
      "target_email": "user@jtax.com",
      "new_pin": "5678"
    }
    """
    data = request.get_json(silent=True) or {}
    admin_email = data.get("admin_email", "").strip().lower()
    admin_password = data.get("admin_password", "")
    admin_pin = data.get("admin_pin", "")
    target_email = data.get("target_email", "").strip().lower()
    new_pin = data.get("new_pin", "")

    if not all([admin_email, admin_password, admin_pin, target_email, new_pin]):
        return jsonify({"error": "Missing required fields."}), 400

    if not is_trusted_admin_email(admin_email):
        return jsonify({"error": "Email is not a trusted admin."}), 403

    # Check PIN against your policy
    ok_pin, pin_error = check_pin_policy(new_pin)
    if not ok_pin:
        return jsonify(
            {"error": "New PIN does not meet requirements", "details": [pin_error]}
        ), 400

    try:
        conn = get_db_conn()
    except Exception as e:
        return jsonify({"error": f"Database error: {e}"}), 500

    try:
        # Verify admin
        admin_user = get_user_by_email(conn, admin_email)
        if not admin_user:
            return jsonify({"error": "Admin user not found."}), 404

        if not admin_user.get("has_password") or not admin_user.get("password_hash"):
            return jsonify({"error": "Admin password not set."}), 403
        if not admin_user.get("has_pin") or not admin_user.get("pin_hash"):
            return jsonify({"error": "Admin PIN not set."}), 403

        if not verify_secret(admin_password, admin_user["password_hash"]):
            return jsonify({"error": "Invalid admin password."}), 403
        if not verify_secret(admin_pin, admin_user["pin_hash"]):
            return jsonify({"error": "Invalid admin PIN."}), 403

        # Target user
        target_user = get_user_by_email(conn, target_email)
        if not target_user:
            return jsonify({"error": "Target user not found."}), 404

        new_pin_hash = hash_secret(new_pin)

        cur = conn.cursor()
        cur.execute(
            """
            UPDATE users
            SET pin_hash = %s,
                has_pin = TRUE,
                updated_at = NOW()
            WHERE email = %s;
            """,
            (new_pin_hash, target_email),
        )
        conn.commit()

        return jsonify(
            {"message": f"PIN updated for {target_email}."}
        ), 200
    finally:
        conn.close()



@app.post("/admin/delete-user")
def admin_delete_user():
    """
    Admin-only: delete another user account.

    Expected JSON:
    {
      "admin_email": "admin@jtax.com",
      "admin_password": "AdminPass123!",
      "admin_pin": "1234",
      "target_email": "user@jtax.com"
    }
    """
    data = request.get_json(silent=True) or {}
    admin_email = data.get("admin_email", "").strip().lower()
    admin_password = data.get("admin_password", "")
    admin_pin = data.get("admin_pin", "")
    target_email = data.get("target_email", "").strip().lower()

    if not all([admin_email, admin_password, admin_pin, target_email]):
        return jsonify({"error": "Missing required fields."}), 400

    if not is_trusted_admin_email(admin_email):
        return jsonify({"error": "Email is not a trusted admin."}), 403

    if admin_email == target_email:
        return jsonify({"error": "You cannot delete your own account."}), 400

    try:
        conn = get_db_conn()
    except Exception as e:
        return jsonify({"error": f"Database error: {e}"}), 500

    try:
        admin_user = get_user_by_email(conn, admin_email)
        if not admin_user:
            return jsonify({"error": "Admin user not found."}), 404

        if not admin_user.get("has_password") or not admin_user.get("password_hash"):
            return jsonify({"error": "Admin password not set."}), 403
        if not admin_user.get("has_pin") or not admin_user.get("pin_hash"):
            return jsonify({"error": "Admin PIN not set."}), 403

        if not verify_secret(admin_password, admin_user["password_hash"]):
            return jsonify({"error": "Invalid admin password."}), 403
        if not verify_secret(admin_pin, admin_user["pin_hash"]):
            return jsonify({"error": "Invalid admin PIN."}), 403

        cur = conn.cursor()
        cur.execute(
            "DELETE FROM users WHERE email = %s RETURNING email;",
            (target_email,),
        )
        deleted = cur.fetchone()
        conn.commit()

        if not deleted:
            return jsonify({"error": "Target user not found."}), 404

        return jsonify(
            {"message": f"User {target_email} deleted."}
        ), 200
    finally:
        conn.close()

# --Scheduling--------------

@app.post("/schedule/init-store/<int:store_number>")
def init_store_schedule(store_number: int):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO schedule_availability (store_number, day_of_week, status)
        SELECT %s, d, 'STANDARD'
        FROM generate_series(0,6) AS d
        ON CONFLICT (store_number, day_of_week) DO NOTHING;
    """, (store_number,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"ok": True, "store_number": store_number})


@app.get("/schedule/store/<int:store_number>")
def get_store_schedule(store_number: int):
    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO schedule_availability (store_number, day_of_week, status)
        SELECT %s, d, 'STANDARD'
        FROM generate_series(0,6) AS d
        ON CONFLICT (store_number, day_of_week) DO NOTHING;
    """, (store_number,))
    conn.commit()

    cur.execute("""
        SELECT
            a.day_of_week,
            a.status,
            CASE
                WHEN a.status = 'CUSTOM' THEN a.start_time
                WHEN a.status = 'STANDARD' THEN s.start_time
                ELSE NULL
            END AS resolved_start,
            CASE
                WHEN a.status = 'CUSTOM' THEN a.end_time
                WHEN a.status = 'STANDARD' THEN s.end_time
                ELSE NULL
            END AS resolved_end,
            a.updated_at
        FROM schedule_availability a
        LEFT JOIN schedule_standard_hours s
            ON s.day_of_week = a.day_of_week
        WHERE a.store_number = %s
        ORDER BY a.day_of_week ASC;
    """, (store_number,))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    def t(v):
        return v.strftime("%H:%M") if v else None

    return jsonify({
        "store_number": store_number,
        "days": [
            {
                "day": r["day_of_week"],
                "status": r["status"],
                "start": t(r["resolved_start"]),
                "end": t(r["resolved_end"]),
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None
            }
            for r in rows
        ]
    })


@app.get("/schedule/employees/<int:store_number>")
def get_employees(store_number: int):
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT employee_uid, full_name, role_title, is_active, archived_until
        FROM schedule_employees
        WHERE store_number = %s
        ORDER BY full_name ASC;
    """, (store_number,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify({
        "store_number": store_number,
        "employees": [
            {
                "employee_uid": r["employee_uid"],
                "full_name": r["full_name"],
                "role_title": r["role_title"],
                "is_active": r["is_active"],
                "archived_until": r["archived_until"].isoformat() if r["archived_until"] else None
            } for r in rows
        ]
    })



# --ISSUE TRACKER------------

@app.post("/issues")
def add_issue():
    """
    Add a new issue to the database.

    Expected JSON body:
    {
      "store_name": "Store 123 - Main St",
      "issue": {
        "Name": "...",              # or "Issue Name"
        "Priority": "...",
        "Store Number": "12345",
        "Computer Number": "PC-01",
        "Device": "Computer",       # <--- device type
        "Category": "Hardware",     # <--- problem category
        "Description": "...",
        "Narrative": "",
        "Replicable?": "Yes/No",
        "Global Issue": "False",
        "Global Number": "12",
        "Status": "Unresolved",
        "Resolution": ""
      }
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    store_name = data.get("store_name")
    issue = data.get("issue")

    if not store_name or not issue:
        return jsonify({"error": "store_name and issue are required"}), 400

    # Pull fields out of the issue dict
    store_number = issue.get("Store Number")
    issue_name = issue.get("Name") or issue.get("Issue Name")
    priority = issue.get("Priority")
    computer_number = issue.get("Computer Number")
    device_type = issue.get("Device")          # <--- NEW
    category = issue.get("Category")           # <--- NEW
    description = issue.get("Description")
    narrative = issue.get("Narrative", "")
    replicable = issue.get("Replicable?")
    raw_global_issue = issue.get("Global Issue")
    raw_global_num = issue.get("Global Number")
    status = issue.get("Status")
    resolution = issue.get("Resolution", "")

    # --- NORMALIZE global_issue TO BOOL ---
    if isinstance(raw_global_issue, bool):
        global_issue = raw_global_issue
    else:
        global_issue = str(raw_global_issue).strip().lower() in ("true", "yes", "y", "1")

    # --- NORMALIZE global_num TO INT OR NONE ---
        # --- NORMALIZE global_num TO INT OR NONE ---
    if raw_global_num not in (None, ""):
        try:
            global_num = int(raw_global_num)
        except ValueError:
            return jsonify({"error": "Global Number must be an integer"}), 400
    else:
        global_num = None

    
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO issues (
            store_name, store_number, issue_name, priority,
            computer_number, device_type, category,
            description, narrative, replicable, global_issue, 
            global_num, status, resolution
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *;
        """,
        (
            store_name,
            int(store_number) if store_number is not None else None,
            issue_name,
            priority,
            computer_number,
            device_type,
            category,
            description,
            narrative,
            replicable,
            global_issue,
            global_num if global_num is not None else None,
            status,
            resolution,
        ),
    )
    new_issue = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"message": "Issue added", "issue": new_issue}), 201


@app.get("/issues/all")
def get_all_issues():
    """
    Return all issues in the DB, ordered by store_number then id.

    Response: JSON list of issue rows (same shape as /issues/by-store)
    """
    try:
        conn = get_db_conn()
    except Exception as e:
        return jsonify({"error": f"Database connection error: {e}"}), 500

    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM issues
            ORDER BY store_number, id;
            """
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        return jsonify({"error": f"Database query error: {e}"}), 500

    # /issues/by-store returns a plain list, so we match that:
    return jsonify(rows), 200


@app.get("/issues/by-store")
def get_issues_by_store():
    """
    Get issues for a specific store.

    Query params:
      ?store_number=123   OR   ?store_name=Store%20123...

    Returns a list of issues from the DB.
    """
    store_number = request.args.get("store_number")
    store_name = request.args.get("store_name")

    if not store_number and not store_name:
        return jsonify({"error": "store_number or store_name is required"}), 400

    conn = get_db_conn()
    cur = conn.cursor()

    if store_number:
        cur.execute(
            """
            SELECT * FROM issues
            WHERE store_number = %s
            ORDER BY id;
            """,
            (int(store_number),),
        )
    else:
        cur.execute(
            """
            SELECT * FROM issues
            WHERE store_name = %s
            ORDER BY id;
            """,
            (store_name,),
        )

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify(rows), 200


@app.get("/devices/by-store")
def get_devices_by_store():
    """
    Query params:
      ?store_number=12345

    Returns:
      {
        "store_number": 12345,
        "devices": [
          {device row...},
          ...
        ]
      }
    """
    store_number = request.args.get("store_number")
    if not store_number:
        return jsonify({"error": "store_number is required"}), 400

    try:
        store_number_int = int(store_number)
    except ValueError:
        return jsonify({"error": "store_number must be an integer"}), 400

    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            device_uid,
            store_number,
            device_type,
            device_number,
            manufacturer,
            model,
            device_notes
        FROM store_devices
        WHERE store_number = %s
        ORDER BY device_type, device_number NULLS LAST, manufacturer, model;
        """,
        (store_number_int,),
    )

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify({"store_number": store_number_int, "devices": rows}), 200



@app.post("/issues/update")
def update_issue():
    """
    Update an existing issue in the DB.

    Expected JSON body:
    {
      "issue_id": 123,
      "updated_issue": {
          "Store Name": "...",
          "Store Number": "12345",
          "Name": "...", or "Issue Name": "...",
          "Priority": "...",
          "Computer Number": "...",
          "Device": "Computer",
          "Category": "Hardware",
          "Description": "...",
          "Narrative": "...",
          "Replicable?": "...",
          "Global Issue": "FALSE",
          "Global Number": "12",
          "Status": "...",
          "Resolution": "..."
      }
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    issue_id = data.get("issue_id")
    updated_issue = data.get("updated_issue")

    if issue_id is None or updated_issue is None:
        return jsonify({"error": "issue_id and updated_issue are required"}), 400

    store_name = updated_issue.get("Store Name") or updated_issue.get("Store_Name")
    store_number = updated_issue.get("Store Number")
    issue_name = updated_issue.get("Name") or updated_issue.get("Issue Name")
    priority = updated_issue.get("Priority")
    computer_number = updated_issue.get("Computer Number")
    device_type = updated_issue.get("Device")
    category = updated_issue.get("Category")
    description = updated_issue.get("Description")
    narrative = updated_issue.get("Narrative", "")
    replicable = updated_issue.get("Replicable?")
    raw_global_issue = updated_issue.get("Global Issue")
    raw_global_num = updated_issue.get("Global Number")
    status = updated_issue.get("Status")
    resolution = updated_issue.get("Resolution", "")

    # --- NORMALIZE global_issue ---
    if raw_global_issue is None:
        global_issue = None  # means "don't change it"
        
    elif isinstance(raw_global_issue, bool):
        global_issue = raw_global_issue
    else:
        global_issue = str(raw_global_issue).strip().lower() in ("true", "yes", "y", "1")

    # --- NORMALIZE global_num ---
    if raw_global_num not in (None, ""):
        try:
            global_num = int(raw_global_num)
        except ValueError:
            return jsonify({"error": "Global Number must be an integer"}), 400
    else:
        global_num = None

    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE issues
        SET
            store_name   = COALESCE(%s, store_name),
            store_number = COALESCE(%s, store_number),
            issue_name   = %s,
            priority     = %s,
            computer_number = %s,
            device_type  = %s,
            category     = %s,
            description  = %s,
            narrative    = %s,
            replicable   = %s,
            global_issue = COALESCE(%s, global_issue),
            global_num   = COALESCE(%s, global_num),
            status       = %s,
            resolution   = %s,
            updated_at   = NOW()
        WHERE id = %s
        RETURNING *;
        """,
        (
            store_name,
            int(store_number) if store_number is not None else None,
            issue_name,
            priority,
            computer_number,
            device_type,
            category,
            description,
            narrative,
            replicable,
            global_issue,
            global_num if global_num is not None else None,
            status,
            resolution,
            issue_id,
        ),
    )
    updated_row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    if not updated_row:
        return jsonify({"error": "Issue not found"}), 404

    return jsonify({"message": "Issue updated", "issue": updated_row}), 200

@app.get("/issues/search")
def search_issues():
    """
    Advanced search for issues.

    Query params (all optional, at least one required):
      store_number=12345
      category=some_text
      status=Unresolved
      device=Computer
      name=Printer%20Down
      global_issue=True

    All text fields use ILIKE '%value%' (case-insensitive, partial match).
    """
    store_number = request.args.get("store_number")
    category = request.args.get("category")   # maps to device_type
    status = request.args.get("status")
    device = request.args.get("device")       # also maps to device_type
    name = request.args.get("name")           # maps to issue_name
    global_issue = request.args.get("global_issue")

    if not any([store_number, category, status, device, name, global_issue]):
        return jsonify({"error": "At least one search parameter is required"}), 400

    conn = get_db_conn()
    cur = conn.cursor()

    query = "SELECT * FROM issues WHERE 1=1"
    params = []

    if store_number:
        query += " AND store_number = %s"
        params.append(int(store_number))

    # In your current schema, 'category' and 'device' both map to device_type.
    if category:
        query += " AND category ILIKE %s"
        params.append(f"%{category}%")
    
    if status:
        query += " AND status ILIKE %s"
        params.append(f"%{status}%")

    if device:
        query += " AND device_type ILIKE %s"
        params.append(f"%{device}%")

    if name:
        query += " AND issue_name ILIKE %s"
        params.append(f"%{name}%")

    if global_issue is not None:
        val = str(global_issue).strip().lower()
        if val in ("true", "1", "yes", "y"):
            query += " AND global_issue = %s"
            params.append(True)
        elif val in ("false", "0", "no", "n"):
            query += " AND global_issue = %s"
            params.append(False)

    cur.execute(query, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify(rows), 200


@app.post("/issues/delete")
def delete_issue():
    """
    Delete an existing issue from the DB.

    Expected JSON body:
    {
      "issue_id": 123
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    issue_id = data.get("issue_id")
    if issue_id is None:
        return jsonify({"error": "issue_id is required"}), 400

    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM issues WHERE id = %s RETURNING *;",
        (issue_id,),
    )
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    if not deleted:
        return jsonify({"error": "Issue not found"}), 404

    return jsonify({"message": "Issue deleted", "issue": deleted}), 200


# Initialize DB schema when the app starts 

def api_device_dryrun_action(store_number, device_type, device_number, manufacturer, model):
    """
    Returns: (ok:bool, action:str, reason_or_err:str|None)
    action in {"insert", "update", "skip", "error"}
    """
    conn = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()

        dt = (device_type or "").strip()
        dn = (device_number or "").strip() or None
        mf = (manufacturer or "").strip() or None
        md = (model or "").strip() or None

        dt_norm = dt.strip().title()
        if dt_norm == "Cradlepoint":
            dt_norm = "CradlePoint"

        # Printer / CradlePoint: key = (store_number, device_type)
        if dt_norm in ("Printer", "CradlePoint"):
            cur.execute("""
                SELECT manufacturer, model
                FROM store_devices
                WHERE store_number=%s AND device_type=%s
                LIMIT 1
            """, (store_number, dt_norm))
            existing = cur.fetchone()
            return True, ("insert" if existing is None else "skip"), None

        # Phone: key = (store_number, device_number) where type=Phone
        if dt_norm == "Phone":
            if not dn:
                return False, "error", "Phone row missing device_number"
            cur.execute("""
                SELECT 1
                FROM store_devices
                WHERE store_number=%s AND device_type='Phone' AND device_number=%s
                LIMIT 1
            """, (store_number, dn))
            existing = cur.fetchone()
            return True, ("insert" if existing is None else "skip"), None

        # Computer: key = (store_number, device_number) where type=Computer
        if dt_norm == "Computer":
            if not dn:
                return False, "error", "Computer row missing device_number"
            cur.execute("""
                SELECT manufacturer, model
                FROM store_devices
                WHERE store_number=%s AND device_type='Computer' AND device_number=%s
                LIMIT 1
            """, (store_number, dn))
            existing = cur.fetchone()
            if existing is None:
                return True, "insert", None

            ex_mf, ex_md = existing
            # match your update rule: update if manufacturer OR model differs
            if (ex_mf != mf) or (ex_md != md):
                return True, "update", None
            return True, "skip", None

        return False, "error", f"Unsupported device type: {device_type}"

    except Exception as e:
        return False, "error", str(e)
    finally:
        if conn:
            conn.close()


def api_upsert_device(store_number, device_type, device_number, manufacturer, model):
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        dt = (device_type or "").strip().title()  # Normalize (e.g., "printer" -> "Printer")
        if dt == "Cradlepoint":
            dt = "CradlePoint"
        dn = (device_number or "").strip() or None
        mf = (manufacturer or "").strip() or None
        md = (model or "").strip() or None

        exists = False
        needs_update = False

        if dt in ("Printer", "CradlePoint"):
            # Key: store_number + device_type (no device_number)
            cur.execute("""
                SELECT manufacturer, model
                FROM store_devices
                WHERE store_number = %s AND device_type = %s
                LIMIT 1
            """, (store_number, dt))
            existing = cur.fetchone()
            if existing:
                exists = True
                # For these types, original logic: no update (DO NOTHING), so skip

        elif dt == "Phone":
            if not dn:
                return False, None, "Phone row missing device_number"
            # Key: store_number + device_number (with device_type fixed)
            cur.execute("""
                SELECT manufacturer, model
                FROM store_devices
                WHERE store_number = %s AND device_type = 'Phone' AND device_number = %s
                LIMIT 1
            """, (store_number, dn))
            existing = cur.fetchone()
            if existing:
                exists = True
                # For Phone, original logic: no update (DO NOTHING), so skip

        elif dt == "Computer":
            if not dn:
                return False, None, "Computer row missing device_number"
            # Key: store_number + device_number (with device_type fixed)
            cur.execute("""
                SELECT manufacturer, model
                FROM store_devices
                WHERE store_number = %s AND device_type = 'Computer' AND device_number = %s
                LIMIT 1
            """, (store_number, dn))
            existing = cur.fetchone()
            if existing:
                exists = True
                ex_mf, ex_md = existing
                # For Computer, original logic: update only if manufacturer or model differs
                if (ex_mf != mf) or (ex_md != md):
                    needs_update = True

        else:
            return False, None, f"Unsupported device type: {device_type}"

        if exists:
            if needs_update:
                # Update (only for Computer)
                cur.execute("""
                    UPDATE store_devices
                    SET manufacturer = %s,
                        model = %s,
                        updated_at = NOW()
                    WHERE store_number = %s
                      AND device_type = %s
                      AND device_number = %s
                """, (mf, md, store_number, dt, dn))
                conn.commit()
                return True, "update", None
            else:
                # Skip (no change needed)
                return True, "skip", None
        else:
            # Insert new row
            device_uid = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO store_devices
                    (device_uid, store_number, device_type, device_number, manufacturer, model)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (device_uid, store_number, dt, dn, mf, md))
            conn.commit()
            return True, "insert", None

    except Exception as e:
        conn.rollback()
        err = str(e)
        if hasattr(e, "pgerror") and e.pgerror:
            err = e.pgerror
        return False, None, err

    finally:
        cur.close()
        conn.close()

def store_exists(cur, store_number: int) -> bool:
    cur.execute("SELECT 1 FROM stores WHERE store_number=%s LIMIT 1;", (store_number,))
    return cur.fetchone() is not None


@app.route("/admin/import_devices", methods=["POST"])
def import_devices():
    try:
        payload = request.get_json(force=True)

        dry_run = bool(payload.get("dry_run", False))
        rows = payload.get("rows", [])
        if not isinstance(rows, list) or not rows:
            return jsonify({"ok": False, "error": "rows must be a non-empty list"}), 400

        summary = {"insert": 0, "update": 0, "skip": 0, "applied": 0, "error": 0}
        err_rows = []

        # one DB connection for store-existence checks
        conn_check = get_db_conn()
        cur_check = conn_check.cursor()
        try:
            for idx, r in enumerate(rows):
                store_number = r.get("store_number") or r.get("Store Number")
                device_type  = r.get("device_type")  or r.get("Device Type")
                device_number= r.get("device_number")or r.get("Device Number")
                manufacturer = r.get("manufacturer") or r.get("Manufacturer")
                model        = r.get("model")        or r.get("Model")

                try:
                    store_number = int(str(store_number).strip())
                except Exception:
                    summary["error"] += 1
                    err_rows.append({"row_index": idx, "error": f"Bad Store Number: {store_number}", "row": r})
                    continue

               
                if not store_exists(cur_check, store_number):
                    summary["error"] += 1
                    err_rows.append({
                        "row_index": idx,
                        "error": f"Store {store_number} does not exist in stores table (FK would fail).",
                        "row": r
                    })
                    continue

                if dry_run:
                    ok, action, err = api_device_dryrun_action(
                        store_number, device_type, device_number, manufacturer, model
                    )
                    if ok:
                        summary[action if action in summary else "skip"] += 1
                    else:
                        summary["error"] += 1
                        err_rows.append({"row_index": idx, "error": err, "row": r})
                else:
                    ok, _, err = api_upsert_device(
                        store_number, device_type, device_number, manufacturer, model
                    )
                    if ok:
                        summary["applied"] += 1
                    else:
                        summary["error"] += 1
                        err_rows.append({"row_index": idx, "error": err, "row": r})
        finally:
            try:
                cur_check.close()
            except Exception:
                pass
            conn_check.close()

        return jsonify({
            "ok": True,
            "dry_run": dry_run,
            "processed": len(rows),
            "summary": summary,
            "errors": err_rows
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# --- Ensure DB schema exists on Render/Gunicorn import ---
try:
    init_db()
except Exception as e:
    # Keep the service booting so you can still see logs/routes,
    # but you should check Render logs for this message.
    print(f"[init_db] failed: {e}")


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
