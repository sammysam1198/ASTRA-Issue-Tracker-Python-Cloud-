# api/db.py
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import current_app

def get_db_conn():
    url = current_app.config.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg2.connect(url, cursor_factory=RealDictCursor)
