(() => {
  const config = JSON.parse(document.getElementById("stream-config").textContent);
  const tokenKey = `noobsquad-stream-viewer:${config.path}`;
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
  if (tokenSaved && !window.location.hash) {
    const shareableUrl = `${window.location.pathname}${window.location.search}#${encodeURIComponent(token)}`;
    window.history.replaceState(null, "", shareableUrl);
  }
  const connectButton = document.getElementById("connect-viewer");
  const audioButton = document.getElementById("toggle-audio");
  const status = document.getElementById("viewer-status");
  const quality = document.getElementById("viewer-quality");
  const video = document.getElementById("stream-video");
  const diagnostics = window.NoobSquadStreamDiagnostics;
  const reportDiagnostic = (event, details = {}) => diagnostics?.report(event, details);
  reportDiagnostic("viewer.page.loaded");
  const DEFAULT_ICE_SERVERS = [
    { urls: "stun:stun.l.google.com:19302" },
    { urls: "stun:stun1.l.google.com:19302" },
  ];

  if (!config.token) {
    connectButton.disabled = true;
    setTimeout(() => setStatus("Link para assistir inválido.", "error"), 0);
    return;
  }

  let running = false;
  let peer = null;
  let frameWatchdogTimer = null;
  let retryAttempt = 0;
  let retryCycle = 0;
  let lastReportedSessionState = null;

  async function reportSelectedCandidate(connection) {
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
      reportDiagnostic("viewer.ice.selected", {
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

  function setStatus(message, kind = "") {
    status.textContent = message;
    status.className = `status ${kind}`.trim();
  }

  function delay(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }

  function clearFrameWatchdog() {
    if (frameWatchdogTimer !== null) {
      window.clearTimeout(frameWatchdogTimer);
      frameWatchdogTimer = null;
    }
  }

  function hasDecodedVideoFrame() {
    return video.readyState >= 2 && video.videoWidth >= 16 && video.videoHeight >= 16;
  }

  function startFrameWatchdog(connection) {
    clearFrameWatchdog();
    if (hasDecodedVideoFrame()) return;
    frameWatchdogTimer = window.setTimeout(() => {
      frameWatchdogTimer = null;
      if (connection === peer && running && !hasDecodedVideoFrame()) {
        reportDiagnostic("viewer.no_frames", {
          readyState: video.readyState,
          connectionState: connection.connectionState,
          iceConnectionState: connection.iceConnectionState,
        });
        setStatus(
          "WebRTC conectou, mas o navegador ainda não decodificou nenhum quadro de vídeo.",
          "error",
        );
        quality.textContent = "A conexão de mídia está ativa; aguardando quadros exibíveis.";
      }
    }, 10000);
  }

  function describeConnectionError(error) {
    const message = error && error.message ? error.message : String(error);
    if (/no stream is available on path/i.test(message)) {
      return "O vídeo ainda não chegou ao servidor. Aguardando o apresentador conectar ou reconectar.";
    }
    if (/failed to fetch|networkerror/i.test(message)) {
      return "Não foi possível alcançar o servidor de mídia. Verifique a conexão de rede.";
    }
    if (/negociação ICE|conexão de mídia/i.test(message)) {
      return `${message} Confira UDP/TCP 28189 e, se a rede bloquear WebRTC direto, configure um servidor TURN.`;
    }
    return message;
  }

  function waitForIceGathering(connection) {
    const startedAt = Date.now();
    if (connection.iceGatheringState === "complete") {
      reportDiagnostic("viewer.ice.gathered", { durationMs: 0, iceGatheringState: "complete" });
      return Promise.resolve();
    }
    reportDiagnostic("viewer.ice.gather.started", { iceGatheringState: connection.iceGatheringState });
    return new Promise((resolve) => {
      const timeout = window.setTimeout(() => finish(true), 10000);
      function finish(timedOut = false) {
        window.clearTimeout(timeout);
        connection.removeEventListener("icegatheringstatechange", check);
        reportDiagnostic(
          timedOut ? "viewer.ice.gather.timeout" : "viewer.ice.gathered",
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

  async function getSessionState() {
    const startedAt = Date.now();
    const response = await fetch(config.statusUrl, {
      cache: "no-store",
      headers: { "Authorization": `Bearer ${config.token}` },
    });
    if (!response.ok) {
      reportDiagnostic("viewer.status.failed", {
        httpStatus: response.status,
        durationMs: Date.now() - startedAt,
      });
      throw new Error("A sessão não está mais disponível.");
    }
    const state = (await response.json()).state;
    if (state !== lastReportedSessionState) {
      lastReportedSessionState = state;
      reportDiagnostic("viewer.session.state", { sessionState: state });
    }
    return state;
  }

  async function connectToMedia() {
    const iceServers = Array.isArray(config.iceServers) && config.iceServers.length
      ? config.iceServers
      : DEFAULT_ICE_SERVERS;
    const connection = new RTCPeerConnection({ iceServers });
    peer = connection;
    retryAttempt += 1;
    const attemptStartedAt = Date.now();
    reportDiagnostic("viewer.peer.created", { attempt: retryAttempt });
    connection.addTransceiver("video", { direction: "recvonly" });
    connection.addTransceiver("audio", { direction: "recvonly" });
    connection.ontrack = (event) => {
      if (connection !== peer || !running) return;
      reportDiagnostic("viewer.track.received", {
        trackKind: event.track?.kind,
        trackState: event.track?.readyState,
      });
      if (event.streams && event.streams[0]) {
        video.srcObject = event.streams[0];
      } else {
        video.srcObject = new MediaStream([event.track]);
      }
      audioButton.disabled = false;
      void video.play().catch(() => {
        reportDiagnostic("viewer.play.rejected", { readyState: video.readyState });
        setStatus("Conectado. Use os controles do vídeo para iniciar a reprodução.", "live");
      });
    };
    connection.addEventListener("connectionstatechange", () => {
      if (connection !== peer || !running) return;
      const failed = connection.connectionState === "failed";
      reportDiagnostic(
        failed ? "viewer.connection.failed" : "viewer.connection.state",
        { connectionState: connection.connectionState, iceConnectionState: connection.iceConnectionState },
      );
      if (connection.connectionState === "connected" || failed) void reportSelectedCandidate(connection);
    });
    connection.addEventListener("iceconnectionstatechange", () => {
      if (connection !== peer || !running) return;
      const failed = connection.iceConnectionState === "failed";
      reportDiagnostic(
        failed ? "viewer.ice.failed" : "viewer.ice.state",
        { connectionState: connection.connectionState, iceConnectionState: connection.iceConnectionState },
      );
      if (failed) void reportSelectedCandidate(connection);
    });
    connection.addEventListener("icegatheringstatechange", () => {
      if (connection !== peer || !running) return;
      reportDiagnostic("viewer.ice.gathering", { iceGatheringState: connection.iceGatheringState });
    });

    const offer = await connection.createOffer();
    await connection.setLocalDescription(offer);
    await waitForIceGathering(connection);

    const readUrl = `${config.mediaUrl.replace(/\/$/, "")}/${encodeURIComponent(config.path)}/whep`;
    const requestStartedAt = Date.now();
    reportDiagnostic("viewer.whep.started", { attempt: retryAttempt });
    const response = await fetch(readUrl, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${config.token}`,
        "Content-Type": "application/sdp",
        "Accept": "application/sdp",
      },
      body: connection.localDescription.sdp,
    });
    reportDiagnostic("viewer.whep.response", {
      attempt: retryAttempt,
      httpStatus: response.status,
      durationMs: Date.now() - requestStartedAt,
    });
    if (!response.ok) {
      const details = await response.text();
      reportDiagnostic("viewer.http.failed", { attempt: retryAttempt, httpStatus: response.status });
      throw new Error(details || `O servidor de mídia respondeu ${response.status}.`);
    }

    const answer = await response.text();
    await connection.setRemoteDescription({ type: "answer", sdp: answer });
    await new Promise((resolve, reject) => {
      const cleanup = () => {
        window.clearTimeout(timeout);
        connection.removeEventListener("connectionstatechange", checkState);
      };
      const timeout = window.setTimeout(() => {
        cleanup();
        reportDiagnostic("viewer.connection.timeout", {
          connectionState: connection.connectionState,
          iceConnectionState: connection.iceConnectionState,
          durationMs: Date.now() - attemptStartedAt,
        });
        void reportSelectedCandidate(connection);
        reject(new Error(
          `Tempo esgotado na negociação ICE (conexão: ${connection.connectionState}; ICE: ${connection.iceConnectionState}).`
        ));
      }, 15000);
      const checkState = () => {
        if (connection.connectionState === "connected") {
          cleanup();
          window.clearTimeout(timeout);
          setStatus("Conectado ao vivo.", "live");
          reportDiagnostic("viewer.connected", {
            attempt: retryAttempt,
            durationMs: Date.now() - attemptStartedAt,
            connectionState: connection.connectionState,
            iceConnectionState: connection.iceConnectionState,
          });
          void reportSelectedCandidate(connection);
          resolve();
        } else if (["failed", "closed"].includes(connection.connectionState)) {
          cleanup();
          reportDiagnostic("viewer.connection.failed", {
            connectionState: connection.connectionState,
            iceConnectionState: connection.iceConnectionState,
            durationMs: Date.now() - attemptStartedAt,
          });
          void reportSelectedCandidate(connection);
          reject(new Error(
            `A conexão de mídia falhou (conexão: ${connection.connectionState}; ICE: ${connection.iceConnectionState}).`
          ));
        } else if (connection.connectionState === "disconnected") {
          setStatus("Conexão WebRTC instável; aguardando recuperação…", "error");
        }
      };
      connection.addEventListener("connectionstatechange", checkState);
      checkState();
    });
    startFrameWatchdog(connection);
  }

  function waitForConnectionEnd(connection) {
    return new Promise((resolve) => {
      let settled = false;
      let disconnectTimer = null;
      const cleanup = () => {
        connection.removeEventListener("connectionstatechange", checkState);
        clearFrameWatchdog();
        if (disconnectTimer !== null) {
          window.clearTimeout(disconnectTimer);
          disconnectTimer = null;
        }
      };
      const finish = (state) => {
        if (settled) return;
        settled = true;
        cleanup();
        resolve(state);
      };
      const checkState = () => {
        if (["failed", "closed"].includes(connection.connectionState)) {
          finish(connection.connectionState);
        } else if (connection.connectionState === "disconnected") {
          setStatus("Conexão WebRTC instável; aguardando recuperação…", "error");
          if (disconnectTimer === null) {
            disconnectTimer = window.setTimeout(() => {
              disconnectTimer = null;
              if (connection.connectionState === "disconnected") {
                finish("disconnected");
              }
            }, 5000);
          }
        } else if (connection.connectionState === "connected" && disconnectTimer !== null) {
          window.clearTimeout(disconnectTimer);
          disconnectTimer = null;
          setStatus("Conectado ao vivo.", "live");
        }
      };

      connection.addEventListener("connectionstatechange", checkState);
      checkState();
    });
  }

  async function runViewer() {
    running = true;
    connectButton.textContent = "Desconectar";
    connectButton.classList.remove("primary");
    connectButton.classList.add("secondary");

    while (running) {
      try {
        const state = await getSessionState();
        if (state === "ended") {
          setStatus("Esta transmissão foi encerrada.");
          break;
        }
        if (state !== "live") {
          setStatus("Aguardando o apresentador iniciar o compartilhamento.");
          await delay(1800);
          continue;
        }

        setStatus("Conectando ao vídeo…");
        await connectToMedia();
        const connectedPeer = peer;
        if (running && connectedPeer) {
          await waitForConnectionEnd(connectedPeer);
          if (!running) break;
          if (peer === connectedPeer) {
            connectedPeer.close();
            peer = null;
          }
          peer = null;
          setStatus("A conexão foi interrompida. Tentando reconectar…");
          await delay(1200);
        }
      } catch (error) {
        if (!running) break;
        retryCycle += 1;
        if (retryCycle <= 3 || retryCycle % 10 === 0) {
          reportDiagnostic("viewer.retry", {
            attempt: retryCycle,
            retryMs: 1800,
            errorName: error?.name || "Error",
            errorMessage: error?.message || String(error),
            connectionState: peer?.connectionState,
            iceConnectionState: peer?.iceConnectionState,
          });
        }
        if (peer) peer.close();
        peer = null;
        setStatus(`Aguardando vídeo: ${describeConnectionError(error)}`);
        await delay(1800);
      }
    }

    if (peer) peer.close();
    peer = null;
    running = false;
    connectButton.textContent = "Conectar ao vivo";
    connectButton.classList.remove("secondary");
    connectButton.classList.add("primary");
  }

  connectButton.addEventListener("click", () => {
    if (running) {
      running = false;
      if (peer) peer.close();
      peer = null;
      setStatus("Desconectado.");
    } else {
      void runViewer();
    }
  });

  video.addEventListener("loadedmetadata", () => {
    reportDiagnostic("viewer.video.metadata", {
      videoWidth: video.videoWidth,
      videoHeight: video.videoHeight,
      readyState: video.readyState,
    });
    if (video.videoWidth >= 16 && video.videoHeight >= 16) {
      quality.textContent = `Vídeo recebido: ${video.videoWidth}×${video.videoHeight}.`;
    }
  });

  video.addEventListener("loadeddata", () => {
    if (!hasDecodedVideoFrame()) {
      reportDiagnostic("viewer.video.placeholder", {
        videoWidth: video.videoWidth,
        videoHeight: video.videoHeight,
        readyState: video.readyState,
        connectionState: peer?.connectionState,
        iceConnectionState: peer?.iceConnectionState,
      });
      return;
    }
    clearFrameWatchdog();
    reportDiagnostic("viewer.video.first_frame", {
      videoWidth: video.videoWidth,
      videoHeight: video.videoHeight,
      readyState: video.readyState,
    });
    setStatus("Vídeo reproduzindo.", "live");
    quality.textContent = `Primeiro quadro decodificado: ${video.videoWidth}×${video.videoHeight}.`;
  });

  video.addEventListener("error", () => {
    reportDiagnostic("viewer.video.error", {
      readyState: video.readyState,
      videoErrorCode: video.error?.code,
      videoErrorMessage: video.error?.message,
    });
  });

  audioButton.addEventListener("click", () => {
    video.muted = !video.muted;
    audioButton.textContent = video.muted ? "Ativar áudio" : "Silenciar";
  });

  if (config.ended) setStatus("Esta transmissão foi encerrada.");
})();
