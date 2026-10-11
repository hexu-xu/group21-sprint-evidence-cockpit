"""Historical delivery gate regression after session-based identity."""

import json
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from aimanager.extensions import db
from aimanager.models import User
from dod_gate import APPROVED, REJECTED, REQUIRED_EVIDENCE, evaluate_dod


@pytest.fixture
def app():
    application = create_app({
        "TESTING": True, "SECRET_KEY": "test-secret", "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with application.app_context():
        db.create_all()
        for username, role in (("manager", "product"), ("member", "tech"), ("admin", "quality"), ("member2", "ai_record")):
            db.session.add(User(
                username=username, password_hash=generate_password_hash("test-password"),
                platform_role="admin" if username == "admin" else "standard", evidence_role=role,
            ))
        db.session.commit()
    yield application
    with application.app_context():
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, username):
    response = client.post("/auth/login", data={"username": username, "password": "test-password"})
    assert response.status_code == 302


def complete_evidence(review=APPROVED):
    evidence = {key: {"status": APPROVED, "value": f"{key} 真实证据"} for key in REQUIRED_EVIDENCE}
    evidence["human_review"] = {"status": review, "value": "人工审查结论"}
    return evidence


def test_cockpit_requires_login(client):
    assert client.get("/evidence").status_code == 302


def test_old_role_link_opens_history_without_elevating_permissions(client):
    login(client, "member")
    response = client.get("/?role=quality", follow_redirects=True)
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "交付质量记录" in body
    assert "DoD门禁" not in body
    assert client.get("/quality?role=quality").status_code == 403


@pytest.mark.parametrize("username", ["manager", "member", "member2"])
def test_non_quality_role_cannot_see_chain_or_quality_detail(client, username):
    login(client, username)
    body = client.get("/evidence?role=quality").get_data(as_text=True)
    assert "DoD门禁" not in body
    assert "AI功能分支" not in body
    assert client.get("/quality?role=quality").status_code == 403


def test_quality_sees_eight_segment_chain_in_order(client):
    login(client, "admin")
    response = client.get("/quality?role=product")
    assert response.status_code == 200
    chain = response.get_data(as_text=True).split('<ol class="chain">', 1)[1]
    names = ["用户故事", "开发任务", "AI功能分支", "Git提交", "自动化测试", "人工审查", "DoD门禁", "可以评审"]
    assert [chain.index(name) for name in names] == sorted(chain.index(name) for name in names)


def test_historical_evidence_still_drives_page(app, client):
    login(client, "admin")
    evidence = json.loads((Path(__file__).resolve().parents[1] / "data" / "evidence.json").read_text(encoding="utf-8"))
    body = client.get("/evidence").get_data(as_text=True)
    assert evaluate_dod(evidence)["label"] in body
    assert evidence["feature_commit"]["value"].split()[0] in body
    assert "待实际候选提交" not in body


@pytest.mark.parametrize("review,expected", [(APPROVED, "可以进入交付评审"), (REJECTED, "未达到DoD")])
def test_dod_green_and_rejected_states(app, client, review, expected):
    app.config["EVIDENCE_DATA"] = complete_evidence(review)
    login(client, "admin")
    body = client.get("/quality").get_data(as_text=True)
    assert expected in body
    assert ("未达到DoD" in body) == (review == REJECTED)
