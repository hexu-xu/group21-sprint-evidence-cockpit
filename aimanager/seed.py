"""Idempotent local demo accounts and project; password comes from the environment."""

import os

import click
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash

from .extensions import db
from .models import Project, ProjectMember, User

DEMO_USERS = (
    ("admin", "admin", "quality"),
    ("manager", "standard", "product"),
    ("member", "standard", "tech"),
    ("member2", "standard", "ai_record"),
    ("observer", "read_only_admin", "ai_record"),
)


@click.command("seed-demo")
@with_appcontext
def seed_demo():
    """Create four role types and one empty project without demo tasks."""
    password = os.environ.get("DEMO_PASSWORD", "")
    if len(password) < 8:
        raise click.ClickException("请先设置至少8位的 DEMO_PASSWORD 环境变量")
    users = {}
    for username, platform_role, evidence_role in DEMO_USERS:
        user = db.session.scalar(db.select(User).where(User.username == username))
        if user is None:
            user = User(
                username=username, password_hash=generate_password_hash(password),
                platform_role=platform_role, evidence_role=evidence_role,
            )
            db.session.add(user)
            db.session.flush()
        users[username] = user

    project = db.session.scalar(db.select(Project).where(Project.name == "产品研发"))
    if project is None:
        project = Project(name="产品研发", description="统一规划团队任务与交付进度", created_by_id=users["manager"].id)
        db.session.add(project)
        db.session.flush()
    for username, role in (("manager", "manager"), ("member", "member"), ("member2", "member")):
        exists = db.session.scalar(db.select(ProjectMember).where(
            ProjectMember.project_id == project.id, ProjectMember.user_id == users[username].id
        ))
        if exists is None:
            db.session.add(ProjectMember(project_id=project.id, user_id=users[username].id, project_role=role))
    db.session.commit()
    click.echo("演示数据已准备：admin、manager、member、member2、observer。")
