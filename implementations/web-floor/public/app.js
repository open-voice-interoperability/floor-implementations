// Configurable delay (in milliseconds) per word. After a message is posted, the next message
// will be delayed by (word_count * MESSAGE_DISPLAY_DELAY_MS_PER_WORD) milliseconds to give
// the user time to read the previous message. Set to 0 to disable delay.
const MESSAGE_DISPLAY_DELAY_MS_PER_WORD = 150;

// Upper bound for freeing a popup's blob URL if we never observe it closing.
const POPUP_URL_REVOKE_MAX_MS = 60000;
// How often to check whether a popup window has been closed by the user.
const POPUP_CLOSE_POLL_MS = 1000;

// Proxy-send timeouts: control events (invite, getManifests, grantFloor, etc.)
// resolve quickly; utterance events can trigger a long convener fan-out.
const CONTROL_EVENT_TIMEOUT_MS = 10000;
const UTTERANCE_TIMEOUT_MS = 180000;

// Revoke a popup's object URL as soon as the popup closes (freeing memory
// promptly), with a hard fallback cap so the URL is never leaked indefinitely.
function scheduleBlobUrlCleanup(popup, htmlUrl) {
  const revoke = () => {
    try { URL.revokeObjectURL(htmlUrl); } catch (_) { /* no-op */ }
  };
  if (!popup) {
    setTimeout(revoke, POPUP_URL_REVOKE_MAX_MS);
    return;
  }
  const startedAt = Date.now();
  const poll = setInterval(() => {
    if (popup.closed || Date.now() - startedAt >= POPUP_URL_REVOKE_MAX_MS) {
      clearInterval(poll);
      revoke();
    }
  }, POPUP_CLOSE_POLL_MS);
}

// Internal message queue and timing tracking for display delays
const messageQueue = {
  queue: [],
  lastDisplayTime: 0,
  lastMessageWordCount: 0,
  isProcessing: false
};

const KNOWN_AGENTS = [
  { url: "https://openvoice-stella.vercel.app/", conversationalName: "Stella (Vercel)" },
  { url: "http://127.0.0.1:8767/", conversationalName: "Stella (local 8767)" },
  { url: "http://127.0.0.1:8768/verity/", conversationalName: "Verity" },
  { url: "http://127.0.0.1:8769/", conversationalName: "GeminiGeo" },
  { url: "http://127.0.0.1:8081/", conversationalName: "TimeAgent" },
  { url: "https://openvoice-time-agent.vercel.app/", conversationalName: "TimeAgent" },
  { url: "http://127.0.0.1:8082/", conversationalName: "Erin" },
  { url: "http://127.0.0.1:8086/", conversationalName: "Convener" },
  { url: "https://secondAssistant.pythonanywhere.com/verity/", conversationalName: "Verity 2" },
  { url: "http://127.0.0.1:8083/", conversationalName: "Finn" },
  { url: "http://127.0.0.1:8084/", conversationalName: "Prudence" },
  { url: "http://127.0.0.1:8085/", conversationalName: "Lucky" },
  { url: "http://127.0.0.1:8199/", conversationalName: "Convener (Strategy)" },
  { url: "http://127.0.0.1:8200/", conversationalName: "Market Validator" },
  { url: "http://127.0.0.1:8201/", conversationalName: "Competitive Intelligence" },
  { url: "http://127.0.0.1:8202/", conversationalName: "Business Model Designer" },
  { url: "http://127.0.0.1:8203/", conversationalName: "Risk Identifier" },
  { url: "http://127.0.0.1:8204/", conversationalName: "Funding Strategist" },
  { url: "http://127.0.0.1:8205/", conversationalName: "Workforce Strategist" },
  { url: "http://127.0.0.1:8208/", conversationalName: "Technical Feasibility" },
  { url: "http://127.0.0.1:8206/", conversationalName: "Devil's Advocate" },
  { url: "http://127.0.0.1:8207/", conversationalName: "Strategy Synthesizer" },
  { url: "http://127.0.0.1:8300/", conversationalName: "Cafeteria Ops Convener" },
  { url: "http://127.0.0.1:8301/", conversationalName: "Menu Designer" },
  { url: "http://127.0.0.1:8302/", conversationalName: "Nutrition Specialist" },
  { url: "http://127.0.0.1:8303/", conversationalName: "Recipe & Portion Specialist" },
  { url: "http://127.0.0.1:8304/", conversationalName: "Menu Optimization Specialist" },
  { url: "http://127.0.0.1:8305/", conversationalName: "Inventory Specialist" },
  { url: "http://127.0.0.1:8306/", conversationalName: "Procurement Specialist" },
  { url: "http://127.0.0.1:8310/", conversationalName: "Shopping List Specialist" },
  { url: "https://bladeszasza-ofpbadword.hf.space/ofp", conversationalName: "" },
  { url: "https://yahandhjjf.us-east-1.awsapprunner.com/", conversationalName: "" }
];

const LOOPBACK_HOSTNAMES = new Set(["localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"]);

function rewriteLoopbackUrlForCurrentHost(urlValue) {
  if (typeof window === "undefined") return urlValue;

  const currentHost = (window.location.hostname || "").trim();
  if (!currentHost) return urlValue;

  const candidate = cleanUrlCandidate(urlValue);
  if (!candidate) return urlValue;

  try {
    const parsed = new URL(candidate);
    const hostname = (parsed.hostname || "").toLowerCase();
    if (!LOOPBACK_HOSTNAMES.has(hostname)) return candidate;

    parsed.hostname = currentHost;
    return parsed.toString();
  } catch (_error) {
    return urlValue;
  }
}

function buildRuntimeKnownAgents(agents) {
  return (agents || []).map((agent) => ({
    ...agent,
    url: rewriteLoopbackUrlForCurrentHost(agent.url)
  }));
}

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
  if (GATEWAY_BASE_URL) return `${GATEWAY_BASE_URL}${pathname}`;
  if (isLocalClientContext()) return `http://localhost:8090${pathname}`;
  return pathname;
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
  responsePatternDefault: document.querySelector("#responsePatternDefault"),
  responsePatternRoundRobin: document.querySelector("#responsePatternRoundRobin"),
  maxWordsSlider: document.querySelector("#maxWordsSlider"),
  maxWordsValue: document.querySelector("#maxWordsValue"),
  showIncoming: document.querySelector("#showIncoming"),
  showOutgoing: document.querySelector("#showOutgoing"),
  getManifestsBtn: document.querySelector("#getManifestsBtn"),
  inviteBtn: document.querySelector("#inviteBtn"),
  sendUtteranceBtn: document.querySelector("#sendUtteranceBtn"),
  clearConversationBtn: document.querySelector("#clearConversationBtn"),
  copyConversationBtn: document.querySelector("#copyConversationBtn"),
  showConversationMarkdownBtn: document.querySelector("#showConversationMarkdownBtn"),
  copyEventLogBtn: document.querySelector("#copyEventLogBtn"),
  copyErrorLogBtn: document.querySelector("#copyErrorLogBtn"),
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

const RUNTIME_HOST = window.location.host || window.location.hostname || "localhost";
const RUNTIME_CLIENT_URL = (window.location.origin && window.location.origin !== "null")
  ? window.location.origin
  : `http://${window.location.hostname || "localhost"}`;

const state = {
  clientName: "AssistantClientConvenerWeb",
  clientUrl: RUNTIME_CLIENT_URL,
  clientUri: `openFloor://${RUNTIME_HOST}/AssistantClientConvenerWeb`,
  knownAgents: buildRuntimeKnownAgents(KNOWN_AGENTS),
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

  // If hostnames differ only by loopback/local-network rewrite (localhost vs LAN IP),
  // still resolve by matching local endpoint shape (scheme + port + path).
  try {
    const targetParsed = new URL(cleanUrlCandidate(targetUrl));
    for (const item of state.knownAgents) {
      if (!item.conversationalName) continue;
      const knownParsed = new URL(cleanUrlCandidate(item.url));
      const sameEndpoint =
        knownParsed.protocol === targetParsed.protocol &&
        (knownParsed.port || "") === (targetParsed.port || "") &&
        knownParsed.pathname.replace(/\/+$/, "") === targetParsed.pathname.replace(/\/+$/, "");
      if (!sameEndpoint) continue;

      const targetHostIsLocal = LOOPBACK_HOSTNAMES.has((targetParsed.hostname || "").toLowerCase()) || isLocalClientContext();
      const knownHostIsLocal = LOOPBACK_HOSTNAMES.has((knownParsed.hostname || "").toLowerCase()) || isLocalClientContext();
      if (targetHostIsLocal && knownHostIsLocal) return item.conversationalName;
    }
  } catch (_error) {
    // Ignore parse errors and fall through to no-name result.
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

function isRevokedSpeaker(targetUrl, speakerUri = "") {
  const targetId = normalizeAgentId(targetUrl);
  if (targetId && state.revokedAgents.has(targetId)) return true;

  const speakerUrl = urlFromSpeakerUri(speakerUri);
  const speakerId = normalizeAgentId(speakerUrl || speakerUri);
  if (speakerId && state.revokedAgents.has(speakerId)) return true;

  return false;
}

// Client-side addressed-agent detection (findAddressedAgentInUtterance and
// friends) was removed here: convener's own classify_utterance()/
// detect_addressed_agent() (unchanged) already reads addressing directly
// out of the raw utterance text server-side -- the floor manager no longer
// needs the client to pre-parse "Market Validator, ..." style prefixes or
// pre-grant a target's floor before sending.

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
  const fallbackName = conversationalName || knownNameForUrl(agentUrl) || resolveDisplayNameForTarget(agentUrl) || "";

  for (const agent of state.invitedAgents) {
    if (normalizeAgentId(agent.url) === normalizedTarget) {
      if (conversationalName) {
        agent.conversationalName = conversationalName;
      } else if (!agent.conversationalName || isUrlLike(agent.conversationalName)) {
        agent.conversationalName = fallbackName;
      }
      return;
    }
  }

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

function copyEventLogToClipboard() {
  const text = ui.eventLog.textContent;
  if (!text) {
    alert("Event log is empty.");
    return;
  }
  navigator.clipboard.writeText(text).then(() => {
    alert("Event log copied to clipboard!");
  }).catch(err => {
    logError("Failed to copy to clipboard", err);
    alert("Failed to copy to clipboard.");
  });
}

function copyErrorLogToClipboard() {
  const text = ui.errorLog.textContent;
  if (!text) {
    alert("Error log is empty.");
    return;
  }
  navigator.clipboard.writeText(text).then(() => {
    alert("Error log copied to clipboard!");
  }).catch(err => {
    logError("Failed to copy to clipboard", err);
    alert("Failed to copy to clipboard.");
  });
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
    floorBtn.textContent = revoked ? "grantFloor" : "revokeFloor";
    floorBtn.className = revoked ? "floor-btn-grant" : "floor-btn-revoke";
    floorBtn.addEventListener("click", async () => {
      // Advisory now that a convener may be registered (Delegate-to-Convener
      // per the OFP routing table) -- don't optimistically mutate local
      // state before the request completes. sendControlEvent's response
      // handling (via processIncomingEnvelope) is what actually updates
      // state.revokedAgents + re-renders, from the floor manager's own
      // authoritative grantFloor/revokeFloor events.
      await sendControlEvent(revoked ? "grantFloor" : "revokeFloor", agent.url);
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

function getSelectedResponsePattern() {
  if (ui.responsePatternRoundRobin?.checked) return "round_robin";
  return "default";
}

function buildDialogEvent(userInput, routingMode = "") {
  const features = {
    text: {
      mimeType: "text/plain",
      tokens: [{ value: userInput }]
    }
  };

  if (routingMode && routingMode !== "default") {
    features.routingMode = {
      mimeType: "text/plain",
      tokens: [{ value: routingMode }]
    };
  }

  const maxWords = ui.maxWordsSlider ? parseInt(ui.maxWordsSlider.value, 10) : 125;
  features.maxWords = {
    mimeType: "text/plain",
    tokens: [{ value: String(maxWords) }]
  };

  return {
    speakerUri: state.clientUri,
    features
  };
}

function buildEnvelopeForTarget(targetUrl, eventTypes, userInput, addressedAgent, usePrivate, routingMode = "") {
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
          dialogEvent: buildDialogEvent(userInput, routingMode)
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

async function proxySend(targetUrl, payload, timeoutMs = CONTROL_EVENT_TIMEOUT_MS) {
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

// Streaming counterpart to proxySend: the gateway relays the upstream body as
// bytes arrive (newline-delimited JSON envelopes) instead of buffering the
// whole response first. onEnvelope is called once per parsed line, as soon as
// it's available, so callers can render each turn immediately rather than
// waiting for the entire response to finish. Used by round-robin mode so each
// specialist's answer shows up as soon as that specialist replies.
async function proxyStream(targetUrl, payload, timeoutMs, onEnvelope) {
  const gatewayUrl = gatewayPath("/api/proxy-stream");
  const response = await fetch(gatewayUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ targetUrl, payload, timeoutMs })
  });

  if (!response.ok || !response.body) {
    const preview = (await response.text().catch(() => "")).replace(/\s+/g, " ").slice(0, 160);
    throw new Error(`Gateway stream failed from ${gatewayUrl} (${response.status} ${response.statusText}): ${preview}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const consumeLine = (line) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    try {
      onEnvelope(JSON.parse(trimmed));
    } catch (error) {
      logError(`Failed to parse streamed line from ${targetUrl}`, String(error));
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: true });
      let newlineIndex;
      while ((newlineIndex = buffer.indexOf("\n")) !== -1) {
        consumeLine(buffer.slice(0, newlineIndex));
        buffer = buffer.slice(newlineIndex + 1);
      }
    }
    if (done) break;
  }

  consumeLine(buffer);
}

// Floor-managed counterparts to proxySend/proxyStream: no targetUrl -- the
// floor manager (web-floor/api/floor_router.py) derives who gets each event
// from its own conversant/floor state and the OFP routing table, not from a
// client-chosen target. This is the ONLY way floor-managed traffic (invite,
// grantFloor/revokeFloor, utterance) should reach agents now; /api/proxy-send
// and /api/proxy-stream remain for genuinely raw, unmanaged single-agent pokes.
async function floorSend(payload, timeoutMs = CONTROL_EVENT_TIMEOUT_MS) {
  const gatewayUrl = gatewayPath("/api/floor/send");
  const response = await fetch(gatewayUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ payload, timeoutMs })
  });

  const rawText = await response.text();

  try {
    return rawText ? JSON.parse(rawText) : {};
  } catch (_error) {
    const preview = rawText.replace(/\s+/g, " ").slice(0, 160);
    throw new Error(
      `Floor manager returned non-JSON from ${gatewayUrl} (${response.status} ${response.statusText}): ${preview}`
    );
  }
}

async function floorStream(payload, timeoutMs, onEnvelope) {
  const gatewayUrl = gatewayPath("/api/floor/stream");
  const response = await fetch(gatewayUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ payload, timeoutMs })
  });

  if (!response.ok || !response.body) {
    const preview = (await response.text().catch(() => "")).replace(/\s+/g, " ").slice(0, 160);
    throw new Error(`Floor manager stream failed from ${gatewayUrl} (${response.status} ${response.statusText}): ${preview}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const consumeLine = (line) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    try {
      onEnvelope(JSON.parse(trimmed));
    } catch (error) {
      logError("Failed to parse streamed line from floor manager", String(error));
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: true });
      let newlineIndex;
      while ((newlineIndex = buffer.indexOf("\n")) !== -1) {
        consumeLine(buffer.slice(0, newlineIndex));
        buffer = buffer.slice(newlineIndex + 1);
      }
    }
    if (done) break;
  }

  consumeLine(buffer);
}

async function fetchFloorState(conversationId) {
  const gatewayUrl = gatewayPath(`/api/floor/state?conversationId=${encodeURIComponent(conversationId)}`);
  const response = await fetch(gatewayUrl);
  if (!response.ok) return null;
  try {
    return await response.json();
  } catch (_error) {
    return null;
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

function extractFeatureTokenValue(feature) {
  if (!feature) return "";
  const tokens = feature?.tokens || [];
  if (tokens.length) {
    if (typeof tokens[0] === "string") return tokens[0];
    return tokens[0]?.value || "";
  }
  const values = feature?.values || [];
  if (values.length) {
    if (typeof values[0] === "string") return values[0];
    return values[0]?.value || "";
  }
  return "";
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

  scheduleBlobUrlCleanup(popup, htmlUrl);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderInlineMarkdown(text) {
  let html = escapeHtml(text || "");

  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');

  return html;
}

function markdownToHtml(markdownText) {
  const lines = String(markdownText || "").replace(/\r\n/g, "\n").split("\n");
  const out = [];

  let inCodeBlock = false;
  let codeBuffer = [];
  let listType = null;

  const closeList = () => {
    if (!listType) return;
    out.push(listType === "ol" ? "</ol>" : "</ul>");
    listType = null;
  };

  for (const line of lines) {
    if (/^```/.test(line.trim())) {
      closeList();
      if (inCodeBlock) {
        out.push(`<pre><code>${escapeHtml(codeBuffer.join("\n"))}</code></pre>`);
        codeBuffer = [];
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
      }
      continue;
    }

    if (inCodeBlock) {
      codeBuffer.push(line);
      continue;
    }

    if (!line.trim()) {
      closeList();
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      closeList();
      const level = heading[1].length;
      out.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    if (/^---+$/.test(line.trim())) {
      closeList();
      out.push("<hr>");
      continue;
    }

    const unordered = line.match(/^\s*[-*]\s+(.+)$/);
    if (unordered) {
      if (listType !== "ul") {
        closeList();
        out.push("<ul>");
        listType = "ul";
      }
      out.push(`<li>${renderInlineMarkdown(unordered[1])}</li>`);
      continue;
    }

    const ordered = line.match(/^\s*\d+\.\s+(.+)$/);
    if (ordered) {
      if (listType !== "ol") {
        closeList();
        out.push("<ol>");
        listType = "ol";
      }
      out.push(`<li>${renderInlineMarkdown(ordered[1])}</li>`);
      continue;
    }

    closeList();
    out.push(`<p>${renderInlineMarkdown(line)}</p>`);
  }

  if (inCodeBlock) {
    out.push(`<pre><code>${escapeHtml(codeBuffer.join("\n"))}</code></pre>`);
  }
  closeList();

  return out.join("\n");
}

function buildConversationMarkdownPopupHtml(markdownText) {
  const renderedHtml = markdownToHtml(markdownText);

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Conversation History (Markdown)</title>
  <style>
    body { margin: 0; font-family: Segoe UI, Arial, sans-serif; background: #ffffff; color: #111111; }
    .wrap { max-width: 980px; margin: 0 auto; padding: 16px; }
    .card { background: #ffffff; border: 1px solid #d1d5db; border-radius: 10px; padding: 16px; margin-bottom: 16px; }
    h1,h2,h3,h4,h5,h6 { margin: 0.65em 0 0.35em; color: #111111; }
    p, li { line-height: 1.5; }
    a { color: #0b57d0; }
    code { background: #f3f4f6; border: 1px solid #d1d5db; border-radius: 4px; padding: 0 5px; }
    pre { background: #f9fafb; border: 1px solid #d1d5db; border-radius: 8px; padding: 12px; overflow: auto; }
    hr { border: none; border-top: 1px solid #d1d5db; margin: 14px 0; }
    .meta { color: #4b5563; font-size: 13px; margin-top: 4px; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      ${renderedHtml}
    </div>
  </div>
</body>
</html>`;
}

function openConversationMarkdownPopup() {
  if (!state.conversationHistory.length) {
    logError("Conversation history is empty.");
    return;
  }

  const lines = ["# Conversation History", ""];
  for (const entry of state.conversationHistory) {
    lines.push(`## ${entry.speaker || "Unknown"}`);
    lines.push("");
    lines.push(entry.text || "");
    lines.push("");
  }
  const markdownText = lines.join("\n");

  const blob = new Blob([buildConversationMarkdownPopupHtml(markdownText)], { type: "text/html" });
  const htmlUrl = URL.createObjectURL(blob);
  const popup = window.open(htmlUrl, "webFloorConversationMarkdown", "popup=yes,width=1100,height=800,resizable=yes,scrollbars=yes");

  if (!popup) {
    logError("Popup blocked while opening markdown conversation view.");
    URL.revokeObjectURL(htmlUrl);
    return;
  }

  scheduleBlobUrlCleanup(popup, htmlUrl);
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

// Creates a button that opens a pre-built HTML report in a popup.
function queueHtmlPopupButton(htmlContent, buttonLabel) {
  if (!htmlContent || !ui.htmlPopupArea) return;

  const blob = new Blob([buildInteractivePopupHtml(htmlContent)], { type: "text/html" });
  const htmlUrl = URL.createObjectURL(blob);

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "html-popup-btn";
  btn.textContent = `\u{1F4CA} ${buttonLabel || "Analysis"} \u2192`;
  btn.addEventListener("click", () => {
    const popup = window.open(htmlUrl, "webFloorHtmlPopup", "popup=yes,width=980,height=720,resizable=yes,scrollbars=yes");
    if (!popup) {
      logError("Popup blocked. Please allow popups for this page in your browser.");
    } else {
      btn.remove();
      scheduleBlobUrlCleanup(popup, htmlUrl);
    }
  });

  ui.htmlPopupArea.appendChild(btn);
  btn.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// Builds the combined multi-agent report popup from accumulated entries.
// Pulled out of processIncomingEnvelope so callers driving multiple separate
// envelopes for one logical round (e.g. round-robin streaming, one envelope
// per specialist turn) can accumulate entries across all of them and build
// the report once at the end, instead of getting a fresh, single-entry array
// on every call.
function buildAndQueueCombinedReport(htmlReportEntries) {
  if (!(htmlReportEntries.length > 1 || htmlReportEntries.some(e => e.html))) return;

  const esc = s => (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const sections = htmlReportEntries.map(entry => {
    const nameHtml = `<h2 style="font-family:sans-serif;margin:0 0 8px;font-size:1.1rem;color:#1a1a1a;border-bottom:2px solid #2196F3;padding-bottom:4px">${esc(entry.name)}</h2>`;
    // entry.html, when present, is already a full rendering of entry.text
    // (a real <ul><li> list, an image-illustrated <p>, or a chart) -- showing
    // the raw text again alongside it just duplicates the same content, and
    // since a <p> collapses entry.text's own newlines, that duplicate shows
    // up as a flattened one-line run-on right above the properly formatted
    // version. Only fall back to the plain-text paragraph when there's no
    // html rendering of it to show instead.
    const textHtml = entry.text && !entry.html
      ? `<p style="font-family:sans-serif;margin:0 0 12px;font-size:0.9rem;color:#333;line-height:1.5">${esc(entry.text)}</p>`
      : "";
    return `<section style="margin-bottom:28px">${nameHtml}${textHtml}${entry.html}</section>`;
  });
  const combinedHtml = sections.join('<hr style="border:none;border-top:1px solid #e0e0e0;margin:4px 0 28px">');
  const label = htmlReportEntries.length === 1
    ? `${htmlReportEntries[0].name} chart`
    : "Full Analysis Report";
  queueHtmlPopupButton(combinedHtml, label);
}

function processIncomingEnvelope(responseData, targetUrl, { directedAddressee = null, reportEntries = null, buildReport = true } = {}) {
  let normalizedResponse = responseData;
  if (typeof normalizedResponse === "string") {
    try {
      normalizedResponse = JSON.parse(normalizedResponse);
    } catch (_error) {
      normalizedResponse = {};
    }
  }

  // Accumulates all agent utterance responses in this envelope for the
  // combined report. When a caller is driving multiple envelopes for one
  // logical round (round-robin streaming), it supplies a shared array via
  // reportEntries so entries accumulate across calls instead of resetting.
  const htmlReportEntries = reportEntries || [];

  const envelope = normalizedResponse?.openFloor || normalizedResponse?.ovon || normalizedResponse?.openfloor || normalizedResponse || {};
  const events = Array.isArray(envelope?.events) ? envelope.events : [];

  const eventTarget = (event) => {
    const to = event?.to || event?.parameters?.to || {};
    return {
      serviceUrl: cleanUrlCandidate(to?.serviceUrl || ""),
      speakerUri: to?.speakerUri || "",
    };
  };

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
      const target = eventTarget(event).serviceUrl || targetUrl;
      removeInvitedAgent(target);
      continue;
    }

    if (eventType === "grantFloor") {
      const target = eventTarget(event).serviceUrl;
      if (target) {
        state.revokedAgents.delete(normalizeAgentId(target));
        renderAgents();
      }
      continue;
    }

    if (eventType === "revokeFloor") {
      const target = eventTarget(event).serviceUrl;
      if (target) {
        state.revokedAgents.add(normalizeAgentId(target));
        renderAgents();
      }
      continue;
    }

    if (eventType === "invite") {
      const target = eventTarget(event);
      const inviteTargetUrl = target.serviceUrl;
      if (inviteTargetUrl) {
        const normalizedTarget = cleanUrlCandidate(inviteTargetUrl);
        const inviteTargetName = resolveDisplayNameForTarget(normalizedTarget, target.speakerUri || "");
        const alreadyInvited = state.invitedAgents.some(a => normalizeAgentId(a.url) === normalizeAgentId(normalizedTarget));
        if (!alreadyInvited && normalizedTarget) {
          updateConversationHistory("Floor", `Inviting ${knownNameForUrl(normalizedTarget) || normalizedTarget}...`);
          addInvitedAgent(normalizedTarget, inviteTargetName);
          sendControlEvent("invite", normalizedTarget).catch(err => {
            logError(`Agent-initiated invite to ${normalizedTarget} failed`, String(err));
          });
        } else if (alreadyInvited && normalizedTarget) {
          addInvitedAgent(normalizedTarget, inviteTargetName);
        }
      }
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
      const sourceNameFeature = dialog?.features?.sourceName;
      const sourceName = (extractFeatureTokenValue(sourceNameFeature) || "").trim();

      // Every response now comes from the floor manager (targetUrl no longer
      // identifies who's actually speaking -- it's always the gateway), so
      // who spoke is read entirely from the event's own dialogEvent.speakerUri.
      const speakerUri = dialog?.speakerUri || "";
      const speakingAgentUrl = urlFromSpeakerUri(speakerUri) || cleanUrlCandidate(speakerUri) || cleanUrlCandidate(targetUrl);
      const speakingAgentId = normalizeAgentId(speakingAgentUrl);

      if (isRevokedSpeaker(speakingAgentUrl, speakerUri)) {
        // Defensive only: the floor manager shouldn't deliver an utterance
        // from an agent it hasn't granted the floor to, but suppress it
        // client-side too in case local state is momentarily stale.
        if (ui.showOutgoing.checked) {
          logEvent(`Suppressed utterance from revoked agent ${speakingAgentUrl}`, event);
        }
        continue;
      }

      const effectiveSpeakerUri = speakerUri || "Unknown";
      if (effectiveSpeakerUri && effectiveSpeakerUri !== "Unknown" && normalizeAgentId(effectiveSpeakerUri) !== normalizeAgentId(state.clientUri)) {
        addConversantToGlobal(speakingAgentUrl || urlFromSpeakerUri(effectiveSpeakerUri), "", effectiveSpeakerUri);
      }
      const displayName = sourceName || resolveDisplayNameForTarget(speakingAgentUrl || targetUrl, effectiveSpeakerUri);
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

      text = normalizeLeadingUrlInText(text, effectiveSpeakerUri, speakingAgentUrl || targetUrl);
      text = prependDirectAddressContext(text, directedTarget, {
        speakerName: displayName,
        speakerUri: effectiveSpeakerUri,
        speakerUrl: targetUrl
      });

      updateConversationHistory(displayName, text, effectiveSpeakerUri, utteranceId);

      // Floor state (grantFloor/revokeFloor) is no longer inferred from
      // "an agent just spoke" -- the floor manager reports its own explicit
      // grantFloor/revokeFloor events (handled above), authoritatively,
      // as real events in this same response envelope.

      const htmlVal = dialog?.features?.html?.tokens?.[0]?.value || "";
      // Collect this response for the combined report built after all events are processed.
      htmlReportEntries.push({ name: displayName, text, html: htmlVal });

      // Per the Open Floor Interoperable Conversation Envelope spec, routing
      // (including rebroadcasting an utterance to other conversants) is the
      // floor manager's responsibility alone -- a conversant (this client,
      // or any agent) never redistributes another conversant's event itself.
      // Multi-agent fan-out belongs server-side, in the floor manager.
    }
  }

  // Build combined report for multi-agent responses (convener fan-out) or
  // any HTML content. Skipped when the caller supplied a shared
  // reportEntries array (round-robin streaming) -- it builds the report
  // itself, once, after all of that round's envelopes have been processed.
  if (buildReport) {
    buildAndQueueCombinedReport(htmlReportEntries);
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
  // Floor-managed: grantFloor/revokeFloor/uninvite are Delegate-to-Convener
  // events per the OFP spec's routing table when a convener is registered
  // (an advisory request convener can veto/substitute), or Pass-Through
  // directly otherwise -- either way, go through the floor manager, never
  // straight to the agent.
  setAgentStatus(agentUrl, "working");

  const payload = buildEnvelopeForTarget(agentUrl, [eventType], "", null, false);
  if (ui.showOutgoing.checked) logEvent(`Outgoing ${eventType} to ${agentUrl}`, payload);

  let response;
  try {
    response = await floorSend(payload, CONTROL_EVENT_TIMEOUT_MS);
  } catch (error) {
    setAgentStatus(agentUrl, "error");
    logError(`${eventType} failed for ${agentUrl}`, String(error));
    return false;
  }

  if (!response?.openFloor) {
    setAgentStatus(agentUrl, "error");
    logError(`${eventType} failed for ${agentUrl}`, response);
    return false;
  }

  if (eventType === "uninvite") {
    removeInvitedAgent(agentUrl);
  } else {
    setAgentStatus(agentUrl, "idle");
  }

  // The floor manager's own response events (e.g. convener substituting a
  // different decision) drive UI state from here -- see the grantFloor/
  // revokeFloor branches in processIncomingEnvelope.
  processIncomingEnvelope(response, agentUrl, { directedAddressee: null });
  return true;
}

async function sendEvents(eventTypes) {
  const assistantUrlRaw = ui.assistantUrl.value || "";
  const assistantUrl = cleanUrlCandidate(assistantUrlRaw.includes(" | ") ? assistantUrlRaw.split(" | ").slice(-1)[0] : assistantUrlRaw);
  const userInput = (ui.utteranceInput.value || "").trim();
  const responsePattern = getSelectedResponsePattern();

  if (eventTypes.includes("utterance") && !userInput) {
    logError("Please enter some text before sending an utterance.");
    return;
  }

  // getManifests is a single-agent probe. Per the OFP routing table it's
  // Pass-Through to ALL conversants once floor-managed -- not what a manual
  // "check this one candidate agent's manifest" click wants (often before
  // it's even invited) -- so it stays on the raw, unmanaged proxy path.
  if (eventTypes.length === 1 && eventTypes[0] === "getManifests") {
    if (!assistantUrl) {
      logError("No Assistant URL specified.");
      return;
    }
    setAgentStatus(assistantUrl, "working");
    const payload = buildEnvelopeForTarget(assistantUrl, ["getManifests"], "", null, false);
    if (ui.showOutgoing.checked) logEvent(`Outgoing to ${assistantUrl}`, payload);
    try {
      const response = await proxySend(assistantUrl, payload, CONTROL_EVENT_TIMEOUT_MS);
      if (!response?.ok) {
        setAgentStatus(assistantUrl, "error");
        logError(`Request failed for ${assistantUrl}`, response);
        return;
      }
      setAgentStatus(assistantUrl, "idle");
      const responseEnvelope = resolveAgentEnvelopeFromGatewayResponse(response);
      if (responseEnvelope) {
        processIncomingEnvelope(responseEnvelope, assistantUrl, { directedAddressee: null });
      } else {
        logError(`Non-JSON response from ${assistantUrl}`, response);
        setAgentStatus(assistantUrl, "error");
      }
    } catch (error) {
      setAgentStatus(assistantUrl, "error");
      logError(`Request failed for ${assistantUrl}`, String(error));
    }
    return;
  }

  if (eventTypes.includes("invite") && !assistantUrl) {
    logError("No Assistant URL specified.");
    return;
  }

  if (eventTypes.includes("utterance")) {
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
  }

  if (assistantUrl && !state.previousUrls.some((url) => normalizeAgentId(url) === normalizeAgentId(assistantUrl))) {
    state.previousUrls.push(assistantUrl);
    refreshKnownAgentList();
  }

  // No more per-target fan-out, no more client-side addressed-agent
  // detection or round-robin convener-target resolution: the floor manager
  // (floor_router.py) derives who gets this from its own conversant/floor
  // state and the OFP routing table, and convener's existing
  // classify_utterance()/detect_addressed_agent() (unchanged) reads
  // addressing directly out of the utterance text server-side -- the same
  // way it always has. One envelope, one request.
  const events = [];
  if (eventTypes.includes("invite")) {
    events.push({ eventType: "invite", to: { serviceUrl: assistantUrl } });
  }
  if (eventTypes.includes("utterance")) {
    events.push({
      eventType: "utterance",
      parameters: { dialogEvent: buildDialogEvent(userInput, responsePattern) },
    });
  }
  if (!events.length) return;

  const payload = {
    openFloor: {
      conversation: serializeConversation(),
      sender: { speakerUri: state.clientUri, serviceUrl: state.clientUrl },
      events,
    },
  };
  const timeoutMs = eventTypes.includes("utterance") ? UTTERANCE_TIMEOUT_MS : CONTROL_EVENT_TIMEOUT_MS;
  if (ui.showOutgoing.checked) logEvent("Outgoing to floor manager", payload);

  if (eventTypes.includes("invite")) {
    addInvitedAgent(assistantUrl);
    renderAgents();
    updateSendButtonState();
  }

  const floorManagerId = gatewayPath("/");

  // Every utterance round now goes through the streaming endpoint (not just
  // round-robin): floor_router.py reports both each conversant's real
  // working/idle transition (on_progress) AND each finalized event the
  // MOMENT it's ready (on_event) -- most importantly, an utterance as soon
  // as that one reply arrives, not batched until the whole round (which
  // can take minutes for a big full-sweep) finishes. Accumulate report
  // entries across the whole stream (mirrors the old round-robin-only
  // path) so the combined report popup still covers every response, built
  // once the stream ends rather than per event.
  if (eventTypes.includes("utterance")) {
    const reportEntries = [];
    try {
      await floorStream(payload, timeoutMs, (line) => {
        if (line?.progress) {
          const { serviceUrl, speakerUri, status } = line.progress;
          setAgentStatus(serviceUrl || speakerUri, status);
          return;
        }
        if (line?.event) {
          processIncomingEnvelope({ openFloor: { events: [line.event] } }, floorManagerId, { reportEntries, buildReport: false });
        }
      });
      buildAndQueueCombinedReport(reportEntries);
    } catch (error) {
      logError("Floor manager request failed", String(error));
    }
    return;
  }

  try {
    const response = await floorSend(payload, timeoutMs);
    if (response?.openFloor) {
      processIncomingEnvelope(response, floorManagerId);
    } else {
      logError("Non-JSON response from floor manager", response);
    }
  } catch (error) {
    logError("Floor manager request failed", String(error));
  }
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
  if (ui.maxWordsSlider && ui.maxWordsValue) {
    ui.maxWordsSlider.addEventListener("input", updateSliderBubble);
  }
  ui.clearConversationBtn.addEventListener("click", clearConversationHistory);
  if (ui.showConversationMarkdownBtn) {
    ui.showConversationMarkdownBtn.addEventListener("click", openConversationMarkdownPopup);
  }
  if (ui.copyConversationBtn) {
    ui.copyConversationBtn.addEventListener("click", () => {
      const text = ui.conversation ? ui.conversation.textContent : "";
      const btn = ui.copyConversationBtn;
      const original = btn.textContent;

      const showResult = (ok) => {
        btn.textContent = ok ? "Copied!" : "Copy failed";
        setTimeout(() => { btn.textContent = original; }, 1500);
      };

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => showResult(true)).catch(() => {
          // clipboard API rejected (e.g. non-secure context) — fall back
          showResult(fallbackCopyText(text));
        });
      } else {
        showResult(fallbackCopyText(text));
      }
    });
  }

  function fallbackCopyText(text) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (_) {}
    document.body.removeChild(ta);
    return ok;
  }
  ui.copyEventLogBtn.addEventListener("click", copyEventLogToClipboard);
  ui.copyErrorLogBtn.addEventListener("click", copyErrorLogToClipboard);
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

function updateSliderBubble() {
  const slider = ui.maxWordsSlider;
  const bubble = ui.maxWordsValue;
  if (!slider || !bubble) return;
  const val = parseInt(slider.value, 10);
  const min = parseInt(slider.min, 10);
  const max = parseInt(slider.max, 10);
  const pct = (val - min) / (max - min);
  // Adjust for thumb radius (~8px) so bubble tracks the thumb, not the track edge
  const thumbR = 8;
  const trackW = slider.offsetWidth;
  const leftPx = pct * (trackW - 2 * thumbR) + thumbR;
  bubble.style.left = `${leftPx}px`;
  bubble.textContent = val;
}

function init() {
  refreshKnownAgentList();
  renderAgents();
  updateSendButtonState();
  bindEvents();
  setDiagnosticsCollapsed(false);
  // Position bubble after layout is complete
  requestAnimationFrame(updateSliderBubble);
}

init();
