# web-floor Architecture

`web-floor` is a browser UI backed by a Flask gateway. The gateway supports two
distinct paths: a spec-literal **floor manager** (the default, spec-compliant
path for multi-agent conversations) and a **raw relay** for manual single-agent
pokes. Both are described below.

## Floor Manager Path (default)

The gateway implements the Open Floor Protocol's Pass-Through /
Delegate-to-Convener routing table (Interoperable Conversation Envelope Spec
v1.1.1, section 2.2). Instead of the browser fanning an event out to every
target itself, it posts one envelope to the gateway, which owns all
conversant/floor state for the conversation and decides where each event
actually goes.

```mermaid
flowchart LR
  U[User in Browser]

  subgraph B[Browser Client]
    UI[index.html UI controls]
    JS["app.js: build ONE envelope per user action"]
  end

  subgraph G[Flask Gateway]
    SEND["POST /api/floor/send"]
    STREAM["POST /api/floor/stream (round robin)"]
    STATE["GET /api/floor/state"]
    ROUTER["floor_router.py: routing-table loop"]
    FSTATE["floor_state.py: per-conversation conversant/floor state"]
  end

  CONV[Convener]
  S1[Specialist agent]
  S2[Specialist agent]

  U --> UI --> JS
  JS --> SEND
  JS --> STREAM
  JS --> STATE

  SEND --> ROUTER
  STREAM --> ROUTER
  ROUTER --> FSTATE
  ROUTER -- "Pass-Through (broadcast / private)" --> S1
  ROUTER -- "Pass-Through (broadcast / private)" --> S2
  ROUTER -- "Delegate / courtesy-copy" --> CONV
  CONV -- "decision events (grant/revoke/invite/utterance)" --> ROUTER

  ROUTER --> JS
  JS --> U
```

### Routing table

| Event | If convener present | If no convener |
|---|---|---|
| `utterance` (sender holds floor) | **Pass-Through** | — |
| `utterance` (sender doesn't hold floor) | Delegate | Ignore |
| `invite`, `uninvite` | Delegate to Convener | Pass-Through |
| `declineInvite`, `acceptInvite`, `bye`, `getManifests`, `publishManifests`, `yieldFloor` | Pass-Through | — |
| `requestFloor` | Delegate to Convener | Send `grantFloor` |
| `grantFloor`, `revokeFloor` | Delegate to Convener | Pass-Through |

- **Pass-Through** delivers to every conversant (or the single recipient named
  by a private utterance's `to` field).
- **Delegate to Convener** forwards the event to whichever conversant declared
  `openFloorRoles.convener` in its manifest (auto-detected on `acceptInvite`);
  convener's returned events are trusted and executed directly, never
  re-delegated.
- The convener also receives a **courtesy copy** of every Pass-Through
  utterance, exactly like any other conversant would, which is what gives it
  its chance to act without any special-casing in the table above.

### Concurrency model

The spec's normative sequential-processing rule governs the *event queue*
(events are processed one at a time, in order) — it does not forbid
delivering a single Pass-Through event to multiple recipients concurrently.
`floor_router.py` delivers to multiple targets over a small thread pool, then
enqueues the collected replies in stable order; the queue itself is still
drained strictly one event at a time. This recovers full concurrency for
"ask everyone" broadcasts without violating the sequential-processing rule.

### Known deviation: floorGranted default on invite

The spec's curation rule defaults a newly-invited conversant to
`floorGranted: true`. This project immediately reconciles that down to
`false` via an explicit `revokeFloor` right after each invite (see
`floor_router.py`'s `apply_local_state`). Each specialist agent's own local
floor gate independently defaults the same way (see
`agents/base_strategy_agent.py`'s `_handle_invite` in the startup-strategy
project). This is deliberate defense-in-depth: even if the floor manager had
a bug and a conversant were delivered an utterance it shouldn't answer, the
agent's own local gate is a second, independent line of defense against
double-answering.

## Raw Relay Path (manual pokes)

`/api/proxy-send` and `/api/proxy-stream` are unchanged from the original
implementation: a stateless single-target relay with no floor/conversant
tracking, for manually poking one agent directly from the UI.

```mermaid
flowchart LR
  U[User in Browser]

  subgraph B[web-floor Browser Client]
    UI[index.html UI controls]
    JS["app.js: build OpenFloor envelopes; render logs and conversation"]
  end

  subgraph G[Flask Gateway: flask_gateway.py]
    STATIC[GET / and static assets]
    PROXY["POST /api/proxy-send (targetUrl, payload, timeoutMs)"]
    HEALTH[GET /health]
    POLICY["CORS_ALLOW_ORIGINS; optional GATEWAY_TARGET_ALLOWLIST"]
  end

  subgraph A[OpenFloor Agents]
    T[TimeAgent local 8081]
    E[Erin local 8082]
    R[Remote or web agents]
  end

  U --> UI
  UI --> JS

  U --> STATIC
  JS --> PROXY
  PROXY --> T
  PROXY --> E
  PROXY --> R

  T --> PROXY
  E --> PROXY
  R --> PROXY

  PROXY --> JS
  JS --> U

  POLICY --> PROXY
  HEALTH --> U

  JS --> Q[Gateway override option]
  Q --> PROXY
```

## Notes

- Browser code sends floor-managed conversation traffic through
  `/api/floor/send`/`/api/floor/stream`, and manual single-agent pokes
  through `/api/proxy-send`/`/api/proxy-stream`. Both paths coexist.
- Gateway forwards requests to local or remote OpenFloor agents.
- `/api/proxy-send` returns a normalized response envelope: `ok`, `status`,
  `statusText`, `text`, `json`. `/api/floor/send` and `/api/floor/stream`
  return an aggregated OpenFloor envelope whose `events` are the ordered
  list of everything the floor manager executed.
- Browser can point at an external gateway with either:
  - query parameter: `?gateway=http://localhost:8090`
  - global variable: `window.WEB_FLOOR_GATEWAY_BASE_URL`
