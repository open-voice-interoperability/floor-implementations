# Stock inventory mock — HTTP + MCP (SQLite)

Small service for **Stockout crisis floor management** demos: one SQLite file, two interfaces.

## Docker (recommended — no venv, no PYTHONPATH)

From the **repository root**:

```bash
docker compose up -d stock-inventory
# or full stack: docker compose up -d
```

Then:

```bash
curl -s "http://localhost:8890/health"
curl -s "http://localhost:8890/inventory/SKU-MOTOR-12?location_id=DC-EU-01"
```

Data persists in the named volume `stock_inventory_data`. Change the host port with env `STOCK_INVENTORY_PORT` (default `8890`).

**MCP** (`get_stock` via stdio) is optional and runs on your machine (Cursor / CLI), not inside this container. Use HTTP from apps in Docker / CI.

## Data model

Table `inventory` (`sku`, `location_id`, `on_hand`, `allocated`, `safety_stock`).

Seed (first init):

| sku            | location_id | on_hand | allocated | Note              |
|----------------|-------------|---------|-----------|-------------------|
| SKU-MOTOR-12   | DC-EU-01    | 0       | 5         | **Stockout** demo |
| SKU-MOTOR-12   | DC-US-01    | 42      | 2         | Healthy           |
| SKU-BOLT-M8    | DC-EU-01    | 5000    | 0         | Healthy           |

Override path with env `STOCK_INVENTORY_DB` (absolute or relative path).

## HTTP API

From repository root:

```bash
pip install -r requirements.txt
export PYTHONPATH=.
python -m uvicorn examples.stock_inventory_service.http_app:app --host 127.0.0.1 --port 8890
```

Examples:

```bash
curl -s http://127.0.0.1:8890/health
curl -s "http://127.0.0.1:8890/inventory/SKU-MOTOR-12?location_id=DC-EU-01"
curl -s "http://127.0.0.1:8890/inventory/SKU-MOTOR-12?location_id=DC-US-01"
```

Response includes `available`, `stockout`, `below_safety_stock`, `source`.

## MCP server (stdio)

Uses official SDK **FastMCP** (`mcp` package). Tool name: **`get_stock`**.

Install MCP **separately** (non è in `requirements.txt` del progetto per evitare conflitto `anyio` con FastAPI 0.104):

```bash
pip install -r examples/stock_inventory_service/requirements-mcp.txt
```

Run:

```bash
export PYTHONPATH=.
python -m examples.stock_inventory_service.mcp_stdio
```

### Cursor / Claude Desktop

Point stdio server at:

- **Command:** `python` (or full path to your venv `python`)
- **Args:** `-m`, `examples.stock_inventory_service.mcp_stdio`
- **Cwd:** repository root
- **Env (optional):** `STOCK_INVENTORY_DB` = path to shared SQLite file

Use the tool **`get_stock`** with arguments `sku`, `location_id` (default `DC-EU-01`). The return value is a JSON string.

## Tests

```bash
export PYTHONPATH=.
python -m pytest tests/test_stock_inventory_db.py -q
```
