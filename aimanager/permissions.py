"""Centralized project permissions, enforced before database writes."""

from flask import abort

from .extensions import db
from .models import ProjectMember


def membership(user, project_id):
    return db.session.scalar(
        db.select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user.id
        )
    )


def can_view_project(user, project_id):
    return user.platform_role in {"admin", "read_only_admin"} or membership(user, project_id) is not None


def can_manage_tasks(user, project_id):
    if user.platform_role == "read_only_admin":
        return False
    if user.platform_role == "admin":
        return True
    member = membership(user, project_id)
    return member is not None and member.project_role == "manager"


def require_view_project(user, project_id):
    if not can_view_project(user, project_id):
        abort(403)


def require_manage_tasks(user, project_id):
    if not can_manage_tasks(user, project_id):
        abort(403)


def can_view_task(user, task):
    return can_manage_tasks(user, task.project_id) or user.platform_role == "read_only_admin" or (
        membership(user, task.project_id) is not None and task.assignee_id == user.id
    )


def can_change_status(user, task):
    if user.platform_role == "read_only_admin":
        return False
    return can_manage_tasks(user, task.project_id) or (
        membership(user, task.project_id) is not None and task.assignee_id == user.id
    )
