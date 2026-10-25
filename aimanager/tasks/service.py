"""Task validation and transactional changes shared by task routes."""

from datetime import date

from ..extensions import db
from ..models import ProjectMember, Task, TaskStatusEvent, User, utc_now

PRIORITIES = {"low", "medium", "high"}
STATUSES = {"todo", "in_progress", "done"}


class TaskInputError(ValueError):
    """A form value is missing, invalid, or refers outside the project."""


def validate_task_form(form, project_id):
    """Validate task fields and ensure the assignee belongs to this project."""
    title = form.get("title", "").strip()
    module_name = form.get("module_name", "").strip() or "未分类"
    description = form.get("description", "").strip()
    priority = form.get("priority", "")
    if not title or len(title) > 120:
        raise TaskInputError("标题不能为空且不能超过120字")
    if len(module_name) > 60:
        raise TaskInputError("所属模块不能超过60字")
    if not description or len(description) > 2000:
        raise TaskInputError("描述不能为空且不能超过2000字")
    if priority not in PRIORITIES:
        raise TaskInputError("请选择有效优先级")
    try:
        due_date = date.fromisoformat(form.get("due_date", ""))
    except ValueError as exc:
        raise TaskInputError("请填写有效截止日期") from exc
    try:
        assignee_id = int(form.get("assignee_id", ""))
    except ValueError as exc:
        raise TaskInputError("请选择有效负责人") from exc
    assignee = db.session.get(User, assignee_id)
    membership = db.session.scalar(
        db.select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == assignee_id
        )
    )
    if assignee is None or not assignee.active or membership is None:
        raise TaskInputError("负责人必须是当前项目的有效成员")
    return module_name, title, description, priority, due_date, assignee_id


def create_task(form, project_id, actor_id):
    module_name, title, description, priority, due_date, assignee_id = validate_task_form(form, project_id)
    task = Task(
        project_id=project_id, module_name=module_name, title=title, description=description,
        priority=priority, due_date=due_date, assignee_id=assignee_id, created_by_id=actor_id,
        status="todo",
    )
    db.session.add(task)
    db.session.flush()
    db.session.add(TaskStatusEvent(task_id=task.id, from_status=None, to_status="todo", actor_id=actor_id))
    db.session.commit()
    return task


def change_status(task, status, actor_id):
    """Save current status and history atomically; unchanged status adds no event."""
    if status not in STATUSES:
        raise TaskInputError("请选择有效任务状态")
    if status == task.status:
        return False
    before = task.status
    task.status = status
    task.completed_at = utc_now() if status == "done" else None
    db.session.add(TaskStatusEvent(task_id=task.id, from_status=before, to_status=status, actor_id=actor_id))
    db.session.commit()
    return True


def delete_task(task):
    """Delete a task and its dependent status history in one transaction."""
    from ..models import TaskComment
    db.session.execute(db.delete(TaskComment).where(TaskComment.task_id == task.id))
    db.session.execute(
        db.delete(TaskStatusEvent).where(TaskStatusEvent.task_id == task.id)
    )
    db.session.delete(task)
    db.session.commit()
