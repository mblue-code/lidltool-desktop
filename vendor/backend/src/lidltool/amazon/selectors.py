from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AmazonOrderListSelectors:
    order_card_selectors: tuple[str, ...]
    fallback_container_selectors: tuple[str, ...]
    detail_link_selectors: tuple[str, ...]
    product_link_selectors: tuple[str, ...]
    product_title_selectors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AmazonDetailSelectors:
    shipment_selectors: tuple[str, ...]
    fallback_shipment_selectors: tuple[str, ...]
    item_row_selectors: tuple[str, ...]
    title_link_selectors: tuple[str, ...]
    title_fallback_selectors: tuple[str, ...]
    price_selectors: tuple[str, ...]
    seller_selectors: tuple[str, ...]
    subtotal_container_selectors: tuple[str, ...]
    subtotal_row_selectors: tuple[str, ...]
    subtotal_amount_selectors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AmazonPaginationSelectors:
    next_page_selectors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AmazonAuthSelectors:
    sign_in_markers: tuple[str, ...]
    mfa_markers: tuple[str, ...]
    captcha_markers: tuple[str, ...]
    claim_markers: tuple[str, ...]
    intent_markers: tuple[str, ...]
    bot_challenge_markers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AmazonSelectorBundle:
    order_list: AmazonOrderListSelectors
    detail: AmazonDetailSelectors
    pagination: AmazonPaginationSelectors
    auth: AmazonAuthSelectors


DEFAULT_AMAZON_SELECTOR_BUNDLE = AmazonSelectorBundle(
    order_list=AmazonOrderListSelectors(
        order_card_selectors=(
            ".order-card",
            ".order",
            "[data-component='orderCard']",
            ".a-box-group.order",
            ".your-orders-content-container .a-box-group",
            "#ordersContainer .order-card",
            ".js-order-card",
            "[class*='order-card']",
        ),
        fallback_container_selectors=(".a-box", ".a-box-group", "div"),
        detail_link_selectors=(
            "a[href*='order-details']",
            "a[href*='orderID=']",
            "a[href*='orderId=']",
        ),
        product_link_selectors=("a[href*='/dp/']", "a[href*='/gp/product/']"),
        product_title_selectors=(".a-link-normal", ".a-text-bold", ".yohtmlc-product-title"),
    ),
    detail=AmazonDetailSelectors(
        shipment_selectors=(
            ".a-box.shipment",
            "[data-component='shipmentCard']",
            ".shipment",
            ".od-shipment",
        ),
        fallback_shipment_selectors=(".a-box-group",),
        item_row_selectors=(
            ".a-fixed-left-grid-inner",
            ".a-row.item-row",
            ".yohtmlc-item",
            "[class*='item']",
        ),
        title_link_selectors=("a[href*='/dp/']", "a[href*='/gp/product/']"),
        title_fallback_selectors=(".a-link-normal", ".a-text-bold", ".yohtmlc-product-title"),
        price_selectors=(".a-color-price", ".a-price .a-offscreen", "[class*='price']"),
        seller_selectors=("[class*='seller']", ".a-size-small"),
        subtotal_container_selectors=(
            "#subtotals-marketplace-table",
            ".a-spacing-mini.a-spacing-top-mini",
        ),
        subtotal_row_selectors=("tr", ".a-row"),
        subtotal_amount_selectors=(".a-color-price", ".a-text-right", "td:last-child"),
    ),
    pagination=AmazonPaginationSelectors(
        next_page_selectors=(
            ".a-pagination .a-last:not(.a-disabled) a",
            "a[aria-label*='Nächste']",
            "a[aria-label*='Next']",
            "a[aria-label*='Suivant']",
            ".a-pagination li:last-child:not(.a-disabled) a",
            "a.a-last:not(.a-disabled)",
        )
    ),
    auth=AmazonAuthSelectors(
        sign_in_markers=(
            'name="signIn"',
            'id="auth-email"',
            'id="ap_email"',
            'id="auth-password"',
            'id="ap_password"',
            'id="auth-supertask-header"',
        ),
        mfa_markers=(
            'name="cvf_captcha_input"',
            'name="code"',
            'name="otpCode"',
            'id="auth-mfa-form"',
            'id="cvf-page-content"',
        ),
        captcha_markers=(
            'id="captchacharacters"',
            'name="cvf_captcha_input"',
            'id="auth-captcha-image"',
            'id="captcha-container"',
        ),
        claim_markers=('id="claimspicker"', 'name="claimCode"', 'data-a-input-name="claimCode"'),
        intent_markers=('name="openid.return_to"', 'id="a-page"', 'data-action="a-popover"'),
        bot_challenge_markers=(
            "automated access",
            "robot check",
            "sorry, we just need to make sure you're not a robot",
            "enable javascript to continue",
        ),
    ),
)
