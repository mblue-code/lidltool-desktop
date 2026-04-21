import assert from "node:assert/strict";
import test from "node:test";

import {
  buildBackendServeArgs,
  normalizeDesktopOcrProvider,
  resolveManagedPlaywrightBrowsersPath,
  shouldManagePlaywrightBrowsers
} from "../src/main/runtime-contract.ts";

test("normalizes unsupported desktop OCR providers to a backend-supported default", () => {
  assert.equal(normalizeDesktopOcrProvider("desktop_local"), "glm_ocr_local");
  assert.equal(normalizeDesktopOcrProvider(" DESKTOP_LOCAL "), "glm_ocr_local");
  assert.equal(normalizeDesktopOcrProvider(""), "glm_ocr_local");
  assert.equal(normalizeDesktopOcrProvider(undefined), "glm_ocr_local");
});

test("preserves supported backend OCR providers", () => {
  assert.equal(normalizeDesktopOcrProvider("glm_ocr_local"), "glm_ocr_local");
  assert.equal(normalizeDesktopOcrProvider("openai_compatible"), "openai_compatible");
  assert.equal(normalizeDesktopOcrProvider("external_api"), "external_api");
});

test("builds backend serve args without the removed desktop flag", () => {
  const args = buildBackendServeArgs("/tmp/lidltool.sqlite", 18765);

  assert.deepEqual(args, [
    "--db",
    "/tmp/lidltool.sqlite",
    "serve",
    "--host",
    "127.0.0.1",
    "--port",
    "18765"
  ]);
  assert.equal(args.includes("--desktop-mode"), false);
});

test("detects when desktop should manage playwright browsers outside the venv", () => {
  assert.equal(shouldManagePlaywrightBrowsers("/tmp/backend-venv/bin/python"), true);
  assert.equal(shouldManagePlaywrightBrowsers("/tmp/.backend/venv/bin/python"), true);
  assert.equal(shouldManagePlaywrightBrowsers("python3"), false);
});

test("resolves managed playwright browser storage under user data", () => {
  assert.equal(
    resolveManagedPlaywrightBrowsersPath("/tmp/lidltool-user-data", "/tmp/backend-venv/bin/python", undefined),
    "/tmp/lidltool-user-data/playwright-browsers"
  );
  assert.equal(
    resolveManagedPlaywrightBrowsersPath("/tmp/lidltool-user-data", "/tmp/backend-venv/bin/python", "/custom/browsers"),
    "/custom/browsers"
  );
  assert.equal(
    resolveManagedPlaywrightBrowsersPath("/tmp/lidltool-user-data", "python3", undefined),
    null
  );
});
