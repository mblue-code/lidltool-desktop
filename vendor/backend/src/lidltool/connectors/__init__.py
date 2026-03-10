from lidltool.connectors.amazon_adapter import AmazonConnectorAdapter
from lidltool.connectors.base import BaseConnectorAdapter, Connector
from lidltool.connectors.dm_adapter import DmConnectorAdapter
from lidltool.connectors.kaufland_adapter import KauflandConnectorAdapter
from lidltool.connectors.lidl_adapter import LidlConnectorAdapter
from lidltool.connectors.manifest import ConnectorManifest, ManifestValidationError
from lidltool.connectors.market_catalog import (
    connector_distribution_payload,
    get_connector_market_catalog,
    product_market_strategy_payload,
    self_hosted_market_strategy_payload,
)
from lidltool.connectors.registry import ConnectorRegistry, get_connector_registry
from lidltool.connectors.rewe_adapter import ReweConnectorAdapter
from lidltool.connectors.rossmann_adapter import RossmannConnectorAdapter
from lidltool.connectors.sdk import (
    ConnectorPolicy,
    ReceiptConnector,
    ReceiptConnectorContractFixture,
    assert_receipt_connector_contract,
)

__all__ = [
    "AmazonConnectorAdapter",
    "BaseConnectorAdapter",
    "ConnectorManifest",
    "ConnectorRegistry",
    "Connector",
    "connector_distribution_payload",
    "DmConnectorAdapter",
    "get_connector_market_catalog",
    "ConnectorPolicy",
    "KauflandConnectorAdapter",
    "LidlConnectorAdapter",
    "ManifestValidationError",
    "product_market_strategy_payload",
    "ReceiptConnector",
    "ReceiptConnectorContractFixture",
    "RossmannConnectorAdapter",
    "ReweConnectorAdapter",
    "assert_receipt_connector_contract",
    "get_connector_registry",
    "self_hosted_market_strategy_payload",
]
