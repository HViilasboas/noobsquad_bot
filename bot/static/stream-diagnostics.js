(() => {
  const configElement = document.getElementById("stream-config");
  if (!configElement) return;

  const config = JSON.parse(configElement.textContent);
  const role = document.body.dataset.streamRole;
  if (!role || !config.path || !config.diagnosticsUrl) return;

  const tokenKey = `noobsquad-stream-${role}:${config.path}`;
  let token = window.location.hash.slice(1);
  let clientId = "";
  try {
    if (token) window.sessionStorage.setItem(tokenKey, token);
    else token = window.sessionStorage.getItem(tokenKey) || "";

    const clientKey = `${tokenKey}:diagnostics-client`;
    clientId = window.sessionStorage.getItem(clientKey) || "";
    if (!clientId) {
      clientId = window.crypto?.randomUUID?.()
        || `${Date.now()}-${Math.random().toString(36).slice(2, 14)}`;
      window.sessionStorage.setItem(clientKey, clientId);
    }
  } catch (_error) {
    clientId = `${Date.now()}-${Math.random().toString(36).slice(2, 14)}`;
  }

  const allowedFields = new Set([
    "attempt", "retryMs", "durationMs", "httpStatus", "readyState",
    "videoWidth", "videoHeight", "videoErrorCode", "rttMs",
    "framesPerSecond", "bitrateMbps", "errorName", "errorMessage",
    "connectionState", "iceConnectionState", "iceGatheringState",
    "sessionState",
    "trackKind", "trackState", "selectedLocalCandidateType",
    "selectedRemoteCandidateType", "selectedLocalCandidateProtocol",
    "selectedRemoteCandidateProtocol", "candidatePairState",
    "displaySurface", "videoErrorMessage",
  ]);

  function report(event, details = {}) {
    if (!token || !clientId) return;
    const safeDetails = {};
    for (const [key, value] of Object.entries(details)) {
      if (!allowedFields.has(key)) continue;
      if (typeof value === "string") safeDetails[key] = value.slice(0, 240);
      else if (typeof value === "number" && Number.isFinite(value)) safeDetails[key] = value;
    }

    const payload = {
      event,
      clientId,
      userAgent: window.navigator?.userAgent || "",
      details: safeDetails,
    };
    void window.fetch(config.diagnosticsUrl, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch(() => {});
  }

  window.NoobSquadStreamDiagnostics = { report };
})();
