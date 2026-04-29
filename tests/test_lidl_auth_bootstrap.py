from __future__ import annotations

import sys
import unittest
import urllib.parse
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest.mock import patch


DESKTOP_ROOT = Path(__file__).resolve().parents[1]
VENDOR_BACKEND_SRC = DESKTOP_ROOT / "vendor" / "backend" / "src"

if str(VENDOR_BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(VENDOR_BACKEND_SRC))

from lidltool.auth.bootstrap_playwright import _build_auth_url, run_headful_bootstrap  # noqa: E402


class LidlAuthBootstrapTests(unittest.TestCase):
    def test_build_auth_url_can_include_oauth_state(self) -> None:
        url = _build_auth_url("challenge", country="DE", language="de", state="state-1")
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)

        self.assertEqual(params["state"], ["state-1"])
        self.assertEqual(params["redirect_uri"], ["com.lidlplus.app://callback"])
        self.assertEqual(params["code_challenge"], ["challenge"])

    def test_headful_bootstrap_uses_auth_browser_runtime_without_state_guard(self) -> None:
        with TemporaryDirectory() as temp_dir:
            def fake_browser_auth(auth_url: str, expected_state: str | None) -> object:
                self.assertIsNone(expected_state)
                return SimpleNamespace(
                    callback_url="com.lidlplus.app://callback?code=auth-code"
                )

            with patch(
                "lidltool.auth.bootstrap_playwright._run_browser_auth",
                side_effect=fake_browser_auth,
            ) as browser_auth_mock:
                with patch(
                    "lidltool.auth.bootstrap_playwright._exchange_code",
                    return_value="refresh-token",
                ) as exchange_mock:
                    token = run_headful_bootstrap(Path(temp_dir) / "lidl-auth.har")

            self.assertEqual(token, "refresh-token")
            auth_url, expected_state = browser_auth_mock.call_args.args
            parsed_start_url = urllib.parse.urlparse(auth_url)
            start_params = urllib.parse.parse_qs(parsed_start_url.query)

            self.assertIsNone(expected_state)
            self.assertNotIn("state", start_params)
            exchange_mock.assert_called_once()
            self.assertEqual(exchange_mock.call_args.args[0], "auth-code")
            self.assertTrue(exchange_mock.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
