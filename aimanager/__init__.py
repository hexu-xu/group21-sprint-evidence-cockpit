"""Flask application factory for 爱管理."""

import os
import secrets
from datetime import timedelta, timezone
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for
from flask_login import login_required
from flask_wtf.csrf import CSRFError
from sqlalchemy import event

from .extensions import csrf, db, login_manager, migrate
from .models import User

ROOT = Path(__file__).resolve().parents[1]


def _local_secret_key(path):
    """Keep local sessions valid across server restarts without checking in a key."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as key_file:
            key_file.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    return path.read_text(encoding="utf-8").strip()


def create_app(test_config=None):
    """Assemble isolated Blueprints and extensions for web use or tests."""
    app = Flask(__name__, template_folder=str(ROOT / "templates"), static_folder=str(ROOT / "static"))
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        SECRET_KEY_FILE=str(Path(app.instance_path) / ".secret_key"),
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL") or "sqlite:///aimanager.db",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        EVIDENCE_PATH=str(ROOT / "data" / "evidence.json"),
        EVIDENCE_DATA=None,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config:
        app.config.update(test_config)
    if not app.config["SECRET_KEY"]:
        app.config["SECRET_KEY"] = _local_secret_key(app.config["SECRET_KEY_FILE"])

    @app.template_filter("local_datetime")
    def local_datetime(value):
        if value is None:
            return "—"
        source = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return source.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    migrate.init_app(app, db)
    csrf.init_app(app)

    with app.app_context():
        if db.engine.url.get_backend_name() == "sqlite":
            @event.listens_for(db.engine, "connect")
            def enable_sqlite_foreign_keys(connection, _record):
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    @login_manager.user_loader
    def load_user(user_id):
        user = db.session.get(User, int(user_id)) if user_id.isdigit() else None
        return user if user is not None and user.active else None

    from .auth import bp as auth_bp
    from .evidence import bp as evidence_bp
    from .tasks import bp as tasks_bp
    from .seed import seed_demo

    app.register_blueprint(auth_bp)
    app.register_blueprint(evidence_bp)
    app.register_blueprint(tasks_bp)
    app.cli.add_command(seed_demo)

    @app.get("/")
    @login_required
    def home():
        if "role" in request.args:
            # Keep historical links working; the query parameter never grants a role.
            return redirect(url_for("evidence.index"))
        return redirect(url_for("tasks.list_tasks"))

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("403.html"), 403

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        if request.endpoint == "auth.login":
            flash("登录页面已过期，请刷新页面后重新输入账号密码。", "error")
            return redirect(url_for("auth.login"))
        return error.description, 400

    return app
