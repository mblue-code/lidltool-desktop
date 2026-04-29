from lidltool.analytics.item_categorizer import (
    _BAKERY_HINTS,
    _contains_any_hint,
    _normalize_category_key,
)


def test_bakery_hint_does_not_match_brother_brand() -> None:
    value = _normalize_category_key(
        "Brother PT-D210 Beschriftungsgerät, QWERTZ Tastaturlayout"
    )

    assert not _contains_any_hint([value], _BAKERY_HINTS)


def test_bakery_hint_still_matches_compound_bread_terms() -> None:
    value = _normalize_category_key("Bio Bauernbrot geschnitten")

    assert _contains_any_hint([value], _BAKERY_HINTS)
