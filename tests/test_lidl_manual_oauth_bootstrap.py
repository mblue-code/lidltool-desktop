from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

DESKTOP_ROOT = Path(__file__).resolve().parents[1]
VENDOR_BACKEND_SRC = DESKTOP_ROOT / "vendor" / "backend" / "src"

if str(VENDOR_BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(VENDOR_BACKEND_SRC))

from lidltool.auth.token_store import TokenStore  # noqa: E402
from lidltool.config import AppConfig  # noqa: E402
from lidltool.connectors.auth.auth_orchestration import ConnectorAuthOrchestrationService  # noqa: E402


class LidlManualOAuthBootstrapTests(unittest.TestCase):
    def test_manual_lidl_bootstrap_can_be_confirmed_from_callback_url(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = AppConfig(
                db_path=root / "lidltool.sqlite",
                config_dir=root / "config",
                document_storage_path=root / "documents",
                credential_encryption_key="desktop-env-secret-key-1234567890",
                desktop_mode=True,
                connector_live_sync_enabled=False,
            )
            config.config_dir.mkdir(parents=True, exist_ok=True)
            config.document_storage_path.mkdir(parents=True, exist_ok=True)
            service = ConnectorAuthOrchestrationService(config=config)

            started = service.start_bootstrap(source_id="lidl_plus_de")

            self.assertEqual(started.status, "started")
            self.assertIsNotNone(started.bootstrap)
            assert started.bootstrap is not None
            self.assertEqual(started.bootstrap.state, "running")
            self.assertTrue(started.metadata["manual_callback_supported"])
            self.assertTrue(str(started.metadata["auth_start_url"]).startswith("https://accounts.lidl.com/"))
            self.assertIn(
                "Open the Lidl sign-in in your browser to continue.",
                list(started.bootstrap.output_tail),
            )

            status = service.get_auth_status(source_id="lidl_plus_de", validate_session=False)
            self.assertEqual(status.state, "bootstrap_running")
            self.assertTrue(status.metadata["manual_callback_supported"])
            self.assertEqual(status.metadata["callback_url_prefixes"], ["com.lidlplus.app://callback"])

            with patch(
                "lidltool.connectors.auth.auth_orchestration.exchange_lidl_callback_url",
                return_value="refresh-token-1",
            ) as exchange_mock:
                confirmed = service.confirm_bootstrap(
                    source_id="lidl_plus_de",
                    callback_url="com.lidlplus.app://callback?code=test-code",
                )

            self.assertTrue(confirmed.ok)
            self.assertEqual(confirmed.status, "confirmed")
            exchange_mock.assert_called_once_with(
                "com.lidlplus.app://callback?code=test-code",
                unittest.mock.ANY,
            )
            self.assertEqual(
                TokenStore.from_config(config).get_refresh_token(),
                "refresh-token-1",
            )
            self.assertEqual(
                service.get_auth_status(source_id="lidl_plus_de", validate_session=False).state,
                "connected",
            )


if __name__ == "__main__":
    unittest.main()
