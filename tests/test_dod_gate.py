"""DoD门禁单元测试：覆盖三态语义、拒绝项拦截和缺失组合。"""

import pytest

from dod_gate import (
    APPROVED,
    PENDING,
    REJECTED,
    REQUIRED_EVIDENCE,
    build_evidence_chain,
    evaluate_dod,
    normalize_status,
)


@pytest.fixture
def approved_evidence():
    """六项必要证据全部为approved的最小证据集。"""
    return {key: {"status": APPROVED, "value": f"{key} 真实证据"} for key in REQUIRED_EVIDENCE}


def test_complete_approved_evidence_is_reviewable(approved_evidence):
    result = evaluate_dod(approved_evidence)
    assert result["passed"] is True
    assert result["status"] == APPROVED
    assert result["label"] == "可以进入Sprint评审"


@pytest.mark.parametrize("missing", REQUIRED_EVIDENCE)
def test_any_pending_evidence_blocks_review(approved_evidence, missing):
    """任意一项待补证，都不能显示可以评审。"""
    approved_evidence[missing] = {"status": PENDING, "value": "待补充"}
    result = evaluate_dod(approved_evidence)
    assert result["passed"] is False
    assert result["status"] == PENDING
    assert missing in result["missing"]
    assert result["label"] == "未达到DoD"


@pytest.mark.parametrize("missing", REQUIRED_EVIDENCE)
def test_rejected_evidence_never_passes(approved_evidence, missing):
    """被拒绝或被退回的证据，即使其他证据齐全也绝不能通过。"""
    approved_evidence[missing] = {"status": REJECTED, "value": "审查退回修复"}
    result = evaluate_dod(approved_evidence)
    assert result["passed"] is False
    assert result["status"] == REJECTED
    assert missing in result["rejected"]
    assert result["label"] == "未达到DoD"
    assert "退回修复" in result["message"]


def test_boolean_false_cannot_pass(approved_evidence):
    """布尔False表示尚未完成，不能当作通过。"""
    approved_evidence["tests_passed"] = False
    result = evaluate_dod(approved_evidence)
    assert result["passed"] is False
    assert result["statuses"]["tests_passed"] == PENDING


def test_boolean_true_counts_as_approved():
    result = evaluate_dod({key: True for key in REQUIRED_EVIDENCE})
    assert result["passed"] is True


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, APPROVED),
        (False, PENDING),
        (None, PENDING),
        ("", PENDING),
        ("approved", APPROVED),
        ("已通过", APPROVED),
        ("rejected", REJECTED),
        ("退回修复", REJECTED),
        ("不通过", REJECTED),
        ("pending", PENDING),
        ("待杨濠宇复审", PENDING),
        ("c7e0fb1", APPROVED),
        ("15 passed in 0.19s", APPROVED),
        ({"status": "rejected", "value": "退回"}, REJECTED),
    ],
)
def test_normalize_status_three_state(value, expected):
    assert normalize_status(value) == expected


def test_chain_reads_top_level_evidence_and_has_eight_segments(approved_evidence):
    """证据链必须直接读取顶层证据，并且固定为八段。"""
    approved_evidence["human_review"] = {"status": PENDING, "value": "待杨濠宇复审"}
    dod = evaluate_dod(approved_evidence)
    chain = build_evidence_chain(approved_evidence, dod)

    assert len(chain) == 8
    assert [item["name"] for item in chain] == [
        "用户故事",
        "Sprint任务",
        "AI功能分支",
        "Git提交",
        "自动化测试",
        "人工审查",
        "DoD门禁",
        "可以评审",
    ]
    assert chain[5]["value"] == "待杨濠宇复审"
    assert chain[5]["css_class"] == "pending"
    assert chain[7]["value"] == dod["message"]


def test_chain_uses_real_commit_and_test_text():
    """Git提交与自动化测试两段应展示证据文件中的真实文本。"""
    evidence = {key: {"status": APPROVED, "value": "x"} for key in REQUIRED_EVIDENCE}
    evidence["feature_commit"] = {"status": APPROVED, "value": "c7e0fb1 feat: add role-gated evidence cockpit"}
    evidence["tests_passed"] = {"status": APPROVED, "value": "15 passed in 0.19s"}
    chain = build_evidence_chain(evidence, evaluate_dod(evidence))

    assert chain[3]["value"] == "c7e0fb1 feat: add role-gated evidence cockpit"
    assert chain[4]["value"] == "15 passed in 0.19s"
