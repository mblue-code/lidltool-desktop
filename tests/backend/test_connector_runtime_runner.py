from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from lidltool.connectors.runtime.protocol import (
    build_runtime_request_envelope,
    dump_runtime_envelope_json,
    parse_runtime_response_envelope,
)


class ConnectorRuntimeRunnerTest(unittest.TestCase):
    def test_plugin_stdout_is_redirected_to_stderr(self) -> None:
        with tempfile.TemporaryDirectory(prefix="desktop-runtime-runner-") as tmpdir:
            plugin_path = Path(tmpdir) / "noisy_plugin.py"
            plugin_path.write_text(
                textwrap.dedent(
                    """
                    from lidltool.connectors.sdk.receipt import DiagnosticsOutput, GetDiagnosticsResponse


                    class NoisyPlugin:
                        def invoke_action(self, request):
                            print("plugin-noise-on-stdout", flush=True)
                            return GetDiagnosticsResponse(
                                output=DiagnosticsOutput(diagnostics={"status": "ok"})
                            )
                    """
                ).strip()
                + "\n",
                encoding="utf-8",
            )

            request = build_runtime_request_envelope(
                plugin_id="local.test_noisy",
                source_id="test_noisy",
                runtime_kind="subprocess_python",
                entrypoint=f"{plugin_path}:NoisyPlugin",
                request={
                    "contract_version": "1",
                    "plugin_family": "receipt",
                    "action": "get_diagnostics",
                    "input": {},
                },
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "lidltool.connectors.runtime.runner",
                    "--entrypoint",
                    f"{plugin_path}:NoisyPlugin",
                ],
                input=dump_runtime_envelope_json(request),
                text=True,
                capture_output=True,
                check=True,
            )

        envelope = parse_runtime_response_envelope(result.stdout)
        self.assertTrue(envelope.ok)
        self.assertIsNotNone(envelope.response)
        response_payload = envelope.response.model_dump(mode="python")
        self.assertEqual(response_payload["action"], "get_diagnostics")
        self.assertEqual(response_payload["output"]["diagnostics"], {"status": "ok"})
        self.assertIn("plugin-noise-on-stdout", result.stderr)


if __name__ == "__main__":
    unittest.main()
