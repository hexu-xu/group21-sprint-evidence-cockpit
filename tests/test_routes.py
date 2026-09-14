"""路由与页面测试：验证岗位隔离、服务端403、红绿状态和证据链展示。"""

import json
from pathlib import Path

import pytest

from app import create_app
from dod_gate import APPROVED, REJECTED, REQUIRED_EVIDENCE

# 旧版页面曾使用的占位符，必须不再出现在证据链中。
STALE_PLACEHOLDERS = ("待实际候选提交", "待实际测试结果", "待填写")


@pytest.fixture
def client():
    """使用真实证据文件的应用实例。"""
    return create_app({"TESTING": True}).test_client()


def _complete_evidence(human_review_status=APPROVED):
    """构造六项证据齐全的内存证据集，用于验证绿色与拒绝状态。

    使用内存注入而不是临时文件，既不修改真实证据文件，也不依赖沙箱临时目录。
    """
    evidence = {
        key: {"status": APPROVED, "value": f"{key} 真实证据"} for key in REQUIRED_EVIDENCE
    }
    evidence["human_review"] = {"status": human_review_status, "value": "杨濠宇审查结论"}
    return evidence


def _chain_block(body):
    """截取八段证据链区块，避免状态面板中的同名文字干扰顺序断言。"""
    return body.split('<ol class="chain">', 1)[1]


def test_home_shows_product_scope(client):
    response = client.get("/?role=product")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "U6 用户故事" in body
    # 产品岗位不应看到完整证据链的DRI内容。
    assert "AI功能分支" not in body


@pytest.mark.parametrize("role", ["product", "tech", "ai_record"])
def test_non_quality_roles_cannot_see_full_chain(client, role):
    body = client.get(f"/?role={role}").get_data(as_text=True)
    assert "DoD门禁" not in body
    assert "可以评审" not in body


def test_quality_sees_eight_segment_chain_in_order(client):
    body = client.get("/?role=quality").get_data(as_text=True)
    chain = _chain_block(body)
    order = ["用户故事", "Sprint任务", "AI功能分支", "Git提交", "自动化测试", "人工审查", "DoD门禁", "可以评审"]
    positions = [chain.index(name) for name in order]
    assert positions == sorted(positions)


def test_quality_page_has_no_stale_placeholders(client):
    body = client.get("/?role=quality").get_data(as_text=True)
    for placeholder in STALE_PLACEHOLDERS:
        assert placeholder not in body


def test_quality_page_shows_real_commit_and_test_data():
    """证据链必须读取顶层真实提交与测试结果，而不是写死的旧数组。

    断言直接对照 data/evidence.json 的真实内容，避免把提交号硬编码进测试。
    """
    evidence_path = Path(__file__).resolve().parents[1] / "data" / "evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    body = create_app({"TESTING": True}).test_client().get("/?role=quality").get_data(as_text=True)

    assert evidence["feature_commit"]["value"].split()[0] in body
    assert evidence["tests_passed"]["value"].split("→")[-1].strip() in body


def test_real_candidate_is_red_until_review_approved(client):
    """真实证据中人工审查仍为pending，因此必须是红色未达到DoD。"""
    body = client.get("/?role=quality").get_data(as_text=True)
    assert "未达到DoD" in body
    assert "可以进入Sprint评审" not in body


def test_complete_evidence_turns_green():
    app = create_app({"TESTING": True, "EVIDENCE_DATA": _complete_evidence()})
    body = app.test_client().get("/?role=quality").get_data(as_text=True)
    assert "可以进入Sprint评审" in body
    assert "未达到DoD" not in body


def test_rejected_review_stays_red_even_when_other_evidence_is_approved():
    """人工审查被拒绝时，即使其他证据齐全也必须保持红色。"""
    app = create_app(
        {"TESTING": True, "EVIDENCE_DATA": _complete_evidence(REJECTED)}
    )
    body = app.test_client().get("/?role=quality").get_data(as_text=True)
    assert "未达到DoD" in body
    assert "可以进入Sprint评审" not in body


@pytest.mark.parametrize("role", ["product", "tech", "ai_record"])
def test_non_quality_cannot_open_quality_detail(client, role):
    response = client.get(f"/quality?role={role}")
    assert response.status_code == 403
    assert "403 无权查看" in response.get_data(as_text=True)


def test_quality_can_open_quality_detail(client):
    response = client.get("/quality?role=quality")
    assert response.status_code == 200
    assert "完整证据链" in response.get_data(as_text=True)
