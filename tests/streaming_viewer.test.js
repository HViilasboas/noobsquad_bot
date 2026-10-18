const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

const viewerSource = fs.readFileSync(
  path.join(__dirname, "..", "bot", "static", "viewer.js"),
  "utf8",
);

class FakePeerConnection {
  constructor() {
    this.connectionState = "new";
    this.iceConnectionState = "new";
    this.iceGatheringState = "complete";
    this.listeners = new Map();
    this.localDescription = null;
    this.remoteDescription = null;
    this.closeCount = 0;
    this.transceivers = [];
    FakePeerConnection.instances.push(this);
  }

  addTransceiver(kind, options) {
    this.transceivers.push({ kind, options });
  }

  addEventListener(name, callback) {
    const callbacks = this.listeners.get(name) || new Set();
    callbacks.add(callback);
    this.listeners.set(name, callbacks);
  }

  removeEventListener(name, callback) {
    this.listeners.get(name)?.delete(callback);
  }

  dispatch(name) {
    for (const callback of this.listeners.get(name) || []) callback();
  }

  async createOffer() {
    return { type: "offer", sdp: "fake offer" };
  }

  async setLocalDescription(description) {
    this.localDescription = description;
  }

  async setRemoteDescription(description) {
    this.remoteDescription = description;
    this.connectionState = "connected";
    this.iceConnectionState = "connected";
    this.ontrack?.({ streams: [{ id: "test-stream" }], track: { kind: "video" } });
    this.dispatch("connectionstatechange");
  }

  close() {
    this.closeCount += 1;
    this.connectionState = "closed";
    this.iceConnectionState = "closed";
    this.dispatch("connectionstatechange");
  }
}

FakePeerConnection.instances = [];

function createViewerHarness({ hash = "#test-read-token", storedToken = null } = {}) {
  FakePeerConnection.instances = [];
  const elements = new Map();
  const timers = new Map();
  let nextTimerId = 0;
  let replacedUrl = null;
  const makeElement = (id) => {
    const listeners = new Map();
    const element = {
      id,
      textContent: "",
      className: "",
      disabled: false,
      muted: true,
      srcObject: null,
      readyState: 0,
      videoWidth: 0,
      videoHeight: 0,
      classList: { add() {}, remove() {} },
      addEventListener(name, callback) { listeners.set(name, callback); },
      emit(name) { listeners.get(name)?.(); },
      click() { listeners.get("click")?.(); },
      async play() {},
    };
    elements.set(id, element);
    return element;
  };

  const config = {
    path: "nss-test-session",
    token: "",
    mediaUrl: "https://stream.example.test/media",
    statusUrl: "/api/watch/nss-test-session/status",
    diagnosticsUrl: "/api/watch/nss-test-session/diagnostics",
    iceServers: [],
    ended: false,
  };
  for (const id of [
    "stream-config",
    "connect-viewer",
    "toggle-audio",
    "viewer-status",
    "viewer-quality",
    "stream-video",
  ]) makeElement(id);
  elements.get("stream-config").textContent = JSON.stringify(config);

  const calls = [];
  const diagnostics = [];
  const context = {
    console,
    document: { getElementById: (id) => elements.get(id) },
    window: {
      location: { hash, pathname: "/watch/nss-test-session", search: "" },
      history: { replaceState(_state, _title, url) { replacedUrl = url; } },
      sessionStorage: { setItem() {}, getItem() { return storedToken; } },
      setTimeout(callback, delay) {
        const id = ++nextTimerId;
        timers.set(id, { callback, delay });
        return id;
      },
      clearTimeout(id) { timers.delete(id); },
      MediaStream: class { constructor(tracks) { this.tracks = tracks; } },
      NoobSquadStreamDiagnostics: {
        report(event, details) { diagnostics.push({ event, details }); },
      },
    },
    RTCPeerConnection: FakePeerConnection,
    fetch: async (url, options = {}) => {
      calls.push({ url, options });
      if (!options.method) return { ok: true, json: async () => ({ state: "live" }) };
      return { ok: true, text: async () => "fake answer" };
    },
  };

  vm.runInNewContext(viewerSource, context, { filename: "viewer.js" });
  return {
    elements,
    calls,
    diagnostics,
    getReplacedUrl: () => replacedUrl,
    triggerTimer(delay) {
      const timer = [...timers.entries()].find(([, value]) => value.delay === delay);
      assert.ok(timer, `Expected a pending ${delay}ms timer`);
      timers.delete(timer[0]);
      timer[1].callback();
    },
  };
}

async function waitUntil(predicate, timeoutMs = 1000) {
  const deadline = Date.now() + timeoutMs;
  while (!predicate()) {
    if (Date.now() >= deadline) throw new Error("Timed out waiting for viewer state");
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
}

test("viewer keeps the WebRTC connection alive after connecting until it ends", async () => {
  const { elements, calls, diagnostics } = createViewerHarness();
  const button = elements.get("connect-viewer");

  button.click();
  await waitUntil(() => FakePeerConnection.instances[0]?.remoteDescription);
  await new Promise((resolve) => setTimeout(resolve, 40));

  const connection = FakePeerConnection.instances[0];
  assert.equal(connection.connectionState, "connected");
  assert.equal(connection.closeCount, 0);
  assert.equal(button.textContent, "Desconectar");
  assert.equal(elements.get("stream-video").srcObject.id, "test-stream");
  assert.ok(calls.some((call) => call.url.endsWith("/nss-test-session/whep")));
  assert.ok(diagnostics.some((event) => event.event === "viewer.whep.started"));
  assert.ok(diagnostics.some((event) => event.event === "viewer.whep.response"));
  assert.ok(diagnostics.some((event) => event.event === "viewer.connected"));
  assert.ok(diagnostics.some((event) => event.event === "viewer.track.received"));

  button.click();
  await waitUntil(() => button.textContent === "Conectar ao vivo");
  assert.equal(connection.closeCount, 1);
});

test("viewer restores its share token into a copied URL from session storage", () => {
  const { elements, getReplacedUrl } = createViewerHarness({
    hash: "",
    storedToken: "test-read-token",
  });

  assert.equal(elements.get("connect-viewer").disabled, false);
  assert.equal(
    getReplacedUrl(),
    "/watch/nss-test-session#test-read-token",
  );
});

test("viewer reports when WebRTC connects without decoding video frames", async () => {
  const { elements, diagnostics, triggerTimer } = createViewerHarness();
  const button = elements.get("connect-viewer");
  const status = elements.get("viewer-status");
  const video = elements.get("stream-video");

  button.click();
  await waitUntil(() => FakePeerConnection.instances[0]?.remoteDescription);
  triggerTimer(10000);

  assert.match(status.textContent, /não decodificou nenhum quadro/);
  assert.match(elements.get("viewer-quality").textContent, /conexão de mídia está ativa/);

  video.videoWidth = 1920;
  video.videoHeight = 1080;
  video.readyState = 2;
  video.emit("loadeddata");
  assert.equal(status.textContent, "Vídeo reproduzindo.");
  assert.match(elements.get("viewer-quality").textContent, /1920×1080/);
  assert.ok(diagnostics.some((event) => event.event === "viewer.video.first_frame"));

  button.click();
  await waitUntil(() => button.textContent === "Conectar ao vivo");
});

test("viewer does not treat a 2x2 placeholder as a decoded video frame", async () => {
  const { elements, diagnostics } = createViewerHarness();
  const button = elements.get("connect-viewer");
  const status = elements.get("viewer-status");
  const video = elements.get("stream-video");

  button.click();
  await waitUntil(() => FakePeerConnection.instances[0]?.remoteDescription);

  video.readyState = 4;
  video.videoWidth = 2;
  video.videoHeight = 2;
  video.emit("loadeddata");

  assert.notEqual(status.textContent, "Vídeo reproduzindo.");
  assert.ok(diagnostics.some((event) => event.event === "viewer.video.placeholder"));
  assert.equal(diagnostics.some((event) => event.event === "viewer.video.first_frame"), false);

  button.click();
  await waitUntil(() => button.textContent === "Conectar ao vivo");
});
