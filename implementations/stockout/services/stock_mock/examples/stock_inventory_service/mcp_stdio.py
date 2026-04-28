#!/usr/bin/env python3
"""
MCP stdio server: tool ``get_stock`` (SQLite) — same data as ``http_app``.

Run (repo root, with ``mcp`` installed):
  python examples/stock_inventory_service/mcp_stdio.py

Cursor MCP config example (stdio):
  {
    "mcpServers": {
      "stock-inventory": {
        "command": "python",
        "args": ["/ABS/PATH/FLOOR/examples/stock_inventory_service/mcp_stdio.py"],
        "env": {"STOCK_INVENTORY_DB": "/optional/path/inventory.db"}
      }
    }
  }
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from examples.stock_inventory_service.inventory_db import get_stock as read_inventory
from examples.stock_inventory_service.inventory_db import init_schema_and_seed

mcp = FastMCP(
    "StockInventory",
    instructions="Mock inventory service: get_stock reads levels from SQLite (demo for stockout crisis).",
)


@mcp.tool()
def get_stock(sku: str, location_id: str = "DC-EU-01") -> str:
    """
    Return current stock levels for a SKU at a warehouse location.

    Use for stockout detection: parse JSON and check ``stockout`` and ``available``.
    """
    init_schema_and_seed()
    payload: dict[str, Any] = read_inventory(sku, location_id=location_id)
    return json.dumps(payload, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
