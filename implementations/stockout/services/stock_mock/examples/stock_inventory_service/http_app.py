"""
Minimal HTTP API over the same SQLite inventory as the MCP server.

Run:
  uvicorn examples.stock_inventory_service.http_app:app --host 127.0.0.1 --port 8890

Or from repo root with PYTHONPATH=. :
  python -m uvicorn examples.stock_inventory_service.http_app:app --host 127.0.0.1 --port 8890
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from examples.stock_inventory_service.inventory_db import (
    get_stock,
    init_schema_and_seed,
)

app = FastAPI(
    title="Stock inventory mock API",
    description="HTTP front-end for SQLite stock levels (Stockout crisis demo).",
    version="0.1.0",
)


@app.on_event("startup")
async def _startup() -> None:
    init_schema_and_seed()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/inventory/{sku}")
async def read_inventory(
    sku: str,
    location_id: str = Query("DC-EU-01", description="Warehouse / DC code"),
) -> dict:
    payload = get_stock(sku, location_id=location_id)
    if not payload.get("found"):
        raise HTTPException(status_code=404, detail="SKU/location not found")
    return payload
