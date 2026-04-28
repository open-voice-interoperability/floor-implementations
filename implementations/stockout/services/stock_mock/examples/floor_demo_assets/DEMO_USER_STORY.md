# User story demo — Stockout crisis & OFP floor

Documento di **design narrativo**: cosa racconti in sala, chi è chi, cosa vede il pubblico sulla **GUI** e cosa succede sul **Floor** (API + log governance).

---

## Premessa (una frase per il pubblico)

*«Una rottura di stock non è solo un numero in ERP: è una **conversazione operativa** tra ruoli diversi. Il **floor OFP** decide chi ha diritto di “parlare” in ogni istante e lascia una **traccia di governance** separata dal testo della discussione.»*

---

## Contesto business (fiction realistica)

- **SKU:** `SKU-MOTOR-12` (componente critico per linea di produzione).
- **Sito:** magazzino **DC-EU-01** (Europa).
- **Evento:** a fine turno il WMS segnala **giacenza insufficiente** rispetto agli impegni (simuliamo con il servizio inventario su **:8890**).
- **Obiettivo del team:** decidere in **meno di un’ora** un piano (trasferimento da altro hub, accelerazione ordine, o mix) **senza** che tre funzioni promettano cose contraddittorie al plant manager.

---

## Attori (cast fisso)

| Attore | Tipo | Ruolo nella storia | `speakerUri` (demo GUI) |
|--------|------|---------------------|---------------------------|
| **Diego** | **Umano** | *Logistics / control tower*: verifica stock, apre la crisi nel transcript, assegna convener, chiude con decisione. | `tag:demo.floor,2025:diego` (default; sovrascrivibile con `FLOOR_DEMO_HUMAN_SPEAKER_URI`) |
| **Planner** | **Agente AI** (script in UI) | Proposta **ATP / riallocazione** (es. da DC-US-01). | `tag:demo.floor,2025:planner` |
| **Procurement** | **Agente AI** | Proposta **PO expedite** / fornitore. | `tag:demo.floor,2025:procurement` |
| **Carrier** | **Agente AI** | **Vincoli** di pickup / finestra. | `tag:demo.floor,2025:carrier` |
| **Convener** | Umano o AI | Moderazione floor; in OFP `assignedFloorRoles.convener`. | `tag:demo.floor,2025:convener` (default in sidebar) |

---

## Cosa succede — atto per atto

### Atto 0 — Il fatto (dati, non ancora floor)

- **Diego** dalla sidebar preme **«Verifica stock (HTTP)»** verso il mock su **8890** (`SKU-MOTOR-12`, `DC-EU-01`).
- **Risposta:** `stockout: true`, `available` negativo rispetto agli impegni.
- **Sulla GUI (transcript):** compare un messaggio da **Diego** con il JSON e l’alert stockout.
- **Sul Floor:** nessun evento floor obbligatorio qui; è solo il **trigger** della war room.

*Messaggio per il pubblico:* **8890** = sensore dominio; **OFP** entra quando serve **negoziazione ordinata**.

---

### Atto 1 — Apertura sessione crisi (floor + convener)

- Diego **assegna il Convener** (sidebar).
- **Sul Floor (pannello destro):** `assignConvener` nel log governance.
- **Sul transcript:** niente inserimento manuale: l’apertura “a parole” della sessione resta **fuori GUI** (voce del presentatore).

---

### Atto 2 — Turni (solo chi ha il floor)

- Diego preme **«Planner → Procurement → Carrier (script)»**: per ogni agente, `requestFloor` → grant → riga nel transcript → `release`.
- **Sul Floor:** sequenza `requestFloor` / `grantFloor` / `yieldFloor` per ogni turno.

---

### Atto 3 — Tensione (opzionale)

- Convener (o floor manager) usa **revokeFloor** dalla sidebar verso un `speakerUri` ancora “problematico”.

---

### Atto 4 — Decisione

- **Diego** comunica la **decisione** a voce (o in slide); il transcript in GUI resta la traccia di stock + turni (nessun box testo libero).

---

## Mappa “cosa vede il pubblico”

| Zona schermo | Cosa mostra | Cosa rappresenta |
|--------------|-------------|------------------|
| **Sinistra — transcript** | Alert stock, proposte Planner/Procurement/Carrier, estratti skill/spec se usati. | **Contenuto** registrato dalla sidebar. |
| **Destra — governance (SSE)** | `requestFloor`, `grantFloor`, `yieldFloor`, `revokeFloor`, holder, convener. | **Processo** OFP. |
| **Sidebar** | Stock, convener, turni script, skill, spec, revoke. | **Leve** di Diego / presentatore. |

---

## Cosa **non** promettiamo in questa fase

- Testi agenti = **script** nella UI; il floor è **reale** (API).
- Whisper / envelope completi = fase successiva (oggi REST floor + transcript).
- Inventario **8890** non è dentro l’envelope OFP; è **sorgente dati** collegata alla narrativa.

---

## One-liner da slide

*«Stockout = dato; crisi = conversazione; OFP floor = chi parla e quando, con un verbale di governance accanto al dialogo.»*
