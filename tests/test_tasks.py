"""Task creation, assignment, visibility and status authorization."""

import re
from datetime import date, timedelta

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from aimanager.extensions import db
from aimanager.models import (Project, ProjectMember, ProjectProgressCheckpoint,
                              ProjectProgressCheckpointRevision, Task, TaskStatusEvent, User)


@pytest.fixture
def app():
    application = create_app({
        "TESTING": True, "SECRET_KEY": "test-secret", "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with application.app_context():
        db.create_all()
        for username, role in (("manager", "standard"), ("member", "standard"), ("member2", "standard"), ("outsider", "standard"), ("admin", "admin"), ("observer", "read_only_admin")):
            db.session.add(User(
                username=username, password_hash=generate_password_hash("test-password"),
                platform_role=role, evidence_role="quality" if username == "admin" else "product",
            ))
        db.session.flush()
        users = {u.username: u for u in db.session.scalars(db.select(User)).all()}
        project = Project(name="爱管理", created_by_id=users["manager"].id)
        db.session.add(project)
        db.session.flush()
        for username, role in (("manager", "manager"), ("member", "member"), ("member2", "member")):
            db.session.add(ProjectMember(project_id=project.id, user_id=users[username].id, project_role=role))
        db.session.commit()
    yield application
    with application.app_context():
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, username):
    return client.post("/auth/login", data={"username": username, "password": "test-password"})


def logout(client):
    return client.post("/auth/logout")


def form(app, assignee="member"):
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.username == assignee))
        return {
            "project_id": "1", "module_name": "用户与权限", "title": "实现任务协作",
            "description": "连接任务、成员与状态", "priority": "high",
            "due_date": "2026-10-20", "assignee_id": str(user.id),
        }


def test_login_rejects_wrong_password_and_redirects_unauthenticated(client):
    assert client.get("/tasks").status_code == 302
    response = client.post("/auth/login", data={"username": "manager", "password": "wrong"})
    assert "用户名或密码错误" in response.get_data(as_text=True)
    assert client.get("/tasks").status_code == 302


def test_login_page_switches_existing_account(app, client):
    login(client, "manager")
    client.post("/tasks/new", data=form(app, "member"))
    login(client, "admin")
    login_page = client.get("/auth/login")
    assert login_page.status_code == 200
    assert "当前登录：<strong>admin</strong>" in login_page.get_data(as_text=True)

    wrong = client.post("/auth/login", data={"username": "member", "password": "wrong"})
    assert "当前仍以 admin 登录" in wrong.get_data(as_text=True)
    assert client.get("/quality").status_code == 200

    switched = login(client, "member")
    assert switched.status_code == 302
    body = client.get("/tasks").get_data(as_text=True)
    assert "member" in body and "实现任务协作" in body
    assert "新建任务" not in body
    assert client.get("/quality").status_code == 403


def test_manager_creates_and_sees_assigned_task(app, client):
    login(client, "manager")
    response = client.post("/tasks/new", data=form(app))
    assert response.status_code == 302
    with app.app_context():
        task = db.session.scalar(db.select(Task))
        assert (task.title, task.description, task.priority, str(task.due_date), task.status) == (
            "实现任务协作", "连接任务、成员与状态", "high", "2026-10-20", "todo"
        )
        assert task.assignee.username == "member"
        assert task.module_name == "用户与权限"
        events = db.session.scalars(db.select(TaskStatusEvent)).all()
        assert len(events) == 1 and events[0].to_status == "todo"
    body = client.get("/tasks").get_data(as_text=True)
    assert "实现任务协作" in body and "member" in body
    assert "任务看板" in body
    assert "任务总数" in body
    assert "任务故事地图" in body and "用户与权限" in body


def test_story_map_tabs_group_modules_and_show_completion_time(app, client):
    login(client, "manager")
    first = form(app)
    first["module_name"] = "用户与权限"
    client.post("/tasks/new", data=first)
    second = form(app, "member2")
    second.update({"module_name": "任务协作", "title": "处理任务状态"})
    client.post("/tasks/new", data=second)
    client.post("/tasks/2/status", data={"status": "done"})

    todo = client.get("/tasks?status=todo").get_data(as_text=True)
    done = client.get("/tasks?status=done").get_data(as_text=True)
    assert 'status=todo" aria-current="page"' in todo
    assert 'status=done" aria-current="page"' in done
    assert todo.count('class="map-task-card"') == 1
    assert done.count('class="map-task-card"') == 1
    assert "用户与权限" in todo and "任务协作" in todo
    assert "完成时间" in done and "处理任务状态" in done
    assert client.get("/tasks?status=unknown").status_code == 400


def test_manager_can_reclassify_task_but_member_cannot(app, client):
    login(client, "manager")
    client.post("/tasks/new", data=form(app))
    assert client.post("/tasks/1/module", data={"module_name": "项目管理"}).status_code == 302
    with app.app_context():
        assert db.session.get(Task, 1).module_name == "项目管理"
    assert "项目管理" in client.get("/tasks").get_data(as_text=True)
    assert "调整所属模块" in client.get("/tasks/1").get_data(as_text=True)
    assert client.post("/tasks/1/module", data={"module_name": ""}).status_code == 302
    with app.app_context():
        assert db.session.get(Task, 1).module_name == "项目管理"
    logout(client)
    login(client, "member")
    assert "调整所属模块" not in client.get("/tasks/1").get_data(as_text=True)
    assert client.post("/tasks/1/module", data={"module_name": "越权修改"}).status_code == 403


def test_manager_deletes_task_and_its_status_history(app, client):
    login(client, "manager")
    client.post("/tasks/new", data=form(app))
    client.post("/tasks/1/status", data={"status": "in_progress"})
    detail = client.get("/tasks/1").get_data(as_text=True)
    assert "删除此任务" in detail
    confirm = client.get("/tasks/1/delete")
    assert confirm.status_code == 200
    assert "确认删除任务" in confirm.get_data(as_text=True)
    response = client.post("/tasks/1/delete", data={"confirm_task_id": "1"})
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(Task, 1) is None
        assert db.session.scalars(db.select(TaskStatusEvent)).all() == []
    assert "实现任务协作" not in client.get("/tasks").get_data(as_text=True)


def test_admin_can_delete_task(app, client):
    login(client, "manager")
    client.post("/tasks/new", data=form(app))
    logout(client)
    login(client, "admin")
    assert client.get("/tasks/1/delete").status_code == 200
    assert client.post("/tasks/1/delete", data={"confirm_task_id": "1"}).status_code == 302
    with app.app_context():
        assert db.session.get(Task, 1) is None


@pytest.mark.parametrize("username", ["member", "member2", "observer", "outsider"])
def test_non_managers_cannot_delete_tasks(app, client, username):
    login(client, "manager")
    client.post("/tasks/new", data=form(app))
    logout(client)
    login(client, username)
    if username in {"member", "observer"}:
        assert "删除此任务" not in client.get("/tasks/1").get_data(as_text=True)
    assert client.get("/tasks/1/delete").status_code == 403
    assert client.post("/tasks/1/delete", data={"confirm_task_id": "1"}).status_code == 403
    with app.app_context():
        assert db.session.get(Task, 1) is not None


def test_delete_requires_confirmation_and_csrf(app, client):
    login(client, "manager")
    client.post("/tasks/new", data=form(app))
    assert client.post("/tasks/1/delete", data={"confirm_task_id": "2"}).status_code == 302
    with app.app_context():
        assert db.session.get(Task, 1) is not None

    app.config["WTF_CSRF_ENABLED"] = True
    assert client.post("/tasks/1/delete", data={"confirm_task_id": "1"}).status_code == 400
    page = client.get("/tasks/1/delete").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    assert client.post("/tasks/1/delete", data={
        "confirm_task_id": "1", "csrf_token": token,
    }).status_code == 302
    with app.app_context():
        assert db.session.get(Task, 1) is None


def test_project_manager_cannot_delete_another_projects_task(app, client):
    with app.app_context():
        admin = db.session.scalar(db.select(User).where(User.username == "admin"))
        member = db.session.scalar(db.select(User).where(User.username == "member"))
        other_project = Project(name="其他项目", created_by_id=admin.id)
        db.session.add(other_project)
        db.session.flush()
        task = Task(
            project_id=other_project.id, module_name="后台服务", title="其他项目任务",
            description="仅该项目负责人可管理", priority="medium", due_date=date(2026, 10, 20),
            assignee_id=member.id, created_by_id=admin.id, status="todo",
        )
        db.session.add(task)
        db.session.commit()
        task_id = task.id
    login(client, "manager")
    assert client.get(f"/tasks/{task_id}/delete").status_code == 403
    assert client.post(f"/tasks/{task_id}/delete", data={"confirm_task_id": str(task_id)}).status_code == 403
    with app.app_context():
        assert db.session.get(Task, task_id) is not None


def test_member_can_only_view_and_update_own_task(app, client):
    login(client, "manager")
    client.post("/tasks/new", data=form(app, "member"))
    other = form(app, "member2")
    other["title"] = "另一成员任务"
    client.post("/tasks/new", data=other)
    logout(client)
    login(client, "member")
    body = client.get("/tasks?project_id=1").get_data(as_text=True)
    assert "实现任务协作" in body and "另一成员任务" not in body
    assert client.get("/tasks/2").status_code == 403
    assert client.post("/tasks/2/status", data={"status": "done"}).status_code == 403
    assert client.post("/tasks/1/status", data={"status": "in_progress"}).status_code == 302
    with app.app_context():
        task = db.session.get(Task, 1)
        assert task.status == "in_progress"
        assert [(e.from_status, e.to_status) for e in db.session.scalars(db.select(TaskStatusEvent).where(TaskStatusEvent.task_id == 1).order_by(TaskStatusEvent.id))] == [(None, "todo"), ("todo", "in_progress")]
    logout(client)
    login(client, "manager")
    assert "进行中" in client.get("/tasks").get_data(as_text=True)


def test_manager_only_creation_and_valid_project_assignee(app, client):
    login(client, "member")
    assert client.post("/tasks/new", data=form(app)).status_code == 403
    logout(client)
    login(client, "manager")
    bad = form(app, "outsider")
    response = client.post("/tasks/new", data=bad)
    assert "负责人必须是当前项目" in response.get_data(as_text=True)
    bad = form(app)
    bad["priority"] = "urgent"
    assert "有效优先级" in client.post("/tasks/new", data=bad).get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Task.id))) == 0


def test_outsider_cannot_view_project_and_observer_cannot_write(app, client):
    login(client, "manager")
    client.post("/tasks/new", data=form(app))
    logout(client)
    login(client, "outsider")
    assert client.get("/tasks?project_id=1").status_code == 403
    assert client.get("/tasks/1").status_code == 403
    logout(client)
    login(client, "observer")
    assert "实现任务协作" in client.get("/tasks").get_data(as_text=True)
    assert client.post("/tasks/new", data=form(app)).status_code == 403
    assert client.post("/tasks/1/status", data={"status": "done"}).status_code == 403


def test_invalid_status_does_not_write_history(app, client):
    login(client, "manager")
    client.post("/tasks/new", data=form(app))
    response = client.post("/tasks/1/status", data={"status": "blocked"}, follow_redirects=True)
    assert "有效任务状态" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Task, 1).status == "todo"
        assert db.session.scalar(db.select(db.func.count(TaskStatusEvent.id))) == 1


def test_product_pages_do_not_show_coursework_terms(client):
    login_page = client.get("/auth/login").get_data(as_text=True)
    login(client, "manager")
    pages = [login_page, client.get("/tasks").get_data(as_text=True),
             client.get("/tasks/new").get_data(as_text=True)]
    for page in pages:
        assert "Sprint" not in page
        assert "实验" not in page
        assert "作业" not in page


def test_overview_tracks_project_counts_and_status_changes(app, client):
    login(client, "manager")
    empty = client.get("/tasks/overview?project_id=1")
    assert empty.status_code == 200
    assert "暂无任务" in empty.get_data(as_text=True)
    assert "当前项目还没有任务" in empty.get_data(as_text=True)

    for title in ("任务甲", "任务乙", "任务丙"):
        data = form(app)
        data["title"] = title
        assert client.post("/tasks/new", data=data).status_code == 302
    client.post("/tasks/2/status", data={"status": "in_progress"})
    client.post("/tasks/3/status", data={"status": "done"})

    body = client.get("/tasks/overview?project_id=1").get_data(as_text=True)
    assert "任务总数</span><strong>3</strong>" in body
    assert "已完成</span><strong>1</strong>" in body
    assert "进行中</span><strong>1</strong>" in body
    assert "待完成</span><strong>1</strong>" in body
    assert body.count("1 项 · 33%") == 3
    assert "完成率 33%" in body

    client.post("/tasks/1/status", data={"status": "done"})
    changed = client.get("/tasks/overview?project_id=1").get_data(as_text=True)
    assert "已完成</span><strong>2</strong>" in changed
    assert "完成率 67%" in changed


def test_overview_project_and_role_boundaries(app, client):
    login(client, "manager")
    client.post("/tasks/new", data=form(app, "member"))
    with app.app_context():
        admin = db.session.scalar(db.select(User).where(User.username == "admin"))
        other = Project(name="私有项目", created_by_id=admin.id)
        db.session.add(other)
        db.session.flush()
        member2 = db.session.scalar(db.select(User).where(User.username == "member2"))
        db.session.add(Task(
            project_id=other.id, module_name="其他", title="跨项目机密任务",
            description="不得出现在首个项目概览", priority="medium",
            due_date=date(2026, 10, 20), assignee_id=member2.id,
            created_by_id=admin.id, status="todo",
        ))
        db.session.commit()
        other_id = other.id
    body = client.get("/tasks/overview?project_id=1").get_data(as_text=True)
    assert "任务总数</span><strong>1</strong>" in body
    assert "跨项目机密任务" not in body
    assert client.get(f"/tasks/overview?project_id={other_id}").status_code == 403

    logout(client)
    login(client, "member")
    assert client.get("/tasks/overview?project_id=1").status_code == 403
    own_board = client.get("/tasks?project_id=1").get_data(as_text=True)
    assert "分配给我的任务" in own_board
    assert "项目概览" not in own_board
    logout(client)
    login(client, "observer")
    assert client.get("/tasks/overview?project_id=1").status_code == 200
    assert client.post("/tasks/new", data=form(app)).status_code == 403
    logout(client)
    login(client, "outsider")
    assert client.get("/tasks/overview?project_id=1").status_code == 403


def test_end_to_end_main_and_permission_journeys(app, client):
    assert login(client, "manager").status_code == 302
    assert client.post("/tasks/new", data=form(app, "member")).status_code == 302
    assert "任务总数</span><strong>1</strong>" in client.get(
        "/tasks/overview?project_id=1"
    ).get_data(as_text=True)
    logout(client)
    login(client, "member")
    assert "实现任务协作" in client.get("/tasks?project_id=1").get_data(as_text=True)
    assert client.post("/tasks/1/status", data={"status": "done"}).status_code == 302
    assert client.get("/tasks/overview?project_id=1").status_code == 403
    logout(client)
    login(client, "manager")
    final = client.get("/tasks/overview?project_id=1").get_data(as_text=True)
    assert "已完成</span><strong>1</strong>" in final
    assert "完成率 100%" in final
    logout(client)
    login(client, "member2")
    assert client.get("/tasks/1").status_code == 403
    assert client.post("/tasks/1/status", data={"status": "todo"}).status_code == 403


def test_progress_checkpoints_compare_recorded_stories_without_mixing_task_counts(app, client):
    login(client, "manager")
    client.post("/tasks/new", data=form(app))
    past = (date.today() - timedelta(days=2)).isoformat()
    future = (date.today() + timedelta(days=4)).isoformat()
    assert client.post("/tasks/overview/checkpoints", data={
        "project_id": "1", "target_date": past, "planned_count": "7",
        "actual_count": "7", "actual_evidence": "已验收故事清单及提交号",
    }).status_code == 302
    assert client.post("/tasks/overview/checkpoints", data={
        "project_id": "1", "target_date": future, "planned_count": "9",
        "actual_count": "", "actual_evidence": "",
    }).status_code == 302
    body = client.get("/tasks/overview?project_id=1").get_data(as_text=True)
    assert "达到检查点目标" in body
    assert "下一检查点" in body and "计划累计 9 项" in body
    assert "计划与实际均为累计 7 项" in body
    assert "任务总数</span><strong>1</strong>" in body
    assert "已验收故事清单及提交号" in body

    with app.app_context():
        checkpoint = db.session.scalar(db.select(ProjectProgressCheckpoint)
                                       .where(ProjectProgressCheckpoint.target_date == date.fromisoformat(past)))
        checkpoint_id = checkpoint.id
    assert client.post("/tasks/overview/checkpoints", data={
        "project_id": "1", "checkpoint_id": str(checkpoint_id),
        "target_date": past, "planned_count": "7", "actual_count": "6",
        "actual_evidence": "独立验收报告", "revision_reason": "复核后更正实际值",
    }).status_code == 302
    lagging = client.get("/tasks/overview?project_id=1").get_data(as_text=True)
    assert "落后 1 项" in lagging and "实际累计 6 项" in lagging


def test_progress_checkpoints_reject_unsupported_actuals_and_inconsistent_plan(app, client):
    login(client, "manager")
    past = (date.today() - timedelta(days=2)).isoformat()
    future = (date.today() + timedelta(days=4)).isoformat()
    endpoint = "/tasks/overview/checkpoints"
    assert "证据位置" in client.post(endpoint, data={
        "project_id": "1", "target_date": past, "planned_count": "7",
        "actual_count": "7", "actual_evidence": "",
    }, follow_redirects=True).get_data(as_text=True)
    assert "未来检查点不能提前填写实际结果" in client.post(endpoint, data={
        "project_id": "1", "target_date": future, "planned_count": "9",
        "actual_count": "9", "actual_evidence": "尚未发生",
    }, follow_redirects=True).get_data(as_text=True)
    assert client.post(endpoint, data={
        "project_id": "1", "target_date": past, "planned_count": "7",
        "actual_count": "7", "actual_evidence": "验收报告",
    }).status_code == 302
    assert "累计计划数不能低于" in client.post(endpoint, data={
        "project_id": "1", "target_date": future, "planned_count": "6",
        "actual_count": "", "actual_evidence": "",
    }, follow_redirects=True).get_data(as_text=True)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(ProjectProgressCheckpoint.id))) == 1


def test_progress_checkpoints_are_project_scoped_and_manager_only(app, client):
    login(client, "manager")
    past = (date.today() - timedelta(days=2)).isoformat()
    payload = {"project_id": "1", "target_date": past, "planned_count": "7",
               "actual_count": "7", "actual_evidence": "验收报告"}
    assert client.post("/tasks/overview/checkpoints", data=payload).status_code == 302
    logout(client)
    for username in ("member", "observer", "outsider"):
        login(client, username)
        assert client.post("/tasks/overview/checkpoints", data=payload).status_code == 403
        if username == "member":
            assert client.get("/tasks/overview?project_id=1").status_code == 403
        logout(client)
    login(client, "manager")
    with app.app_context():
        admin = db.session.scalar(db.select(User).where(User.username == "admin"))
        other = Project(name="其他项目", created_by_id=admin.id)
        db.session.add(other)
        db.session.commit()
        other_id = other.id
        checkpoint_id = db.session.scalar(db.select(ProjectProgressCheckpoint.id))
    assert client.post("/tasks/overview/checkpoints", data={
        **payload, "project_id": str(other_id),
    }).status_code == 403
    assert client.post("/tasks/overview/checkpoints", data={
        **payload, "project_id": str(other_id), "checkpoint_id": str(checkpoint_id),
    }).status_code == 403


def test_progress_revision_preserves_original_plan_evidence_and_reason(app, client):
    login(client, "manager")
    past = (date.today() - timedelta(days=2)).isoformat()
    established = date.today().isoformat()
    endpoint = "/tasks/overview/checkpoints"
    original = {"project_id": "1", "target_date": past,
                "planned_count": "9", "actual_count": "7", "actual_evidence": "证据A",
                "baseline_version": "v1", "baseline_established_on": established}
    assert client.post(endpoint, data=original).status_code == 302
    with app.app_context():
        checkpoint_id = db.session.scalar(db.select(ProjectProgressCheckpoint.id))
    changed = {**original, "checkpoint_id": str(checkpoint_id),
               "planned_count": "7", "actual_evidence": "证据B"}
    no_reason = client.post(endpoint, data=changed, follow_redirects=True).get_data(as_text=True)
    assert "修改检查点须填写修订原因" in no_reason
    no_version = client.post(endpoint, data={**changed, "revision_reason": "调整目标"},
                             follow_redirects=True).get_data(as_text=True)
    assert "修改计划目标须填写新的基线版本" in no_version
    with app.app_context():
        current = db.session.get(ProjectProgressCheckpoint, checkpoint_id)
        assert (current.planned_count, current.actual_evidence) == (9, "证据A")

    revised = {**changed, "baseline_version": "v2",
               "revision_reason": "评审确认范围调整，保留原目标"}
    assert client.post(endpoint, data=revised).status_code == 302
    body = client.get("/tasks/overview?project_id=1").get_data(as_text=True)
    assert "达到检查点目标" in body
    assert "9 → 7" in body and "证据A → 证据B" in body
    assert "v1" in body and "v2" in body and established in body
    assert "评审确认范围调整，保留原目标" in body
    with app.app_context():
        revisions = db.session.scalars(db.select(ProjectProgressCheckpointRevision)
                                       .order_by(ProjectProgressCheckpointRevision.id)).all()
        assert len(revisions) == 2
        assert revisions[0].old_planned_count is None
        assert revisions[1].old_planned_count == 9
        assert revisions[1].new_planned_count == 7
        assert revisions[1].old_actual_evidence == "证据A"
        assert revisions[1].new_actual_evidence == "证据B"
        assert revisions[1].actor_id is not None and revisions[1].reason


def test_progress_actual_correction_requires_reason_and_keeps_previous_evidence(app, client):
    login(client, "manager")
    past = (date.today() - timedelta(days=1)).isoformat()
    endpoint = "/tasks/overview/checkpoints"
    original = {"project_id": "1", "target_date": past,
                "planned_count": "7", "actual_count": "6", "actual_evidence": "初验报告"}
    assert client.post(endpoint, data=original).status_code == 302
    with app.app_context():
        checkpoint_id = db.session.scalar(db.select(ProjectProgressCheckpoint.id))
    changed = {**original, "checkpoint_id": str(checkpoint_id),
               "actual_count": "7", "actual_evidence": "复验报告"}
    body = client.post(endpoint, data=changed, follow_redirects=True).get_data(as_text=True)
    assert "修改检查点须填写修订原因" in body
    assert client.post(endpoint, data={**changed, "revision_reason": "复验通过"}).status_code == 302
    with app.app_context():
        events = db.session.scalars(db.select(ProjectProgressCheckpointRevision)
                                    .order_by(ProjectProgressCheckpointRevision.id)).all()
        assert (events[-1].old_actual_count, events[-1].new_actual_count) == (6, 7)
        assert (events[-1].old_actual_evidence, events[-1].new_actual_evidence) == ("初验报告", "复验报告")
