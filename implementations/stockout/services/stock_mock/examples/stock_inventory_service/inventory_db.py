"""
SQLite-backed inventory reads for HTTP and MCP stock demos.

Uses a single file database (path from STOCK_INVENTORY_DB env or default under this package).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_RELATIVE = Path(__file__).resolve().parent / "data" / "inventory.db"


def _db_path() -> Path:
    raw = os.environ.get("STOCK_INVENTORY_DB")
    if raw:
        return Path(raw).expanduser().resolve()
    DEFAULT_RELATIVE.parent.mkdir(parents=True, exist_ok=True)
    return DEFAULT_RELATIVE


def init_schema_and_seed(db_path: Optional[Path] = None) -> Path:
    """
    Create tables and seed mock rows if the DB file is missing or empty.

    Returns:
        Path to the SQLite database file.
    """
    path = db_path or _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inventory (
                sku TEXT NOT NULL,
                location_id TEXT NOT NULL,
                on_hand INTEGER NOT NULL,
                allocated INTEGER NOT NULL DEFAULT 0,
                safety_stock INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (sku, location_id)
            )
            """
        )
        cur = conn.execute("SELECT COUNT(*) FROM inventory")
        count = int(cur.fetchone()[0])
        if count == 0:
            rows = [
                ("SKU-MOTOR-12", "DC-EU-01", 0, 5, 10),
                ("SKU-MOTOR-12", "DC-US-01", 42, 2, 8),
                ("SKU-BOLT-M8", "DC-EU-01", 5000, 0, 500),
            ]
            conn.executemany(
                "INSERT INTO inventory (sku, location_id, on_hand, allocated, safety_stock) "
                "VALUES (?, ?, ?, ?, ?)",
                rows,
            )
        conn.commit()
    finally:
        conn.close()
    return path


def get_stock(sku: str, location_id: str = "DC-EU-01", db_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Return stock snapshot for demo / MCP / HTTP.

    Args:
        sku: Product identifier.
        location_id: Warehouse / site code.
        db_path: Optional override DB path (for tests).

    Returns:
        Dict with levels, flags, and source label.
    """
    path = db_path or _db_path()
    if not path.is_file():
        init_schema_and_seed(path)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            "SELECT sku, location_id, on_hand, allocated, safety_stock "
            "FROM inventory WHERE sku = ? AND location_id = ?",
            (sku, location_id),
        )
        row = cur.fetchone()
        if row is None:
            return {
                "sku": sku,
                "location_id": location_id,
                "found": False,
                "stockout": False,
                "below_safety_stock": False,
                "on_hand": None,
                "allocated": None,
                "available": None,
                "safety_stock": None,
                "source": "sqlite-inventory-mock",
            }
        on_hand = int(row["on_hand"])
        allocated = int(row["allocated"])
        safety = int(row["safety_stock"])
        available = on_hand - allocated
        stockout = available <= 0
        below_safety = available < safety
        return {
            "sku": sku,
            "location_id": location_id,
            "found": True,
            "on_hand": on_hand,
            "allocated": allocated,
            "available": available,
            "safety_stock": safety,
            "stockout": stockout,
            "below_safety_stock": below_safety,
            "source": "sqlite-inventory-mock",
        }
    finally:
        conn.close()
