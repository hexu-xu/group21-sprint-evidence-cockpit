"""Project manager team view and member-owned task workflow."""

from datetime import date, datetime, timedelta, timezone
from collections import OrderedDict

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import (Project, ProjectMember, ProjectProgressCheckpoint,
                      ProjectProgressCheckpointRevision, Task, TaskComment, User, utc_now)
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
    filters = {key: request.args.get(key, "").strip() for key in
               ("priority", "assignee_id", "due_from", "due_to", "q")}
    filter_query = {key: value for key, value in filters.items() if value}
    if filters["priority"]:
        if filters["priority"] not in {"low", "medium", "high"}:
            abort(400)
        query = query.where(Task.priority == filters["priority"])
    if filters["assignee_id"]:
        try:
            assignee_id = int(filters["assignee_id"])
        except ValueError:
            abort(400)
        if not (can_manage or current_user.platform_role == "read_only_admin") and assignee_id != current_user.id:
            abort(403)
        query = query.where(Task.assignee_id == assignee_id)
    for key, operator in (("due_from", Task.due_date.__ge__),
                          ("due_to", Task.due_date.__le__)):
        if filters[key]:
            try:
                due = date.fromisoformat(filters[key])
            except ValueError:
                abort(400)
            query = query.where(operator(due))
    if filters["due_from"] and filters["due_to"] and filters["due_from"] > filters["due_to"]:
        abort(400)
    if filters["q"]:
        if len(filters["q"]) > 120:
            abort(400)
        query = query.where(Task.title.contains(filters["q"]))
    tasks = db.session.scalars(query).all()
    board = {status: [task for task in tasks if task.status == status]
             for status in ("todo", "in_progress", "done")}
    modules = OrderedDict()
    for task in sorted(tasks, key=lambda item: (item.module_name.casefold(), item.id)):
        modules.setdefault(task.module_name, {status: [] for status in board})[task.status].append(task)
    stats = task_statistics(tasks, date.today())
    full_project_view = can_manage or current_user.platform_role == "read_only_admin"
    members = db.session.scalars(
        db.select(User).join(ProjectMember, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project.id).order_by(User.username)
    ).all() if full_project_view else []
    return render_template("tasks/list.html", project=project, tasks=tasks,
                           can_manage=can_manage, board=board, modules=modules,
                           active_status=active_status, stats=stats, today=date.today(),
                           full_project_view=full_project_view, filters=filters,
                           filter_query=filter_query, members=members)


def _manager_project():
    project = selected_project()
    if project is None:
        abort(404)
    if not can_manage_tasks(current_user, project.id) and current_user.platform_role != "read_only_admin":
        abort(403)
    return project


@bp.get("/attention")
@login_required
def attention_tasks():
    """D4: incomplete overdue or untouched tasks, scoped to one project."""
    project = _manager_project()
    try:
        stale_days = int(request.args.get("stale_days", "7"))
    except ValueError:
        abort(400)
    if not 1 <= stale_days <= 365:
        abort(400)
    today = date.today()
    cutoff = utc_now() - timedelta(days=stale_days)
    tasks = db.session.scalars(db.select(Task).where(Task.project_id == project.id)
                               .order_by(Task.due_date, Task.id)).all()
    attention = []
    for task in tasks:
        if task.status == "done":
            continue
        updated = task.updated_at.replace(tzinfo=timezone.utc) if task.updated_at.tzinfo is None else task.updated_at
        overdue = task.due_date < today
        stale = updated < cutoff
        if overdue or stale:
            attention.append((task, overdue, stale))
    return render_template("tasks/attention.html", project=project, attention=attention,
                           stale_days=stale_days, can_manage=can_manage_tasks(current_user, project.id))


@bp.get("/analytics")
@login_required
def analytics():
    """D6: status counts for a selected due-date window."""
    project = _manager_project()
    bounds = {}
    for key in ("from_date", "to_date"):
        raw = request.args.get(key, "").strip()
        try:
            bounds[key] = date.fromisoformat(raw) if raw else None
        except ValueError:
            abort(400)
    if bounds["from_date"] and bounds["to_date"] and bounds["from_date"] > bounds["to_date"]:
        abort(400)
    query = db.select(Task).where(Task.project_id == project.id)
    if bounds["from_date"]:
        query = query.where(Task.due_date >= bounds["from_date"])
    if bounds["to_date"]:
        query = query.where(Task.due_date <= bounds["to_date"])
    tasks = db.session.scalars(query.order_by(Task.due_date, Task.id)).all()
    stats = task_statistics(tasks, date.today())
    by_date = OrderedDict()
    for task in tasks:
        row = by_date.setdefault(task.due_date, {"todo": 0, "in_progress": 0, "done": 0})
        row[task.status] += 1
    return render_template("tasks/analytics.html", project=project, stats=stats,
                           by_date=by_date, bounds=bounds,
                           can_manage=can_manage_tasks(current_user, project.id))


@bp.get("/trend")
@login_required
def progress_trend():
    """D3: chronological cumulative plan/actual trend without interpolating missing actuals."""
    project = _manager_project()
    checkpoints = db.session.scalars(
        db.select(ProjectProgressCheckpoint).where(ProjectProgressCheckpoint.project_id == project.id)
        .order_by(ProjectProgressCheckpoint.target_date)
    ).all()
    ceiling = max([1] + [max(c.planned_count, c.actual_count or 0) for c in checkpoints])
    rows = []
    previous_actual = None
    for item in checkpoints:
        actual_delta = None if item.actual_count is None or previous_actual is None else item.actual_count - previous_actual
        if item.actual_count is not None:
            previous_actual = item.actual_count
        rows.append({"point": item, "plan_width": round(item.planned_count * 100 / ceiling),
                     "actual_width": round(item.actual_count * 100 / ceiling) if item.actual_count is not None else None,
                     "actual_delta": actual_delta})
    return render_template("tasks/trend.html", project=project, rows=rows,
                           can_manage=can_manage_tasks(current_user, project.id))


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
    checkpoints = db.session.scalars(
        db.select(ProjectProgressCheckpoint)
        .where(ProjectProgressCheckpoint.project_id == project.id)
        .order_by(ProjectProgressCheckpoint.target_date)
    ).all()
    revisions = db.session.scalars(
        db.select(ProjectProgressCheckpointRevision)
        .where(ProjectProgressCheckpointRevision.project_id == project.id)
        .order_by(ProjectProgressCheckpointRevision.changed_at.desc(),
                  ProjectProgressCheckpointRevision.id.desc())
    ).all()
    today = date.today()
    latest_due = next((item for item in reversed(checkpoints) if item.target_date <= today), None)
    next_target = next((item for item in checkpoints if item.target_date > today), None)
    comparison = None
    if latest_due and latest_due.actual_count is not None:
        comparison = latest_due.actual_count - latest_due.planned_count
    return render_template("tasks/overview.html", project=project,
                           can_manage=can_manage, stats=stats, distribution=distribution,
                           checkpoints=checkpoints, revisions=revisions, latest_due=latest_due,
                           next_target=next_target, comparison=comparison, today=today)


def _cumulative_count(value, label):
    try:
        count = int(value)
    except (TypeError, ValueError) as exc:
        raise TaskInputError(f"{label}须为非负整数") from exc
    if not 0 <= count <= 100000:
        raise TaskInputError(f"{label}须为0到100000之间的整数")
    return count


def _checkpoint_values(checkpoint):
    if checkpoint is None:
        return {}
    return {
        "target_date": checkpoint.target_date,
        "planned_count": checkpoint.planned_count,
        "actual_count": checkpoint.actual_count,
        "actual_evidence": checkpoint.actual_evidence,
        "baseline_version": checkpoint.baseline_version,
        "baseline_established_on": checkpoint.baseline_established_on,
    }


@bp.post("/overview/checkpoints")
@login_required
def save_progress_checkpoint():
    project = selected_project()
    if project is None:
        abort(404)
    require_manage_tasks(current_user, project.id)
    try:
        checkpoint_id = request.form.get("checkpoint_id", "").strip()
        checkpoint = None
        if checkpoint_id:
            checkpoint = db.session.get(ProjectProgressCheckpoint, int(checkpoint_id))
            if checkpoint is None or checkpoint.project_id != project.id:
                abort(403)
        previous = _checkpoint_values(checkpoint)
        target_date = date.fromisoformat(request.form.get("target_date", ""))
        planned_count = _cumulative_count(request.form.get("planned_count"), "计划累计数")
        actual_raw = request.form.get("actual_count", "").strip()
        actual_count = _cumulative_count(actual_raw, "实际累计数") if actual_raw else None
        evidence = request.form.get("actual_evidence", "").strip()
        if len(evidence) > 255:
            raise TaskInputError("实际结果证据位置不能超过255字")
        if actual_count is not None and target_date > date.today():
            raise TaskInputError("未来检查点不能提前填写实际结果")
        if actual_count is not None and not evidence:
            raise TaskInputError("填写实际累计数时，请同时填写证据位置")
        if actual_count is None and evidence:
            raise TaskInputError("尚未填写实际累计数时，请清空证据位置")
        other = db.session.scalars(
            db.select(ProjectProgressCheckpoint)
            .where(ProjectProgressCheckpoint.project_id == project.id)
        ).all()
        existing = next((item for item in other if item.baseline_version and
                         item.baseline_established_on), None)
        version = request.form.get("baseline_version", "").strip()
        established_raw = request.form.get("baseline_established_on", "").strip()
        if checkpoint is None:
            version = version or (existing.baseline_version if existing else "v1")
            established_on = (date.fromisoformat(established_raw) if established_raw else
                              (existing.baseline_established_on if existing else date.today()))
        else:
            version = version or checkpoint.baseline_version
            established_on = (date.fromisoformat(established_raw) if established_raw else
                              checkpoint.baseline_established_on)
        if not version or len(version) > 32 or not established_on:
            raise TaskInputError("请填写可核实的基线版本和编制日期")
        if established_on > date.today():
            raise TaskInputError("基线编制日期不能晚于今天")
        if (checkpoint is None and existing and version == existing.baseline_version and
                established_on != existing.baseline_established_on):
            raise TaskInputError("同一基线版本的编制日期须保持一致")
        reason = request.form.get("revision_reason", "").strip()
        if len(reason) > 255:
            raise TaskInputError("修订原因不能超过255字")
        for item in other:
            if checkpoint is not None and item.id == checkpoint.id:
                continue
            if item.target_date == target_date:
                raise TaskInputError("该日期已有检查点，请编辑原记录")
            if item.target_date < target_date and item.planned_count > planned_count:
                raise TaskInputError("累计计划数不能低于更早检查点")
            if item.target_date > target_date and item.planned_count < planned_count:
                raise TaskInputError("累计计划数不能高于更晚检查点")
            if actual_count is not None and item.actual_count is not None:
                if item.target_date < target_date and item.actual_count > actual_count:
                    raise TaskInputError("实际累计数不能低于更早检查点")
                if item.target_date > target_date and item.actual_count < actual_count:
                    raise TaskInputError("实际累计数不能高于更晚检查点")
        new_values = {
            "target_date": target_date, "planned_count": planned_count,
            "actual_count": actual_count, "actual_evidence": evidence,
            "baseline_version": version, "baseline_established_on": established_on,
        }
        if checkpoint is not None and previous != new_values:
            if not reason:
                raise TaskInputError("修改检查点须填写修订原因")
            if (target_date != checkpoint.target_date or planned_count != checkpoint.planned_count):
                if version == checkpoint.baseline_version:
                    raise TaskInputError("修改计划目标须填写新的基线版本")
                used_version = db.session.scalar(
                    db.select(ProjectProgressCheckpointRevision.id)
                    .where(ProjectProgressCheckpointRevision.checkpoint_id == checkpoint.id,
                           ProjectProgressCheckpointRevision.new_baseline_version == version)
                )
                if used_version:
                    raise TaskInputError("该检查点的基线版本已使用，请填写新版本")
    except TaskInputError as exc:
        flash(str(exc), "error")
        return redirect(url_for("tasks.project_overview", project_id=project.id))
    except (TypeError, ValueError):
        flash("检查点编号或日期无效", "error")
        return redirect(url_for("tasks.project_overview", project_id=project.id))

    if checkpoint is None:
        checkpoint = ProjectProgressCheckpoint(project_id=project.id)
        db.session.add(checkpoint)
        previous = {}
        reason = reason or "首次建立检查点"
    elif previous == new_values:
        flash("检查点内容未变", "success")
        return redirect(url_for("tasks.project_overview", project_id=project.id))
    checkpoint.target_date = target_date
    checkpoint.planned_count = planned_count
    checkpoint.actual_count = actual_count
    checkpoint.actual_evidence = evidence
    checkpoint.baseline_version = version
    checkpoint.baseline_established_on = established_on
    checkpoint.updated_by_id = current_user.id
    db.session.flush()
    db.session.add(ProjectProgressCheckpointRevision(
        checkpoint_id=checkpoint.id, project_id=project.id,
        old_target_date=previous.get("target_date"), new_target_date=target_date,
        old_planned_count=previous.get("planned_count"), new_planned_count=planned_count,
        old_actual_count=previous.get("actual_count"), new_actual_count=actual_count,
        old_actual_evidence=previous.get("actual_evidence"), new_actual_evidence=evidence,
        old_baseline_version=previous.get("baseline_version"), new_baseline_version=version,
        old_baseline_established_on=previous.get("baseline_established_on"),
        new_baseline_established_on=established_on,
        reason=reason, actor_id=current_user.id,
    ))
    db.session.commit()
    flash("项目进度检查点已保存", "success")
    return redirect(url_for("tasks.project_overview", project_id=project.id))


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
    comments = db.session.scalars(
        db.select(TaskComment).where(TaskComment.task_id == task.id)
        .order_by(TaskComment.created_at, TaskComment.id)
    ).all()
    return render_template("tasks/detail.html", task=task, existing_modules=existing_modules,
                           comments=comments,
                           can_update=can_change_status(current_user, task),
                           can_manage=can_manage_tasks(current_user, task.project_id))


@bp.post("/<int:task_id>/comments")
@login_required
def add_comment(task_id):
    task = db.get_or_404(Task, task_id)
    if not can_change_status(current_user, task):
        abort(403)
    body = request.form.get("body", "").strip()
    if not body or len(body) > 2000:
        flash("进展备注不能为空且不能超过2000字", "error")
    else:
        db.session.add(TaskComment(task_id=task.id, author_id=current_user.id, body=body))
        task.updated_at = utc_now()
        db.session.commit()
        flash("进展备注已保存", "success")
    return redirect(url_for("tasks.task_detail", task_id=task.id))


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
