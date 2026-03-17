const KNOWN_AGENTS = [
  { url: "http://localhost:8767/", conversationalName: "Stella" },
  { url: "http://localhost:8768/verity/", conversationalName: "Verity" },
  { url: "http://localhost:8769/", conversationalName: "GeminiGeo" },
  { url: "http://localhost:8081/", conversationalName: "TimeAgent" },
  { url: "https://openvoice-time-agent.vercel.app/", conversationalName: "TimeAgent" },
  { url: "http://localhost:8082/", conversationalName: "Erin" },
  { url: "https://secondAssistant.pythonanywhere.com/verity/", conversationalName: "Verity 2" },
  { url: "https://openvoice-stella.vercel.app/", conversationalName: "Stella" },
  { url: "https://bladeszasza-ofpbadword.hf.space/ofp", conversationalName: "" },
  { url: "https://yahandhjjf.us-east-1.awsapprunner.com/", conversationalName: "" }
];

function normalizeGatewayBaseUrl(value) {
  if (!value || typeof value !== "string") return "";
  const candidate = value.trim().replace(/\/+$/, "");
  if (!candidate) return "";
  if (!/^https?:\/\//i.test(candidate)) return "";
  return candidate;
}

const gatewayQueryParam = new URLSearchParams(window.location.search).get("gateway") || "";
const gatewayGlobal = typeof window !== "undefined" ? window.WEB_FLOOR_GATEWAY_BASE_URL : "";
const GATEWAY_BASE_URL = normalizeGatewayBaseUrl(gatewayQueryParam || gatewayGlobal || "");

function gatewayPath(pathname) {
  if (!GATEWAY_BASE_URL) return pathname;
  return `${GATEWAY_BASE_URL}${pathname}`;
}

const ui = {
  assistantUrl: document.querySelector("#assistantUrl"),
  knownAgentSelect: document.querySelector("#knownAgentSelect"),
  knownAgentList: document.querySelector("#knownAgentList"),
  utteranceInput: document.querySelector("#utteranceInput"),
  sendToAll: document.querySelector("#sendToAll"),
  showIncoming: document.querySelector("#showIncoming"),
  showOutgoing: document.querySelector("#showOutgoing"),
  clearAllLogsBtn: document.querySelector("#clearAllLogsBtn"),
  getManifestsBtn: document.querySelector("#getManifestsBtn"),
  inviteBtn: document.querySelector("#inviteBtn"),
  sendUtteranceBtn: document.querySelector("#sendUtteranceBtn"),
  clearConversationBtn: document.querySelector("#clearConversationBtn"),
  clearEventLogBtn: document.querySelector("#clearEventLogBtn"),
  clearErrorLogBtn: document.querySelector("#clearErrorLogBtn"),
  noAgents: document.querySelector("#noAgents"),
  agentsList: document.querySelector("#agentsList"),
  conversation: document.querySelector("#conversation"),
  eventLog: document.querySelector("#eventLog"),
  errorLog: document.querySelector("#errorLog")
};

const state = {
  clientName: "AssistantClientConvenerWeb",
  clientUrl: `http://${window.location.hostname}`,
  clientUri: `openFloor://${window.location.hostname}/AssistantClientConvenerWeb`,
  knownAgents: [...KNOWN_AGENTS],
  previousUrls: [],
  invitedAgents: [],
  revokedAgents: new Set(),
  manifestCache: new Map(),
  conversationHistory: [],
  processedUtteranceIds: new Set(),
  globalConversation: {
    id: crypto?.randomUUID ? crypto.randomUUID() : `conv-${Date.now()}`,
    conversants: []
  }
};

function cleanUrlCandidate(value) {
  if (!value || typeof value !== "string") return "";
  let cleaned = value.trim().replace(/^[\[\(<{\"']+/, "");
  cleaned = cleaned.replace(/[\"'\],;!?\)\]}>]+$/g, "");
  return cleaned;
}

function urlFromSpeakerUri(speakerUri) {
  const candidate = cleanUrlCandidate(speakerUri);
  if (!candidate) return "";
  if (/^agent:https?:\/\//i.test(candidate)) return candidate.slice(6);
  if (/^https?:\/\//i.test(candidate)) return candidate;
  return "";
}

function isUrlLike(value) {
  const candidate = cleanUrlCandidate(value).toLowerCase();
  return candidate.startsWith("http://") || candidate.startsWith("https://") || candidate.startsWith("agent:http://") || candidate.startsWith("agent:https://");
}

function normalizeAgentId(value) {
  let candidate = cleanUrlCandidate(value);
  if (!candidate) return "";
  if (candidate.toLowerCase().startsWith("agent:")) candidate = candidate.slice(6);
  return candidate.replace(/\/+$/, "").toLowerCase();
}

function knownNameForUrl(targetUrl) {
  const normalized = normalizeAgentId(targetUrl);
  for (const item of state.knownAgents) {
    if (item.conversationalName && normalizeAgentId(item.url) === normalized) return item.conversationalName;
  }
  return "";
}

function nameFromUrlPath(urlValue) {
  if (!isUrlLike(urlValue)) return "";
  const normalized = urlFromSpeakerUri(urlValue) || cleanUrlCandidate(urlValue);
  const tail = normalized.replace(/\/+$/, "").split("/").pop()?.trim() || "";
  if (!tail) return "";
  for (const item of state.knownAgents) {
    if (item.conversationalName && item.conversationalName.toLowerCase() === tail.toLowerCase()) return item.conversationalName;
  }
  if (tail.toLowerCase() === "verity") return "Verity";
  return "";
}

function cacheConversationalName(name, ...keys) {
  if (!name) return;
  for (const key of keys) {
    const normalized = normalizeAgentId(key);
    if (normalized) state.manifestCache.set(normalized, name);
  }
}

function resolveConversationalName(speakerUri, targetUrl = "") {
  const normalizedSpeaker = normalizeAgentId(speakerUri);
  const normalizedTarget = normalizeAgentId(targetUrl);

  for (const conversant of state.globalConversation.conversants) {
    const identification = conversant.identification || {};
    if (normalizedSpeaker && normalizeAgentId(identification.speakerUri) === normalizedSpeaker) {
      if (identification.conversationalName) return identification.conversationalName;
    }
  }

  if (normalizedSpeaker && state.manifestCache.has(normalizedSpeaker)) return state.manifestCache.get(normalizedSpeaker);
  if (normalizedTarget && state.manifestCache.has(normalizedTarget)) return state.manifestCache.get(normalizedTarget);
  return "";
}

function resolveDisplayNameForTarget(targetUrl, speakerUri = "") {
  const cleanedTarget = cleanUrlCandidate(targetUrl);

  if (speakerUri) {
    const name = resolveConversationalName(speakerUri, cleanedTarget);
    if (name && !isUrlLike(name)) return normalizeDisplayName(name);
  }

  for (const agent of state.invitedAgents) {
    if (normalizeAgentId(agent.url) === normalizeAgentId(cleanedTarget) && agent.conversationalName && !isUrlLike(agent.conversationalName)) {
      return normalizeDisplayName(agent.conversationalName);
    }
  }

  const known = knownNameForUrl(cleanedTarget);
  if (known) return normalizeDisplayName(known);

  const fromCache = resolveConversationalName(`agent:${cleanedTarget}`, cleanedTarget);
  if (fromCache && !isUrlLike(fromCache)) return normalizeDisplayName(fromCache);

  const pathName = nameFromUrlPath(cleanedTarget) || nameFromUrlPath(speakerUri);
  if (pathName) return normalizeDisplayName(pathName);

  return cleanedTarget || urlFromSpeakerUri(speakerUri) || "Unknown";
}

function normalizeDisplayName(name) {
  if (!name) return name;
  if (isUrlLike(name)) {
    const pathName = nameFromUrlPath(name);
    if (pathName) return pathName;
  }
  if (name.trim().toLowerCase().startsWith("verity")) return "Verity";
  return name;
}

function resolveHistorySpeakerName(speaker, speakerUri = "") {
  const candidateUrl = urlFromSpeakerUri(speakerUri) || urlFromSpeakerUri(speaker) || (isUrlLike(speaker) ? cleanUrlCandidate(speaker) : "");
  if (candidateUrl) {
    const display = resolveDisplayNameForTarget(candidateUrl, speakerUri);
    if (display && !isUrlLike(display)) return normalizeDisplayName(display);
  }

  const fallback = normalizeDisplayName(speaker || "").trim();
  if (fallback && !isUrlLike(fallback)) return fallback;

  if (candidateUrl) return cleanUrlCandidate(candidateUrl);
  if (fallback && isUrlLike(fallback)) return urlFromSpeakerUri(fallback) || cleanUrlCandidate(fallback);

  return "Unknown";
}

function isNamePrefixMatch(text, candidateName) {
  if (!text || !candidateName) return false;
  const trimmed = text.trimStart();
  const pattern = new RegExp(`^${escapeRegExp(candidateName)}(?:\\b|[\\s,:;.!?\\-])`, "i");
  return pattern.test(trimmed);
}

function stripLeadingAddressName(text, name) {
  if (!text || !name) return text;
  const pattern = new RegExp(`^\\s*${escapeRegExp(name)}(?:\\b|[\\s,:;.!?\\-])+`, "i");
  return text.replace(pattern, "").trimStart();
}

function parseUtteranceForAddressedAgent(text, addressedAgent) {
  if (!text) return text;
  const addressedName = (addressedAgent?.name || "").trim().toLowerCase();
  if (addressedName === "stella") {
    return stripLeadingAddressName(text, "stella");
  }
  return text;
}

function findAddressedConversantByPrefix(text) {
  const matches = [];
  for (const conversant of state.globalConversation.conversants) {
    const identification = conversant.identification || {};
    let conversationalName = (identification.conversationalName || "").trim();
    const speakerUri = identification.speakerUri || "";
    const serviceUrl = identification.serviceUrl || "";

    if (isUrlLike(conversationalName)) {
      conversationalName = resolveDisplayNameForTarget(serviceUrl || urlFromSpeakerUri(speakerUri), speakerUri);
    }

    if (!conversationalName || !speakerUri || isUrlLike(conversationalName)) continue;
    if (isNamePrefixMatch(text, conversationalName)) {
      matches.push({
        score: conversationalName.length,
        url: serviceUrl,
        name: conversationalName,
        speaker_uri: speakerUri
      });
    }
  }

  if (!matches.length) return null;
  matches.sort((a, b) => b.score - a.score);
  return matches[0];
}

function findAddressedAgentInUtterance(text) {
  if (!text) return null;

  const conversantMatch = findAddressedConversantByPrefix(text);
  if (conversantMatch) return conversantMatch;

  const matches = [];
  for (const agent of state.invitedAgents) {
    const targetUrl = agent.url;
    let name = (agent.conversationalName || "").trim();
    if (!name) name = resolveConversationalName(`agent:${targetUrl}`, targetUrl);
    if (!name) name = knownNameForUrl(targetUrl);
    if (!name) continue;

    if (isNamePrefixMatch(text, name)) {
      matches.push({ score: name.length, url: targetUrl, name, speaker_uri: resolveSpeakerUriForAgentUrl(targetUrl) });
    }
  }

  if (!matches.length) return null;
  matches.sort((a, b) => b.score - a.score);
  return matches[0];
}

function resolveSpeakerUriForAgentUrl(agentUrl) {
  for (const conversant of state.globalConversation.conversants) {
    const identification = conversant.identification || {};
    if (normalizeAgentId(identification.serviceUrl) === normalizeAgentId(agentUrl) && identification.speakerUri) {
      return identification.speakerUri;
    }
  }
  return `agent:${agentUrl}`;
}

function addConversantToGlobal(agentUrl, conversationalName = "", speakerUri = "") {
  if (!agentUrl) return;
  const normalizedTarget = normalizeAgentId(agentUrl);

  for (const conversant of state.globalConversation.conversants) {
    const identification = conversant.identification || {};
    if (normalizeAgentId(identification.serviceUrl) === normalizedTarget) {
      if (conversationalName && (!identification.conversationalName || isUrlLike(identification.conversationalName))) {
        identification.conversationalName = conversationalName;
      }
      if (speakerUri && !identification.speakerUri) {
        identification.speakerUri = speakerUri;
      }
      if (!identification.organization) {
        identification.organization = "Unknown";
      }
      if (!identification.synopsis) {
        identification.synopsis = `Conversant endpoint at ${agentUrl}`;
      }
      return;
    }
  }

  const display = conversationalName || resolveDisplayNameForTarget(agentUrl, speakerUri || `agent:${agentUrl}`) || agentUrl;
  state.globalConversation.conversants.push({
    identification: {
      speakerUri: speakerUri || `agent:${agentUrl}`,
      serviceUrl: agentUrl,
      organization: "Unknown",
      conversationalName: display,
      synopsis: `Conversant endpoint at ${agentUrl}`
    }
  });
}

function removeConversantFromGlobal(agentUrl) {
  const normalizedTarget = normalizeAgentId(agentUrl);
  state.globalConversation.conversants = state.globalConversation.conversants.filter(
    (conversant) => normalizeAgentId(conversant?.identification?.serviceUrl) !== normalizedTarget
  );
}

function removeInvitedAgent(agentUrl) {
  if (!agentUrl) return;
  const normalizedTarget = normalizeAgentId(agentUrl);
  state.revokedAgents.delete(normalizedTarget);
  state.invitedAgents = state.invitedAgents.filter(
    (item) => normalizeAgentId(item.url) !== normalizedTarget
  );
  removeConversantFromGlobal(agentUrl);
  renderAgents();
  updateSendButtonState();
}

function addInvitedAgent(agentUrl, conversationalName = "") {
  if (!agentUrl) return;
  const normalizedTarget = normalizeAgentId(agentUrl);

  for (const agent of state.invitedAgents) {
    if (normalizeAgentId(agent.url) === normalizedTarget) {
      if (conversationalName) agent.conversationalName = conversationalName;
      return;
    }
  }

  const fallbackName = conversationalName || knownNameForUrl(agentUrl) || resolveDisplayNameForTarget(agentUrl) || "";
  state.invitedAgents.push({
    url: cleanUrlCandidate(agentUrl),
    conversationalName: fallbackName,
    selected: true,
    status: "idle"
  });

  addConversantToGlobal(agentUrl, fallbackName);
}

function setAgentStatus(agentUrl, status) {
  const normalizedTarget = normalizeAgentId(agentUrl);
  for (const agent of state.invitedAgents) {
    if (normalizeAgentId(agent.url) === normalizedTarget) {
      agent.status = status;
      break;
    }
  }
  renderAgents();
}

function updateSendButtonState() {
  ui.sendUtteranceBtn.disabled = state.invitedAgents.length === 0;
}

function updateConversationHistory(speaker, text, speakerUri = "", utteranceId = "") {
  if (utteranceId && state.processedUtteranceIds.has(utteranceId)) return;

  const displaySpeaker = resolveHistorySpeakerName(speaker, speakerUri);
  state.conversationHistory.push({ speaker: displaySpeaker, speakerUri: speakerUri || displaySpeaker, text });
  if (utteranceId) state.processedUtteranceIds.add(utteranceId);

  const lineNo = state.conversationHistory.length;
  const line = `${lineNo}. [${displaySpeaker.toUpperCase()}] ${text}`;
  if (ui.conversation.textContent.trim()) ui.conversation.textContent += "\n\n";
  ui.conversation.textContent += line;
  ui.conversation.scrollTop = ui.conversation.scrollHeight;
}

function clearConversationHistory() {
  state.conversationHistory = [];
  state.processedUtteranceIds.clear();
  ui.conversation.textContent = "";
}

function clearEventLog() {
  ui.eventLog.textContent = "";
}

function clearErrorLog() {
  ui.errorLog.textContent = "";
}

function clearAllLogs() {
  clearConversationHistory();
  clearEventLog();
  clearErrorLog();
}

function logEvent(message, payload = null) {
  const ts = new Date().toISOString();
  const chunk = payload ? `${message}\n${JSON.stringify(payload, null, 2)}` : message;
  ui.eventLog.textContent += `[${ts}] ${chunk}\n\n`;
  ui.eventLog.scrollTop = ui.eventLog.scrollHeight;
}

function logError(message, payload = null) {
  const ts = new Date().toISOString();
  const chunk = payload ? `${message}\n${JSON.stringify(payload, null, 2)}` : message;
  ui.errorLog.textContent += `[${ts}] ${chunk}\n\n`;
  ui.errorLog.scrollTop = ui.errorLog.scrollHeight;
}

function refreshKnownAgentList() {
  const merged = [];
  const seen = new Set();

  for (const item of state.knownAgents) {
    if (!item.url) continue;
    const normalized = normalizeAgentId(item.url);
    if (seen.has(normalized)) continue;
    seen.add(normalized);
    merged.push(item);
  }

  for (const url of state.previousUrls) {
    if (!url) continue;
    const normalized = normalizeAgentId(url);
    if (seen.has(normalized)) continue;
    seen.add(normalized);
    merged.push({ url, conversationalName: resolveDisplayNameForTarget(url) || "" });
  }

  ui.knownAgentList.innerHTML = "";
  for (const item of merged) {
    const option = document.createElement("option");
    option.value = item.conversationalName ? `${item.conversationalName} | ${item.url}` : item.url;
    ui.knownAgentList.appendChild(option);
  }

  if (ui.knownAgentSelect) {
    const currentUrl = ui.assistantUrl.value;
    ui.knownAgentSelect.innerHTML = '<option value="">-- select an agent --</option>';
    for (const item of merged) {
      const option = document.createElement("option");
      option.value = item.url;
      option.textContent = item.conversationalName ? `${item.conversationalName} | ${item.url}` : item.url;
      if (item.url === currentUrl) option.selected = true;
      ui.knownAgentSelect.appendChild(option);
    }
  }
}

function renderAgents() {
  ui.agentsList.innerHTML = "";
  ui.noAgents.style.display = state.invitedAgents.length ? "none" : "block";

  for (const agent of state.invitedAgents) {
    const row = document.createElement("div");
    row.className = "agent-row";

    const select = document.createElement("input");
    select.type = "checkbox";
    select.checked = !!agent.selected;
    select.addEventListener("change", () => {
      agent.selected = select.checked;
      if (select.checked) ui.sendToAll.checked = false;
    });

    const floorBtn = document.createElement("button");
    const revoked = state.revokedAgents.has(normalizeAgentId(agent.url));
    floorBtn.textContent = revoked ? "Grant Floor" : "Revoke Floor";
    floorBtn.className = revoked ? "floor-btn-grant" : "floor-btn-revoke";
    floorBtn.addEventListener("click", async () => {
      if (revoked) {
        // Requested behavior: make grant floor return agent to invited state
        state.revokedAgents.delete(normalizeAgentId(agent.url));
        renderAgents();
        await sendControlEvent("grantFloor", agent.url);
        return;
      }

      const ok = await sendControlEvent("revokeFloor", agent.url);
      if (!ok) return;
      state.revokedAgents.add(normalizeAgentId(agent.url));
      renderAgents();
    });

    const uninviteBtn = document.createElement("button");
    uninviteBtn.textContent = "Uninvite";
    uninviteBtn.addEventListener("click", async () => {
      const ok = await sendControlEvent("uninvite", agent.url);
      if (!ok) return;
      removeInvitedAgent(agent.url);
    });

    const dot = document.createElement("span");
    dot.className = `status-dot status-${agent.status || "idle"}`;

    const name = document.createElement("div");
    name.className = "agent-name";
    name.textContent = agent.conversationalName || resolveDisplayNameForTarget(agent.url) || "Unknown";

    const url = document.createElement("div");
    url.className = "agent-url";
    url.textContent = agent.url;

    row.append(select, floorBtn, uninviteBtn, dot, name, url);
    ui.agentsList.appendChild(row);
  }
}

function serializeConversation() {
  return {
    id: state.globalConversation.id,
    conversants: state.globalConversation.conversants.map((item) => ({
      identification: {
        speakerUri: item?.identification?.speakerUri || "",
        serviceUrl: item?.identification?.serviceUrl || "",
        organization: item?.identification?.organization || "Unknown",
        conversationalName: item?.identification?.conversationalName || "",
        synopsis: item?.identification?.synopsis || `Conversant endpoint at ${item?.identification?.serviceUrl || "unknown"}`
      }
    }))
  };
}

function buildDialogEvent(userInput) {
  return {
    speakerUri: state.clientUri,
    features: {
      text: {
        mimeType: "text/plain",
        tokens: [{ value: userInput }]
      }
    }
  };
}

function buildEnvelopeForTarget(targetUrl, eventTypes, userInput, addressedAgent, usePrivate) {
  const payload = {
    openFloor: {
      conversation: serializeConversation(),
      sender: {
        speakerUri: state.clientUri,
        serviceUrl: state.clientUrl
      },
      events: []
    }
  };

  for (const eventType of eventTypes) {
    if (eventType === "invite") {
      payload.openFloor.events.push({ eventType: "invite", to: { serviceUrl: targetUrl } });
    } else if (eventType === "getManifests") {
      payload.openFloor.events.push({ eventType: "getManifests", to: { serviceUrl: targetUrl } });
    } else if (eventType === "grantFloor") {
      payload.openFloor.events.push({ eventType: "grantFloor", to: { serviceUrl: targetUrl } });
    } else if (eventType === "revokeFloor") {
      payload.openFloor.events.push({ eventType: "revokeFloor", to: { serviceUrl: targetUrl } });
    } else if (eventType === "uninvite") {
      payload.openFloor.events.push({ eventType: "uninvite", to: { serviceUrl: targetUrl } });
    } else if (eventType === "utterance") {
      const event = {
        eventType: "utterance",
        parameters: {
          dialogEvent: buildDialogEvent(userInput)
        }
      };

      if (addressedAgent?.speaker_uri) {
        event.to = {
          speakerUri: addressedAgent.speaker_uri,
          private: !!usePrivate
        };
      } else {
        event.to = {
          serviceUrl: targetUrl,
          private: !!usePrivate
        };
      }
      payload.openFloor.events.push(event);
    }
  }

  return payload;
}

async function proxySend(targetUrl, payload, timeoutMs = 10000) {
  const gatewayUrl = gatewayPath("/api/proxy-send");
  const response = await fetch(gatewayUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ targetUrl, payload, timeoutMs })
  });

  const rawText = await response.text();

  try {
    return rawText ? JSON.parse(rawText) : {};
  } catch (_error) {
    const preview = rawText.replace(/\s+/g, " ").slice(0, 160);
    throw new Error(
      `Gateway returned non-JSON from ${gatewayUrl} (${response.status} ${response.statusText}): ${preview}`
    );
  }
}

function normalizeLeadingUrlInText(rawText, speakerUri = "", speakerUrl = "") {
  if (!rawText || typeof rawText !== "string") return rawText;
  const trimmed = rawText.trimStart();
  const leadingWs = rawText.slice(0, rawText.length - trimmed.length);
  const match = /^(?:agent:)?https?:\/\/[^\s]+/i.exec(trimmed);
  if (!match) return rawText;

  const rawUrl = match[0];
  const candidateUrl = urlFromSpeakerUri(rawUrl) || cleanUrlCandidate(rawUrl);
  const resolved = resolveDisplayNameForTarget(candidateUrl || speakerUrl, speakerUri);
  if (!resolved || isUrlLike(resolved)) return rawText;

  let remainder = trimmed.slice(match[0].length);
  remainder = remainder.replace(/^[\s,:;.!?\-]+/, "");
  if (!remainder) return `${leadingWs}${resolved}`;
  return `${leadingWs}${resolved}: ${remainder}`;
}

function prependDirectAddressContext(text, directedAddressee, { speakerName = "", speakerUri = "", speakerUrl = "" } = {}) {
  if (!text || !directedAddressee) return text;

  let normalizedText = normalizeLeadingUrlInText(text, speakerUri, speakerUrl);
  if (isUrlLike(normalizedText.trim())) {
    const candidateUrl = urlFromSpeakerUri(normalizedText) || cleanUrlCandidate(normalizedText);
    const resolved = resolveDisplayNameForTarget(candidateUrl, speakerUri);
    if (resolved && !isUrlLike(resolved)) normalizedText = resolved;
  }

  let addresseeName = (directedAddressee.name || "").trim();
  if (isUrlLike(addresseeName)) {
    addresseeName = resolveDisplayNameForTarget(directedAddressee.url || urlFromSpeakerUri(directedAddressee.speaker_uri), directedAddressee.speaker_uri);
  }
  if (!addresseeName) return normalizedText;

  if (speakerName) {
    const own = speakerName.trim();
    if (own) {
      if (normalizedText.trim().toLowerCase() === own.toLowerCase()) return normalizedText;
      if (new RegExp(`^${escapeRegExp(own)}(?:\\b|[\\s,:;.!?\\-])`, "i").test(normalizedText.trim())) return normalizedText;
    }
  }

  if (speakerName && speakerName.trim().toLowerCase() === addresseeName.toLowerCase()) return normalizedText;

  if (directedAddressee.speaker_uri && speakerUri && normalizeAgentId(directedAddressee.speaker_uri) === normalizeAgentId(speakerUri)) {
    return normalizedText;
  }

  if (directedAddressee.url) {
    const normAddresseeUrl = normalizeAgentId(directedAddressee.url);
    if (speakerUrl && normalizeAgentId(speakerUrl) === normAddresseeUrl) return normalizedText;
    if (speakerUri && normalizeAgentId(speakerUri) === normAddresseeUrl) return normalizedText;
  }

  if (new RegExp(`^${escapeRegExp(addresseeName)}(?:\\b|[\\s,:;.!?\\-])`, "i").test(normalizedText.trimStart())) return normalizedText;

  return `${addresseeName}, ${normalizedText}`;
}

function resolveDirectedAddresseeForEvent(event, fallbackDirectedAddressee = null) {
  const explicitTo = event?.to || event?.parameters?.to || {};
  const explicitSpeakerUri = cleanUrlCandidate(explicitTo?.speakerUri || "");
  const explicitServiceUrl = cleanUrlCandidate(explicitTo?.serviceUrl || "");

  if (!explicitSpeakerUri && !explicitServiceUrl) return fallbackDirectedAddressee;

  if (explicitSpeakerUri && normalizeAgentId(explicitSpeakerUri) === normalizeAgentId(state.clientUri)) {
    return fallbackDirectedAddressee;
  }

  if (explicitServiceUrl && normalizeAgentId(explicitServiceUrl) === normalizeAgentId(state.clientUrl)) {
    return fallbackDirectedAddressee;
  }

  const resolvedUrl = explicitServiceUrl || urlFromSpeakerUri(explicitSpeakerUri) || "";
  const resolvedName = resolveDisplayNameForTarget(resolvedUrl, explicitSpeakerUri);

  return {
    name: !isUrlLike(resolvedName) ? resolvedName : (fallbackDirectedAddressee?.name || ""),
    url: resolvedUrl || fallbackDirectedAddressee?.url || "",
    speaker_uri: explicitSpeakerUri || fallbackDirectedAddressee?.speaker_uri || ""
  };
}

function openHtmlInPopup(htmlContent) {
  if (!htmlContent) return;

  const blob = new Blob([htmlContent], { type: "text/html" });
  const htmlUrl = URL.createObjectURL(blob);
  const popupFeatures = "popup=yes,width=980,height=720,resizable=yes,scrollbars=yes";
  const popup = window.open(htmlUrl, "webFloorHtmlPopup", popupFeatures);

  if (!popup) {
    logError("Popup blocked while opening agent HTML response.");
    URL.revokeObjectURL(htmlUrl);
    return;
  }

  setTimeout(() => {
    try {
      URL.revokeObjectURL(htmlUrl);
    } catch (_) {
      // no-op
    }
  }, 60000);
}

function processIncomingEnvelope(responseData, targetUrl, { directedAddressee = null } = {}) {
  const events = responseData?.openFloor?.events || [];

  for (const event of events) {
    const eventType = event?.eventType || "";

    if (eventType === "uninvite") {
      removeInvitedAgent(targetUrl);
      continue;
    }

    if (eventType === "publishManifests") {
      const manifests = event?.parameters?.servicingManifests || [];
      if (!manifests.length) continue;

      const manifest = manifests[0] || {};
      const identification = manifest.identification || {};
      const conversationalName = identification.conversationalName || "";
      const assistantUri = identification.uri || "";
      const manifestSpeakerUri = identification.speakerUri || "";
      const serviceUrl = identification.serviceUrl || targetUrl;

      cacheConversationalName(conversationalName, serviceUrl, targetUrl, assistantUri, manifestSpeakerUri);

      addConversantToGlobal(serviceUrl, conversationalName, manifestSpeakerUri || `agent:${serviceUrl}`);

      for (const agent of state.invitedAgents) {
        if (normalizeAgentId(agent.url) === normalizeAgentId(serviceUrl) || normalizeAgentId(agent.url) === normalizeAgentId(targetUrl)) {
          if (conversationalName) agent.conversationalName = conversationalName;
        }
      }

      if (serviceUrl && !state.previousUrls.some((url) => normalizeAgentId(url) === normalizeAgentId(serviceUrl)) && !knownNameForUrl(serviceUrl)) {
        state.previousUrls.push(serviceUrl);
        refreshKnownAgentList();
      }

      renderAgents();
      continue;
    }

    if (eventType === "utterance") {
      const dialog = event?.parameters?.dialogEvent || event?.dialogEvent || {};
      const speakerUri = dialog?.speakerUri || "Unknown";
      const displayName = resolveDisplayNameForTarget(targetUrl, speakerUri);
      const directedTarget = resolveDirectedAddresseeForEvent(event, directedAddressee);

      const textFeature = dialog?.features?.text || {};
      const tokens = textFeature?.tokens || [];
      const values = textFeature?.values || [];
      const utteranceId = dialog?.id || "";

      let text = "";
      if (tokens.length && typeof tokens[0] === "object") {
        text = tokens[0]?.value || "";
      } else if (values.length) {
        text = typeof values[0] === "string" ? values[0] : values[0]?.value || "";
      }
      if (!text) continue;

      text = normalizeLeadingUrlInText(text, speakerUri, targetUrl);
      text = prependDirectAddressContext(text, directedTarget, {
        speakerName: displayName,
        speakerUri,
        speakerUrl: targetUrl
      });

      updateConversationHistory(displayName, text, speakerUri, utteranceId);

      const htmlTokens = dialog?.features?.html?.tokens || [];
      if (htmlTokens.length && htmlTokens[0]?.value) {
        openHtmlInPopup(htmlTokens[0].value);
      }
    }
  }

  if (ui.showIncoming.checked) {
    logEvent(`Incoming from ${targetUrl}`, responseData);
  }
}

async function sendControlEvent(eventType, agentUrl) {
  setAgentStatus(agentUrl, "working");

  const payload = buildEnvelopeForTarget(agentUrl, [eventType], "", null, false);
  if (ui.showOutgoing.checked) logEvent(`Outgoing ${eventType} to ${agentUrl}`, payload);

  const response = await proxySend(agentUrl, payload, 10000);

  if (!response?.ok) {
    setAgentStatus(agentUrl, "error");
    logError(`${eventType} failed for ${agentUrl}`, response);
    return false;
  }

  setAgentStatus(agentUrl, "idle");
  if (response.json) processIncomingEnvelope(response.json, agentUrl, { directedAddressee: null });
  return true;
}

function collectTargetUrls(eventTypes, assistantUrl) {
  if (eventTypes.includes("invite") || eventTypes.includes("getManifests")) {
    return assistantUrl ? [assistantUrl] : [];
  }

  if (ui.sendToAll.checked) {
    return state.invitedAgents.map((agent) => agent.url);
  }

  return state.invitedAgents.filter((agent) => agent.selected).map((agent) => agent.url);
}

async function sendEvents(eventTypes) {
  const assistantUrlRaw = ui.assistantUrl.value || "";
  const assistantUrl = cleanUrlCandidate(assistantUrlRaw.includes(" | ") ? assistantUrlRaw.split(" | ").slice(-1)[0] : assistantUrlRaw);
  const userInput = (ui.utteranceInput.value || "").trim();

  let targetUrls = collectTargetUrls(eventTypes, assistantUrl);
  let addressedAgent = null;
  let parsedUserInput = userInput;

  if (eventTypes.includes("utterance")) {
    if (!userInput) {
      logError("Please enter some text before sending an utterance.");
      return;
    }

    addressedAgent = findAddressedAgentInUtterance(userInput);
    if (addressedAgent && state.invitedAgents.length) {
      if (isUrlLike(addressedAgent.name)) {
        addressedAgent.name = resolveDisplayNameForTarget(addressedAgent.url || urlFromSpeakerUri(addressedAgent.speaker_uri), addressedAgent.speaker_uri);
      }
      parsedUserInput = parseUtteranceForAddressedAgent(userInput, addressedAgent);
      targetUrls = state.invitedAgents.map((agent) => agent.url);
    }

    updateConversationHistory("You", userInput);
  }

  if (!targetUrls.length) {
    if (eventTypes.includes("invite") || eventTypes.includes("getManifests")) {
      logError("No Assistant URL specified.");
    } else if (!state.invitedAgents.length) {
      logError("No invited agents to send to. Invite an agent first.");
    } else {
      logError("No agents selected. Enable send-to-all or select agent checkboxes.");
    }
    return;
  }

  if (assistantUrl && !state.previousUrls.some((url) => normalizeAgentId(url) === normalizeAgentId(assistantUrl))) {
    state.previousUrls.push(assistantUrl);
    refreshKnownAgentList();
  }

  const usePrivate = !ui.sendToAll.checked;

  const sendTasks = targetUrls.map(async (targetUrl) => {
    if (eventTypes.includes("invite")) {
      addInvitedAgent(targetUrl);
      renderAgents();
      updateSendButtonState();
    }

    setAgentStatus(targetUrl, "working");

    const payload = buildEnvelopeForTarget(targetUrl, eventTypes, parsedUserInput, addressedAgent, usePrivate);
    if (ui.showOutgoing.checked) logEvent(`Outgoing to ${targetUrl}`, payload);

    let response;
    try {
      response = await proxySend(targetUrl, payload, 10000);
    } catch (error) {
      setAgentStatus(targetUrl, "error");
      logError(`Request failed for ${targetUrl}`, String(error));
      return;
    }

    if (!response?.ok) {
      setAgentStatus(targetUrl, "error");
      logError(`Request failed for ${targetUrl}`, response);
      return;
    }

    setAgentStatus(targetUrl, "idle");

    if (response.json) {
      processIncomingEnvelope(response.json, targetUrl, { directedAddressee: addressedAgent });
    } else {
      logError(`Non-JSON response from ${targetUrl}`, response);
      setAgentStatus(targetUrl, "error");
    }
  });

  await Promise.allSettled(sendTasks);
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function bindEvents() {
  ui.getManifestsBtn.addEventListener("click", () => sendEvents(["getManifests"]));
  ui.inviteBtn.addEventListener("click", () => {
    const events = ["invite"];
    if ((ui.utteranceInput.value || "").trim()) events.push("utterance");
    sendEvents(events);
  });
  ui.sendUtteranceBtn.addEventListener("click", () => sendEvents(["utterance"]));
  ui.clearAllLogsBtn.addEventListener("click", clearAllLogs);
  ui.clearConversationBtn.addEventListener("click", clearConversationHistory);
  ui.clearEventLogBtn.addEventListener("click", clearEventLog);
  ui.clearErrorLogBtn.addEventListener("click", clearErrorLog);

  ui.utteranceInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      ui.sendUtteranceBtn.click();
    }
  });

  if (ui.knownAgentSelect) {
    ui.knownAgentSelect.addEventListener("change", () => {
      const selected = ui.knownAgentSelect.value;
      if (selected) {
        ui.assistantUrl.value = selected;
        ui.knownAgentSelect.value = "";
      }
    });
  }
}

function init() {
  refreshKnownAgentList();
  renderAgents();
  updateSendButtonState();
  bindEvents();

  ui.assistantUrl.value = state.knownAgents[0]?.url || "http://localhost:8767/";
}

init();
