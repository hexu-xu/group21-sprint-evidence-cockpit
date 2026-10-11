"""Login forms survive local restarts and handle expired tokens clearly."""

import re

from werkzeug.security import generate_password_hash

from app import create_app
from aimanager.extensions import db
from aimanager.models import User


def test_local_secret_key_persists_across_app_creation(tmp_path):
    key_file = tmp_path / "instance" / ".secret_key"
    config = {"TESTING": True, "SECRET_KEY": None, "SECRET_KEY_FILE": str(key_file)}
    first = create_app(config)
    second = create_app(config)
    assert first.secret_key == second.secret_key == key_file.read_text(encoding="utf-8")
    assert len(first.secret_key) == 64


def test_expired_login_token_is_recoverable(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "csrf-test-secret",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        db.create_all()
        db.session.add(User(
            username="manager", password_hash=generate_password_hash("test-password"),
            platform_role="standard", evidence_role="product",
        ))
        db.session.commit()

    client = app.test_client()
    expired = client.post("/auth/login", data={
        "username": "manager", "password": "test-password", "csrf_token": "stale",
    }, follow_redirects=True)
    assert expired.status_code == 200
    assert "登录页面已过期" in expired.get_data(as_text=True)

    page = client.get("/auth/login").get_data(as_text=True)
    token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    logged_in = client.post("/auth/login", data={
        "username": "manager", "password": "test-password", "csrf_token": token,
    })
    assert logged_in.status_code == 302
    assert logged_in.headers["Location"].endswith("/tasks")
