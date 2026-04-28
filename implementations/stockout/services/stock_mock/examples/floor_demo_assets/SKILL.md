# Conference floor demo — procedure card

Skill operativa per la demo **conversation + floor** (Streamlit): policy fuori dal prompt, versionabile in repository.

## Prima di salire sul palco

- Verificare che `.env` non sia committato e che non compaiano segreti nei log della demo.
- Usare solo chiavi API di test/bassa quota; disporre di fallback offline (script già in cache).
- CORS e porta API allineati alla UI (`FLOOR_API` nel progetto **STOCKOUT** `app.py` o variabili d’ambiente).

## Durante la demo

- Massimo **una** chiamata di rete “perizia” (lookup spec); timeout breve; in caso di errore leggere il messaggio di fallback previsto.
- Mostrare **due timeline**: transcript pubblico vs governance floor (`requestFloor`, `grantFloor`, `yieldFloor`, `revokeFloor`).
- Non leggere stack trace in voce; spiegare il *perché* della decisione (`reason` / `@override`, ecc.).

## Dopo la demo

- Ruotare chiavi se qualcosa è finito per errore in uno schermo condiviso.
- Esportare (se serve) solo metadati redatti: niente payload con PII.
