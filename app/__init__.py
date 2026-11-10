# -*- coding: utf-8 -*-
"""应用工厂：装配蓝图、静态资源与统一错误处理。"""
import os

from flask import Flask, jsonify, send_from_directory

from . import config


def create_app() -> Flask:
    app = Flask(__name__, static_url_path="",
                static_folder=os.path.join(config.BASE_DIR, "static"),
                template_folder=os.path.join(config.BASE_DIR, "templates"))
    app.secret_key = config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH
    app.config["PERMANENT_SESSION_LIFETIME"] = 7 * 24 * 3600  # 登录态 7 天

    from .auth import bp as auth_bp
    from .files import bp as files_bp
    from .folders import bp as folders_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(folders_bp)

    @app.get("/")
    def index():
        return send_from_directory(app.template_folder, "index.html")

    @app.get("/login")
    def login_page():
        return send_from_directory(app.template_folder, "login.html")

    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"error": "接口不存在"}), 404

    @app.errorhandler(413)
    def too_large(_):
        return jsonify({"error": "文件超过 50MB 上限"}), 413

    @app.errorhandler(500)
    def server_error(_):
        return jsonify({"error": "服务器内部错误"}), 500

    return app
