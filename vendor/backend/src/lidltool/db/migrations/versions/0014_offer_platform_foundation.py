"""add offer platform foundation tables

Revision ID: 0014_offer_platform_foundation
Revises: 0013_connector_payload_quarantine
Create Date: 2026-03-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_offer_platform_foundation"
down_revision = "0013_connector_payload_quarantine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offer_sources",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("plugin_id", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("merchant_name", sa.String(), nullable=False),
        sa.Column("merchant_id", sa.String(), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("region_code", sa.String(), nullable=True),
        sa.Column("store_id", sa.String(), nullable=True),
        sa.Column("store_name", sa.String(), nullable=True),
        sa.Column("scope_key", sa.String(length=255), nullable=False),
        sa.Column("raw_scope_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope_key"),
    )
    op.create_index(op.f("ix_offer_sources_country_code"), "offer_sources", ["country_code"], unique=False)
    op.create_index(op.f("ix_offer_sources_plugin_id"), "offer_sources", ["plugin_id"], unique=False)
    op.create_index(op.f("ix_offer_sources_region_code"), "offer_sources", ["region_code"], unique=False)
    op.create_index(op.f("ix_offer_sources_scope_key"), "offer_sources", ["scope_key"], unique=False)
    op.create_index(op.f("ix_offer_sources_source_id"), "offer_sources", ["source_id"], unique=False)
    op.create_index(op.f("ix_offer_sources_store_id"), "offer_sources", ["store_id"], unique=False)

    op.create_table(
        "offers",
        sa.Column("offer_id", sa.String(), nullable=False),
        sa.Column("offer_source_id", sa.String(), nullable=False),
        sa.Column("plugin_id", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("source_offer_id", sa.String(), nullable=False),
        sa.Column("fingerprint", sa.String(length=128), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("offer_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=True),
        sa.Column("original_price_cents", sa.Integer(), nullable=True),
        sa.Column("discount_percent", sa.Float(), nullable=True),
        sa.Column("bundle_terms", sa.Text(), nullable=True),
        sa.Column("offer_url", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("validity_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("validity_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("normalized_payload", sa.JSON(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["offer_source_id"], ["offer_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("offer_id"),
        sa.UniqueConstraint("fingerprint"),
    )
    op.create_index(op.f("ix_offers_fingerprint"), "offers", ["fingerprint"], unique=False)
    op.create_index(op.f("ix_offers_offer_source_id"), "offers", ["offer_source_id"], unique=False)
    op.create_index(op.f("ix_offers_plugin_id"), "offers", ["plugin_id"], unique=False)
    op.create_index(op.f("ix_offers_source_id"), "offers", ["source_id"], unique=False)
    op.create_index(op.f("ix_offers_source_offer_id"), "offers", ["source_offer_id"], unique=False)
    op.create_index(op.f("ix_offers_status"), "offers", ["status"], unique=False)
    op.create_index(op.f("ix_offers_validity_end"), "offers", ["validity_end"], unique=False)
    op.create_index(op.f("ix_offers_validity_start"), "offers", ["validity_start"], unique=False)

    op.create_table(
        "offer_items",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("offer_id", sa.String(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("source_item_id", sa.String(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("brand", sa.String(), nullable=True),
        sa.Column("canonical_product_id", sa.String(), nullable=True),
        sa.Column("gtin_ean", sa.String(), nullable=True),
        sa.Column("alias_candidates", sa.JSON(), nullable=False),
        sa.Column("quantity_text", sa.String(), nullable=True),
        sa.Column("unit", sa.String(), nullable=True),
        sa.Column("size_text", sa.String(), nullable=True),
        sa.Column("price_cents", sa.Integer(), nullable=True),
        sa.Column("original_price_cents", sa.Integer(), nullable=True),
        sa.Column("discount_percent", sa.Float(), nullable=True),
        sa.Column("bundle_terms", sa.Text(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["canonical_product_id"], ["products.product_id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.offer_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_offer_items_canonical_product_id"), "offer_items", ["canonical_product_id"], unique=False)
    op.create_index(op.f("ix_offer_items_gtin_ean"), "offer_items", ["gtin_ean"], unique=False)
    op.create_index(op.f("ix_offer_items_offer_id"), "offer_items", ["offer_id"], unique=False)
    op.create_index("ux_offer_items_offer_line", "offer_items", ["offer_id", "line_no"], unique=True)

    op.create_table(
        "product_watchlists",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), nullable=True),
        sa.Column("query_text", sa.Text(), nullable=True),
        sa.Column("source_id", sa.String(), nullable=True),
        sa.Column("min_discount_percent", sa.Float(), nullable=True),
        sa.Column("max_price_cents", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.product_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_product_watchlists_active"), "product_watchlists", ["active"], unique=False)
    op.create_index(op.f("ix_product_watchlists_product_id"), "product_watchlists", ["product_id"], unique=False)
    op.create_index(op.f("ix_product_watchlists_source_id"), "product_watchlists", ["source_id"], unique=False)
    op.create_index(op.f("ix_product_watchlists_user_id"), "product_watchlists", ["user_id"], unique=False)

    op.create_table(
        "offer_matches",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("match_key", sa.String(length=255), nullable=False),
        sa.Column("offer_id", sa.String(), nullable=False),
        sa.Column("offer_item_id", sa.String(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("watchlist_id", sa.String(), nullable=True),
        sa.Column("matched_product_id", sa.String(), nullable=True),
        sa.Column("match_kind", sa.String(), nullable=False),
        sa.Column("match_method", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("reason_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["matched_product_id"], ["products.product_id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["offers.offer_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["offer_item_id"], ["offer_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.ForeignKeyConstraint(["watchlist_id"], ["product_watchlists.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("match_key"),
    )
    op.create_index(op.f("ix_offer_matches_match_key"), "offer_matches", ["match_key"], unique=False)
    op.create_index(op.f("ix_offer_matches_match_kind"), "offer_matches", ["match_kind"], unique=False)
    op.create_index(op.f("ix_offer_matches_matched_product_id"), "offer_matches", ["matched_product_id"], unique=False)
    op.create_index(op.f("ix_offer_matches_offer_id"), "offer_matches", ["offer_id"], unique=False)
    op.create_index(op.f("ix_offer_matches_offer_item_id"), "offer_matches", ["offer_item_id"], unique=False)
    op.create_index(op.f("ix_offer_matches_status"), "offer_matches", ["status"], unique=False)
    op.create_index(op.f("ix_offer_matches_user_id"), "offer_matches", ["user_id"], unique=False)
    op.create_index(op.f("ix_offer_matches_watchlist_id"), "offer_matches", ["watchlist_id"], unique=False)

    op.create_table(
        "alert_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("offer_match_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["offer_match_id"], ["offer_matches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index(op.f("ix_alert_events_dedupe_key"), "alert_events", ["dedupe_key"], unique=False)
    op.create_index(op.f("ix_alert_events_event_type"), "alert_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_alert_events_offer_match_id"), "alert_events", ["offer_match_id"], unique=False)
    op.create_index(op.f("ix_alert_events_status"), "alert_events", ["status"], unique=False)
    op.create_index(op.f("ix_alert_events_user_id"), "alert_events", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_alert_events_user_id"), table_name="alert_events")
    op.drop_index(op.f("ix_alert_events_status"), table_name="alert_events")
    op.drop_index(op.f("ix_alert_events_offer_match_id"), table_name="alert_events")
    op.drop_index(op.f("ix_alert_events_event_type"), table_name="alert_events")
    op.drop_index(op.f("ix_alert_events_dedupe_key"), table_name="alert_events")
    op.drop_table("alert_events")

    op.drop_index(op.f("ix_offer_matches_watchlist_id"), table_name="offer_matches")
    op.drop_index(op.f("ix_offer_matches_user_id"), table_name="offer_matches")
    op.drop_index(op.f("ix_offer_matches_status"), table_name="offer_matches")
    op.drop_index(op.f("ix_offer_matches_offer_item_id"), table_name="offer_matches")
    op.drop_index(op.f("ix_offer_matches_offer_id"), table_name="offer_matches")
    op.drop_index(op.f("ix_offer_matches_matched_product_id"), table_name="offer_matches")
    op.drop_index(op.f("ix_offer_matches_match_kind"), table_name="offer_matches")
    op.drop_index(op.f("ix_offer_matches_match_key"), table_name="offer_matches")
    op.drop_table("offer_matches")

    op.drop_index(op.f("ix_product_watchlists_user_id"), table_name="product_watchlists")
    op.drop_index(op.f("ix_product_watchlists_source_id"), table_name="product_watchlists")
    op.drop_index(op.f("ix_product_watchlists_product_id"), table_name="product_watchlists")
    op.drop_index(op.f("ix_product_watchlists_active"), table_name="product_watchlists")
    op.drop_table("product_watchlists")

    op.drop_index("ux_offer_items_offer_line", table_name="offer_items")
    op.drop_index(op.f("ix_offer_items_offer_id"), table_name="offer_items")
    op.drop_index(op.f("ix_offer_items_gtin_ean"), table_name="offer_items")
    op.drop_index(op.f("ix_offer_items_canonical_product_id"), table_name="offer_items")
    op.drop_table("offer_items")

    op.drop_index(op.f("ix_offers_validity_start"), table_name="offers")
    op.drop_index(op.f("ix_offers_validity_end"), table_name="offers")
    op.drop_index(op.f("ix_offers_status"), table_name="offers")
    op.drop_index(op.f("ix_offers_source_offer_id"), table_name="offers")
    op.drop_index(op.f("ix_offers_source_id"), table_name="offers")
    op.drop_index(op.f("ix_offers_plugin_id"), table_name="offers")
    op.drop_index(op.f("ix_offers_offer_source_id"), table_name="offers")
    op.drop_index(op.f("ix_offers_fingerprint"), table_name="offers")
    op.drop_table("offers")

    op.drop_index(op.f("ix_offer_sources_store_id"), table_name="offer_sources")
    op.drop_index(op.f("ix_offer_sources_source_id"), table_name="offer_sources")
    op.drop_index(op.f("ix_offer_sources_scope_key"), table_name="offer_sources")
    op.drop_index(op.f("ix_offer_sources_region_code"), table_name="offer_sources")
    op.drop_index(op.f("ix_offer_sources_plugin_id"), table_name="offer_sources")
    op.drop_index(op.f("ix_offer_sources_country_code"), table_name="offer_sources")
    op.drop_table("offer_sources")
