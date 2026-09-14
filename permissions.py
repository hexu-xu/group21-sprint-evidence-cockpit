"""岗位定义与服务端权限判断。

四个岗位键固定为 product / tech / quality / ai_record，
每个岗位只返回自己职责范围内的内容，quality（本轮DRI）额外可看完整证据链。
"""

# 岗位键 -> 展示名/标题/职责内容。quality 的条目为空，因为它的内容由证据链动态生成。
ROLE_CONTENT = {
    "product": {
        "label": "产品与范围",
        "title": "U6 用户故事",
        "items": [
            "U6：团队成员只能看到自己有权限的项目内容",
            "价值：减少无关信息干扰",
            "验收：岗位内容隔离，DRI可查看完整证据链",
        ],
    },
    "tech": {
        "label": "技术与架构",
        "title": "Sprint开发任务",
        "items": [
            "实现岗位内容隔离",
            "功能分支：feat/sprint-evidence-cockpit",
            "运行：按README安装、启动并执行pytest",
        ],
    },
    "quality": {"label": "质量与风险（DRI）", "title": "完整证据链", "items": []},
    "ai_record": {
        "label": "AI协调与记录",
        "title": "AI互动记录",
        "items": [
            "AI角色：编码、测试、审查",
            "提示词与输出摘要：由团队原始记录提供",
            "证据缺口：由人工审查状态动态反映",
        ],
    },
}


def normalize_role(role):
    """把未知岗位归一到product，避免未知参数导致越权或报错。"""
    return role if role in ROLE_CONTENT else "product"


def can_view_quality(role):
    """只有quality岗位可以查看完整质量详情；其余岗位一律返回False。"""
    return normalize_role(role) == "quality"
