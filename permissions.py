ROLE_CONTENT = {
    "product": {
        "label": "产品与范围",
        "title": "U6 用户故事",
        "items": ["U6：团队成员只能看到自己有权限的项目内容", "价值：减少无关信息干扰", "验收：岗位内容隔离，DRI可查看完整证据链"],
    },
    "tech": {
        "label": "技术与架构",
        "title": "Sprint开发任务",
        "items": ["实现岗位内容隔离", "功能分支：feat/sprint-evidence-cockpit", "运行：按README安装、启动并执行pytest"],
    },
    "quality": {"label": "质量与风险（DRI）", "title": "完整证据链", "items": []},
    "ai_record": {
        "label": "AI协调与记录",
        "title": "AI互动记录",
        "items": ["AI角色：编码、测试、审查", "提示词与输出摘要：由团队原始记录提供", "证据缺口：首次开发记录待张生达登记"],
    },
}


def normalize_role(role):
    return role if role in ROLE_CONTENT else "product"


def can_view_quality(role):
    return normalize_role(role) == "quality"
