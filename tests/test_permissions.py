"""岗位权限单元测试：确认只有quality可以查看完整质量详情。"""

import pytest

from permissions import ROLE_CONTENT, can_view_quality, normalize_role


def test_only_quality_can_view_full_detail():
    assert can_view_quality("quality")
    for role in ("product", "tech", "ai_record"):
        assert not can_view_quality(role)


@pytest.mark.parametrize("role", sorted(ROLE_CONTENT))
def test_every_known_role_has_label_and_title(role):
    """四个岗位都必须有展示名和标题，避免页面出现空岗位。"""
    content = ROLE_CONTENT[role]
    assert content["label"]
    assert content["title"]


def test_unknown_role_falls_back_to_product():
    """未知岗位参数不得导致越权，统一回落到product。"""
    assert normalize_role("unknown") == "product"
    assert can_view_quality("unknown") is False
