REQUIRED_EVIDENCE = (
    "story_confirmed",
    "task_claimed",
    "ai_branch",
    "feature_commit",
    "tests_passed",
    "human_review",
)


def _is_real(value):
    if not value or not isinstance(value, str):
        return False
    return not value.startswith("待")


def evaluate_dod(evidence):
    checks = {key: _is_real(evidence.get(key)) for key in REQUIRED_EVIDENCE}
    passed = all(checks.values())
    return {
        "checks": checks,
        "passed": passed,
        "label": "可以进入Sprint评审" if passed else "未达到DoD",
        "message": "证据链完整，已达到DoD。" if passed else "证据不全，暂不能进入Sprint评审。",
        "missing": [key for key, value in checks.items() if not value],
    }
