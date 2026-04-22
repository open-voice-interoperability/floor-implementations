# Bundled Floor + stock services

This folder lets **STOCKOUT** run the demo **without** opening the separate FLOOR repository: from the repo root use `docker compose up -d`.

## What is vendored

- **`floor_api/src/`** — snapshot of the FLOOR FastAPI app (`src/` from the OFP Floor project), including `/api/v1/floor/*` and governance decisions.
- **`stock_mock/examples/`** — snapshot of the FLOOR stock inventory HTTP service (port **8890**).

To refresh after you change the canonical **FLOOR** repo (optional dev workflow):

```bash
# From STOCKOUT root, with ../FLOOR present:
rm -rf services/floor_api/src services/stock_mock/examples
cp -R ../FLOOR/src services/floor_api/
cp -R ../FLOOR/examples services/stock_mock/
```

Then rebuild: `docker compose build --no-cache && docker compose up -d`.

## Ports (defaults)

| Service    | Host port | Container |
|------------|-----------|-----------|
| Floor API  | 8787      | 8000      |
| Stock mock | 8890      | 8890      |

Override with `STOCKOUT_FLOOR_PORT` / `STOCKOUT_STOCK_PORT` in the environment when invoking Compose.
