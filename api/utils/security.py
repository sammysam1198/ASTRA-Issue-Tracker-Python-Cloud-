# api/utils/security.py
import bcrypt

SPECIAL_CHARS = set('!@#$%^&*":><')

def hash_secret(plain: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(plain.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_secret(plain: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), stored_hash.encode("utf-8"))
    except ValueError:
        return False

def check_password_policy(password: str, username: str):
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
        errors.append('Password must contain at least one special character (! @ # $ % ^&*":><).')
    return len(errors) == 0, errors

def check_pin_policy(pin: str):
    if not pin.isdigit():
        return False, "PIN must contain only digits."
    if not (4 <= len(pin) <= 6):
        return False, "PIN must be between 4 and 6 digits."
    if len(set(pin)) == 1:
        return False, "PIN cannot be all one digit (e.g., 0000, 1111)."
    return True, None
