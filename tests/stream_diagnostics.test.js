const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const diagnosticsSource = fs.readFileSync(
  path.join(__dirname, "..", "bot", "static", "stream-diagnostics.js"),
  "utf8",
);

test("diagnostics send authenticated, allowlisted client events", () => {
  const configElement = {
    textContent: JSON.stringify({
      path: "nss-test-session",
      diagnosticsUrl: "/api/watch/nss-test-session/diagnostics",
    }),
  };
  const storage = new Map();
  const requests = [];
  const context = {
    document: {
      body: { dataset: { streamRole: "watch" } },
      getElementById(id) { return id === "stream-config" ? configElement : null; },
    },
    window: {
      location: { hash: "#read-secret" },
      sessionStorage: {
        setItem(key, value) { storage.set(key, value); },
        getItem(key) { return storage.get(key) || null; },
      },
      crypto: { randomUUID: () => "client_test_123" },
      navigator: { userAgent: "Test browser" },
      fetch(url, options) { requests.push({ url, options }); return Promise.resolve({ ok: true }); },
    },
  };

  vm.runInNewContext(diagnosticsSource, context, { filename: "stream-diagnostics.js" });
  context.window.NoobSquadStreamDiagnostics.report("viewer.ice.failed", {
    connectionState: "failed",
    rttMs: 42.5,
    sdp: "PRIVATE_SDP",
  });

  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, "/api/watch/nss-test-session/diagnostics");
  assert.equal(requests[0].options.headers.Authorization, "Bearer read-secret");
  const payload = JSON.parse(requests[0].options.body);
  assert.equal(payload.clientId, "client_test_123");
  assert.equal(payload.details.connectionState, "failed");
  assert.equal(payload.details.rttMs, 42.5);
  assert.equal("sdp" in payload.details, false);
});
