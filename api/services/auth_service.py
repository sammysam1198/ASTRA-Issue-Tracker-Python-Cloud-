# api/services/auth_service.py
from datetime import datetime, timezone, timedelta
from ..repos.users_repo import get_user_by_email, upsert_user, update_last_login
from ..utils.security import hash_secret, verify_secret, check_password_policy, check_pin_policy
from ..utils.admins import is_trusted_admin_email

ALLOWED_DOMAINS = ("@jtax.com", "@jacksonhewittcoo.com")

def register_user(email, username, password, pin):
    lowered = email.lower()
    if not lowered.endswith(ALLOWED_DOMAINS):
        return False, ({"error": "Email domain not allowed"}, 403)

    ok_pw, pw_errors = check_password_policy(password, username)
    if not ok_pw:
        return False, ({"error": "Password does not meet requirements", "details": pw_errors}, 400)

    ok_pin, pin_error = check_pin_policy(pin)
    if not ok_pin:
        return False, ({"error": "PIN does not meet requirements", "details": [pin_error]}, 400)

    upsert_user(lowered, username, hash_secret(password), hash_secret(pin))
    return True, ({"message": "User registered/updated successfully."}, 200)

def login(email, username, password, pin):
    user = get_user_by_email(email)
    if not user:
        return False, ({"error": "No user found with that email"}, 404)

    if user["username"] != username:
        return False, ({"error": "Unable to log in at this time"}, 401)

    if not user["has_password"] or not user["password_hash"]:
        return False, ({"error": "Password not set! Contact Admin"}, 403)
    if not verify_secret(password, user["password_hash"]):
        return False, ({"error": "Unable to log in at this time"}, 401)

    if not user["has_pin"] or not user["pin_hash"]:
        return False, ({"error": "PIN not set! Contact Admin"}, 403)
    if not verify_secret(pin, user["pin_hash"]):
        return False, ({"error": "Unable to log in at this time"}, 401)

    update_last_login(email)
    return True, ({"message": "Login successful"}, 200)

def quick_login(username, password):
    # You currently query by username, then enforce last_login_at within 156 hours :contentReference[oaicite:7]{index=7}
    # For brevity: implement via a username repo method.
    ...
