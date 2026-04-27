from __future__ import annotations

import sqlite3
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


DESKTOP_ROOT = Path(__file__).resolve().parents[1]
VENDOR_BACKEND_SRC = DESKTOP_ROOT / "vendor" / "backend" / "src"

if str(VENDOR_BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(VENDOR_BACKEND_SRC))

from lidltool.connectors.auth.browser_runtime import (  # noqa: E402
    _build_external_chromium_launch,
    _capture_system_profile_browser_result,
    _chromium_history_timestamp,
    _chromium_last_used_profile_name,
    _chromium_user_data_dir_for_executable,
    _external_browser_temp_root,
    _macos_app_bundle_from_executable,
    _read_callback_from_chromium_history,
    _read_callback_from_system_browser_tabs,
    _record_navigation_away,
    _read_devtools_active_port,
    _seed_external_chromium_profile,
    _should_use_external_chromium_handoff,
    _should_use_system_profile_browser_handoff,
    _should_accept_callback_candidate,
    SystemChromiumProfileTarget,
)
from lidltool.connectors.sdk.runtime import AuthBrowserPlan  # noqa: E402


class AuthBrowserRuntimeTests(unittest.TestCase):
    def test_build_external_chromium_launch_uses_open_new_instance_on_macos(self) -> None:
        executable = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        user_data_dir = Path("/tmp/lidltool-auth-browser-test")

        with patch("lidltool.connectors.auth.browser_runtime.sys.platform", "darwin"):
            launch = _build_external_chromium_launch(
                executable_path=executable,
                user_data_dir=user_data_dir,
                start_url="https://account.penny.de/auth",
            )

        self.assertTrue(launch.launcher_may_exit_early)
        self.assertEqual(launch.command[:5], ("open", "-n", "-a", "/Applications/Google Chrome.app", "--args"))
        self.assertIn("--remote-debugging-port=0", launch.command)
        self.assertIn("--remote-debugging-address=127.0.0.1", launch.command)
        self.assertIn(f"--user-data-dir={user_data_dir}", launch.command)

    def test_macos_app_bundle_is_derived_from_chromium_executable(self) -> None:
        executable = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

        with patch("lidltool.connectors.auth.browser_runtime.sys.platform", "darwin"):
            bundle = _macos_app_bundle_from_executable(executable)

        self.assertEqual(bundle, Path("/Applications/Google Chrome.app"))

    def test_external_browser_temp_root_prefers_system_tmp_on_macos(self) -> None:
        with patch("lidltool.connectors.auth.browser_runtime.sys.platform", "darwin"):
            root = _external_browser_temp_root()

        self.assertIn(root, {"/private/tmp", "/tmp"})

    def test_read_devtools_active_port_uses_first_line(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "DevToolsActivePort"
            path.write_text("45123\n/devtools/browser/abc\n", encoding="utf-8")

            port = _read_devtools_active_port(Path(tmp_dir))

        self.assertEqual(port, 45123)

    def test_seed_external_chromium_profile_enables_apple_events_javascript(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            _seed_external_chromium_profile(root)
            payload = (root / "Default" / "Preferences").read_text(encoding="utf-8")

        self.assertIn('"allow_javascript_apple_events":true', payload)

    def test_detects_last_used_chromium_profile_name(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            user_data_dir = Path(tmp_dir)
            (user_data_dir / "Local State").write_text(
                '{"profile":{"last_used":"Profile 2"}}',
                encoding="utf-8",
            )

            profile_name = _chromium_last_used_profile_name(user_data_dir)

        self.assertEqual(profile_name, "Profile 2")

    def test_maps_macos_chrome_executable_to_real_user_data_dir(self) -> None:
        executable = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

        with patch("lidltool.connectors.auth.browser_runtime.sys.platform", "darwin"):
            with patch("lidltool.connectors.auth.browser_runtime._real_user_home_dir", return_value="/Users/tester"):
                browser_name, user_data_dir = _chromium_user_data_dir_for_executable(executable)

        self.assertEqual(browser_name, "Google Chrome")
        self.assertEqual(
            user_data_dir,
            Path("/Users/tester/Library/Application Support/Google/Chrome"),
        )

    def test_reads_matching_callback_from_chromium_history(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            history_db_path = root / "History"
            connection = sqlite3.connect(history_db_path)
            try:
                connection.execute(
                    "create table urls (id integer primary key, url text not null, last_visit_time integer not null)"
                )
                connection.execute(
                    "insert into urls (url, last_visit_time) values (?, ?)",
                    (
                        "https://www.penny.de/app/login?code=test-code&state=expected-state",
                        _chromium_history_timestamp(datetime.now(tz=UTC)),
                    ),
                )
                connection.commit()
            finally:
                connection.close()

            target = SystemChromiumProfileTarget(
                executable_path=Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                app_bundle_path=Path("/Applications/Google Chrome.app"),
                browser_name="Google Chrome",
                user_data_dir=root,
                profile_name="Default",
                history_db_path=history_db_path,
            )

            callback = _read_callback_from_chromium_history(
                target=target,
                callback_prefixes=("https://www.penny.de/app/login",),
                expected_callback_state="expected-state",
                not_before=0,
            )

        self.assertEqual(
            callback,
            "https://www.penny.de/app/login?code=test-code&state=expected-state",
        )

    def test_reads_matching_callback_from_system_browser_tabs(self) -> None:
        target = SystemChromiumProfileTarget(
            executable_path=Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            app_bundle_path=Path("/Applications/Google Chrome.app"),
            browser_name="Google Chrome",
            user_data_dir=Path("/tmp/chrome"),
            profile_name="Default",
            history_db_path=Path("/tmp/chrome/Default/History"),
        )

        class _Completed:
            returncode = 0
            stdout = (
                "https://example.com/\n"
                "https://www.penny.de/app/login?code=test-code&state=expected-state\n"
            )

        with patch("lidltool.connectors.auth.browser_runtime.sys.platform", "darwin"):
            with patch("lidltool.connectors.auth.browser_runtime.subprocess.run", return_value=_Completed()):
                callback = _read_callback_from_system_browser_tabs(
                    target=target,
                    callback_prefixes=("https://www.penny.de/app/login",),
                    expected_callback_state="expected-state",
                )

        self.assertEqual(
            callback,
            "https://www.penny.de/app/login?code=test-code&state=expected-state",
        )

    def test_prefers_system_profile_handoff_for_interactive_oauth_callback_flows(self) -> None:
        plan = AuthBrowserPlan(
            start_url="https://account.penny.de/auth",
            callback_url_prefixes=("https://www.penny.de/app/login",),
            expected_callback_state="state-1",
        )

        with patch(
            "lidltool.connectors.auth.browser_runtime._resolve_system_chromium_profile_target",
            return_value=object(),
        ):
            with patch("lidltool.connectors.auth.browser_runtime.sys.platform", "darwin"):
                enabled = _should_use_system_profile_browser_handoff(
                    plan=plan,
                    mode="local_display",
                    environment={},
                )

        self.assertTrue(enabled)

    def test_system_profile_handoff_can_wait_for_manual_browser_open(self) -> None:
        target = SystemChromiumProfileTarget(
            executable_path=Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            app_bundle_path=Path("/Applications/Google Chrome.app"),
            browser_name="Google Chrome",
            user_data_dir=Path("/tmp/chrome"),
            profile_name="Default",
            history_db_path=Path("/tmp/chrome/Default/History"),
        )
        request = type("Request", (), {})()
        request.plan = AuthBrowserPlan(
            start_url="https://account.penny.de/auth",
            callback_url_prefixes=("https://www.penny.de/app/login",),
            expected_callback_state="state-1",
            auto_launch_browser=False,
        )

        with patch(
            "lidltool.connectors.auth.browser_runtime._resolve_system_chromium_profile_target",
            return_value=target,
        ):
            with patch(
                "lidltool.connectors.auth.browser_runtime._wait_for_callback_in_system_profile_browser",
                return_value="https://www.penny.de/app/login?code=test-code&state=state-1",
            ) as wait_mock:
                with patch(
                    "lidltool.connectors.auth.browser_runtime._launch_system_profile_browser"
                ) as launch_mock:
                    callback_url, storage_state = _capture_system_profile_browser_result(
                        request=request,
                        environment={},
                    )

        self.assertEqual(
            callback_url,
            "https://www.penny.de/app/login?code=test-code&state=state-1",
        )
        self.assertIsNone(storage_state)
        launch_mock.assert_not_called()
        wait_mock.assert_called_once()
        self.assertFalse(wait_mock.call_args.kwargs["auto_launch_browser"])

    def test_prefers_external_chromium_for_interactive_oauth_callback_flows(self) -> None:
        plan = AuthBrowserPlan(
            start_url="https://account.penny.de/auth",
            callback_url_prefixes=("https://www.penny.de/app/login",),
            expected_callback_state="state-1",
        )

        self.assertTrue(
            _should_use_external_chromium_handoff(
                plan=plan,
                mode="local_display",
                environment={},
                executable_path=Path("/Applications/Google Chrome.app"),
            )
        )

    def test_external_chromium_handoff_stays_disabled_without_oauth_callback_state(self) -> None:
        plan = AuthBrowserPlan(
            start_url="https://www.rewe.de/",
            callback_url_prefixes=("https://www.rewe.de/",),
        )

        self.assertFalse(
            _should_use_external_chromium_handoff(
                plan=plan,
                mode="local_display",
                environment={},
                executable_path=Path("/Applications/Google Chrome.app"),
            )
        )

    def test_external_chromium_handoff_respects_env_disable_flag(self) -> None:
        plan = AuthBrowserPlan(
            start_url="https://account.penny.de/auth",
            callback_url_prefixes=("https://www.penny.de/app/login",),
            expected_callback_state="state-1",
        )

        self.assertFalse(
            _should_use_external_chromium_handoff(
                plan=plan,
                mode="local_display",
                environment={"LIDLTOOL_AUTH_BROWSER_PREFER_EXTERNAL_CHROMIUM": "false"},
                executable_path=Path("/Applications/Google Chrome.app"),
            )
        )

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
