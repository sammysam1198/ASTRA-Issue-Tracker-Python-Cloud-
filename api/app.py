# api/app.py
from flask import Flask, jsonify
from .config import Config
from .db_init import init_db

from .blueprints.auth_routes import bp as auth_bp
from .blueprints.admin_routes import bp as admin_bp
from .blueprints.issues_routes import bp as issues_bp
from .blueprints.devices_routes import bp as devices_bp
from .blueprints.stores_routes import bp as stores_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Health
    @app.get("/")
    def home():
        return jsonify({"status": "ok", "message": "Issue Tracker API is running"})

    # Register routes
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(issues_bp, url_prefix="/issues")
    app.register_blueprint(devices_bp, url_prefix="/devices")
    app.register_blueprint(stores_bp, url_prefix="")  # keeps /stores as-is

    # Create tables on boot 
    init_db()

    return app
