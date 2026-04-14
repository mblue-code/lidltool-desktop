from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LidlMarket:
    source_id: str
    country_code: str
    language_code: str
    web_host: str

    @property
    def ui_locale(self) -> str:
        return f"{self.language_code}-{self.country_code}"


_KNOWN_LIDL_MARKETS: dict[str, LidlMarket] = {
    "lidl_plus_de": LidlMarket(
        source_id="lidl_plus_de",
        country_code="DE",
        language_code="de",
        web_host="www.lidl.de",
    ),
    "lidl_plus_gb": LidlMarket(
        source_id="lidl_plus_gb",
        country_code="GB",
        language_code="en",
        web_host="www.lidl.co.uk",
    ),
    "lidl_plus_fr": LidlMarket(
        source_id="lidl_plus_fr",
        country_code="FR",
        language_code="fr",
        web_host="www.lidl.fr",
    ),
}


def resolve_lidl_market(source_id: str) -> LidlMarket:
    market = _KNOWN_LIDL_MARKETS.get(source_id)
    if market is not None:
        return market

    suffix = source_id.rsplit("_", 1)[-1]
    country_code = suffix.upper()
    language_code = suffix.lower()
    return LidlMarket(
        source_id=source_id,
        country_code=country_code,
        language_code=language_code,
        web_host="www.lidl.de",
    )
