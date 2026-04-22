"""
MCP stdio server (lite): tool ``get_inventory`` → HTTP ``GET /inventory/{sku}``.

Run from STOCKOUT root (``STOCK_API`` defaults to http://localhost:8890):

  STOCK_API=http://localhost:8890 python -m stockout_mcp.server
"""

from __future__ import annotations

import json
import os

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "StockoutStockLite",
    instructions=(
        "Stock mock via HTTP: call get_inventory with sku and location_id; "
        "returns JSON from the same API the Streamlit war room uses."
    ),
)


@mcp.tool()
def get_inventory(sku: str, location_id: str = "DC-EU-01") -> str:
    """
    Fetch stock levels for a SKU at a location via the stock mock HTTP API.

    Same contract as ``GET {STOCK_API}/inventory/{sku}?location_id=...``.
    """
    base = (os.environ.get("STOCK_API") or "http://localhost:8890").rstrip("/")
    url = f"{base}/inventory/{sku}"
    try:
        r = httpx.get(url, params={"location_id": location_id}, timeout=15.0)
        if r.status_code == 404:
            return json.dumps(
                {
                    "found": False,
                    "sku": sku,
                    "location_id": location_id,
                    "http_status": 404,
                },
                indent=2,
            )
        r.raise_for_status()
        return json.dumps(r.json(), indent=2, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc), "sku": sku, "location_id": location_id}, indent=2)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
