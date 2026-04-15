from __future__ import annotations

from sqlalchemy.orm import Session

from lidltool.analytics.item_categorizer import (
    _contains_any_hint,
    categorize_transaction_item,
)
from lidltool.analytics.normalization import load_normalization_bundle
from lidltool.db.engine import create_engine_for_url, init_db, session_factory, session_scope
from lidltool.db.models import Source


def test_contains_any_hint_uses_token_boundaries_not_raw_substrings() -> None:
    assert _contains_any_hint(["aluminium_platte"], ["latte"]) is False
    assert _contains_any_hint(["caffe_latte"], ["latte"]) is True


def test_amazon_items_fall_back_to_other_without_source_native_signal(tmp_path) -> None:
    db_file = tmp_path / "categorizer.sqlite"
    engine = create_engine_for_url(f"sqlite:///{db_file}")
    init_db(engine)
    sessions = session_factory(engine)

    with session_scope(sessions) as session:
        source = Source(id="amazon_de", kind="connector", display_name="Amazon")
        session.add(source)
        session.flush()
        bundle = load_normalization_bundle(session, source=source.id)
        result = categorize_transaction_item(
            session=session,
            source=source,
            item_name=(
                "ZOFUN 2 Stück Aluminium-Metall Aluminiumplatten schwarz, 300 x 300 MM "
                "Alublech 1mm Aluminiumblech 1mm aus 5052-Aluminium"
            ),
            current_category=None,
            product_id=None,
            raw_payload={},
            normalization_bundle=bundle,
            use_model=False,
            model_client=None,
            rules=(),
        )

    assert result.category_name == "other"
    assert result.method == "fallback_other"
