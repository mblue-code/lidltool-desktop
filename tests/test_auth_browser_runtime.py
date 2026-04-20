from __future__ import annotations

import sys
import unittest
from pathlib import Path


DESKTOP_ROOT = Path(__file__).resolve().parents[1]
VENDOR_BACKEND_SRC = DESKTOP_ROOT / "vendor" / "backend" / "src"

if str(VENDOR_BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(VENDOR_BACKEND_SRC))

from lidltool.connectors.auth.browser_runtime import (  # noqa: E402
    _record_navigation_away,
    _should_accept_callback_candidate,
)


class AuthBrowserRuntimeTests(unittest.TestCase):
    def test_ignores_blank_startup_pages_when_tracking_navigation_away(self) -> None:
        start_url = "https://account.dm.de/purchases"

        self.assertFalse(
            _record_navigation_away(
                candidate="about:blank",
                start_url=start_url,
                saw_navigation_away=False,
            )
        )

    def test_ignores_non_http_resource_urls_when_tracking_navigation_away(self) -> None:
        start_url = "https://account.dm.de/purchases"

        self.assertFalse(
            _record_navigation_away(
                candidate="data:text/plain,https://account.dm.de/purchases",
                start_url=start_url,
                saw_navigation_away=False,
            )
        )

    def test_marks_navigation_away_for_redirects_before_returning_to_same_callback_url(self) -> None:
        start_url = "https://account.dm.de/purchases"

        saw_navigation_away = _record_navigation_away(
            candidate="https://signin.dm.de/dm-de/authentication/web-login",
            start_url=start_url,
            saw_navigation_away=False,
        )

        self.assertTrue(saw_navigation_away)

    def test_same_url_callback_requires_observed_navigation_away(self) -> None:
        start_url = "https://account.dm.de/purchases"

        self.assertFalse(
            _should_accept_callback_candidate(
                candidate=start_url,
                start_url=start_url,
                require_navigation_away_before_completion=True,
                expected_callback_state=None,
                saw_navigation_away=False,
            )
        )

        self.assertTrue(
            _should_accept_callback_candidate(
                candidate=start_url,
                start_url=start_url,
                require_navigation_away_before_completion=True,
                expected_callback_state=None,
                saw_navigation_away=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
