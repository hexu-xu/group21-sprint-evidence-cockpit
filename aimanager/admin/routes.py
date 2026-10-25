"""Administrator account/role operations and project roster."""

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from ..extensions import db
from ..models import Project, ProjectMember, User, UserRole
from ..permissions import can_manage_tasks
from . import bp

PROFILES = {"standard", "read_only_admin", "admin"}
PROJECT_ROLES = {"member", "manager"}


def require_admin():
    if current_user.platform_role != "admin":
        abort(403)


@bp.get("/users")
@login_required
def users():
    require_admin()
    return render_template(
        "admin/users.html",
        users=db.session.scalars(db.select(User).order_by(User.username)).all(),
        roles=db.session.scalars(db.select(UserRole).order_by(UserRole.name)).all(),
        projects=db.session.scalars(db.select(Project).order_by(Project.name)).all(),
    )


@bp.post("/roles")
@login_required
def create_role():
    require_admin()
    name = request.form.get("name", "").strip()
    profile = request.form.get("platform_role", "")
    if not name or len(name) > 80 or profile not in PROFILES:
        flash("角色名称或权限模板无效", "error")
    else:
        try:
            db.session.add(UserRole(name=name, platform_role=profile))
            db.session.commit()
            flash("角色已创建", "success")
        except IntegrityError:
            db.session.rollback()
            flash("角色名称已存在", "error")
    return redirect(url_for("admin.users"))


@bp.post("/users")
@login_required
def create_user():
    require_admin()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role_raw = request.form.get("role_id", "")
    project_raw = request.form.get("project_id", "")
    project_role = request.form.get("project_role", "")
    try:
        role = db.session.get(UserRole, int(role_raw))
        project = db.session.get(Project, int(project_raw))
    except (TypeError, ValueError):
        role = project = None
    if (not username or len(username) > 80 or len(password) < 8 or len(password) > 128
            or role is None or project is None or project_role not in PROJECT_ROLES):
        flash("请输入有效用户名、至少8位密码、角色和所属项目", "error")
        return redirect(url_for("admin.users"))
    try:
        user = User(username=username, password_hash=generate_password_hash(password),
                    role_id=role.id, platform_role=role.platform_role, evidence_role="product")
        db.session.add(user)
        db.session.flush()
        db.session.add(ProjectMember(project_id=project.id, user_id=user.id,
                                     project_role=project_role))
        db.session.commit()
        flash("用户已创建并加入项目", "success")
    except IntegrityError:
        db.session.rollback()
        flash("用户名已存在", "error")
    return redirect(url_for("admin.users"))


@bp.post("/users/<int:user_id>/role")
@login_required
def assign_role(user_id):
    require_admin()
    user = db.get_or_404(User, user_id)
    raw = request.form.get("role_id", "")
    if user.id == current_user.id:
        flash("不能修改自己的角色", "error")
        return redirect(url_for("admin.users"))
    if raw == "":
        role = None
    else:
        try:
            role = db.session.get(UserRole, int(raw))
        except ValueError:
            role = None
        if role is None:
            abort(400)
    user.role_id = role.id if role else None
    user.platform_role = role.platform_role if role else "standard"
    db.session.commit()
    flash("用户角色已更新", "success")
    return redirect(url_for("admin.users"))


@bp.post("/users/<int:user_id>/active")
@login_required
def set_active(user_id):
    require_admin()
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash("不能停用自己的账号", "error")
    else:
        user.active = request.form.get("active") == "1"
        db.session.commit()
        flash("用户状态已更新", "success")
    return redirect(url_for("admin.users"))


@bp.get("/projects/<int:project_id>/members")
@login_required
def project_members(project_id):
    project = db.get_or_404(Project, project_id)
    if not can_manage_tasks(current_user, project.id) and current_user.platform_role != "read_only_admin":
        abort(403)
    members = db.session.scalars(
        db.select(ProjectMember).where(ProjectMember.project_id == project.id)
        .join(User, User.id == ProjectMember.user_id).order_by(User.username)
    ).all()
    return render_template("admin/members.html", project=project, members=members,
                           can_manage=can_manage_tasks(current_user, project.id))
