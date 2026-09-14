from permissions import can_view_quality, normalize_role


def test_only_quality_can_view_full_detail():
    assert can_view_quality("quality")
    for role in ("product", "tech", "ai_record"):
        assert not can_view_quality(role)


def test_unknown_role_falls_back_to_product():
    assert normalize_role("unknown") == "product"
