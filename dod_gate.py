"""DoD门禁：根据证据的真实状态，判断交付内容能否进入评审。

设计原则：
1. 证据状态统一为三态：approved（已通过）/ rejected（被拒绝或失败）/ pending（待补证）。
2. 只有6项必要证据全部为 approved 时，整体才是 approved，才允许显示绿色。
3. rejected 与 pending 都属于“未达到DoD”，其中 rejected 表示已明确失败或被退回，
   绝不能因为其他证据齐全而被放过。
4. 未识别状态与无效提交证据均按待补证处理；本模块不修改证据文件。
"""

import re

# 三态常量：全项目统一使用这三个值，避免出现“绿色写死”或字符串误判。
APPROVED = "approved"
REJECTED = "rejected"
PENDING = "pending"

# 必要证据键，顺序与证据链展示顺序一致。
REQUIRED_EVIDENCE = (
    "story_confirmed",
    "task_claimed",
    "ai_branch",
    "feature_commit",
    "tests_passed",
    "human_review",
)

# 证据键到中文展示名的映射，页面和审查报告共用，保证名称一致。
EVIDENCE_LABELS = {
    "story_confirmed": "用户故事",
    "task_claimed": "开发任务",
    "ai_branch": "AI功能分支",
    "feature_commit": "Git提交",
    "tests_passed": "自动化测试",
    "human_review": "人工审查",
}

# 允许的文本别名，兼容中文结论和布尔以外的历史写法。
_APPROVED_ALIASES = {
    "approved", "approve", "pass", "passed", "ok", "true", "通过", "已通过", "允许合并",
}
_REJECTED_ALIASES = {
    "rejected", "reject", "fail", "failed", "false", "拒绝", "不通过", "未通过", "退回", "退回修复",
}
_PENDING_ALIASES = {
    "pending", "todo", "待定", "待审查", "待复审", "待确认", "待补证", "进行中",
}

_COMMIT_REFERENCE = re.compile(r"([0-9a-fA-F]{7,40})(?:\s+.+)?\Z")
_PASSED_TEST_OUTPUT = re.compile(r"\d+ passed in \d+(?:\.\d+)?s\Z", re.IGNORECASE)

# 三态对应的页面状态样式，避免模板里再做条件判断。
_STATUS_CLASSES = {APPROVED: "pass", REJECTED: "fail", PENDING: "pending"}
_STATUS_LABELS = {APPROVED: "已通过", REJECTED: "已拒绝", PENDING: "待补证"}


def _valid_commit_reference(value):
    """提交证据需以 7～40 位十六进制哈希开头，可带提交说明。"""
    if not isinstance(value, str):
        return False
    match = _COMMIT_REFERENCE.fullmatch(value.strip())
    return bool(match and len(set(match.group(1).lower())) > 1)


def _status_label(value):
    """只接受明确列出的状态值，未知值一律保持待补证。"""
    if value is True:
        return APPROVED
    if value is False or value is None:
        return PENDING
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return PENDING
        if text in _APPROVED_ALIASES:
            return APPROVED
        if text in _REJECTED_ALIASES:
            return REJECTED
        if text in _PENDING_ALIASES or value.strip().startswith("待"):
            return PENDING
        return PENDING
    return PENDING


def normalize_status(value):
    """把状态或兼容的原始证据值归一化为三态。

    字典中的 status 必须是明确状态，不能把任意非空文本当成通过。
    旧格式的裸提交哈希与 pytest 成功摘要仍可作为原始证据。
    """
    if isinstance(value, dict):
        return _status_label(value.get("status"))
    status = _status_label(value)
    if status != PENDING:
        return status
    if isinstance(value, str):
        text = value.strip()
        if _valid_commit_reference(text) or _PASSED_TEST_OUTPUT.fullmatch(text):
            return APPROVED
    return PENDING


def evidence_value(evidence, key):
    """取出证据的展示文本：字典取 value，布尔转中文，缺省显示“未提供”。"""
    raw = evidence.get(key)
    if isinstance(raw, dict):
        return str(raw.get("value") or "未提供")
    if raw is True:
        return "已完成"
    if raw is False or raw is None:
        return "未提供"
    return str(raw)


def evaluate_dod(evidence):
    """计算整体DoD结论。

    返回结构包含三态结果、逐项检查、缺口清单和页面文案。
    只要出现 rejected 或 pending，``passed`` 必须为 False。
    """
    statuses = {key: normalize_status(evidence.get(key)) for key in REQUIRED_EVIDENCE}
    commit = evidence.get("feature_commit")
    commit_value = commit.get("value") if isinstance(commit, dict) else commit
    if statuses["feature_commit"] == APPROVED and not _valid_commit_reference(commit_value):
        statuses["feature_commit"] = PENDING
    rejected = [key for key, status in statuses.items() if status == REJECTED]
    pending = [key for key, status in statuses.items() if status == PENDING]
    passed = not rejected and not pending and all(
        status == APPROVED for status in statuses.values()
    )

    if rejected:
        overall, message = REJECTED, "存在被拒绝或失败证据，已退回修复，不能进入交付评审。"
    elif pending:
        overall, message = PENDING, "证据不全，暂不能进入交付评审。"
    else:
        overall, message = APPROVED, "证据链完整，已达到DoD。"

    return {
        "status": overall,
        "passed": passed,
        "checks": {key: status == APPROVED for key, status in statuses.items()},
        "statuses": statuses,
        "missing": rejected + pending,
        "rejected": rejected,
        "pending": pending,
        "label": "可以进入交付评审" if passed else "未达到DoD",
        "message": message,
    }


def build_evidence_chain(evidence, dod):
    """按八段顺序构建证据链，直接读取顶层真实证据数据。

    前6段读取证据文件顶层的必要证据键（故事、任务、分支、提交、测试、审查），
    后2段是DoD门禁结论和是否可以进入评审，均由 ``evaluate_dod`` 的结果生成，
    不再使用任何写死的占位数组。
    """
    chain = []
    for key in REQUIRED_EVIDENCE:
        status = dod["statuses"][key]
        chain.append(
            {
                "name": EVIDENCE_LABELS[key],
                "value": evidence_value(evidence, key),
                "status": status,
                "status_label": _STATUS_LABELS[status],
            }
        )

    # 第七段：DoD门禁本身的状态。
    chain.append(
        {
            "name": "DoD门禁",
            "value": dod["label"],
            "status": dod["status"],
            "status_label": _STATUS_LABELS[dod["status"]],
        }
    )
    # 第八段：是否可以进入评审，由门禁结论决定，不单独写死。
    chain.append(
        {
            "name": "可以评审",
            "value": dod["message"],
            "status": dod["status"],
            "status_label": _STATUS_LABELS[dod["status"]],
        }
    )

    # 为模板附加样式类名，避免在HTML里堆叠条件判断。
    for item in chain:
        item["css_class"] = _STATUS_CLASSES[item["status"]]
    return chain
