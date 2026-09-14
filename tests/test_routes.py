import pytest
from app import create_app


@pytest.fixture
def client():
    return create_app({"TESTING": True}).test_client()


def test_home_shows_product_scope(client):
    response = client.get("/?role=product")
    assert response.status_code == 200
    assert "U6 用户故事" in response.get_data(as_text=True)
    assert "完整证据链" in response.get_data(as_text=True)


def test_quality_shows_chain_and_red_baseline(client):
    response = client.get("/?role=quality")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "AI功能分支" in body
    assert "未达到DoD" in body


@pytest.mark.parametrize("role", ["product", "tech", "ai_record"])
def test_non_quality_cannot_open_quality_detail(client, role):
    response = client.get(f"/quality?role={role}")
    assert response.status_code == 403
    assert "403 无权查看" in response.get_data(as_text=True)


def test_quality_can_open_quality_detail(client):
    response = client.get("/quality?role=quality")
    assert response.status_code == 200
    assert "完整证据链" in response.get_data(as_text=True)
