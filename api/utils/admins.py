# api/utils/admins.py
TRUSTED_ADMINS = {
    "Sammi.fishbein@jtax.com",
    "John.Maron@jtax.com",
    "Dominique.Smith@jtax.com"
}

def is_trusted_admin_email(email: str | None) -> bool:
    if not email:
        return False
    email = email.strip().lower()
    return email in {e.lower() for e in TRUSTED_ADMINS}
