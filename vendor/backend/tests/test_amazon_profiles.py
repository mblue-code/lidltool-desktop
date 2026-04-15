from __future__ import annotations

from pathlib import Path

from lidltool.amazon.profiles import get_country_profile, list_country_profiles
from lidltool.connectors.registry import build_builtin_connector_registry


def test_amazon_country_profiles_are_complete() -> None:
    profiles = list_country_profiles()
    assert {profile.source_id for profile in profiles} == {"amazon_de", "amazon_fr", "amazon_gb"}

    for profile in profiles:
        assert profile.country_code
        assert profile.domain.startswith("amazon.")
        assert profile.currency in {"EUR", "GBP"}
        assert profile.languages
        assert profile.selector_bundle.order_list.order_card_selectors
        assert profile.selector_bundle.detail.shipment_selectors
        assert profile.auth_rules.blocked_url_patterns()
        assert profile.order_history_url().startswith("https://www.")
        assert profile.sign_in_url().endswith("/ap/signin")


def test_amazon_profiles_resolve_by_source_id_and_domain() -> None:
    assert get_country_profile(source_id="amazon_de").domain == "amazon.de"
    assert get_country_profile(source_id="amazon_fr").domain == "amazon.fr"
    assert get_country_profile(source_id="amazon_gb").domain == "amazon.co.uk"
    assert get_country_profile(domain="amazon.fr").source_id == "amazon_fr"
    assert get_country_profile(domain="amazon.co.uk").source_id == "amazon_gb"


def test_amazon_manifests_exist_for_each_profile() -> None:
    registry = build_builtin_connector_registry()
    for profile in list_country_profiles():
        manifest = registry.require_manifest(profile.source_id)
        assert manifest.country_code == profile.country_code
        assert manifest.display_name == "Amazon"
        assert manifest.config_schema is not None
        assert [field.key for field in manifest.config_schema.fields] == [
            "years",
            "headless",
            "dump_html",
        ]
