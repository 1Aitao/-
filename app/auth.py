# -*- coding: utf-8 -*-
"""登录 / 登出 / 鉴权（FR-01）。

本期仅预置单账号，不开放注册；未登录访问业务接口统一返回 401（PRD 3.2）。
会话基于 Flask 签名 Cookie，服务重启后客户端仍需重新验证，登录态简单可靠。
"""
import functools

from flask import Blueprint, jsonify, request, session

from . import config

bp = Blueprint("auth", __name__)


def login_required(view):
    """业务接口统一鉴权装饰器：未登录返回 401，由前端引导至登录页。"""

    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return jsonify({"error": "未登录或会话已过期"}), 401
        return view(*args, **kwargs)

    return wrapper


@bp.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if username == config.ADMIN_USERNAME and password == config.ADMIN_PASSWORD:
        session.clear()
        session["user"] = username
        session.permanent = True
        return jsonify({"user": username})
    return jsonify({"error": "账号或密码错误"}), 401


@bp.post("/api/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})


@bp.get("/api/me")
def me():
    if session.get("user"):
        return jsonify({"user": session["user"]})
    return jsonify({"error": "未登录"}), 401
