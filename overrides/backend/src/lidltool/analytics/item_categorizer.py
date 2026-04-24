from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from ipaddress import ip_address
from urllib.parse import urlparse
from typing import Protocol, runtime_checkable

from sqlalchemy import select
from sqlalchemy.orm import Session

from lidltool.ai.codex_oauth import complete_text_with_codex_oauth
from lidltool.ai.item_categorizer import (
    ItemCategorizerSettings,
    resolve_item_categorizer_settings,
)
from lidltool.ai.config import get_ai_oauth_access_token
from lidltool.ai.runtime import (
    JsonCompletionRequest as SharedJsonCompletionRequest,
    ModelRuntime as SharedModelRuntime,
    RuntimeProviderKind,
    RuntimeTask as SharedRuntimeTask,
    is_local_endpoint as shared_is_local_endpoint,
    resolve_runtime as resolve_shared_runtime,
    validate_runtime_endpoint,
)
from lidltool.ai.runtime import RuntimeHealth as SharedRuntimeHealth
from lidltool.ai.runtime import RuntimePolicyMode as SharedRuntimePolicy
from lidltool.analytics.categorization import CompiledRule, find_category_rule
from lidltool.analytics.normalization import (
    CategoryNormalizationMatch,
    NormalizationBundle,
    find_category_name_normalization,
    find_category_value_normalization,
)
from lidltool.config import AppConfig
from lidltool.db.models import Category, Product, Source, TransactionItem

LOGGER = logging.getLogger(__name__)

ITEM_CATEGORIZATION_VERSION = "canonical-item-categorizer-v1"
_DEPOSIT_RE = re.compile(
    r"\b(pfand|pfandr[ue]ckgabe|deposit|bottle\s+deposit|einwegpfand|mehrwegpfand)\b",
    re.IGNORECASE,
)
_SHIPPING_RE = re.compile(
    r"\b(shipping|delivery|versand|versandkosten|lieferung|porto|postage)\b",
    re.IGNORECASE,
)
_PRODUCE_RE = re.compile(
    r"\b("
    r"apfel|aepfel|äpfel|banan(?:e|en)?|birn(?:e|en)?|erdbeer(?:e|en)?|"
    r"gurk(?:e|en)?|karott(?:e|en)?|kartoffel(?:n)?|kiwi|mango|"
    r"mel[ae]|obst|orange(?:n)?|paprika|pfirsich(?:e)?|"
    r"prugn[ae]|(?:eisberg|kopf|romana)?salat|tomat(?:e|en)?|trauben|zitrone(?:n)?|"
    r"zucchin[aei]?"
    r")\b",
    re.IGNORECASE,
)
_BEVERAGES_RE = re.compile(
    r"\b("
    r"cola|limo|limonade|saft|juice|wasser|sprudel|soda|tee|tea|"
    r"kaffee|coffee|energy|bier|beer|wein|wine|getraenk|getränk|drink"
    r")\b",
    re.IGNORECASE,
)
_DAIRY_RE = re.compile(
    r"\b("
    r"skyr|joghurt|jogurt|yoghurt|yogurt|quark|milch|"
    r"kaese|käse|cheese|butter|sahne|kefir|ayran"
    r")\b",
    re.IGNORECASE,
)
_PANTRY_RE = re.compile(
    r"\b("
    r"fusilli|spaghetti|penne|rigatoni|maccheroni|pasta|nudel|reis|rice|"
    r"ketchup|sauce|senf|mustard|mayo|mayonnaise|honig|honey|"
    r"oel|öl|oil|essig|vinegar|mehl|flour|zucker|sugar|salz|"
    r"gewuerz|gewürz|muesli|müsli|hafer"
    r")\b",
    re.IGNORECASE,
)
_BAKERY_RE = re.compile(
    r"\b("
    r"brot|br[öo]tchen|toast|baguette|croissant|brezel|stange|kuchen"
    r")\b",
    re.IGNORECASE,
)
_SNACKS_RE = re.compile(
    r"\b("
    r"chips|cracker|cookie|keks|kekse|schoko|schokolade|bonbon|candy|riegel"
    r")\b",
    re.IGNORECASE,
)
_FROZEN_RE = re.compile(
    r"\b("
    r"tiefk[üu]hl|tk\b|eiscreme|ice\s*cream|frozen"
    r")\b",
    re.IGNORECASE,
)
_HOUSEHOLD_RE = re.compile(
    r"\b("
    r"spuel|spül|reiniger|putz|waschmittel|m[üu]llbeutel|toilettenpapier|küchenrolle|kuechenrolle"
    r")\b",
    re.IGNORECASE,
)
_PERSONAL_CARE_RE = re.compile(
    r"\b("
    r"shampoo|sp[üu]lung|seife|zahnpasta|deo|duschgel|rasierer|lotion|creme"
    r")\b",
    re.IGNORECASE,
)
_MEAT_RE = re.compile(
    r"\b("
    r"fleisch|wurst|schinken|salami|h[aä]hnchen|chicken|rind|beef|hack"
    r")\b",
    re.IGNORECASE,
)
_FISH_RE = re.compile(
    r"\b("
    r"fisch|lachs|thunfisch|tunfisch|garnelen|garnele|shrimp|shrimps|kabeljau|seelachs|forelle|hering|matjes|makrele"
    r")\b",
    re.IGNORECASE,
)
_PRODUCE_HINTS = (
    "champignon",
    "zwiebel",
    "himbeer",
    "erbsen",
    "spinat",
    "broccoli",
    "brokkoli",
    "salat",
    "tomaten",
    "cherrytomaten",
    "schnittlauch",
    "lauchzwiebeln",
    "mohren",
    "moehren",
    "romana",
    "bohnen",
)
_BEVERAGE_HINTS = (
    "cola",
    "limo",
    "limonade",
    "saft",
    "wasser",
    "sprudel",
    "soda",
    "tee",
    "kaffee",
    "coffee",
    "energy",
    "bier",
    "wein",
    "getraenk",
    "drink",
    "latte",
    "macch",
    "fuzetea",
    "sirup",
)
_DAIRY_HINTS = (
    "gouda",
    "mozzarella",
    "hirtenkaese",
    "frischkaese",
    "kochsahne",
    "creme_fraiche",
    "schmand",
    "philadelphia",
    "skyr",
    "jogh",
    "yoghurt",
    "quark",
    "milch",
    "kaese",
    "cheese",
    "butter",
    "sahne",
    "kefir",
    "ayran",
)
_PANTRY_HINTS = (
    "fusilli",
    "spaghetti",
    "penne",
    "rigatoni",
    "collez",
    "tort",
    "pasta",
    "nudel",
    "reis",
    "rice",
    "ketchup",
    "sauce",
    "senf",
    "mustard",
    "mayo",
    "honig",
    "honey",
    "oel",
    "oil",
    "essig",
    "vinegar",
    "mehl",
    "flour",
    "zucker",
    "sugar",
    "salz",
    "gewuerz",
    "muesli",
    "hafer",
    "hummus",
    "spaetzle",
)
_BAKERY_HINTS = (
    "brot",
    "broetchen",
    "toast",
    "baguette",
    "croissant",
    "brezel",
    "kuchen",
    "boerek",
)
_SNACKS_HINTS = (
    "chips",
    "cracker",
    "cookie",
    "keks",
    "schoko",
    "bonbon",
    "candy",
    "riegel",
    "berliner",
)
_FROZEN_HINTS = (
    "tiefkuehl",
    "eiscreme",
    "ice_cream",
    "frozen",
)
_HOUSEHOLD_HINTS = (
    "waschmittel",
    "waschmit",
    "spezialwaschm",
    "feinwaschmit",
    "muellbeutel",
    "toilettenpapier",
    "kuechenrolle",
    "reiniger",
    "putz",
    "spuel",
)
_PERSONAL_CARE_HINTS = (
    "shampoo",
    "spuelung",
    "seife",
    "zahnpasta",
    "deo",
    "duschgel",
    "rasierer",
    "lotion",
    "creme",
)
_MEAT_HINTS = (
    "schinken",
    "salami",
    "hahn",
    "haehn",
    "chicken",
    "hackfleisch",
    "geschnetzel",
    "schnitz",
    "fleisch",
    "wurst",
)
_FISH_HINTS = (
    "fisch",
    "lachs",
    "thunfisch",
    "tunfisch",
    "garnelen",
    "garnele",
    "shrimp",
    "shrimps",
    "kabeljau",
    "seelachs",
    "forelle",
    "hering",
    "matjes",
    "makrele",
)
_MODEL_RESPONSE_JSON_RE = re.compile(r"```(?:json)?\s*(?P<body>\{.*\})\s*```", re.DOTALL)
_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class TaxonomyCategory:
    name: str
    parent_name: str | None
    aliases: tuple[str, ...] = ()


TAXONOMY_CATEGORIES: tuple[TaxonomyCategory, ...] = (
    TaxonomyCategory("groceries", None, ("grocery", "groceries", "food", "foods")),
    TaxonomyCategory(
        "groceries:dairy",
        "groceries",
        ("dairy", "milk_products", "milchprodukte", "milk product"),
    ),
    TaxonomyCategory(
        "groceries:baking",
        "groceries",
        ("baking", "bake", "backzutaten", "baking_goods"),
    ),
    TaxonomyCategory(
        "groceries:beverages",
        "groceries",
        ("beverages", "beverage", "drink", "drinks", "getraenke", "getränke"),
    ),
    TaxonomyCategory(
        "groceries:produce",
        "groceries",
        ("produce", "fruit", "vegetables", "obst", "gemuese", "gemüse"),
    ),
    TaxonomyCategory(
        "groceries:bakery",
        "groceries",
        ("bakery", "bread", "breads", "backwaren", "baked_goods"),
    ),
    TaxonomyCategory(
        "groceries:fish",
        "groceries",
        ("fish", "seafood", "fisch", "meeresfruechte", "meeresfrüchte"),
    ),
    TaxonomyCategory(
        "groceries:meat",
        "groceries",
        ("meat", "fleisch", "wurst", "sausage"),
    ),
    TaxonomyCategory(
        "groceries:frozen",
        "groceries",
        ("frozen", "frozen_food", "tiefkuehl", "tiefkühl"),
    ),
    TaxonomyCategory(
        "groceries:snacks",
        "groceries",
        ("snacks", "snack", "sweets", "candy", "chips"),
    ),
    TaxonomyCategory(
        "groceries:pantry",
        "groceries",
        ("pantry", "staples", "dry_goods", "trockenwaren"),
    ),
    TaxonomyCategory("household", None, ("home", "haushalt", "cleaning")),
    TaxonomyCategory(
        "personal_care",
        None,
        ("personal care", "beauty", "pflege", "drogerie", "hygiene"),
    ),
    TaxonomyCategory("electronics", None, ("electronic", "tech", "technology")),
    TaxonomyCategory(
        "gaming_media",
        None,
        ("gaming", "games", "game", "media", "books", "video_games"),
    ),
    TaxonomyCategory(
        "shipping_fees",
        None,
        (
            "shipping",
            "shipping fee",
            "shipping fees",
            "delivery",
            "delivery fee",
            "delivery fees",
            "versand",
            "versandkosten",
            "porto",
            "postage",
        ),
    ),
    TaxonomyCategory(
        "deposit",
        None,
        ("pfand", "deposit", "bottle deposit", "bottle_deposit", "pfandrueckgabe"),
    ),
    TaxonomyCategory(
        "other",
        None,
        ("other", "misc", "miscellaneous", "uncategorized", "unknown", "fee", "fees"),
    ),
)


@dataclass(slots=True)
class CategorizationResult:
    category_id: str | None
    category_name: str
    method: str
    confidence: float | None
    source_value: str | None = None
    version: str | None = None


@dataclass(slots=True)
class CategorizationRequest:
    item_name: str
    current_category: str | None
    product_id: str | None
    raw_payload: dict[str, object] | None
    item_confidence: float | None = None
    merchant_name: str | None = None
    source_item_id: str | None = None
    unit: str | None = None
    unit_price_cents: int | None = None
    line_total_cents: int | None = None


@dataclass(slots=True)
class _ResolvedCategory:
    category_id: str | None
    category_name: str


@dataclass(slots=True)
class _ModelItemPayload:
    item: TransactionItem
    source_value: str | None
    merchant_name: str | None
    source_id: str


@dataclass(slots=True)
class _ModelPrediction:
    category_name: str
    confidence: float | None
    reason_code: str | None


RuntimeTask = SharedRuntimeTask
RuntimePolicy = SharedRuntimePolicy


@dataclass(frozen=True, slots=True)
class RuntimeHealth:
    task: RuntimeTask
    provider: str
    status: str
    base_url: str | None
    model: str | None
    policy: RuntimePolicy
    local_endpoint: bool
    capabilities: tuple[str, ...] = ("json_completion",)
    error: str | None = None


@dataclass(frozen=True, slots=True)
class JsonCompletionRequest:
    task: RuntimeTask
    system_prompt: str
    payload: dict[str, object]
    model: str
    temperature: float = 0.0
    max_tokens: int = 256
    timeout_s: float = 30.0
    max_retries: int = 0
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class JsonCompletionResult:
    task: RuntimeTask
    provider: str
    model: str
    text: str
    latency_ms: int
    raw_response: object | None = None


@runtime_checkable
class ModelRuntime(Protocol):
    task: RuntimeTask
    provider_name: str
    model_name: str | None

    def health(self) -> RuntimeHealth:
        raise NotImplementedError

    def complete_json(self, request: JsonCompletionRequest) -> JsonCompletionResult:
        raise NotImplementedError


def resolve_model_runtime(
    config: AppConfig,
    *,
    task: RuntimeTask | str,
    policy: RuntimePolicy | str | None = None,
    api_key_override: str | None = None,
) -> ModelRuntime | None:
    resolved_task = RuntimeTask(task)
    resolved_policy = RuntimePolicy(policy) if policy is not None else _default_runtime_policy(
        config,
        task=resolved_task,
    )
    resolution = resolve_shared_runtime(
        config,
        task=resolved_task,
        policy_mode=resolved_policy,
        api_key_override=api_key_override,
    )
    if resolution.runtime is None:
        LOGGER.warning(
            "runtime.blocked task=%s policy=%s status=%s reason=%s",
            resolved_task.value,
            resolved_policy.value,
            resolution.status_code,
            resolution.reason_code or "-",
        )
        return None
    if resolution.provider_kind == RuntimeProviderKind.BUNDLED_LOCAL_TEXT:
        return BundledLocalTextRuntimeAdapter(runtime=resolution.runtime)
    return OpenAICompatibleRuntimeAdapter(runtime=resolution.runtime)


def resolve_item_categorizer_runtime_client(config: AppConfig) -> ItemCategorizerModelClient | None:
    settings = resolve_item_categorizer_settings(config)
    if not settings.enabled:
        return None
    provider = (getattr(config, "item_categorizer_provider", "") or "").strip()
    if provider == "oauth_codex":
        bearer_token = get_ai_oauth_access_token(config)
        if not bearer_token:
            return None
        return ChatGPTOAuthItemCategorizerModelClient(settings=settings, bearer_token=bearer_token)
    runtime = resolve_model_runtime(config, task=RuntimeTask.ITEM_CATEGORIZATION)
    if runtime is None:
        return None
    return RuntimeBackedItemCategorizerModelClient(settings=settings, runtime=runtime)


def build_item_categorizer_model_client(config: AppConfig) -> ItemCategorizerModelClient | None:
    return resolve_item_categorizer_runtime_client(config)


class OpenAICompatibleRuntimeAdapter:
    def __init__(self, *, runtime: SharedModelRuntime) -> None:
        self._runtime = runtime
        self.task = RuntimeTask(runtime.task)
        self.provider_name = runtime.provider_kind.value
        self.model_name = runtime.model_name

    def health(self) -> RuntimeHealth:
        shared = self._runtime.health()
        return _compat_runtime_health(shared)

    def complete_json(self, request: JsonCompletionRequest) -> JsonCompletionResult:
        response = self._runtime.complete_json(
            SharedJsonCompletionRequest(
                task=self.task,
                model_name=request.model or self.model_name or _DEFAULT_MODEL,
                system_prompt=request.system_prompt,
                user_json=request.payload,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                timeout_s=request.timeout_s,
                max_retries=request.max_retries,
                metadata=request.metadata,
            )
        )
        return JsonCompletionResult(
            task=self.task,
            provider=self.provider_name,
            model=response.model_name,
            text=response.raw_text,
            latency_ms=response.latency_ms,
            raw_response=None,
        )


class BundledLocalTextRuntimeAdapter(OpenAICompatibleRuntimeAdapter):
    pass


class RuntimeBackedItemCategorizerModelClient:
    def __init__(self, *, settings: ItemCategorizerSettings, runtime: ModelRuntime) -> None:
        self._settings = settings
        self._runtime = runtime
        self.model_name = settings.model
        self._runtime_health = runtime.health()
        self.max_batch_size = _effective_model_batch_size(
            settings.max_batch_size,
            runtime_health=self._runtime_health,
            model_name=self.model_name,
        )
        self.confidence_threshold = settings.confidence_threshold
        self.ocr_confidence_threshold = settings.ocr_confidence_threshold

    def health(self) -> RuntimeHealth:
        return self._runtime.health()

    def classify_batch(
        self,
        items: Sequence[dict[str, object]],
    ) -> list[_ModelPrediction | None]:
        if not items:
            return []
        request = JsonCompletionRequest(
            task=self._runtime.task,
            system_prompt=_model_system_prompt(),
            payload={
                "taxonomy": [entry.name for entry in TAXONOMY_CATEGORIES],
                "items": list(items),
            },
            model=self.model_name,
            temperature=0,
            max_tokens=max(512, 128 * len(items)),
            timeout_s=_effective_model_timeout(
                self._settings.timeout_s,
                item_count=len(items),
                model_name=self.model_name,
                local_endpoint=self._runtime_health.local_endpoint,
            ),
            max_retries=self._settings.max_retries,
        )
        try:
            completion = self._runtime.complete_json(request)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(
                "runtime.error task=%s provider=%s model=%s error=%s",
                self._runtime.task.value,
                self._runtime.provider_name,
                self.model_name,
                exc,
            )
            raise
        LOGGER.info(
            "runtime.success task=%s provider=%s model=%s latency_ms=%s items=%s",
            completion.task.value,
            completion.provider,
            completion.model,
            completion.latency_ms,
            len(items),
        )
        return _parse_model_predictions(completion.text, expected=len(items))

    def is_prediction_usable(self, prediction: _ModelPrediction) -> bool:
        if prediction.confidence is None:
            return False
        return prediction.confidence >= self.confidence_threshold


class ChatGPTOAuthItemCategorizerModelClient:
    def __init__(self, *, settings: ItemCategorizerSettings, bearer_token: str) -> None:
        self._settings = settings
        self._bearer_token = bearer_token
        self.model_name = settings.model
        self.max_batch_size = settings.max_batch_size
        self.confidence_threshold = settings.confidence_threshold
        self.ocr_confidence_threshold = settings.ocr_confidence_threshold

    def health(self) -> RuntimeHealth:
        return RuntimeHealth(
            task=RuntimeTask.ITEM_CATEGORIZATION,
            provider="chatgpt_codex_oauth",
            status="ready" if self._bearer_token else "not_configured",
            base_url="https://chatgpt.com/backend-api/codex/responses",
            model=self.model_name,
            policy=RuntimePolicy.REMOTE_ALLOWED,
            local_endpoint=False,
            error=None if self._bearer_token else "missing oauth bearer token",
        )

    def classify_batch(
        self,
        items: Sequence[dict[str, object]],
    ) -> list[_ModelPrediction | None]:
        if not items:
            return []
        request = JsonCompletionRequest(
            task=RuntimeTask.ITEM_CATEGORIZATION,
            system_prompt=_model_system_prompt(),
            payload={
                "taxonomy": [entry.name for entry in TAXONOMY_CATEGORIES],
                "items": list(items),
            },
            model=self.model_name,
            temperature=0,
            max_tokens=max(512, 128 * len(items)),
            timeout_s=max(self._settings.timeout_s, 30.0),
            max_retries=self._settings.max_retries,
        )
        started = time.perf_counter()
        response = complete_text_with_codex_oauth(
            bearer_token=self._bearer_token,
            model=request.model,
            instructions=request.system_prompt,
            input_items=[
                {
                    "role": "user",
                    "content": json.dumps(request.payload, ensure_ascii=False),
                }
            ],
            timeout_s=request.timeout_s,
        )
        latency_ms = response.latency_ms or int((time.perf_counter() - started) * 1000)
        LOGGER.info(
            "runtime.success task=%s provider=%s model=%s latency_ms=%s items=%s",
            request.task.value,
            "chatgpt_codex_oauth",
            self.model_name,
            latency_ms,
            len(items),
        )
        return _parse_model_predictions(response.text, expected=len(items))

    def is_prediction_usable(self, prediction: _ModelPrediction) -> bool:
        if prediction.confidence is None:
            return False
        return prediction.confidence >= self.confidence_threshold

def _skip_model_for_low_confidence(
    *,
    item_name: str,
    item_confidence: float | None,
    model_client: object,
) -> bool:
    if item_confidence is None:
        return False
    threshold = getattr(model_client, "ocr_confidence_threshold", None)
    if not isinstance(threshold, int | float):
        return False
    if item_confidence >= float(threshold):
        return False
    normalized = " ".join(item_name.split()).strip()
    if len(normalized) <= 4:
        return True
    alpha_chars = sum(1 for char in normalized if char.isalpha())
    digit_chars = sum(1 for char in normalized if char.isdigit())
    return alpha_chars < max(3, len(normalized) // 3) or digit_chars > alpha_chars


def categorize_transaction_item(
    *,
    session: Session,
    source: Source,
    item_name: str,
    current_category: str | None,
    product_id: str | None,
    raw_payload: dict[str, object] | None,
    normalization_bundle: NormalizationBundle,
    use_model: bool,
    model_client: ItemCategorizerModelClient | None,
    rules: Sequence[CompiledRule] | None = None,
    item_confidence: float | None = None,
) -> CategorizationResult:
    ensure_category_taxonomy(session)
    category_rows = load_category_lookup(session)
    source_value = _extract_source_category(raw_payload, current_category)
    deposit_hit = _looks_like_deposit(
        item_name=item_name,
        source_value=source_value,
        is_deposit=bool(_safe_get(raw_payload, "is_deposit", default=False)),
    )
    if deposit_hit:
        return _taxonomy_result(
            category_rows=category_rows,
            category_name="deposit",
            method="deposit_rule",
            confidence=1.0,
            source_value=source_value,
        )

    if source_value is None and _looks_like_shipping_fee(item_name=item_name, source_value=source_value):
        return _taxonomy_result(
            category_rows=category_rows,
            category_name="shipping_fees",
            method="shipping_rule",
            confidence=0.99,
            source_value=source_value,
        )
    if _looks_like_produce(item_name=item_name, source_value=source_value):
        return _taxonomy_result(
            category_rows=category_rows,
            category_name="groceries:produce",
            method="produce_rule",
            confidence=0.97,
            source_value=source_value,
        )

    result = _deterministic_category_result(
        session=session,
        category_rows=category_rows,
        item_name=item_name,
        source_value=source_value,
        product_id=product_id,
        normalization_bundle=normalization_bundle,
        rules=rules or (),
    )
    if result is not None:
        return result

    heuristic_result = _heuristic_category_result(
        category_rows=category_rows,
        item_name=item_name,
        source_value=source_value,
    )
    if heuristic_result is not None:
        return heuristic_result

    temporary_item = TransactionItem(
        transaction_id="categorizer-preview",
        source_item_id=None,
        line_no=1,
        name=item_name,
        qty=Decimal("1.000"),
        unit=None,
        unit_price_cents=None,
        line_total_cents=0,
        category=current_category,
        category_id=None,
        category_method=None,
        category_confidence=None,
        category_source_value=source_value,
        category_version=None,
        product_id=product_id,
        is_deposit=False,
        confidence=_to_decimal(item_confidence),
        raw_payload=raw_payload,
    )
    if (
        use_model
        and model_client is not None
        and _should_use_model_for_item(temporary_item)
        and not _skip_model_for_low_confidence(
            item_name=item_name,
            item_confidence=item_confidence,
            model_client=model_client,
        )
    ):
        try:
            prediction = _predict_with_model_client(
                model_client=model_client,
                items=[
                    {
                        "item_name": item_name,
                        "merchant_name": None,
                        "source_id": source.id,
                        "current_category": current_category,
                        "unit": None,
                        "unit_price_cents": None,
                        "line_total_cents": None,
                    }
                ],
            )[0]
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(
                "categorization.model.error source=%s item=%s error=%s",
                source.id,
                item_name,
                exc,
            )
        else:
            if prediction is not None:
                predicted = _resolve_category_reference(
                    category_rows,
                    prediction.category_name,
                    allow_unknown=False,
                )
                if (
                    predicted is not None
                    and predicted.category_name != "other"
                    and _prediction_is_usable(
                    model_client=model_client,
                    prediction=prediction,
                    )
                ):
                        return CategorizationResult(
                            category_id=predicted.category_id,
                            category_name=predicted.category_name,
                            method="qwen_local",
                            confidence=prediction.confidence,
                            source_value=source_value,
                            version=_model_version(model_client),
                        )

    return _taxonomy_result(
        category_rows=category_rows,
        category_name="other",
        method="fallback_other",
        confidence=None,
        source_value=source_value,
    )


def categorize_transaction_items(
    *,
    session: Session,
    source: Source,
    requests: Sequence[CategorizationRequest],
    normalization_bundle: NormalizationBundle,
    use_model: bool,
    model_client: ItemCategorizerModelClient | None,
    compiled_rules: Sequence[CompiledRule] | None = None,
    model_confidence_threshold: float | None = None,
    model_batch_size: int | None = None,
) -> list[CategorizationResult]:
    ensure_category_taxonomy(session)
    category_rows = load_category_lookup(session)
    results: list[CategorizationResult | None] = [None] * len(requests)
    model_candidates: list[tuple[int, _ModelItemPayload]] = []

    for index, request in enumerate(requests):
        source_value = _extract_source_category(request.raw_payload, request.current_category)
        if _looks_like_deposit(
            item_name=request.item_name,
            source_value=source_value,
            is_deposit=bool(_safe_get(request.raw_payload, "is_deposit", default=False)),
        ):
            results[index] = _taxonomy_result(
                category_rows=category_rows,
                category_name="deposit",
                method="deposit_rule",
                confidence=1.0,
                source_value=source_value,
            )
            continue
        if source_value is None and _looks_like_shipping_fee(item_name=request.item_name, source_value=source_value):
            results[index] = _taxonomy_result(
                category_rows=category_rows,
                category_name="shipping_fees",
                method="shipping_rule",
                confidence=0.99,
                source_value=source_value,
            )
            continue
        if _looks_like_produce(item_name=request.item_name, source_value=source_value):
            results[index] = _taxonomy_result(
                category_rows=category_rows,
                category_name="groceries:produce",
                method="produce_rule",
                confidence=0.97,
                source_value=source_value,
            )
            continue

        deterministic = _deterministic_category_result(
            session=session,
            category_rows=category_rows,
            item_name=request.item_name,
            source_value=source_value,
            product_id=request.product_id,
            normalization_bundle=normalization_bundle,
            rules=compiled_rules or (),
        )
        if deterministic is not None:
            results[index] = deterministic
            continue

        heuristic = _heuristic_category_result(
            category_rows=category_rows,
            item_name=request.item_name,
            source_value=source_value,
        )
        if heuristic is not None:
            results[index] = heuristic
            continue

        preview_item = TransactionItem(
            transaction_id="categorizer-preview",
            source_item_id=request.source_item_id,
            line_no=index + 1,
            name=request.item_name,
            qty=Decimal("1.000"),
            unit=request.unit,
            unit_price_cents=request.unit_price_cents,
            line_total_cents=request.line_total_cents or 0,
            category=request.current_category,
            category_id=None,
            category_method=None,
            category_confidence=None,
            category_source_value=source_value,
            category_version=None,
            product_id=request.product_id,
            is_deposit=False,
            confidence=_to_decimal(request.item_confidence),
            raw_payload=request.raw_payload,
        )
        if (
            use_model
            and model_client is not None
            and _should_use_model_for_item(preview_item)
            and not _skip_model_for_low_confidence(
                item_name=request.item_name,
                item_confidence=request.item_confidence,
                model_client=model_client,
            )
        ):
            model_candidates.append(
                (
                    index,
                    _ModelItemPayload(
                        item=preview_item,
                        source_value=source_value,
                        merchant_name=request.merchant_name,
                        source_id=source.id,
                    ),
                )
            )
            continue

        results[index] = _taxonomy_result(
            category_rows=category_rows,
            category_name="other",
            method="fallback_other",
            confidence=None,
            source_value=source_value,
        )

    if model_client is not None and model_candidates:
        batch_limit = max(
            int(model_batch_size or getattr(model_client, "max_batch_size", 1) or 1),
            1,
        )
        for chunk in _iter_chunks(model_candidates, batch_limit):
            indexed_payloads = list(chunk)
            try:
                predictions = _predict_with_model_client(
                    model_client=model_client,
                    items=[
                        {
                            "item_name": payload.item.name,
                            "merchant_name": payload.merchant_name,
                            "source_id": payload.source_id,
                            "current_category": payload.source_value,
                            "unit": payload.item.unit,
                            "unit_price_cents": payload.item.unit_price_cents,
                            "line_total_cents": payload.item.line_total_cents,
                        }
                        for _, payload in indexed_payloads
                    ],
                )
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning(
                    "categorization.model.failed model=%s items=%s error=%s",
                    getattr(model_client, "model_name", "unknown"),
                    len(indexed_payloads),
                    exc,
                )
                predictions = [None] * len(indexed_payloads)
            for (index, payload), prediction in zip(indexed_payloads, predictions, strict=False):
                if (
                    prediction is not None
                    and prediction.category_name != "other"
                    and _prediction_is_usable(
                    model_client=model_client,
                    prediction=prediction,
                    confidence_threshold=model_confidence_threshold,
                    )
                ):
                    resolved = _resolve_category_reference(
                        category_rows,
                        prediction.category_name,
                        allow_unknown=False,
                    )
                    if resolved is not None:
                        results[index] = CategorizationResult(
                            category_id=resolved.category_id,
                            category_name=resolved.category_name,
                            method="qwen_local",
                            confidence=prediction.confidence,
                            source_value=payload.source_value,
                            version=_model_version(model_client),
                        )
                        continue
                results[index] = _taxonomy_result(
                    category_rows=category_rows,
                    category_name="other",
                    method="fallback_other",
                    confidence=None,
                    source_value=payload.source_value,
                )

    return [
        result
        if result is not None
        else _taxonomy_result(
            category_rows=category_rows,
            category_name="other",
            method="fallback_other",
            confidence=None,
            source_value=_extract_source_category(request.raw_payload, request.current_category),
        )
        for request, result in zip(requests, results, strict=True)
    ]


def apply_item_categorization(
    *,
    session: Session,
    source: Source,
    items: Sequence[TransactionItem],
    normalization_bundle: NormalizationBundle,
    rules: Sequence[CompiledRule],
    config: AppConfig,
    merchant_name: str | None,
    model_client: ItemCategorizerModelClient | None = None,
) -> None:
    if not items:
        return
    ensure_category_taxonomy(session)
    category_rows = load_category_lookup(session)
    model_client = model_client or build_item_categorizer_model_client(config)
    model_candidates: list[_ModelItemPayload] = []
    method_counts: dict[str, int] = {}

    for item in items:
        source_value = _extract_source_category(item.raw_payload, item.category_source_value or item.category)
        if _looks_like_deposit(
            item_name=item.name,
            source_value=source_value,
            is_deposit=bool(_safe_get(item.raw_payload, "is_deposit", default=False)),
        ):
            deposit = _taxonomy_result(
                category_rows=category_rows,
                category_name="deposit",
                method="deposit_rule",
                confidence=1.0,
                source_value=source_value,
            )
            _apply_result(item, deposit)
            method_counts[deposit.method] = method_counts.get(deposit.method, 0) + 1
            continue
        if source_value is None and _looks_like_shipping_fee(item_name=item.name, source_value=source_value):
            shipping = _taxonomy_result(
                category_rows=category_rows,
                category_name="shipping_fees",
                method="shipping_rule",
                confidence=0.99,
                source_value=source_value,
            )
            _apply_result(item, shipping)
            method_counts[shipping.method] = method_counts.get(shipping.method, 0) + 1
            continue
        if _looks_like_produce(item_name=item.name, source_value=source_value):
            produce = _taxonomy_result(
                category_rows=category_rows,
                category_name="groceries:produce",
                method="produce_rule",
                confidence=0.97,
                source_value=source_value,
            )
            _apply_result(item, produce)
            method_counts[produce.method] = method_counts.get(produce.method, 0) + 1
            continue
        deterministic = _deterministic_category_result(
            session=session,
            category_rows=category_rows,
            item_name=item.name,
            source_value=source_value,
            product_id=item.product_id,
            normalization_bundle=normalization_bundle,
            rules=rules,
        )
        if deterministic is not None:
            _apply_result(item, deterministic)
            method_counts[deterministic.method] = method_counts.get(deterministic.method, 0) + 1
            continue
        heuristic = _heuristic_category_result(
            category_rows=category_rows,
            item_name=item.name,
            source_value=source_value,
        )
        if heuristic is not None:
            _apply_result(item, heuristic)
            method_counts[heuristic.method] = method_counts.get(heuristic.method, 0) + 1
            continue
        if model_client is not None and _should_use_model_for_item(item):
            model_candidates.append(
                _ModelItemPayload(
                    item=item,
                    source_value=source_value,
                    merchant_name=merchant_name,
                    source_id=source.id,
                )
            )
            continue
        fallback = _taxonomy_result(
            category_rows=category_rows,
            category_name="other",
            method="fallback_other",
            confidence=None,
            source_value=source_value,
        )
        _apply_result(item, fallback)
        method_counts[fallback.method] = method_counts.get(fallback.method, 0) + 1

    if model_client is not None and model_candidates:
        for chunk in _iter_chunks(model_candidates, model_client.max_batch_size):
            model_results = _classify_model_chunk(
                category_rows=category_rows,
                chunk=chunk,
                model_client=model_client,
            )
            for item, result in model_results:
                _apply_result(item, result)
                method_counts[result.method] = method_counts.get(result.method, 0) + 1

    LOGGER.info(
        "categorization.batch source=%s merchant=%s items=%s methods=%s model_enabled=%s",
        source.id,
        merchant_name,
        len(items),
        json.dumps(method_counts, sort_keys=True),
        bool(model_client is not None),
    )


def ensure_category_taxonomy(session: Session) -> dict[str, Category]:
    existing = session.execute(select(Category).order_by(Category.name.asc(), Category.category_id.asc())).scalars().all()
    by_name = {(row.name or "").strip(): row for row in existing if (row.name or "").strip()}
    for entry in TAXONOMY_CATEGORIES:
        expected_parent_id = (
            by_name[entry.parent_name].category_id if entry.parent_name is not None and entry.parent_name in by_name else None
        )
        row = by_name.get(entry.name)
        if row is None:
            row = Category(
                category_id=entry.name,
                name=entry.name,
                parent_category_id=expected_parent_id,
            )
            session.add(row)
            session.flush()
            by_name[entry.name] = row
            continue
        if row.parent_category_id != expected_parent_id:
            row.parent_category_id = expected_parent_id
    return by_name


def load_category_lookup(session: Session) -> dict[str, Category]:
    return ensure_category_taxonomy(session)


def canonicalize_category_name(value: str | None) -> str | None:
    normalized = _normalize_category_key(value)
    if not normalized:
        return None
    return _CATEGORY_ALIAS_LOOKUP.get(normalized)


def resolve_category_override(
    session: Session,
    *,
    category_value: str | None,
) -> _ResolvedCategory | None:
    ensure_category_taxonomy(session)
    return _resolve_category_reference(load_category_lookup(session), category_value, allow_unknown=True)


@runtime_checkable
class ItemCategorizerModelClient(Protocol):
    model_name: str
    max_batch_size: int

    def classify_batch(
        self,
        items: Sequence[dict[str, object]],
    ) -> list[_ModelPrediction | None]:
        raise NotImplementedError

    def is_prediction_usable(self, prediction: _ModelPrediction) -> bool:
        raise NotImplementedError


class OpenAICompatibleItemCategorizerClient(RuntimeBackedItemCategorizerModelClient):
    def __init__(self, config: AppConfig) -> None:
        settings = resolve_item_categorizer_settings(config)
        runtime = resolve_model_runtime(config, task=RuntimeTask.ITEM_CATEGORIZATION)
        if runtime is None:
            raise RuntimeError("item categorizer runtime is not configured")
        super().__init__(settings=settings, runtime=runtime)


def _deterministic_category_result(
    *,
    session: Session,
    category_rows: dict[str, Category],
    item_name: str,
    source_value: str | None,
    product_id: str | None,
    normalization_bundle: NormalizationBundle,
    rules: Sequence[CompiledRule],
) -> CategorizationResult | None:
    source_result: CategorizationResult | None = None
    if source_value:
        direct_source = _resolve_category_reference(category_rows, source_value, allow_unknown=False)
        if direct_source is not None:
            source_result = CategorizationResult(
                category_id=direct_source.category_id,
                category_name=direct_source.category_name,
                method="source_native",
                confidence=0.95 if direct_source.category_id is not None else 0.85,
                source_value=source_value,
                version=ITEM_CATEGORIZATION_VERSION,
            )
        value_rule = find_category_value_normalization(
            current_category=source_value,
            bundle=normalization_bundle,
        )
        if value_rule is not None:
            source_result = _result_from_match(
                category_rows=category_rows,
                match=value_rule,
                method="normalization_rule",
                source_value=source_value,
                allow_unknown=True,
            )

    name_rule = find_category_name_normalization(item_name=item_name, bundle=normalization_bundle)
    if name_rule is not None:
        return _product_override_or_result(
            session=session,
            category_rows=category_rows,
            product_id=product_id,
            result=_result_from_match(
                category_rows=category_rows,
                match=name_rule,
                method="normalization_rule",
                source_value=source_value,
                allow_unknown=True,
            ),
        )

    category_rule = find_category_rule(item_name=item_name, rules=rules)
    if category_rule is not None and (
        source_result is None or source_result.category_name == "other"
    ):
        return _product_override_or_result(
            session=session,
            category_rows=category_rows,
            product_id=product_id,
            result=_result_from_rule(
                category_rows=category_rows,
                rule=category_rule,
                source_value=source_value,
            ),
        )

    product_result = _product_category_result(
        session=session,
        category_rows=category_rows,
        product_id=product_id,
        source_value=source_value,
    )
    if product_result is not None and (
        source_result is None
        or source_result.category_name == "other"
        or source_result.method in {"normalization_rule", "category_rule"}
    ):
        return product_result
    if source_result is not None and source_result.category_name != "other":
        return source_result
    return product_result


def _product_override_or_result(
    *,
    session: Session,
    category_rows: dict[str, Category],
    product_id: str | None,
    result: CategorizationResult,
) -> CategorizationResult:
    product_result = _product_category_result(
        session=session,
        category_rows=category_rows,
        product_id=product_id,
        source_value=result.source_value,
    )
    if product_result is None or result.category_name in {"deposit", "shipping_fees"}:
        return result
    if result.category_name not in {"other"} and result.method == "source_native":
        return result
    return product_result


def _product_category_result(
    *,
    session: Session,
    category_rows: dict[str, Category],
    product_id: str | None,
    source_value: str | None,
) -> CategorizationResult | None:
    if not product_id:
        return None
    product = session.get(Product, product_id)
    if product is None or not product.category_id:
        return None
    category = _resolve_category_by_id(category_rows, product.category_id)
    if category is None:
        return None
    return CategorizationResult(
        category_id=category.category_id,
        category_name=category.name,
        method="product",
        confidence=0.98,
        source_value=source_value,
        version=ITEM_CATEGORIZATION_VERSION,
    )


def _result_from_match(
    *,
    category_rows: dict[str, Category],
    match: CategoryNormalizationMatch,
    method: str,
    source_value: str | None,
    allow_unknown: bool,
) -> CategorizationResult:
    resolved = _resolve_category_reference(
        category_rows,
        match.replacement,
        allow_unknown=allow_unknown,
    )
    if resolved is None:
        resolved = _ResolvedCategory(category_id=None, category_name="other")
    return CategorizationResult(
        category_id=resolved.category_id,
        category_name=resolved.category_name,
        method=method,
        confidence=0.94,
        source_value=source_value,
        version=ITEM_CATEGORIZATION_VERSION,
    )


def _result_from_rule(
    *,
    category_rows: dict[str, Category],
    rule: CompiledRule,
    source_value: str | None,
) -> CategorizationResult:
    resolved = _resolve_category_reference(category_rows, rule.category, allow_unknown=True)
    if resolved is None:
        resolved = _ResolvedCategory(category_id=None, category_name="other")
    return CategorizationResult(
        category_id=resolved.category_id,
        category_name=resolved.category_name,
        method="category_rule",
        confidence=0.9,
        source_value=source_value,
        version=ITEM_CATEGORIZATION_VERSION,
    )


def _taxonomy_result(
    *,
    category_rows: dict[str, Category],
    category_name: str,
    method: str,
    confidence: float | None,
    source_value: str | None,
) -> CategorizationResult:
    resolved = _resolve_category_reference(category_rows, category_name, allow_unknown=False)
    if resolved is None:
        raise RuntimeError(f"missing canonical category: {category_name}")
    return CategorizationResult(
        category_id=resolved.category_id,
        category_name=resolved.category_name,
        method=method,
        confidence=confidence,
        source_value=source_value,
        version=ITEM_CATEGORIZATION_VERSION,
    )


def _resolve_category_reference(
    category_rows: dict[str, Category],
    raw_value: str | None,
    *,
    allow_unknown: bool,
) -> _ResolvedCategory | None:
    if raw_value is None:
        return None
    stripped = raw_value.strip()
    if not stripped:
        return None
    canonical = canonicalize_category_name(stripped)
    if canonical is not None:
        row = category_rows.get(canonical)
        if row is not None:
            return _ResolvedCategory(category_id=row.category_id, category_name=row.name)
    lower_name_map = {name.lower(): row for name, row in category_rows.items()}
    row = lower_name_map.get(stripped.lower())
    if row is not None:
        return _ResolvedCategory(category_id=row.category_id, category_name=row.name)
    if allow_unknown:
        return _ResolvedCategory(category_id=None, category_name=stripped)
    return None


def _resolve_category_by_id(
    category_rows: dict[str, Category],
    category_id: str,
) -> Category | None:
    for row in category_rows.values():
        if row.category_id == category_id:
            return row
    return None


def _classify_model_chunk(
    *,
    category_rows: dict[str, Category],
    chunk: Sequence[_ModelItemPayload],
    model_client: OpenAICompatibleItemCategorizerClient,
) -> list[tuple[TransactionItem, CategorizationResult]]:
    payload = [
        {
            "item_name": entry.item.name,
            "merchant_name": entry.merchant_name,
            "source_id": entry.source_id,
            "current_category": entry.source_value,
            "unit": entry.item.unit,
            "unit_price_cents": entry.item.unit_price_cents,
            "line_total_cents": entry.item.line_total_cents,
        }
        for entry in chunk
    ]
    try:
        predictions = model_client.classify_batch(payload)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning(
            "categorization.model.failed model=%s items=%s error=%s",
            model_client.model_name,
            len(chunk),
            exc,
        )
        predictions = [None] * len(chunk)

    results: list[tuple[TransactionItem, CategorizationResult]] = []
    for entry, prediction in zip(chunk, predictions, strict=False):
        if prediction is not None and _prediction_is_usable(model_client=model_client, prediction=prediction):
            resolved = _resolve_category_reference(
                category_rows,
                prediction.category_name,
                allow_unknown=False,
            )
            if resolved is not None and resolved.category_name != "other":
                result = CategorizationResult(
                    category_id=resolved.category_id,
                    category_name=resolved.category_name,
                    method="qwen_local",
                    confidence=prediction.confidence,
                    source_value=entry.source_value,
                    version=f"{ITEM_CATEGORIZATION_VERSION}:{model_client.model_name}",
                )
                results.append((entry.item, result))
                continue
        fallback = _taxonomy_result(
            category_rows=category_rows,
            category_name="other",
            method="fallback_other",
            confidence=None,
            source_value=entry.source_value,
        )
        results.append((entry.item, fallback))
    return results


def _prediction_is_usable(
    *,
    model_client: ItemCategorizerModelClient,
    prediction: _ModelPrediction,
    confidence_threshold: float | None = None,
) -> bool:
    if prediction.confidence is None:
        return False
    if confidence_threshold is not None:
        return prediction.confidence >= confidence_threshold
    if hasattr(model_client, "is_prediction_usable"):
        return model_client.is_prediction_usable(prediction)
    threshold = confidence_threshold if confidence_threshold is not None else 0.65
    return prediction.confidence >= threshold


def _predict_with_model_client(
    *,
    model_client: ItemCategorizerModelClient,
    items: Sequence[dict[str, object]],
) -> list[_ModelPrediction | None]:
    if hasattr(model_client, "classify_batch"):
        return model_client.classify_batch(items)
    if hasattr(model_client, "categorize_items"):
        raw_rows = model_client.categorize_items(items)
        predictions: list[_ModelPrediction | None] = []
        for row in raw_rows:
            if not isinstance(row, dict):
                predictions.append(None)
                continue
            raw_category_name = row.get("category_name")
            if not isinstance(raw_category_name, str) or not raw_category_name.strip():
                predictions.append(None)
                continue
            confidence = row.get("confidence")
            predictions.append(
                _ModelPrediction(
                    category_name=raw_category_name.strip(),
                    confidence=float(confidence) if isinstance(confidence, int | float) else None,
                    reason_code=str(row.get("reason_code")).strip()
                    if row.get("reason_code") is not None
                    else None,
                )
            )
        return predictions
    raise RuntimeError("item categorizer model client must define classify_batch() or categorize_items()")


def _model_version(model_client: ItemCategorizerModelClient) -> str:
    model_name = getattr(model_client, "model_name", None)
    if isinstance(model_name, str) and model_name.strip():
        return f"{ITEM_CATEGORIZATION_VERSION}:{model_name.strip()}"
    return ITEM_CATEGORIZATION_VERSION


def _apply_result(item: TransactionItem, result: CategorizationResult) -> None:
    item.category = result.category_name
    item.category_id = result.category_id
    item.category_method = result.method
    item.category_confidence = _to_decimal(result.confidence)
    item.category_source_value = result.source_value
    item.category_version = result.version or ITEM_CATEGORIZATION_VERSION


def _extract_source_category(
    raw_payload: dict[str, object] | None,
    current_category: str | None,
) -> str | None:
    if isinstance(raw_payload, dict):
        raw_category = raw_payload.get("category")
        if isinstance(raw_category, str) and raw_category.strip():
            return raw_category.strip()
    if current_category is not None and current_category.strip():
        stripped = current_category.strip()
        if canonicalize_category_name(stripped) is None:
            return stripped
    return None


def _looks_like_deposit(*, item_name: str, source_value: str | None, is_deposit: bool) -> bool:
    if is_deposit:
        return True
    haystacks = [item_name, source_value or ""]
    return any(_DEPOSIT_RE.search(value) for value in haystacks if value)


def _looks_like_shipping_fee(*, item_name: str, source_value: str | None) -> bool:
    haystacks = [item_name, source_value or ""]
    return any(_SHIPPING_RE.search(value) for value in haystacks if value)


def _looks_like_produce(*, item_name: str, source_value: str | None) -> bool:
    haystacks = [item_name, source_value or ""]
    return any(_PRODUCE_RE.search(value) for value in haystacks if value)


def _heuristic_category_result(
    *,
    category_rows: dict[str, Category],
    item_name: str,
    source_value: str | None,
) -> CategorizationResult | None:
    haystacks = [item_name, source_value or ""]
    normalized_haystacks = [
        _normalize_category_key(value)
        for value in haystacks
        if value
    ]
    heuristic_rules: tuple[tuple[re.Pattern[str], str, str, float], ...] = (
        (_HOUSEHOLD_RE, "household", "household_rule", 0.9),
        (_PERSONAL_CARE_RE, "personal_care", "personal_care_rule", 0.88),
        (_BEVERAGES_RE, "groceries:beverages", "beverage_rule", 0.9),
        (_DAIRY_RE, "groceries:dairy", "dairy_rule", 0.9),
        (_BAKERY_RE, "groceries:bakery", "bakery_rule", 0.88),
        (_FISH_RE, "groceries:fish", "fish_rule", 0.9),
        (_MEAT_RE, "groceries:meat", "meat_rule", 0.88),
        (_FROZEN_RE, "groceries:frozen", "frozen_rule", 0.88),
        (_SNACKS_RE, "groceries:snacks", "snack_rule", 0.86),
        (_PANTRY_RE, "groceries:pantry", "pantry_rule", 0.86),
    )
    hint_rules: tuple[tuple[tuple[str, ...], str, str, float], ...] = (
        (_HOUSEHOLD_HINTS, "household", "household_rule", 0.9),
        (_PERSONAL_CARE_HINTS, "personal_care", "personal_care_rule", 0.88),
        (_PRODUCE_HINTS, "groceries:produce", "produce_rule", 0.97),
        (_FISH_HINTS, "groceries:fish", "fish_rule", 0.92),
        (_MEAT_HINTS, "groceries:meat", "meat_rule", 0.9),
        (_DAIRY_HINTS, "groceries:dairy", "dairy_rule", 0.9),
        (_BAKERY_HINTS, "groceries:bakery", "bakery_rule", 0.88),
        (_BEVERAGE_HINTS, "groceries:beverages", "beverage_rule", 0.88),
        (_FROZEN_HINTS, "groceries:frozen", "frozen_rule", 0.88),
        (_SNACKS_HINTS, "groceries:snacks", "snack_rule", 0.86),
        (_PANTRY_HINTS, "groceries:pantry", "pantry_rule", 0.86),
    )
    for hints, category_name, method, confidence in hint_rules:
        if _contains_any_hint(normalized_haystacks, hints):
            return _taxonomy_result(
                category_rows=category_rows,
                category_name=category_name,
                method=method,
                confidence=confidence,
                source_value=source_value,
            )
    for pattern, category_name, method, confidence in heuristic_rules:
        if any(pattern.search(value) for value in haystacks if value):
            return _taxonomy_result(
                category_rows=category_rows,
                category_name=category_name,
                method=method,
                confidence=confidence,
                source_value=source_value,
            )
    return None


def _effective_model_batch_size(
    configured_batch_size: int,
    *,
    runtime_health: RuntimeHealth,
    model_name: str | None,
) -> int:
    normalized_model = (model_name or "").strip().lower()
    if runtime_health.local_endpoint and "mlx" in normalized_model:
        return 1
    return max(int(configured_batch_size or 1), 1)


def _effective_model_timeout(
    configured_timeout_s: float,
    *,
    item_count: int,
    model_name: str | None,
    local_endpoint: bool,
) -> float:
    normalized_model = (model_name or "").strip().lower()
    if local_endpoint and "mlx" in normalized_model:
        return max(float(configured_timeout_s or 0.0), 10.0 + (4.0 * max(item_count - 1, 0)))
    return float(configured_timeout_s)


def _should_use_model_for_item(item: TransactionItem) -> bool:
    normalized_name = " ".join(item.name.split()).strip()
    if len(normalized_name) < 3:
        return False
    alpha_chars = sum(1 for char in normalized_name if char.isalpha())
    if item.confidence is None:
        return True
    confidence = float(item.confidence)
    if confidence >= 0.65:
        return True
    return alpha_chars >= max(3, len(normalized_name) // 2)


def _should_skip_model_for_low_ocr_confidence(
    *,
    item_name: str,
    item_confidence: float | None,
    model_client: ItemCategorizerModelClient,
) -> bool:
    if item_confidence is None:
        return False
    threshold = getattr(model_client, "ocr_confidence_threshold", None)
    if not isinstance(threshold, int | float):
        return False
    if item_confidence >= float(threshold):
        return False
    return _looks_like_noisy_text(item_name)


def _looks_like_noisy_text(value: str) -> bool:
    normalized = " ".join(value.split()).strip()
    if len(normalized) <= 4:
        return True
    alpha_chars = sum(1 for char in normalized if char.isalpha())
    digit_chars = sum(1 for char in normalized if char.isdigit())
    return alpha_chars < max(3, len(normalized) // 3) or digit_chars > alpha_chars


def _contains_any_hint(values: Sequence[str], hints: Sequence[str]) -> bool:
    for value in values:
        if not value:
            continue
        if any(hint in value for hint in hints):
            return True
    return False


def _validate_model_runtime_endpoint(
    *,
    base_url: str | None,
    allow_remote: bool,
    allow_insecure_transport: bool,
) -> None:
    validate_runtime_endpoint(
        base_url=base_url,
        allow_remote=allow_remote,
        allow_insecure_transport=allow_insecure_transport,
        purpose="item_categorizer",
    )


def _validate_item_categorizer_endpoint(
    *,
    config: AppConfig,
    settings: ItemCategorizerSettings,
) -> None:
    _validate_model_runtime_endpoint(
        base_url=settings.base_url,
        allow_remote=settings.allow_remote,
        allow_insecure_transport=bool(config.allow_insecure_transport),
    )


def _default_runtime_policy(config: AppConfig, *, task: RuntimeTask) -> RuntimePolicy:
    if task is RuntimeTask.PI_AGENT:
        return RuntimePolicy(str(config.pi_agent_runtime_policy))
    if task is RuntimeTask.ITEM_CATEGORIZATION:
        return RuntimePolicy(str(config.item_categorization_runtime_policy))
    return RuntimePolicy.LOCAL_PREFERRED


def _compat_runtime_health(shared: SharedRuntimeHealth) -> RuntimeHealth:
    return RuntimeHealth(
        task=RuntimeTask(shared.task),
        provider=shared.provider_kind.value,
        status=shared.status_code,
        base_url=shared.base_url,
        model=shared.model_name,
        policy=RuntimePolicy(shared.policy_mode),
        local_endpoint=bool(shared.capabilities.local),
        capabilities=tuple(
            capability
            for capability, enabled in {
                "json_completion": shared.capabilities.json_completion,
                "chat_completion": shared.capabilities.chat_completion,
                "streaming": shared.capabilities.streaming,
            }.items()
            if enabled
        ),
        error=shared.message,
    )


def _parse_model_predictions(text: str, *, expected: int) -> list[_ModelPrediction | None]:
    payload = _parse_json_payload(text)
    if not isinstance(payload, dict):
        raise RuntimeError("item categorizer model did not return a JSON object")
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise RuntimeError("item categorizer model response did not include a results list")
    predictions: list[_ModelPrediction | None] = [None] * expected
    for index, raw_result in enumerate(raw_results):
        if index >= expected or not isinstance(raw_result, dict):
            continue
        category_name = raw_result.get("category_name")
        if not isinstance(category_name, str) or not category_name.strip():
            continue
        confidence = raw_result.get("confidence")
        predictions[index] = _ModelPrediction(
            category_name=category_name.strip(),
            confidence=float(confidence) if isinstance(confidence, int | float) else None,
            reason_code=str(raw_result.get("reason_code")).strip()
            if raw_result.get("reason_code") is not None
            else None,
        )
    return predictions


def _parse_json_payload(text: str) -> object:
    stripped = _THINK_TAG_RE.sub("", text).strip()
    fenced = _MODEL_RESPONSE_JSON_RE.search(stripped)
    if fenced is not None:
        stripped = fenced.group("body").strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        candidate = _extract_json_object_candidate(stripped)
        if candidate is not None:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
        raise RuntimeError("item categorizer model returned invalid JSON") from exc


def _extract_json_object_candidate(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _coerce_completion_text(response: object) -> str:
    choices = getattr(response, "choices", None)
    if not choices:
        raise RuntimeError("item categorizer response did not include choices")
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            text = getattr(item, "text", None)
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
                continue
            if isinstance(item, dict):
                raw_text = item.get("text")
                if isinstance(raw_text, str) and raw_text.strip():
                    chunks.append(raw_text.strip())
        joined = "\n".join(chunks).strip()
        if joined:
            return joined
    raise RuntimeError("item categorizer response did not include text content")


def _model_system_prompt() -> str:
    categories = ", ".join(entry.name for entry in TAXONOMY_CATEGORIES)
    return (
        "You categorize retail basket line items into a fixed taxonomy. "
        "Inputs are often short German supermarket labels with abbreviations, punctuation, and compound words "
        "(for example Lidl and EDEKA receipt item names). "
        f"Allowed categories: {categories}. "
        "Return JSON only with shape "
        '{"results":[{"category_name":"...", "confidence":0.0, "reason_code":"..."}]}. '
        "Do not add commentary. Use the closest category from the allowed list. "
        "Use `other` only when the item is genuinely too ambiguous. "
        "Examples: Bauernbrötchen -> groceries:bakery, Gouda Scheiben 48% -> groceries:dairy, "
        "Feinwaschmit. Color -> household, Lachsfilet -> groceries:fish, Hähn.Schw.Steak Kräu -> groceries:meat, "
        "Champignon weiß -> groceries:produce."
    )


def _normalize_category_key(value: str | None) -> str:
    if value is None:
        return ""
    normalized = (
        value.strip()
        .lower()
        .replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    normalized = normalized.replace("&", " and ")
    normalized = normalized.replace("/", " ").replace("-", " ")
    normalized = re.sub(r"[^a-z0-9:]+", "_", normalized)
    return normalized.strip("_")


def _iter_chunks(
    values: Sequence[object],
    size: int,
) -> Iterable[Sequence[object]]:
    for start in range(0, len(values), max(size, 1)):
        yield values[start : start + max(size, 1)]


def _to_decimal(value: float | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(f"{value:.3f}")


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _safe_get(raw_payload: dict[str, object] | None, key: str, *, default: object) -> object:
    if not isinstance(raw_payload, dict):
        return default
    return raw_payload.get(key, default)


_CATEGORY_ALIAS_LOOKUP: dict[str, str] = {}
for _entry in TAXONOMY_CATEGORIES:
    _CATEGORY_ALIAS_LOOKUP[_normalize_category_key(_entry.name)] = _entry.name
    _CATEGORY_ALIAS_LOOKUP[_normalize_category_key(_entry.name.replace(":", " "))] = _entry.name
    for _alias in _entry.aliases:
        _CATEGORY_ALIAS_LOOKUP[_normalize_category_key(_alias)] = _entry.name
