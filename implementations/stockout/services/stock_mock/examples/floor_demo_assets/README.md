# Demo: conversation & floor (OFP)

**Storia da raccontare in sala (attori, atti, GUI vs floor):** [DEMO_USER_STORY.md](DEMO_USER_STORY.md).

Questa cartella contiene **asset di supporto** storici per la demo **conversation + floor** (checklist, lookup spec). L’**app Streamlit** è nel progetto **`STOCKOUT`** (cartella **allo stesso livello** di `FLOOR`), file `app.py`. Leggi il `README.md` dentro quella cartella sul tuo disco (non è dentro il repo `FLOOR`).

---

## Cosa mostra la demo

**War room sullo stockout:** tu (**Diego** di default) usi la sidebar per **verificare lo stock** (HTTP su :8890), poi **convener** e **turni** degli agenti (Planner, Procurement, Carrier) sul **floor** reale (:8787). A sinistra il **transcript**, a destra il **log di governance** (lettura REST a ogni rerun; SSE per client esterni).

Backend: API FastAPI FLOOR (`/api/v1/floor/...`, SSE `/api/v1/events/floor/{conversation_id}`) + servizio inventario mock (`/inventory/...` su :8890).

---

## Prerequisiti

- Docker e Docker Compose (consigliato per l’API, senza configurare Python sul Mac).
- Opzionale: [stock mock HTTP](../../README.md) sulla porta **8890** se vuoi collegare lo scenario stockout (`docker compose up -d` avvia anche `stock-inventory`).

---

## Avvio rapido

### 1. API Floor (e servizi dipendenti)

Dalla **root del repo** `FLOOR`:

```bash
docker compose up -d
```

Verifica:

```bash
curl -s http://localhost:8787/health
```

### 2. UI Streamlit

Dalla cartella **`STOCKOUT`** (sibling di `FLOOR`), con venv e `pip install -r requirements.txt`:

```bash
cd ../STOCKOUT
streamlit run app.py
```

Il browser si apre in genere su `http://localhost:8501`. Nella root di `FLOOR`, `streamlit_app_conversation_floor.py` mostra solo un redirect con le stesse istruzioni.

### 3. Prova come Diego (ordine suggerito)

1. Sidebar → **Verifica stock (HTTP)** con `SKU-MOTOR-12` / `DC-EU-01` → nel transcript compare l’alert (stockout).
2. **Assign convener** (URI default già impostato).
3. Sidebar → **Planner → Procurement → Carrier (script)** → nel transcript compaiono i turni; a destra il log governance si aggiorna.
4. Opzionale: **revokeFloor**, Skill, lookup spec.

---

## Variabili d’ambiente (UI)

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `FLOOR_API` | `http://localhost:8787/api/v1` | Base URL dell’API Floor. |
| `STOCK_API` | `http://localhost:8890` | Base URL del mock inventario (Docker `stock-inventory`). |
| `FLOOR_DEMO_CONVERSATION_ID` | `conference_floor_demo_001` | ID conversazione usato da floor + SSE. |
| `FLOOR_DEMO_HUMAN_NAME` | `Diego` | Nome mostrato per l’umano nella war room. |
| `FLOOR_DEMO_HUMAN_SPEAKER_URI` | `tag:demo.floor,2025:diego` | URI dell’umano (per estensioni future sul floor). |

---

## Contenuto di questa cartella

| File | Ruolo |
|------|--------|
| `SKILL.md` | Checklist demo (sicurezza, comportamento in sala). |
| `spec_lookup.py` | Una richiesta HTTP alla spec envelope 1.1.0 (timeout + fallback). |
| `.spec_title_cache.txt` | Cache opzionale (non in git; generata da `spec_lookup`). |

---

## Documentazione narrativa (script conferenza)

- Script 8–10 min: [docs/CONFERENCE_FLOOR_DEMO_SCRIPT.md](../../docs/CONFERENCE_FLOOR_DEMO_SCRIPT.md)  
- Checklist prova: [docs/CONFERENCE_REHEARSAL_CHECKLIST.md](../../docs/CONFERENCE_REHEARSAL_CHECKLIST.md)  

---

## Inventario mock (stockout) via Docker

Servizio separato sulla porta **8890** (stesso `docker compose up -d`):

```bash
curl -s "http://localhost:8890/inventory/SKU-MOTOR-12?location_id=DC-EU-01"
```

Dettagli: [examples/stock_inventory_service/README.md](../stock_inventory_service/README.md).

---

## MCP (opzionale)

Per esporre `get_stock` su SQLite da Cursor/IDE, vedi [examples/stock_inventory_service/README.md](../stock_inventory_service/README.md) (sezione MCP / stdio). L’UI Streamlit di questa demo non richiede MCP per funzionare.
