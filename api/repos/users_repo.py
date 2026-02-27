# api/repos/users_repo.py
from ..db import get_db_conn

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
