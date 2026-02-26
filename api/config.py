# api/config.py
import os

class Config:
    DATABASE_URL = os.environ.get("DATABASE_URL")
