# User story demo — Stockout crisis & OFP floor

**Narrative design** doc: what you say in the room, who is who, what the audience sees on the **GUI** and what happens on the **Floor** (API + governance log).

---

## Opening line (one sentence for the audience)

*“A stock break is not just an ERP number: it is an **operational conversation** between different roles. The **OFP floor** decides who may ‘speak’ at each moment and leaves a **governance trail** separate from the discussion text.”*

---

## Business context (realistic fiction)

- **SKU:** `SKU-MOTOR-12` (critical component for a production line).
- **Site:** warehouse **DC-EU-01** (Europe).
- **Event:** end of shift WMS reports **insufficient stock** vs commitments (simulated with the inventory service on **:8890**).
- **Team goal:** decide within **one hour** on a plan (transfer from another hub, expedited order, or mix) **without** three functions making contradictory promises to the plant manager.

---

## Actors (fixed cast)

| Actor | Type | Role in the story | `speakerUri` (demo GUI) |
|--------|------|---------------------|---------------------------|
| **Diego** | **Human** | *Logistics / control tower*: checks stock, opens the crisis in the transcript, assigns convener, closes with a decision. | `tag:demo.floor,2025:diego` (default; override with `FLOOR_DEMO_HUMAN_SPEAKER_URI`) |
| **Planner** | **AI agent** (UI script) | **ATP / reallocation** proposal (e.g. from DC-US-01). | `tag:demo.floor,2025:planner` |
| **Procurement** | **AI agent** | **Expedite PO** / supplier proposal. | `tag:demo.floor,2025:procurement` |
| **Carrier** | **AI agent** | Pickup **constraints** / time window. | `tag:demo.floor,2025:carrier` |
| **Convener** | Human or AI | Floor moderation; in OFP `assignedFloorRoles.convener`. | `tag:demo.floor,2025:convener` (sidebar default) |

---

## What happens — act by act

### Act 0 — The fact (data, not floor yet)

- **Diego** in the sidebar clicks **“Check stock (HTTP)”** toward the mock on **8890** (`SKU-MOTOR-12`, `DC-EU-01`).
- **Response:** `stockout: true`, `available` negative vs commitments.
- **On the GUI (transcript):** a message from **Diego** with the JSON and the stockout alert.
- **On the Floor:** no mandatory floor event here; this is only the **war room trigger**.

*Line for the audience:* **8890** = domain sensor; **OFP** enters when you need **ordered negotiation**.

---

### Act 1 — Crisis session open (floor + convener)

- Diego **assigns the Convener** (sidebar).
- **On the Floor (panel):** `assignConvener` in the governance log.
- **On the transcript:** no manual insert; the spoken session opening stays **off GUI** (presenter voice).

---

### Act 2 — Turns (only whoever holds the floor)

- Diego clicks **“Planner → Procurement → Carrier (script)”**: for each agent, `requestFloor` → grant → line in transcript → `release`.
- **On the Floor:** `requestFloor` / `grantFloor` / `yieldFloor` sequence for each turn.
- **HITL (spotlight):** after the three scripted turns, **Approve** (green) lets **Planner** confirm the joint plan; **Reject** (red) logs the refusal and **immediately** re-runs the scripted turns with **different** proposal text (round-robin copy), without clicking the sidebar script again.

---

### Act 3 — Tension (optional)

- Convener (or floor manager) uses **revokeFloor** from the sidebar toward a still “problematic” `speakerUri`.

---

### Act 4 — Decision

- **Diego** states the **decision** aloud (or on a slide); the GUI transcript remains the record of stock + turns (no free-text box).

---

## “What the audience sees” map

| Screen area | What it shows | What it means |
|-------------|----------------|-----------------|
| **Transcript** | Stock alert, Planner/Procurement/Carrier proposals, skill/spec excerpts if used. | **Content** recorded from the sidebar. |
| **Trace + summary** | API trace, holder, convener (REST on each rerun). | **OFP process** and server state. |
| **Sidebar** | Stock, convener, scripted turns, skill, spec, revoke. | **Levers** for Diego / presenter. |

---

## What we **do not** promise at this stage

- Agent copy = **script** in the UI; the floor is **real** (API).
- Whisper / full envelopes = next phase (today: floor REST + transcript).
- Inventory **8890** is not inside the OFP envelope; it is **data source** tied to the narrative.

---

## Slide one-liner

*“Stockout = data; crisis = conversation; OFP floor = who speaks when, with a governance record next to the dialogue.”*
