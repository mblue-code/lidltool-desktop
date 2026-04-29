import assert from "node:assert/strict";
import test from "node:test";

import { redactSensitiveText, sanitizeDiagnosticValue } from "../src/main/diagnostics/sanitization.ts";

test("redacts token-like assignments and auth headers", () => {
  const input = [
    "access_token=abc123456789012345678901234567890",
    "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456",
    "url=https://example.test/callback?code=secret-code&state=secret-state"
  ].join("\n");

  const redacted = redactSensitiveText(input, null);

  assert.doesNotMatch(redacted, /abc123456789012345678901234567890/);
  assert.doesNotMatch(redacted, /abcdefghijklmnopqrstuvwxyz123456/);
  assert.doesNotMatch(redacted, /secret-code/);
  assert.doesNotMatch(redacted, /secret-state/);
  assert.match(redacted, /<redacted>/);
});

test("redacts sensitive object keys recursively", () => {
  const redacted = sanitizeDiagnosticValue({
    ok: true,
    nested: {
      refreshToken: "should-not-leak",
      path: "/Users/example/profile"
    }
  }, "/Users/example");

  assert.deepEqual(redacted, {
    ok: true,
    nested: {
      refreshToken: "<redacted>",
      path: "<home>/profile"
    }
  });
});

