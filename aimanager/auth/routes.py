"""Password login for preset demo accounts; self-registration is not enabled."""

from flask import flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from ..extensions import db
from ..models import User
from . import bp


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        previous_username = current_user.username if current_user.is_authenticated else None
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.session.scalar(db.select(User).where(User.username == username))
        if user is not None and user.active and check_password_hash(user.password_hash, password):
            # Drop the previous identity and its session data before switching accounts.
            session.clear()
            login_user(user)
            return redirect(url_for("tasks.list_tasks"))
        if previous_username:
            flash(f"切换失败，当前仍以 {previous_username} 登录。请检查用户名和密码。", "error")
        else:
            flash("用户名或密码错误", "error")
    return render_template("auth/login.html")


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
