# web-floor Architecture

This document describes the current `web-floor` implementation using a browser UI and a thin Flask gateway.

## Diagram

If Mermaid still does not render in VS Code preview, open `architecture.html` in a browser for a no-extension fallback view.

Sanity check:

```mermaid
flowchart LR
  A[Mermaid enabled] --> B[Preview works]
```

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

- Browser code sends all agent calls through `/api/proxy-send`.
- Gateway forwards requests to local or remote OpenFloor agents.
- Gateway returns a normalized response envelope: `ok`, `status`, `statusText`, `text`, `json`.
- Browser can point at an external gateway with either:
  - query parameter: `?gateway=http://localhost:8090`
  - global variable: `window.WEB_FLOOR_GATEWAY_BASE_URL`
