"""Acceptance journeys for the story-map backlog, with real HTTP handlers and SQLite."""

from datetime import date, datetime, timedelta, timezone

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from aimanager.extensions import db
from aimanager.models import (Project, ProjectMember, ProjectProgressCheckpoint,
                              Task, TaskComment, User, UserRole)


@pytest.fixture
def app():
    application = create_app({"TESTING": True, "SECRET_KEY": "story-test",
                              "WTF_CSRF_ENABLED": False,
                              "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with application.app_context():
        db.create_all()
        for name, role in (("admin", "admin"), ("manager", "standard"),
                           ("member", "standard"), ("outsider", "standard"),
                           ("observer", "read_only_admin")):
            db.session.add(User(username=name, password_hash=generate_password_hash("password123"),
                                platform_role=role, evidence_role="product"))
        db.session.flush()
        users = {u.username: u for u in db.session.scalars(db.select(User)).all()}
        for project_name in ("Alpha", "Beta"):
            project = Project(name=project_name, created_by_id=users["admin"].id)
            db.session.add(project)
            db.session.flush()
            if project_name == "Alpha":
                for name, role in (("manager", "manager"), ("member", "member")):
                    db.session.add(ProjectMember(project_id=project.id,
                                                 user_id=users[name].id, project_role=role))
        db.session.commit()
    yield application
    with application.app_context():
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, name):
    assert client.post("/auth/login", data={"username": name, "password": "password123"}).status_code == 302


def add_task(app, *, title="Alpha task", project_id=1, assignee="member", days=3,
             status="todo", updated_days=0):
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.username == assignee))
        task = Task(project_id=project_id, title=title, module_name="module", description="test",
                    priority="high", due_date=date.today() + timedelta(days=days),
                    assignee_id=user.id, created_by_id=user.id, status=status,
                    updated_at=datetime.now(timezone.utc) - timedelta(days=updated_days))
        db.session.add(task)
        db.session.commit()
        return task.id


def test_u1_u2_u3_u4_u5_create_assign_disable_and_authorize(app, client):
    login(client, "admin")
    assert client.post("/admin/roles", data={"name": "项目观察员", "platform_role": "read_only_admin"}).status_code == 302
    with app.app_context():
        role = db.session.scalar(db.select(UserRole).where(UserRole.name == "项目观察员"))
        role_id = role.id
    assert client.post("/admin/users", data={"username": "newuser", "password": "newpass123",
                                              "role_id": role_id, "project_id": 1,
                                              "project_role": "member"}).status_code == 302
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.username == "newuser"))
        user_id = user.id
        assert user.platform_role == "read_only_admin"
        assert db.session.scalar(db.select(ProjectMember).where(ProjectMember.user_id == user_id))
    assert "newuser" in client.get("/admin/users").get_data(as_text=True)
    assert client.post(f"/admin/users/{user_id}/role", data={"role_id": ""}).status_code == 302
    with app.app_context():
        assert db.session.get(User, user_id).platform_role == "standard"
    assert client.post(f"/admin/users/{user_id}/active", data={"active": "0"}).status_code == 302
    assert client.post("/auth/login", data={"username": "newuser", "password": "newpass123"}).status_code == 200


def test_u1_rejects_duplicate_and_requires_project_and_role(app, client):
    login(client, "admin")
    client.post("/admin/roles", data={"name": "员工", "platform_role": "standard"})
    with app.app_context():
        role_id = db.session.scalar(db.select(UserRole.id))
    form = {"username": "created", "password": "newpass123", "role_id": role_id,
            "project_id": 1, "project_role": "member"}
    client.post("/admin/users", data=form)
    client.post("/admin/users", data=form)
    client.post("/admin/users", data={**form, "username": "invalid", "project_id": 999})
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(User).where(User.username == "created")) == 1
        assert db.session.scalar(db.select(User).where(User.username == "invalid")) is None


def test_u7_member_roles_visible_only_to_manager_or_observer(app, client):
    login(client, "manager")
    page = client.get("/admin/projects/1/members")
    assert page.status_code == 200 and "member" in page.get_data(as_text=True)
    assert client.get("/admin/projects/2/members").status_code == 403
    login(client, "member")
    assert client.get("/admin/projects/1/members").status_code == 403
    assert client.get("/admin/users").status_code == 403


def test_t6_progress_note_is_saved_and_private(app, client):
    task_id = add_task(app)
    login(client, "member")
    assert client.post(f"/tasks/{task_id}/comments", data={"body": "完成接口联调"}).status_code == 302
    with app.app_context():
        assert db.session.scalar(db.select(TaskComment).where(TaskComment.task_id == task_id)).body == "完成接口联调"
    assert "完成接口联调" in client.get(f"/tasks/{task_id}").get_data(as_text=True)
    login(client, "outsider")
    assert client.get(f"/tasks/{task_id}").status_code == 403
    assert client.post(f"/tasks/{task_id}/comments", data={"body": "tamper"}).status_code == 403
    login(client, "observer")
    assert client.post(f"/tasks/{task_id}/comments", data={"body": "tamper"}).status_code == 403


def test_t8_status_date_assignee_filters_and_bad_dates(app, client):
    first = add_task(app, title="First", days=1)
    second = add_task(app, title="Second", days=15, status="done")
    login(client, "manager")
    due = (date.today() + timedelta(days=2)).isoformat()
    body = client.get(f"/tasks?project_id=1&status=todo&due_to={due}&q=First").get_data(as_text=True)
    assert "First" in body and "Second" not in body
    assert client.get("/tasks?project_id=1&due_from=bad").status_code == 400
    assert client.get("/tasks?project_id=1&due_from=2026-10-30&due_to=2026-10-01").status_code == 400
    login(client, "member")
    assert client.get("/tasks?project_id=1&assignee_id=999").status_code == 403


def test_d4_overdue_stale_and_done_exclusion(app, client):
    add_task(app, title="Overdue", days=-1)
    add_task(app, title="Stale", days=30, updated_days=10)
    add_task(app, title="Completed", days=-1, status="done")
    add_task(app, title="Other project", project_id=2, days=-1)
    login(client, "manager")
    body = client.get("/tasks/attention?project_id=1&stale_days=7").get_data(as_text=True)
    assert "Overdue" in body and "Stale" in body
    assert "Completed" not in body and "Other project" not in body
    assert client.get("/tasks/attention?project_id=2").status_code == 403


def test_d3_trend_keeps_future_actual_blank(app, client):
    with app.app_context():
        actor = db.session.scalar(db.select(User).where(User.username == "manager"))
        db.session.add(ProjectProgressCheckpoint(project_id=1, target_date=date(2026, 10, 18),
                        planned_count=7, actual_count=7, actual_evidence="验收记录", updated_by_id=actor.id))
        db.session.add(ProjectProgressCheckpoint(project_id=1, target_date=date(2026, 10, 28),
                        planned_count=10, actual_count=None, updated_by_id=actor.id))
        db.session.commit()
    login(client, "manager")
    body = client.get("/tasks/trend?project_id=1").get_data(as_text=True)
    assert "2026-10-18" in body and "2026-10-28" in body
    assert "实际 待登记" in body
    login(client, "member")
    assert client.get("/tasks/trend?project_id=1").status_code == 403


def test_d6_date_status_aggregates_are_project_scoped(app, client):
    add_task(app, title="A", days=1, status="todo")
    add_task(app, title="B", days=2, status="done")
    add_task(app, title="C", days=20, status="todo")
    add_task(app, title="Secret", project_id=2, days=1)
    login(client, "manager")
    end = (date.today() + timedelta(days=3)).isoformat()
    body = client.get(f"/tasks/analytics?project_id=1&to_date={end}").get_data(as_text=True)
    assert "范围内任务</span><strong>2</strong>" in body
    assert "待完成</span><strong>1</strong>" in body
    assert "已完成</span><strong>1</strong>" in body
    assert client.get("/tasks/analytics?project_id=1&from_date=2026-12-01&to_date=2026-01-01").status_code == 400
    login(client, "member")
    assert client.get("/tasks/analytics?project_id=1").status_code == 403
