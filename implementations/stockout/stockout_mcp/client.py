"""
Spawn ``stockout_mcp.server`` over stdio and call ``get_inventory`` once.

Optional dependency: ``pip install -r requirements-mcp-demo.txt``.
Used by the Streamlit war room without touching the existing HTTP stock button path.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


def stock_mcp_runtime_available() -> bool:
    """True if the ``mcp`` package is installed (no import side effects beyond a spec check)."""
    try:
        import importlib.util

        return importlib.util.find_spec("mcp") is not None
    except Exception:
        return False


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


async def _call_get_inventory_async(
    stock_api: str,
    sku: str,
    location_id: str,
) -> tuple[bool, str, int]:
    """Return (ok, text_body, elapsed_ms)."""
    t0 = time.perf_counter()
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    env = {**os.environ, "STOCK_API": stock_api}
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "stockout_mcp.server"],
        env=env,
        cwd=str(_repo_root()),
    )
    elapsed_ms = 0
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "get_inventory",
                {"sku": sku, "location_id": location_id},
            )
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            chunks: list[str] = []
            for block in result.content:
                t = getattr(block, "text", None)
                if t:
                    chunks.append(t)
            body = "\n".join(chunks).strip() or "(empty tool result)"
            if result.isError:
                return False, body, elapsed_ms
            return True, body, elapsed_ms


def run_mcp_get_inventory_sync(
    stock_api: str,
    sku: str,
    location_id: str,
) -> tuple[bool, str, int]:
    """
    Blocking MCP round-trip (stdio server subprocess).

    Runs asyncio in a worker thread to avoid clashing with a host event loop.
    """
    if not stock_mcp_runtime_available():
        return False, "MCP package not installed. Run: pip install -r requirements-mcp-demo.txt", 0

    def _runner() -> tuple[bool, str, int]:
        return asyncio.run(_call_get_inventory_async(stock_api, sku, location_id))

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_runner)
        return fut.result(timeout=60)


def parse_inventory_json(body: str) -> dict[str, Any] | None:
    """Best-effort parse of MCP tool text for UI (stockout flag, etc.)."""
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None
