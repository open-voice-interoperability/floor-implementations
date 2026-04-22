# Conference floor demo — procedure card

Operational skill for the **conversation + floor** demo (Streamlit STOCKOUT): policy outside the prompt, versionable in the repo.

## Before you go on stage

- Ensure `.env` is not committed and no secrets appear in demo logs.
- Use only test / low-quota API keys; have an offline fallback (scripts already cached).
- CORS and API port aligned with the UI (`FLOOR_API` / env vars — see STOCKOUT README).

## During the demo

- At most **one** “expert” network call (spec lookup); short timeout; on error read the planned fallback message.
- Show **two timelines**: public transcript vs floor governance (`requestFloor`, `grantFloor`, `yieldFloor`, `revokeFloor`).
- Do not read stack traces aloud; explain the *why* of the decision (`reason` / `@override`, etc.).

## After the demo

- Rotate keys if something was exposed on a shared screen by mistake.
- If you export anything, export redacted metadata only — no payloads with PII.
