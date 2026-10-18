(() => {
  const config = JSON.parse(document.getElementById("stream-config").textContent);
  const tokenKey = `noobsquad-stream-presenter:${config.path}`;
  let token = window.location.hash.slice(1);
  let tokenSaved = false;
  try {
    if (!token) token = window.sessionStorage.getItem(tokenKey) || "";
    if (token) {
      window.sessionStorage.setItem(tokenKey, token);
      tokenSaved = true;
    }
  } catch (_error) {
    // Keep the fragment visible if session storage is unavailable so reload still works.
  }
  config.token = token;
  if (tokenSaved) {
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
  }
  const startButton = document.getElementById("start-share");
  const stopButton = document.getElementById("stop-share");
  const audioToggle = document.getElementById("share-audio");
  const status = document.getElementById("share-status");
  const quality = document.getElementById("share-quality");
  const preview = document.getElementById("preview");
  const diagnostics = window.NoobSquadStreamDiagnostics;
  const reportDiagnostic = (event, details = {}) => diagnostics?.report(event, details);
  reportDiagnostic("publisher.page.loaded");
  const DEFAULT_ICE_SERVERS = [
    { urls: "stun:stun.l.google.com:19302" },
    { urls: "stun:stun1.l.google.com:19302" },
  ];

  function setStatus(message, kind = "") {
    status.textContent = message;
    status.className = `status ${kind}`.trim();
  }

  if (!config.token) {
    startButton.disabled = true;
    setStatus("Link privado inválido. Peça um novo link ao bot.", "error");
    return;
  }

  if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
    startButton.disabled = true;
    setStatus("Este navegador não oferece captura de tela. Abra o link em um navegador atualizado e seguro.", "error");
    return;
  }

  let displayStream = null;
  let peer = null;
  let stopping = false;
  let reconnecting = false;
  let reconnectTimer = null;
  let publisherRunId = 0;
  let heartbeatTimer = null;
  let heartbeatRequest = null;
  let missedHeartbeats = 0;
  let qualityTimer = null;
  let captureSummary = "";
  let publishAttemptNumber = 0;

  function delay(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }

  function createPeerConnection() {
    const iceServers = Array.isArray(config.iceServers) && config.iceServers.length
      ? config.iceServers
      : DEFAULT_ICE_SERVERS;
    return new RTCPeerConnection({ iceServers });
  }

  async function configureVideoSender(sender) {
    try {
      const parameters = sender.getParameters();
      if (!parameters.encodings?.length) return;
      parameters.encodings[0].maxBitrate = 8_000_000;
      parameters.encodings[0].maxFramerate = 30;
      parameters.degradationPreference = "maintain-resolution";
      await sender.setParameters(parameters);
    } catch (error) {
      console.warn("Não foi possível aplicar o perfil de qualidade da transmissão.", error);
    }
  }

  function showCaptureQuality(track) {
    const settings = track.getSettings();
    const dimensions = settings.width && settings.height
      ? `${settings.width}×${settings.height}`
      : "resolução informada pelo navegador";
    const frameRate = Number.isFinite(settings.frameRate)
      ? `${settings.frameRate.toFixed(0)} fps`
      : "taxa de quadros variável";
    captureSummary = `Captura: ${dimensions}, ${frameRate}`;
    quality.textContent = `${captureSummary}. Meta: até 1920×1080/30 fps e limite de 8 Mbps; o navegador ajusta conforme tela, CPU e rede.`;
    reportDiagnostic("publisher.capture.started", {
      trackKind: track.kind,
      videoWidth: settings.width,
      videoHeight: settings.height,
      framesPerSecond: settings.frameRate,
      displaySurface: settings.displaySurface,
    });
  }

  async function reportSelectedCandidate(connection, role) {
    try {
      const stats = await connection.getStats();
      let selectedPair = null;
      stats.forEach((entry) => {
        if (entry.type === "candidate-pair" && (entry.selected || (entry.nominated && entry.state === "succeeded"))) {
          selectedPair = entry;
        }
      });
      if (!selectedPair) return;
      const local = stats.get(selectedPair.localCandidateId);
      const remote = stats.get(selectedPair.remoteCandidateId);
      reportDiagnostic(`${role}.ice.selected`, {
        selectedLocalCandidateType: local?.candidateType,
        selectedRemoteCandidateType: remote?.candidateType,
        selectedLocalCandidateProtocol: local?.protocol,
        selectedRemoteCandidateProtocol: remote?.protocol,
        candidatePairState: selectedPair.state,
        rttMs: Number.isFinite(selectedPair.currentRoundTripTime)
          ? selectedPair.currentRoundTripTime * 1000
          : undefined,
      });
    } catch (_error) {
      // Some browsers restrict candidate-pair statistics.
    }
  }

  function stopQualityMonitor() {
    if (qualityTimer !== null) {
      window.clearInterval(qualityTimer);
      qualityTimer = null;
    }
  }

  function startQualityMonitor(connection, sender, runId) {
    stopQualityMonitor();
    let previous = null;
    let lastDiagnosticAt = 0;
    qualityTimer = window.setInterval(async () => {
      if (connection !== peer || runId !== publisherRunId || stopping) return;
      try {
        const report = await sender.getStats();
        let videoStats = null;
        report.forEach((entry) => {
          if (
            entry.type === "outbound-rtp" &&
            (entry.kind === "video" || entry.mediaType === "video") &&
            !entry.isRemote
          ) videoStats = entry;
        });
        if (!videoStats) return;

        let framesPerSecond = videoStats.framesPerSecond;
        let bitrate = null;
        if (previous && videoStats.timestamp > previous.timestamp) {
          const elapsed = (videoStats.timestamp - previous.timestamp) / 1000;
          if (!Number.isFinite(framesPerSecond) && Number.isFinite(videoStats.framesEncoded)) {
            framesPerSecond = (videoStats.framesEncoded - previous.framesEncoded) / elapsed;
          }
          if (Number.isFinite(videoStats.bytesSent)) {
            bitrate = ((videoStats.bytesSent - previous.bytesSent) * 8) / elapsed / 1_000_000;
          }
        }
        previous = {
          timestamp: videoStats.timestamp,
          bytesSent: videoStats.bytesSent || 0,
          framesEncoded: videoStats.framesEncoded || 0,
        };

        const fpsLabel = Number.isFinite(framesPerSecond)
          ? `${framesPerSecond.toFixed(0)} fps enviados`
          : "medindo fps";
        const bitrateLabel = Number.isFinite(bitrate)
          ? `${bitrate.toFixed(1)} Mbps enviados`
          : "medindo bitrate";
        quality.textContent = `${captureSummary} · ${fpsLabel} · ${bitrateLabel} (limite 8 Mbps).`;
        if (Date.now() - lastDiagnosticAt >= 15000) {
          lastDiagnosticAt = Date.now();
          reportDiagnostic("publisher.video.stats", {
            framesPerSecond,
            bitrateMbps: bitrate,
          });
        }
      } catch (_error) {
        // Browsers may temporarily omit outbound statistics during renegotiation.
      }
    }, 2500);
  }

  function waitForIceGathering(connection) {
    const startedAt = Date.now();
    if (connection.iceGatheringState === "complete") {
      reportDiagnostic("publisher.ice.gathered", { durationMs: 0, iceGatheringState: "complete" });
      return Promise.resolve();
    }
    reportDiagnostic("publisher.ice.gather.started", { iceGatheringState: connection.iceGatheringState });
    return new Promise((resolve) => {
      const timeout = window.setTimeout(() => finish(true), 10000);
      function finish(timedOut = false) {
        window.clearTimeout(timeout);
        connection.removeEventListener("icegatheringstatechange", check);
        reportDiagnostic(
          timedOut ? "publisher.ice.gather.timeout" : "publisher.ice.gathered",
          { durationMs: Date.now() - startedAt, iceGatheringState: connection.iceGatheringState },
        );
        resolve();
      }
      function check() {
        if (connection.iceGatheringState === "complete") finish();
      }
      connection.addEventListener("icegatheringstatechange", check);
    });
  }

  function waitForConnection(connection, timeoutMs = 20000) {
    return new Promise((resolve, reject) => {
      let timeout;
      const cleanup = () => {
        window.clearTimeout(timeout);
        connection.removeEventListener("connectionstatechange", check);
      };
      const check = () => {
        if (connection.connectionState === "connected") {
          cleanup();
          resolve();
        } else if (["failed", "closed"].includes(connection.connectionState)) {
          cleanup();
          reportDiagnostic("publisher.connection.failed", {
            connectionState: connection.connectionState,
            iceConnectionState: connection.iceConnectionState,
          });
          void reportSelectedCandidate(connection, "publisher");
          reject(new Error("A conexão WebRTC com o servidor de mídia falhou."));
        }
      };
      timeout = window.setTimeout(() => {
        cleanup();
        reportDiagnostic("publisher.connection.timeout", {
          connectionState: connection.connectionState,
          iceConnectionState: connection.iceConnectionState,
        });
        void reportSelectedCandidate(connection, "publisher");
        reject(new Error("Tempo esgotado ao conectar ao servidor de mídia."));
      }, timeoutMs);
      connection.addEventListener("connectionstatechange", check);
      check();
    });
  }

  async function reportState(state) {
    try {
      const response = await fetch(config.statusUrl, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${config.token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ state }),
        keepalive: true,
      });
      if (!response.ok) return false;
      const payload = await response.json();
      return payload.state === state;
    } catch (_error) {
      return false;
    }
  }

  function stopHeartbeat() {
    if (heartbeatTimer !== null) {
      window.clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
    missedHeartbeats = 0;
  }

  function startHeartbeat(connection, runId) {
    stopHeartbeat();
    heartbeatTimer = window.setInterval(async () => {
      if (
        heartbeatRequest || connection !== peer || runId !== publisherRunId ||
        stopping || connection.connectionState !== "connected"
      ) return;

      heartbeatRequest = reportState("live");
      let confirmed = false;
      try {
        confirmed = await heartbeatRequest;
      } finally {
        heartbeatRequest = null;
      }

      if (confirmed) {
        missedHeartbeats = 0;
        return;
      }

      missedHeartbeats += 1;
      if (missedHeartbeats >= 2 && connection === peer && !stopping && !reconnecting) {
        setStatus("O servidor deixou de confirmar o vídeo. Tentando reconectar sem encerrar a captura.", "error");
        void publishWithRetry();
      }
    }, 5000);
  }

  async function reportReady() {
    stopHeartbeat();
    if (heartbeatRequest) await heartbeatRequest;
    return reportState("ready");
  }

  function closePeer() {
    stopQualityMonitor();
    if (!peer) return;
    const previousPeer = peer;
    peer = null;
    previousPeer.onconnectionstatechange = null;
    previousPeer.close();
  }

  function monitorPeer(connection, runId) {
    connection.onconnectionstatechange = () => {
      if (connection !== peer || runId !== publisherRunId || stopping) return;

      if (connection.connectionState === "connected") {
        reportDiagnostic("publisher.connection.state", {
          connectionState: connection.connectionState,
          iceConnectionState: connection.iceConnectionState,
        });
        void reportSelectedCandidate(connection, "publisher");
        if (reconnectTimer !== null) {
          window.clearTimeout(reconnectTimer);
          reconnectTimer = null;
        }
        if (!reconnecting) setStatus("Você está ao vivo.", "live");
        return;
      }

      if (connection.connectionState === "disconnected") {
        reportDiagnostic("publisher.connection.state", {
          connectionState: connection.connectionState,
          iceConnectionState: connection.iceConnectionState,
        });
        setStatus("Conexão instável. Mantendo a captura e tentando recuperar o vídeo.", "error");
        if (reconnectTimer === null) {
          reconnectTimer = window.setTimeout(() => {
            reconnectTimer = null;
            if (
              connection === peer &&
              connection.connectionState === "disconnected" &&
              !reconnecting
            ) {
              void publishWithRetry();
            }
          }, 6000);
        }
      } else if (connection.connectionState === "failed" && !reconnecting) {
        reportDiagnostic("publisher.connection.failed", {
          connectionState: connection.connectionState,
          iceConnectionState: connection.iceConnectionState,
        });
        void reportSelectedCandidate(connection, "publisher");
        void publishWithRetry();
      }
    };
    connection.oniceconnectionstatechange = () => {
      if (connection !== peer || runId !== publisherRunId || stopping) return;
      reportDiagnostic(
        connection.iceConnectionState === "failed" ? "publisher.ice.failed" : "publisher.ice.state",
        { connectionState: connection.connectionState, iceConnectionState: connection.iceConnectionState },
      );
      if (connection.iceConnectionState === "failed") void reportSelectedCandidate(connection, "publisher");
    };
    connection.onicegatheringstatechange = () => {
      if (connection !== peer || runId !== publisherRunId || stopping) return;
      reportDiagnostic("publisher.ice.gathering", { iceGatheringState: connection.iceGatheringState });
    };
  }

  async function publishAttempt(runId) {
    if (!displayStream || stopping) throw new Error("A captura da tela foi encerrada.");
    const attempt = ++publishAttemptNumber;
    const attemptStartedAt = Date.now();

    const connection = createPeerConnection();
    peer = connection;
    reportDiagnostic("publisher.peer.created", { attempt });
    monitorPeer(connection, runId);
    for (const track of displayStream.getTracks()) {
      const sender = connection.addTrack(track, displayStream);
      if (track.kind === "video") await configureVideoSender(sender);
    }

    const offer = await connection.createOffer();
    await connection.setLocalDescription(offer);
    await waitForIceGathering(connection);
    if (runId !== publisherRunId || stopping || connection !== peer) return;

    const publishUrl = `${config.mediaUrl.replace(/\/$/, "")}/${encodeURIComponent(config.path)}/whip`;
    const requestStartedAt = Date.now();
    reportDiagnostic("publisher.whip.started", { attempt });
    const response = await fetch(publishUrl, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${config.token}`,
        "Content-Type": "application/sdp",
        "Accept": "application/sdp",
      },
      body: connection.localDescription.sdp,
    });
    reportDiagnostic("publisher.whip.response", {
      attempt,
      httpStatus: response.status,
      durationMs: Date.now() - requestStartedAt,
    });
    if (!response.ok) {
      const details = await response.text();
      reportDiagnostic("publisher.http.failed", { attempt, httpStatus: response.status });
      throw new Error(details || `O servidor de mídia respondeu ${response.status}.`);
    }

    const answer = await response.text();
    await connection.setRemoteDescription({ type: "answer", sdp: answer });
    await waitForConnection(connection);
    reportDiagnostic("publisher.connected", {
      attempt,
      durationMs: Date.now() - attemptStartedAt,
      connectionState: connection.connectionState,
      iceConnectionState: connection.iceConnectionState,
    });
    if (runId !== publisherRunId || stopping || connection !== peer) return;

    if (!(await reportState("live"))) {
      throw new Error("O MediaMTX ainda não confirmou que o vídeo está disponível.");
    }
    if (runId !== publisherRunId || stopping || connection !== peer) {
      await reportState("ready");
      return;
    }

    startHeartbeat(connection, runId);
    const videoSender = connection.getSenders().find((sender) => sender.track?.kind === "video");
    if (videoSender) startQualityMonitor(connection, videoSender, runId);

    const hasAudio = displayStream.getAudioTracks().length > 0;
    setStatus(
      hasAudio ? "Você está ao vivo com áudio." : "Você está ao vivo (somente vídeo).",
      "live"
    );
  }

  async function publishWithRetry() {
    if (reconnecting || stopping || !displayStream) return;
    reconnecting = true;
    const runId = ++publisherRunId;
    let retryDelay = 1000;

    stopHeartbeat();
    stopQualityMonitor();
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    await reportReady();
    if (runId !== publisherRunId || stopping || !displayStream) return;
    closePeer();

    try {
      while (displayStream && !stopping && runId === publisherRunId) {
        try {
          setStatus("Conectando ao servidor de mídia. A captura permanecerá ativa.");
          await publishAttempt(runId);
          if (runId === publisherRunId && !stopping && peer) return;
        } catch (error) {
          if (runId !== publisherRunId || stopping || !displayStream) break;
          closePeer();
          await reportState("ready");
          if (runId !== publisherRunId || stopping || !displayStream) break;
          reportDiagnostic("publisher.retry", {
            attempt: publishAttemptNumber,
            retryMs: retryDelay,
            errorName: error?.name || "Error",
            errorMessage: error?.message || String(error),
          });
          setStatus(
            `Sem conexão com o servidor de mídia. A tela continua capturada; tentando novamente em ${Math.ceil(retryDelay / 1000)}s. ${error.message || error}`,
            "error"
          );
          await delay(retryDelay);
          retryDelay = Math.min(retryDelay * 2, 8000);
        }
      }
    } finally {
      if (runId === publisherRunId) reconnecting = false;
    }
  }

  async function stopShare(message = "A transmissão foi encerrada.") {
    if (stopping) return;
    stopping = true;
    publisherRunId += 1;
    reconnecting = false;
    stopHeartbeat();
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }

    const stream = displayStream;
    displayStream = null;
    closePeer();
    if (stream) {
      for (const track of stream.getTracks()) track.stop();
    }
    preview.srcObject = null;
    quality.textContent = "";
    await reportReady();
    startButton.disabled = false;
    stopButton.disabled = true;
    setStatus(message);
    stopping = false;
  }

  async function startShare() {
    if (displayStream || stopping) return;
    startButton.disabled = true;
    setStatus("Escolha uma tela, janela ou aba na janela do navegador.");
    reportDiagnostic("publisher.capture.requested");

    try {
      displayStream = await navigator.mediaDevices.getDisplayMedia({
        video: {
          width: { ideal: 1920, max: 1920 },
          height: { ideal: 1080, max: 1080 },
          frameRate: { ideal: 30, max: 30 },
        },
        audio: audioToggle.checked,
      });
      preview.srcObject = displayStream;
      stopButton.disabled = false;
      for (const track of displayStream.getVideoTracks()) {
        if ("contentHint" in track) track.contentHint = "detail";
        showCaptureQuality(track);
        track.addEventListener("ended", () => {
          reportDiagnostic("publisher.track.ended", { trackKind: track.kind, trackState: track.readyState });
          void stopShare("O compartilhamento foi encerrado pelo navegador.");
        }, { once: true });
      }
      void publishWithRetry();
    } catch (error) {
      reportDiagnostic("publisher.capture.failed", {
        errorName: error?.name || "Error",
        errorMessage: error?.message || String(error),
      });
      displayStream = null;
      captureSummary = "";
      quality.textContent = "";
      startButton.disabled = false;
      stopButton.disabled = true;
      setStatus(
        error.name === "NotAllowedError"
          ? "O compartilhamento foi cancelado ou bloqueado no navegador."
          : `Não foi possível iniciar: ${error.message || error}`,
        "error"
      );
    }
  }

  startButton.addEventListener("click", () => void startShare());
  stopButton.addEventListener("click", () => void stopShare());
  window.addEventListener("beforeunload", () => {
    stopping = true;
    publisherRunId += 1;
    stopHeartbeat();
    if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
    closePeer();
    if (displayStream) {
      for (const track of displayStream.getTracks()) track.stop();
    }
    displayStream = null;
    void reportReady();
  });
})();
