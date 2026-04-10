// Configurable delay (in milliseconds) per word. After a message is posted, the next message
// will be delayed by (word_count * MESSAGE_DISPLAY_DELAY_MS_PER_WORD) milliseconds to give
// the user time to read the previous message. Set to 0 to disable delay.
const MESSAGE_DISPLAY_DELAY_MS_PER_WORD = 100;

// Internal message queue and timing tracking for display delays
const messageQueue = {
  queue: [],
  lastDisplayTime: 0,
  lastMessageWordCount: 0,
  isProcessing: false
};

const KNOWN_AGENTS = [
  { url: "https://openvoice-stella.vercel.app/", conversationalName: "Stella (Vercel)" },
  { url: "http://localhost:8767/", conversationalName: "Stella (local 8767)" },
  { url: "http://localhost:8768/verity/", conversationalName: "Verity" },
  { url: "http://localhost:8769/", conversationalName: "GeminiGeo" },
  { url: "http://localhost:8081/", conversationalName: "TimeAgent" },
  { url: "https://openvoice-time-agent.vercel.app/", conversationalName: "TimeAgent" },
  { url: "http://localhost:8082/", conversationalName: "Erin" },
  { url: "https://secondAssistant.pythonanywhere.com/verity/", conversationalName: "Verity 2" },
  { url: "http://localhost:8083/", conversationalName: "Finn" },
  { url: "http://localhost:8084/", conversationalName: "Prudence" },
  { url: "http://localhost:8085/", conversationalName: "Lucky" },
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

function isLocalClientContext() {
  if (typeof window === "undefined") return false;

  const protocol = (window.location.protocol || "").toLowerCase();
  const hostname = (window.location.hostname || "").toLowerCase();

  if (protocol === "file:") return true;
  if (!hostname) return false;

  if (hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1" || hostname === "[::1]" || hostname === "0.0.0.0") {
    return true;
  }

  if (/^10\./.test(hostname) || /^192\.168\./.test(hostname)) return true;

  const private172 = hostname.match(/^172\.(\d{1,3})\./);
  if (private172) {
    const secondOctet = Number(private172[1]);
    if (secondOctet >= 16 && secondOctet <= 31) return true;
  }

  if (hostname.endsWith(".local") || hostname.endsWith(".lan") || hostname.endsWith(".home") || hostname.endsWith(".internal")) {
    return true;
  }

  if (!hostname.includes(".")) return true;

  return false;
}

function isLocalAgentUrl(urlValue) {
  const candidate = cleanUrlCandidate(urlValue);
  if (!candidate) return false;

  try {
    const parsed = new URL(candidate);
    const hostname = (parsed.hostname || "").toLowerCase();
    return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1" || hostname === "[::1]" || hostname === "0.0.0.0";
  } catch (_error) {
    return false;
  }
}

function getVisibleKnownAgents(agents) {
  if (isLocalClientContext()) return agents;
  return agents.filter((item) => !isLocalAgentUrl(item.url));
}

const ui = {
  assistantUrl: document.querySelector("#assistantUrl"),
  knownAgentSelect: document.querySelector("#knownAgentSelect"),
  knownAgentList: document.querySelector("#knownAgentList"),
  utteranceInput: document.querySelector("#utteranceInput"),
  sendToAll: document.querySelector("#sendToAll"),
  showIncoming: document.querySelector("#showIncoming"),
  showOutgoing: document.querySelector("#showOutgoing"),
  getManifestsBtn: document.querySelector("#getManifestsBtn"),
  inviteBtn: document.querySelector("#inviteBtn"),
  sendUtteranceBtn: document.querySelector("#sendUtteranceBtn"),
  clearConversationBtn: document.querySelector("#clearConversationBtn"),
  copyConversationBtn: document.querySelector("#copyConversationBtn"),
  clearEventLogBtn: document.querySelector("#clearEventLogBtn"),
  clearErrorLogBtn: document.querySelector("#clearErrorLogBtn"),
  toggleDiagnosticsBtn: document.querySelector("#toggleDiagnosticsBtn"),
  diagnosticsContent: document.querySelector("#diagnosticsContent"),
  noAgents: document.querySelector("#noAgents"),
  agentsList: document.querySelector("#agentsList"),
  conversation: document.querySelector("#conversation"),
  eventLog: document.querySelector("#eventLog"),
  errorLog: document.querySelector("#errorLog"),
  htmlPopupArea: document.querySelector("#htmlPopupArea")
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

function isPlaceholderSpeakerUri(value) {
  if (!value || typeof value !== "string") return false;
  const normalized = value.trim().toLowerCase();
  return normalized.startsWith("agent:http://") || normalized.startsWith("agent:https://");
}

function preferredSpeakerUri(existingSpeakerUri, newSpeakerUri, serviceUrl = "") {
  if (!newSpeakerUri) return existingSpeakerUri || "";
  if (!existingSpeakerUri) return newSpeakerUri;
  if (isPlaceholderSpeakerUri(existingSpeakerUri)) return newSpeakerUri;
  if (serviceUrl && normalizeAgentId(existingSpeakerUri) === normalizeAgentId(serviceUrl)) return newSpeakerUri;
  return existingSpeakerUri;
}

function addConversantToGlobal(agentUrl, conversationalName = "", speakerUri = "") {
  const cleanedAgentUrl = cleanUrlCandidate(agentUrl) || urlFromSpeakerUri(speakerUri);
  const normalizedTarget = normalizeAgentId(cleanedAgentUrl);
  const normalizedSpeaker = normalizeAgentId(speakerUri);
  const matches = [];

  for (const conversant of state.globalConversation.conversants) {
    const identification = conversant.identification || {};
    const serviceMatch = normalizedTarget && normalizeAgentId(identification.serviceUrl) === normalizedTarget;
    const speakerMatch = normalizedSpeaker && normalizeAgentId(identification.speakerUri) === normalizedSpeaker;
    if (serviceMatch || speakerMatch) matches.push(conversant);
  }

  let primary = matches[0];
  if (!primary) {
    const seedUrl = cleanedAgentUrl || urlFromSpeakerUri(speakerUri);
    primary = {
      identification: {
        speakerUri: speakerUri || (seedUrl ? `agent:${seedUrl}` : ""),
        serviceUrl: seedUrl || "",
        organization: "Unknown",
        conversationalName: "",
        synopsis: `Conversant endpoint at ${seedUrl || "unknown"}`
      }
    };
    state.globalConversation.conversants.push(primary);
  }

  const identification = primary.identification || (primary.identification = {});
  const resolvedServiceUrl = cleanedAgentUrl || identification.serviceUrl || urlFromSpeakerUri(speakerUri) || "";
  if (resolvedServiceUrl) {
    identification.serviceUrl = resolvedServiceUrl;
    identification.synopsis = `Conversant endpoint at ${resolvedServiceUrl}`;
  }
  identification.organization = identification.organization || "Unknown";
  identification.speakerUri = preferredSpeakerUri(identification.speakerUri || "", speakerUri, resolvedServiceUrl) || identification.speakerUri || "";

  if (conversationalName && !isUrlLike(conversationalName)) {
    if (!identification.conversationalName || isUrlLike(identification.conversationalName)) {
      identification.conversationalName = conversationalName;
    }
  } else if (!identification.conversationalName && resolvedServiceUrl) {
    const fallbackName = resolveDisplayNameForTarget(resolvedServiceUrl, identification.speakerUri || "");
    if (fallbackName && !isUrlLike(fallbackName)) {
      identification.conversationalName = fallbackName;
    }
  }

  for (const duplicate of matches.slice(1)) {
    if (duplicate === primary) continue;
    const duplicateId = duplicate.identification || {};
    if (!identification.serviceUrl) identification.serviceUrl = duplicateId.serviceUrl || "";
    if (!identification.speakerUri) identification.speakerUri = duplicateId.speakerUri || "";
    if (!identification.conversationalName) identification.conversationalName = duplicateId.conversationalName || "";
    state.globalConversation.conversants = state.globalConversation.conversants.filter((item) => item !== duplicate);
  }
}

function syncGlobalConversationState() {
  for (const agent of state.invitedAgents) {
    addConversantToGlobal(agent.url, agent.conversationalName || "");
  }

  const deduped = [];
  const seen = new Set();
  for (const conversant of state.globalConversation.conversants) {
    const identification = conversant?.identification || {};
    const key = normalizeAgentId(identification.serviceUrl) || normalizeAgentId(identification.speakerUri);
    if (!key || seen.has(key)) continue;
    seen.add(key);
    deduped.push(conversant);
  }
  state.globalConversation.conversants = deduped;
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
  const hasFocusAgent = !!(ui.assistantUrl.value || "").trim();
  ui.getManifestsBtn.disabled = !hasFocusAgent;
  ui.inviteBtn.disabled = !hasFocusAgent;
  ui.sendUtteranceBtn.disabled = state.invitedAgents.length === 0;
}

function scrollConversationToLatest() {
  if (!ui.conversation) return;

  const container = ui.conversation.closest(".conversation-container");
  const applyScroll = () => {
    ui.conversation.scrollTop = ui.conversation.scrollHeight;
    if (container) {
      container.scrollTop = container.scrollHeight;
    }
  };

  applyScroll();
  requestAnimationFrame(applyScroll);
}

function updateConversationHistory(speaker, text, speakerUri = "", utteranceId = "", isUserUtterance = false) {
  if (utteranceId && state.processedUtteranceIds.has(utteranceId)) return;

  const displaySpeaker = resolveHistorySpeakerName(speaker, speakerUri);
  const lastEntry = state.conversationHistory[state.conversationHistory.length - 1];
  const isPeerAddressed = (value) => /^[a-z][a-z0-9 _-]{0,40}:\s+/i.test((value || "").trim());
  if (
    !isUserUtterance
    && lastEntry
    && lastEntry.speaker === displaySpeaker
    && isPeerAddressed(lastEntry.text)
    && isPeerAddressed(text)
  ) {
    return;
  }

  state.conversationHistory.push({ speaker: displaySpeaker, speakerUri: speakerUri || displaySpeaker, text });
  if (utteranceId) state.processedUtteranceIds.add(utteranceId);

  const lineNo = state.conversationHistory.length;
  const line = `${lineNo}. [${displaySpeaker.toUpperCase()}] ${text}`;
  const wordCount = text.trim().split(/\s+/).length;

  // Queue the message for display with delay management
  // Only apply delay for agent messages, not user messages
  messageQueue.queue.push({ line, wordCount, isUserMessage: isUserUtterance });
  processMessageQueue();
}

function processMessageQueue() {
  if (messageQueue.isProcessing || messageQueue.queue.length === 0) return;

  messageQueue.isProcessing = true;
  const { line, wordCount, isUserMessage } = messageQueue.queue.shift();

  // User messages display immediately; agent messages are delayed based on previous message's word count
  const requiredDelay = (!isUserMessage && MESSAGE_DISPLAY_DELAY_MS_PER_WORD > 0)
    ? messageQueue.lastMessageWordCount * MESSAGE_DISPLAY_DELAY_MS_PER_WORD
    : 0;

  const timeSinceLastDisplay = Date.now() - messageQueue.lastDisplayTime;
  const delayNeeded = Math.max(0, requiredDelay - timeSinceLastDisplay);

  setTimeout(() => {
    // Display the message
    if (ui.conversation.textContent.trim()) ui.conversation.textContent += "\n\n";
    ui.conversation.textContent += line;
    scrollConversationToLatest();

    // Update timing info for next message
    messageQueue.lastDisplayTime = Date.now();
    messageQueue.lastMessageWordCount = wordCount;

    // Process any queued messages
    messageQueue.isProcessing = false;
    processMessageQueue();
  }, delayNeeded);
}

function clearConversationHistory() {
  state.conversationHistory = [];
  state.processedUtteranceIds.clear();
  messageQueue.queue = [];
  messageQueue.lastDisplayTime = 0;
  messageQueue.lastMessageWordCount = 0;
  messageQueue.isProcessing = false;
  ui.conversation.textContent = "";
}

function clearEventLog() {
  ui.eventLog.textContent = "";
}

function clearErrorLog() {
  ui.errorLog.textContent = "";
}

function setDiagnosticsCollapsed(collapsed) {
  if (!ui.diagnosticsContent || !ui.toggleDiagnosticsBtn) return;

  ui.diagnosticsContent.hidden = !!collapsed;
  ui.toggleDiagnosticsBtn.textContent = collapsed ? "Show Diagnostics" : "Collapse Diagnostics";
  ui.toggleDiagnosticsBtn.setAttribute("aria-expanded", String(!collapsed));
}

function scrollLogToLatest(logElement) {
  if (!logElement) return;
  const applyScroll = () => {
    logElement.scrollTop = logElement.scrollHeight;
  };
  applyScroll();
  requestAnimationFrame(applyScroll);
}

function logEvent(message, payload = null) {
  const ts = new Date().toISOString();
  const chunk = payload ? `${message}\n${JSON.stringify(payload, null, 2)}` : message;
  ui.eventLog.textContent += `[${ts}] ${chunk}\n\n`;
  scrollLogToLatest(ui.eventLog);
}

function logError(message, payload = null) {
  const ts = new Date().toISOString();
  const chunk = payload ? `${message}\n${JSON.stringify(payload, null, 2)}` : message;
  ui.errorLog.textContent += `[${ts}] ${chunk}\n\n`;
  scrollLogToLatest(ui.errorLog);
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

  const visibleAgents = getVisibleKnownAgents(merged);

  ui.knownAgentList.innerHTML = "";
  for (const item of visibleAgents) {
    const option = document.createElement("option");
    option.value = item.conversationalName ? `${item.conversationalName} | ${item.url}` : item.url;
    ui.knownAgentList.appendChild(option);
  }

  if (ui.knownAgentSelect) {
    const currentUrl = ui.assistantUrl.value;
    ui.knownAgentSelect.innerHTML = '<option value="">-- select an agent --</option>';
    for (const item of visibleAgents) {
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
      await sendControlEvent("uninvite", agent.url);
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
  syncGlobalConversationState();
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
      } else if (usePrivate) {
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

  const blob = new Blob([buildInteractivePopupHtml(htmlContent)], { type: "text/html" });
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

function buildInteractivePopupHtml(htmlContent) {
  const content = typeof htmlContent === "string" ? htmlContent : "";

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent HTML Response</title>
  <style>
    body { margin: 0; font-family: Arial, sans-serif; background: #fff; color: #111827; }
    #toolbar { position: sticky; top: 0; z-index: 10; background: #f3f4f6; border-bottom: 1px solid #d1d5db; padding: 8px 12px; }
    #popupBackBtn { border: 1px solid #d1d5db; border-radius: 6px; background: #fff; color: #111827; padding: 6px 12px; cursor: pointer; }
    #popupBackBtn[hidden] { display: none; }
    #content { padding: 10px 12px; }
    #content img { max-width: 100%; height: auto; }
    body.image-view-active { background: #000; }
    body.image-view-active #toolbar { background: rgba(17, 24, 39, 0.92); border-bottom-color: rgba(255, 255, 255, 0.14); }
    body.image-view-active #popupBackBtn { background: #111827; color: #fff; border-color: rgba(255, 255, 255, 0.18); }
    body.image-view-active #content { min-height: calc(100vh - 58px); padding: 0; display: flex; align-items: center; justify-content: center; }
    .popup-image-view { width: 100%; height: calc(100vh - 58px); display: flex; align-items: center; justify-content: center; background: #000; }
    .popup-image-view img { width: 100%; height: 100%; object-fit: cover; display: block; }
  </style>
</head>
<body>
  <div id="toolbar">
    <button id="popupBackBtn" type="button" hidden>\u2190 Back</button>
  </div>
  <div id="content">${content}</div>
  <script>
    (function () {
      const contentRoot = document.getElementById("content");
      const backBtn = document.getElementById("popupBackBtn");
      const imageHistory = [];

      function updateBackButton() {
        backBtn.hidden = imageHistory.length === 0;
      }

      function toAbsoluteUrl(value) {
        try {
          return new URL(value, window.location.href).href;
        } catch (_error) {
          return "";
        }
      }

      function getLinkedImageUrl(img) {
        if (!img) return "";

        const anchor = img.closest("a[href]");
        if (anchor && anchor.getAttribute("href")) {
          return toAbsoluteUrl(anchor.getAttribute("href"));
        }

        const possibleAttrs = ["data-full", "data-full-src", "data-href", "data-link", "data-large", "data-original"];
        for (const attr of possibleAttrs) {
          const value = img.getAttribute(attr);
          if (value) return toAbsoluteUrl(value);
        }

        return "";
      }

      backBtn.addEventListener("click", function () {
        const previous = imageHistory.pop();
        if (!previous) {
          document.body.classList.remove("image-view-active");
          updateBackButton();
          return;
        }

        contentRoot.innerHTML = previous.html;
        document.body.classList.toggle("image-view-active", !!previous.imageViewActive);

        updateBackButton();
      });

      contentRoot.addEventListener("click", function (event) {
        const targetElement = event.target;
        const img = targetElement && targetElement.closest ? targetElement.closest("img") : null;
        if (!img || !contentRoot.contains(img)) return;

        const linkedUrl = getLinkedImageUrl(img);
        if (!linkedUrl) return;

        const currentSrc = img.currentSrc || img.getAttribute("src") || "";
        if (!currentSrc || linkedUrl === currentSrc) return;

        event.preventDefault();
        event.stopPropagation();

        imageHistory.push({
          html: contentRoot.innerHTML,
          imageViewActive: document.body.classList.contains("image-view-active")
        });

        contentRoot.innerHTML = '<div class="popup-image-view"><img src="' + linkedUrl.replace(/&/g, "&amp;").replace(/"/g, "&quot;") + '" alt="Expanded image"></div>';
        document.body.classList.add("image-view-active");
        updateBackButton();
      }, true);
    })();
  </script>
</body>
</html>`;
}

function processIncomingEnvelope(responseData, targetUrl, { directedAddressee = null } = {}) {
  let normalizedResponse = responseData;
  if (typeof normalizedResponse === "string") {
    try {
      normalizedResponse = JSON.parse(normalizedResponse);
    } catch (_error) {
      normalizedResponse = {};
    }
  }

  function queueHtmlPopupButton(htmlContent, senderName) {
    if (!htmlContent || !ui.htmlPopupArea) return;

    const blob = new Blob([buildInteractivePopupHtml(htmlContent)], { type: "text/html" });
    const htmlUrl = URL.createObjectURL(blob);

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "html-popup-btn";
    btn.textContent = `\u{1F4C4} View ${senderName || "agent"} response \u2192`;
    btn.addEventListener("click", () => {
      const popup = window.open(htmlUrl, "webFloorHtmlPopup", "popup=yes,width=980,height=720,resizable=yes,scrollbars=yes");
      if (!popup) {
        logError("Popup blocked. Please allow popups for this page in your browser.");
      } else {
        btn.remove();
        setTimeout(() => { try { URL.revokeObjectURL(htmlUrl); } catch (_) {} }, 60000);
      }
    });

    ui.htmlPopupArea.appendChild(btn);
  }

  const envelope = normalizedResponse?.openFloor || normalizedResponse?.ovon || normalizedResponse?.openfloor || normalizedResponse || {};
  const events = Array.isArray(envelope?.events) ? envelope.events : [];

  if (!events.length) {
    if (ui.showOutgoing.checked) {
      logEvent(`Agent at ${targetUrl} returned an empty events list (no response)`, {
        topLevelKeys: normalizedResponse && typeof normalizedResponse === "object" ? Object.keys(normalizedResponse) : [],
        resolvedEnvelopeKey: normalizedResponse?.openFloor ? "openFloor" : normalizedResponse?.ovon ? "ovon" : normalizedResponse?.openfloor ? "openfloor" : "top-level",
      });
    }
  }

  for (const event of events) {
    const eventType = event?.eventType || "";

    if (eventType === "uninvite") {
      removeInvitedAgent(targetUrl);
      continue;
    }

    if (eventType === "publishManifests" || eventType === "publishManifest") {
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
      if (speakerUri && speakerUri !== "Unknown" && normalizeAgentId(speakerUri) !== normalizeAgentId(state.clientUri)) {
        addConversantToGlobal(targetUrl || urlFromSpeakerUri(speakerUri), "", speakerUri);
      }
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
        queueHtmlPopupButton(htmlTokens[0].value, displayName);
      }

      // Rebroadcast incoming agent utterances to other agents as OFP messages.
      if (speakerUri && speakerUri !== "Unknown" && speakerUri !== state.clientUri) {
        const otherAgentUrls = state.invitedAgents
          .map(agent => agent.url)
          .filter(url => normalizeAgentId(url) !== normalizeAgentId(targetUrl));

        if (otherAgentUrls.length > 0) {
          const rebroadcastEvent = {
            eventType: "utterance",
            parameters: {
              dialogEvent: JSON.parse(JSON.stringify(dialog || {}))
            }
          };

          // Preserve explicit addressing when an agent intentionally targets
          // another agent. The client still broadcasts this same event to all
          // agents, and each recipient decides whether to act based on `to`.
          if (event?.to && typeof event.to === "object") {
            rebroadcastEvent.to = JSON.parse(JSON.stringify(event.to));
          }

          // Send OFP envelopes to all other agents via the client rebroadcast path.
          // If `rebroadcastEvent.to` is present, only the addressed agent should respond.
          otherAgentUrls.forEach(otherUrl => {
            const broadcastPayload = {
              openFloor: {
                conversation: serializeConversation(),
                sender: {
                  speakerUri: state.clientUri,
                  serviceUrl: state.clientUrl
                },
                events: [rebroadcastEvent]
              }
            };

            proxySend(otherUrl, broadcastPayload, 10000)
              .then((response) => {
                if (!response?.ok) {
                  if (ui.showOutgoing.checked) {
                    logError(`Broadcast request failed for ${otherUrl}`, response);
                  }
                  return;
                }

                const responseEnvelope = resolveAgentEnvelopeFromGatewayResponse(response);
                if (responseEnvelope) {
                  processIncomingEnvelope(responseEnvelope, otherUrl);
                } else if (ui.showOutgoing.checked) {
                  logError(`Non-JSON broadcast response from ${otherUrl}`, response);
                }
              })
              .catch(error => {
                if (ui.showOutgoing.checked) {
                  logError(`Failed to broadcast utterance to ${otherUrl}`, String(error));
                }
              });
          });
        }
      }
    }
  }

  if (ui.showIncoming.checked) {
    logEvent(`Incoming from ${targetUrl}`, normalizedResponse);
  }
}

function resolveAgentEnvelopeFromGatewayResponse(response) {
  if (!response || typeof response !== "object") return null;

  let candidate = response.json;

  if (typeof candidate === "string") {
    try {
      candidate = JSON.parse(candidate);
    } catch (_error) {
      candidate = null;
    }
  }

  if (!candidate && typeof response.text === "string" && response.text.trim()) {
    try {
      candidate = JSON.parse(response.text);
    } catch (_error) {
      candidate = null;
    }
  }

  if (!candidate || typeof candidate !== "object") return null;
  return candidate;
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

  if (eventType === "uninvite") {
    removeInvitedAgent(agentUrl);
  } else {
    setAgentStatus(agentUrl, "idle");
  }

  const responseEnvelope = resolveAgentEnvelopeFromGatewayResponse(response);
  if (responseEnvelope) processIncomingEnvelope(responseEnvelope, agentUrl, { directedAddressee: null });
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

    // Always render the user's utterance locally, even if downstream parsing/sending fails.
    try {
      updateConversationHistory("You", userInput, "", "", true);
    } catch (error) {
      // Last-resort UI fallback so user text is still visible in conversation history.
      const fallbackLineNo = state.conversationHistory.length + 1;
      const fallbackLine = `${fallbackLineNo}. [YOU] ${userInput}`;
      state.conversationHistory.push({ speaker: "You", speakerUri: "You", text: userInput });
      if (ui.conversation.textContent.trim()) ui.conversation.textContent += "\n\n";
      ui.conversation.textContent += fallbackLine;
      ui.conversation.scrollTop = ui.conversation.scrollHeight;
      logError("Failed to render user utterance via standard formatter; used fallback", String(error));
    }

    try {
      addressedAgent = findAddressedAgentInUtterance(userInput);
      if (addressedAgent && state.invitedAgents.length) {
        if (isUrlLike(addressedAgent.name)) {
          addressedAgent.name = resolveDisplayNameForTarget(addressedAgent.url || urlFromSpeakerUri(addressedAgent.speaker_uri), addressedAgent.speaker_uri);
        }
        parsedUserInput = parseUtteranceForAddressedAgent(userInput, addressedAgent);
        targetUrls = state.invitedAgents.map((agent) => agent.url);
      }
    } catch (error) {
      logError("Failed to parse addressed agent in utterance", String(error));
    }
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
  const timeoutMs = eventTypes.includes("utterance") ? 30000 : 10000;

  const sendTasks = targetUrls.map(async (targetUrl) => {
    if (eventTypes.includes("invite")) {
      addInvitedAgent(targetUrl);
      renderAgents();
      updateSendButtonState();
    }

    setAgentStatus(targetUrl, "working");

    const payload = buildEnvelopeForTarget(targetUrl, eventTypes, parsedUserInput, addressedAgent, usePrivate);
    if (ui.showOutgoing.checked) logEvent(`Outgoing to ${targetUrl}`, payload);
    if (ui.showOutgoing.checked) {
      logEvent(`Gateway timeout for ${targetUrl}`, {
        eventTypes,
        timeoutMs
      });
    }

    let response;
    try {
      response = await proxySend(targetUrl, payload, timeoutMs);
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

    const responseEnvelope = resolveAgentEnvelopeFromGatewayResponse(response);
    if (responseEnvelope) {
      processIncomingEnvelope(responseEnvelope, targetUrl, { directedAddressee: addressedAgent });
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
  ui.clearConversationBtn.addEventListener("click", clearConversationHistory);
  if (ui.copyConversationBtn) {
    ui.copyConversationBtn.addEventListener("click", () => {
      const text = ui.conversation ? ui.conversation.textContent : "";
      navigator.clipboard.writeText(text).then(() => {
        const btn = ui.copyConversationBtn;
        const original = btn.textContent;
        btn.textContent = "Copied!";
        setTimeout(() => { btn.textContent = original; }, 1500);
      }).catch(() => {});
    });
  }
  ui.clearEventLogBtn.addEventListener("click", clearEventLog);
  ui.clearErrorLogBtn.addEventListener("click", clearErrorLog);

  if (ui.toggleDiagnosticsBtn && ui.diagnosticsContent) {
    ui.toggleDiagnosticsBtn.addEventListener("click", () => {
      setDiagnosticsCollapsed(!ui.diagnosticsContent.hidden);
    });
  }

  ui.assistantUrl.addEventListener("input", updateSendButtonState);

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
        updateSendButtonState();
      }
    });
  }
}

function init() {
  refreshKnownAgentList();
  renderAgents();
  updateSendButtonState();
  bindEvents();
  setDiagnosticsCollapsed(false);
}

init();
