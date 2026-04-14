from lidltool.analytics.normalization import canonicalize_category_name


def test_canonicalize_desktop_subcategories() -> None:
    assert canonicalize_category_name("Kosmetik") == "personal_care:cosmetics"
    assert canonicalize_category_name("baby stuff") == "personal_care:baby"
    assert canonicalize_category_name("Toilettenpapier") == "household:paper_goods"
    assert canonicalize_category_name("Reinigung") == "household:cleaning"
    assert canonicalize_category_name("Restaurant") == "dining:restaurant"
    assert canonicalize_category_name("Apotheke") == "health:pharmacy"
    assert canonicalize_category_name("Elektronik") == "shopping:electronics"
    assert canonicalize_category_name("Versandkosten") == "fees:shipping"
