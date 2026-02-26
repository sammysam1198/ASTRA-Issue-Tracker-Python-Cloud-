# api/repos/users_repo.py
from ..db import get_db_conn

def get_user_by_email(email: str):
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, email, username, password_hash, pin_hash,
                   has_password, has_pin, last_login_at, created_at, updated_at
            FROM users
            WHERE email=%s;
        """, (email.lower(),))
        return cur.fetchone()
    finally:
        conn.close()

def upsert_user(email: str, username: str, password_hash: str, pin_hash: str):
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
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
        """, (email.lower(), username, password_hash, pin_hash))
        conn.commit()
    finally:
        conn.close()

def update_last_login(email: str):
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE users
            SET last_login_at = NOW(), updated_at = NOW()
            WHERE email = %s;
        """, (email.lower(),))
        conn.commit()
    finally:
        conn.close()
