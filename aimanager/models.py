"""Persistent users, projects, tasks and status history."""

from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, UniqueConstraint

from .extensions import db


def utc_now():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    platform_role = db.Column(db.String(30), nullable=False)
    evidence_role = db.Column(db.String(30), nullable=False, default="product")
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    @property
    def is_active(self):
        return self.active


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class ProjectMember(db.Model):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    project_role = db.Column(db.String(20), nullable=False)
    user = db.relationship("User")


class Task(db.Model):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("status IN ('todo', 'in_progress', 'done')", name="task_status"),
        CheckConstraint("priority IN ('low', 'medium', 'high')", name="task_priority"),
    )

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    module_name = db.Column(db.String(60), nullable=False, default="未分类")
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(10), nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    assignee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="todo")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    assignee = db.relationship("User", foreign_keys=[assignee_id])
    creator = db.relationship("User", foreign_keys=[created_by_id])
    project = db.relationship("Project")


class TaskStatusEvent(db.Model):
    __tablename__ = "task_status_events"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    from_status = db.Column(db.String(20), nullable=True)
    to_status = db.Column(db.String(20), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    changed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)


class ProjectProgressCheckpoint(db.Model):
    """A cumulative story plan and a human-recorded result for one date."""

    __tablename__ = "project_progress_checkpoints"
    __table_args__ = (
        UniqueConstraint("project_id", "target_date"),
        CheckConstraint("planned_count >= 0", name="progress_planned_nonnegative"),
        CheckConstraint("actual_count IS NULL OR actual_count >= 0", name="progress_actual_nonnegative"),
    )

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    target_date = db.Column(db.Date, nullable=False)
    planned_count = db.Column(db.Integer, nullable=False)
    actual_count = db.Column(db.Integer, nullable=True)
    actual_evidence = db.Column(db.String(255), nullable=False, default="")
    baseline_version = db.Column(db.String(32), nullable=True)
    baseline_established_on = db.Column(db.Date, nullable=True)
    updated_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class ProjectProgressCheckpointRevision(db.Model):
    """Append-only before/after record for a checkpoint creation or revision."""

    __tablename__ = "project_progress_checkpoint_revisions"

    id = db.Column(db.Integer, primary_key=True)
    checkpoint_id = db.Column(db.Integer, db.ForeignKey("project_progress_checkpoints.id"), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    old_target_date = db.Column(db.Date, nullable=True)
    new_target_date = db.Column(db.Date, nullable=False)
    old_planned_count = db.Column(db.Integer, nullable=True)
    new_planned_count = db.Column(db.Integer, nullable=False)
    old_actual_count = db.Column(db.Integer, nullable=True)
    new_actual_count = db.Column(db.Integer, nullable=True)
    old_actual_evidence = db.Column(db.String(255), nullable=True)
    new_actual_evidence = db.Column(db.String(255), nullable=False, default="")
    old_baseline_version = db.Column(db.String(32), nullable=True)
    new_baseline_version = db.Column(db.String(32), nullable=False)
    old_baseline_established_on = db.Column(db.Date, nullable=True)
    new_baseline_established_on = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    changed_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)

    actor = db.relationship("User")
