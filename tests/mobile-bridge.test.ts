import assert from "node:assert/strict";
import test from "node:test";

import {
  decideMobileBridgeRoute,
  discoverPrivateMobileInterfaces,
  isAllowedBridgeRemoteAddress,
  isAllowedPrivateBridgeAddress,
  selectPrivateMobileInterface
} from "../src/main/mobile-bridge.ts";

test("private mobile interface discovery rejects public loopback unspecified and virtual interfaces", () => {
  const interfaces = {
    lo0: [{ address: "127.0.0.1", family: "IPv4", internal: true, cidr: "127.0.0.1/8", mac: "00:00:00:00:00:00", netmask: "255.0.0.0" }],
    en0: [{ address: "192.168.1.24", family: "IPv4", internal: false, cidr: "192.168.1.24/24", mac: "aa:bb:cc:dd:ee:ff", netmask: "255.255.255.0" }],
    en1: [{ address: "8.8.8.8", family: "IPv4", internal: false, cidr: "8.8.8.8/24", mac: "aa:bb:cc:dd:ee:00", netmask: "255.255.255.0" }],
    docker0: [{ address: "172.17.0.1", family: "IPv4", internal: false, cidr: "172.17.0.1/16", mac: "aa:bb:cc:dd:ee:11", netmask: "255.255.0.0" }],
    vmnet1: [{ address: "192.168.64.1", family: "IPv4", internal: false, cidr: "192.168.64.1/24", mac: "aa:bb:cc:dd:ee:22", netmask: "255.255.255.0" }],
    utun4: [{ address: "10.8.0.2", family: "IPv4", internal: false, cidr: "10.8.0.2/24", mac: "aa:bb:cc:dd:ee:33", netmask: "255.255.255.0" }],
    bad: [{ address: "0.0.0.0", family: "IPv4", internal: false, cidr: "0.0.0.0/0", mac: "aa:bb:cc:dd:ee:44", netmask: "0.0.0.0" }]
  };

  assert.equal(isAllowedPrivateBridgeAddress("0.0.0.0"), false);
  assert.equal(isAllowedPrivateBridgeAddress("127.0.0.1"), false);
  assert.equal(isAllowedPrivateBridgeAddress("8.8.8.8"), false);
  assert.equal(isAllowedPrivateBridgeAddress("192.168.1.24"), true);
  assert.deepEqual(discoverPrivateMobileInterfaces(interfaces).map((entry) => entry.address), ["192.168.1.24"]);
  assert.equal(selectPrivateMobileInterface(undefined, interfaces).address, "192.168.1.24");
  assert.throws(() => selectPrivateMobileInterface("8.8.8.8", interfaces), /not an allowed private LAN/);
});

test("mobile bridge route allowlist excludes desktop frontend auth and setup routes", () => {
  assert.equal(decideMobileBridgeRoute("POST", "/api/mobile-pair/v1/handshake").allowed, true);
  assert.equal(decideMobileBridgeRoute("POST", "/api/mobile-captures/v1").allowed, true);
  assert.equal(decideMobileBridgeRoute("GET", "/api/mobile-sync/v1/changes?cursor=abc").allowed, true);
  assert.equal(decideMobileBridgeRoute("POST", "/api/mobile-sync/v1/manual-transactions").allowed, true);
  assert.equal(decideMobileBridgeRoute("GET", "/api/mobile-local/v1/health").allowed, true);

  assert.equal(decideMobileBridgeRoute("GET", "/").allowed, false);
  assert.equal(decideMobileBridgeRoute("GET", "/setup").allowed, false);
  assert.equal(decideMobileBridgeRoute("GET", "/assets/index.js").allowed, false);
  assert.equal(decideMobileBridgeRoute("GET", "/api/v1/auth/me").allowed, false);
  assert.equal(decideMobileBridgeRoute("POST", "/api/mobile-pair/v1/sessions").allowed, false);
  assert.equal(decideMobileBridgeRoute("GET", "/api/mobile-captures/v1").allowed, false);
});

test("mobile bridge only accepts loopback or private remote clients", () => {
  assert.equal(isAllowedBridgeRemoteAddress("127.0.0.1"), true);
  assert.equal(isAllowedBridgeRemoteAddress("::1"), true);
  assert.equal(isAllowedBridgeRemoteAddress("::ffff:192.168.1.10"), true);
  assert.equal(isAllowedBridgeRemoteAddress("10.0.0.25"), true);
  assert.equal(isAllowedBridgeRemoteAddress("172.16.4.3"), true);
  assert.equal(isAllowedBridgeRemoteAddress("8.8.8.8"), false);
  assert.equal(isAllowedBridgeRemoteAddress(""), false);
});
