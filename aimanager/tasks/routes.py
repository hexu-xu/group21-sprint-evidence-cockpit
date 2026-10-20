"""Project manager team view and member-owned task workflow."""

from datetime import date
from collections import OrderedDict

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import Project, ProjectMember, Task, User
from ..permissions import can_change_status, can_manage_tasks, can_view_task, require_manage_tasks, require_view_project
from . import bp
from .service import TaskInputError, change_status, create_task, delete_task


def task_statistics(tasks, today):
    """Count only tasks already authorized for the current page."""
    counts = {status: 0 for status in ("todo", "in_progress", "done")}
    for task in tasks:
        counts[task.status] += 1
    total = len(tasks)
    return {
        **counts,
        "total": total,
        "overdue": sum(task.due_date < today and task.status != "done" for task in tasks),
        "completion_rate": round(counts["done"] * 100 / total) if total else 0,
        "next_due": min((task.due_date for task in tasks
                         if task.status != "done" and task.due_date >= today), default=None),
    }


def selected_project():
    """Choose a visible project; never accept an unauthorized project id."""
    raw_id = request.values.get("project_id")
    if raw_id:
        try:
            project_id = int(raw_id)
        except ValueError:
            abort(400)
        project = db.session.get(Project, project_id)
        if project is None:
            abort(404)
        require_view_project(current_user, project_id)
        return project
    query = db.select(Project).order_by(Project.id)
    if current_user.platform_role not in {"admin", "read_only_admin"}:
        query = query.join(ProjectMember).where(ProjectMember.user_id == current_user.id)
    return db.session.scalar(query)


@bp.get("")
@login_required
def list_tasks():
    active_status = request.args.get("status", "todo")
    if active_status not in {"todo", "in_progress", "done"}:
        abort(400)
    project = selected_project()
    if project is None:
        return render_template("tasks/list.html", project=None, tasks=[], can_manage=False,
                               board={}, modules=[], active_status=active_status, stats={}, today=date.today())
    can_manage = can_manage_tasks(current_user, project.id)
    query = db.select(Task).where(Task.project_id == project.id).order_by(Task.id.desc())
    if not can_manage and current_user.platform_role != "read_only_admin":
        # Filter in SQL, before results reach the template or response.
        query = query.where(Task.assignee_id == current_user.id)
    tasks = db.session.scalars(query).all()
    board = {status: [task for task in tasks if task.status == status]
             for status in ("todo", "in_progress", "done")}
    modules = OrderedDict()
    for task in sorted(tasks, key=lambda item: (item.module_name.casefold(), item.id)):
        modules.setdefault(task.module_name, {status: [] for status in board})[task.status].append(task)
    stats = task_statistics(tasks, date.today())
    full_project_view = can_manage or current_user.platform_role == "read_only_admin"
    return render_template("tasks/list.html", project=project, tasks=tasks,
                           can_manage=can_manage, board=board, modules=modules,
                           active_status=active_status, stats=stats, today=date.today(),
                           full_project_view=full_project_view)


@bp.get("/overview")
@login_required
def project_overview():
    """Show the whole-project summary to managers and read-only observers."""
    project = selected_project()
    if project is None:
        abort(404)
    can_manage = can_manage_tasks(current_user, project.id)
    if not can_manage and current_user.platform_role != "read_only_admin":
        abort(403)
    tasks = db.session.scalars(
        db.select(Task).where(Task.project_id == project.id).order_by(Task.id)
    ).all()
    stats = task_statistics(tasks, date.today())
    distribution = [
        {"label": label, "count": stats[status],
         "percent": round(stats[status] * 100 / stats["total"]) if stats["total"] else 0}
        for status, label in (("todo", "待完成"), ("in_progress", "进行中"), ("done", "已完成"))
    ]
    return render_template("tasks/overview.html", project=project,
                           can_manage=can_manage, stats=stats, distribution=distribution)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new_task():
    project = selected_project()
    if project is None:
        abort(404)
    require_manage_tasks(current_user, project.id)
    members = db.session.scalars(
        db.select(User).join(ProjectMember, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project.id, User.active.is_(True))
        .order_by(User.username)
    ).all()
    existing_modules = db.session.scalars(
        db.select(Task.module_name).where(Task.project_id == project.id)
        .distinct().order_by(Task.module_name)
    ).all()
    if request.method == "POST":
        try:
            task = create_task(request.form, project.id, current_user.id)
        except TaskInputError as exc:
            flash(str(exc), "error")
        else:
            flash("任务已创建", "success")
            return redirect(url_for("tasks.task_detail", task_id=task.id))
    return render_template("tasks/new.html", project=project, members=members,
                           existing_modules=existing_modules)


@bp.get("/<int:task_id>")
@login_required
def task_detail(task_id):
    task = db.get_or_404(Task, task_id)
    if not can_view_task(current_user, task):
        abort(403)
    existing_modules = db.session.scalars(
        db.select(Task.module_name).where(Task.project_id == task.project_id)
        .distinct().order_by(Task.module_name)
    ).all()
    return render_template("tasks/detail.html", task=task, existing_modules=existing_modules,
                           can_update=can_change_status(current_user, task),
                           can_manage=can_manage_tasks(current_user, task.project_id))


@bp.post("/<int:task_id>/status")
@login_required
def update_status(task_id):
    task = db.get_or_404(Task, task_id)
    if not can_change_status(current_user, task):
        abort(403)
    try:
        change_status(task, request.form.get("status", ""), current_user.id)
    except TaskInputError as exc:
        flash(str(exc), "error")
    else:
        flash("任务状态已更新", "success")
    return redirect(url_for("tasks.task_detail", task_id=task.id))


@bp.post("/<int:task_id>/module")
@login_required
def update_module(task_id):
    task = db.get_or_404(Task, task_id)
    require_manage_tasks(current_user, task.project_id)
    module_name = request.form.get("module_name", "").strip()
    if not module_name or len(module_name) > 60:
        flash("所属模块不能为空且不能超过60字", "error")
    else:
        task.module_name = module_name
        db.session.commit()
        flash("所属模块已更新", "success")
    return redirect(url_for("tasks.task_detail", task_id=task.id))


@bp.route("/<int:task_id>/delete", methods=["GET", "POST"])
@login_required
def delete_task_route(task_id):
    task = db.get_or_404(Task, task_id)
    require_manage_tasks(current_user, task.project_id)
    if request.method == "POST":
        if request.form.get("confirm_task_id") != str(task.id):
            flash("请在确认页重新确认要删除的任务", "error")
            return redirect(url_for("tasks.delete_task_route", task_id=task.id))
        project_id = task.project_id
        delete_task(task)
        flash("任务已删除", "success")
        return redirect(url_for("tasks.list_tasks", project_id=project_id))
    return render_template("tasks/delete.html", task=task)
