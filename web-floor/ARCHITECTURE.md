# web-floor Architecture

This document describes the current `web-floor` implementation using a browser UI and a thin Flask gateway.

## Diagram

```mermaid
flowchart LR
  U[User in Browser]

  subgraph B[web-floor Browser Client]
    UI[index.html UI controls]
    JS[app.js\nBuild OpenFloor envelopes\nRender logs and conversation]
  end

  subgraph G[Flask Gateway: flask_gateway.py]
    STATIC[GET / and static assets]
    PROXY[POST /api/proxy-send\n(targetUrl, payload, timeoutMs)]
    HEALTH[GET /health]
    POLICY[CORS_ALLOW_ORIGINS\nGATEWAY_TARGET_ALLOWLIST (optional)]
  end

  subgraph A[OpenFloor Agents]
    T[TimeAgent\nhttp://localhost:8081/]
    E[Erin\nhttp://localhost:8082/]
    R[Remote/Web agents\nhttps://...]
  end

  U --> UI
  UI --> JS

  U -->|Open http://localhost:8090| STATIC
  JS -->|proxy request| PROXY
  PROXY --> T
  PROXY --> E
  PROXY --> R

  T -->|OpenFloor response| PROXY
  E -->|OpenFloor response| PROXY
  R -->|OpenFloor response| PROXY

  PROXY -->|ok, status, text, json| JS
  JS -->|Conversation + Event/Error logs| U

  POLICY -.applies to.-> PROXY
  HEALTH -.for monitoring.-> U

  JS -.optional external gateway.-> Q[?gateway=http://host:port\nor window.WEB_FLOOR_GATEWAY_BASE_URL]
  Q -.routes calls to.-> PROXY
```

## Notes

- Browser code sends all agent calls through `/api/proxy-send`.
- Gateway forwards requests to local or remote OpenFloor agents.
- Gateway returns a normalized response envelope: `ok`, `status`, `statusText`, `text`, `json`.
- Browser can point at an external gateway with either:
  - query parameter: `?gateway=http://localhost:8090`
  - global variable: `window.WEB_FLOOR_GATEWAY_BASE_URL`
