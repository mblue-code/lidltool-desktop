import assert from "node:assert/strict";
import test from "node:test";

import { buildConnectorSyncArgs, buildExportArgs, buildSyncArgs } from "../src/main/runtime-cli-args.ts";

test("builds Lidl sync args without browser options unless full history is requested", () => {
  assert.deepEqual(buildConnectorSyncArgs("lidl_plus_de", { source: "lidl_plus_de" }), []);
  assert.deepEqual(buildConnectorSyncArgs("lidl_plus_de", { source: "lidl_plus_de", full: true }), ["--full"]);
});

test("builds Amazon sync args with normalized connector options", () => {
  assert.deepEqual(
    buildConnectorSyncArgs("amazon_de", {
      source: "amazon_de",
      headless: false,
      domain: " amazon.de ",
      years: 2,
      maxPages: 4
    }),
    [
      "--option",
      "headless=false",
      "--option",
      "domain=amazon.de",
      "--option",
      "years=2",
      "--option",
      "max_pages_per_year=4"
    ]
  );
});

test("builds generic browser sync args with max_pages", () => {
  assert.deepEqual(
    buildConnectorSyncArgs("dm_de", {
      source: "dm_de",
      maxPages: 3
    }),
    ["--option", "headless=true", "--option", "max_pages=3"]
  );
});

test("builds full sync command args including db and source", () => {
  assert.deepEqual(
    buildSyncArgs({ source: "amazon_de", years: 1 }, "/tmp/lidltool.sqlite"),
    [
      "--db",
      "/tmp/lidltool.sqlite",
      "--json",
      "connectors",
      "sync",
      "--source-id",
      "amazon_de",
      "--option",
      "headless=true",
      "--option",
      "years=1"
    ]
  );
});

test("builds export args with default and explicit formats", () => {
  assert.deepEqual(buildExportArgs({ outPath: " /tmp/out.json " }, "/tmp/lidltool.sqlite"), [
    "--db",
    "/tmp/lidltool.sqlite",
    "--json",
    "export",
    "--out",
    "/tmp/out.json",
    "--format",
    "json"
  ]);
  assert.deepEqual(buildExportArgs({ outPath: "/tmp/out.json", format: "json" }, "/tmp/lidltool.sqlite"), [
    "--db",
    "/tmp/lidltool.sqlite",
    "--json",
    "export",
    "--out",
    "/tmp/out.json",
    "--format",
    "json"
  ]);
});
