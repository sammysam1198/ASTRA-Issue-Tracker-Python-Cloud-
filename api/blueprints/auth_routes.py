# api/blueprints/auth_routes.py
from flask import Blueprint, jsonify, request
from ..services.auth_service import register_user, login

bp = Blueprint("auth", __name__)

@bp.post("/register")
def auth_register():
    data = request.get_json(silent=True) or {}
    ok, resp = register_user(
        data.get("email","").strip(),
        data.get("username","").strip(),
        data.get("password",""),
        data.get("pin",""),
    )
    body, status = resp
    return jsonify(body), status

@bp.post("/login")
def auth_login():
    data = request.get_json(silent=True) or {}
    ok, resp = login(
        data.get("email","").strip(),
        data.get("username","").strip(),
        data.get("password",""),
        data.get("pin","").strip(),
    )
    body, status = resp
    return jsonify(body), status
