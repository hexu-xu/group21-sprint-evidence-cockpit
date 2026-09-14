import pytest
from dod_gate import REQUIRED_EVIDENCE, evaluate_dod


@pytest.fixture
def complete_evidence():
    return {key: "real evidence" for key in REQUIRED_EVIDENCE}


def test_complete_evidence_is_reviewable(complete_evidence):
    result = evaluate_dod(complete_evidence)
    assert result["passed"] is True
    assert result["label"] == "可以进入Sprint评审"


@pytest.mark.parametrize("missing", REQUIRED_EVIDENCE)
def test_any_missing_evidence_blocks_review(complete_evidence, missing):
    complete_evidence[missing] = ""
    result = evaluate_dod(complete_evidence)
    assert result["passed"] is False
    assert missing in result["missing"]
    assert result["label"] == "未达到DoD"
