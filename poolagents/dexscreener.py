"""Read-only market data from the public DexScreener API (no key needed).

DexScreener gives prices, liquidity, volume and pool age. It does NOT give
holder data (top 10, dev, insiders, snipers, bundler...) - those still come
from GMGN and go into your snapshot file.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from typing import Any

API = "https://api.dexscreener.com/latest/dex/tokens/{ca}"
SOL_MINT = "So11111111111111111111111111111111111111112"
_BASE58 = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def is_valid_solana_address(ca: str) -> bool:
    return bool(_BASE58.match(ca or ""))


def fetch_pairs(ca: str, timeout: float = 10.0) -> list[dict[str, Any]]:
    if not is_valid_solana_address(ca):
        raise ValueError(f"not a valid Solana address: {ca!r}")
    req = urllib.request.Request(API.format(ca=ca), headers={"User-Agent": "poolagents/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https host
        payload = json.loads(resp.read().decode("utf-8"))
    return [p for p in (payload.get("pairs") or []) if p.get("chainId") == "solana"]


def _is_sol_quoted(p: dict[str, Any]) -> bool:
    q = p.get("quoteToken") or {}
    return q.get("address") == SOL_MINT or q.get("symbol") == "SOL"


def summarize_pairs(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for p in pairs:
        out.append({
            "dex": p.get("dexId"),
            "labels": p.get("labels") or [],
            "pair": f"{(p.get('baseToken') or {}).get('symbol', '?')}/{(p.get('quoteToken') or {}).get('symbol', '?')}",
            "address": p.get("pairAddress"),
            "liquidity_usd": (p.get("liquidity") or {}).get("usd"),
            "volume_24h_usd": (p.get("volume") or {}).get("h24"),
            "volume_5m_usd": (p.get("volume") or {}).get("m5"),
            "created_at_ms": p.get("pairCreatedAt"),
            "is_meteora_sol": p.get("dexId") == "meteora" and _is_sol_quoted(p),
        })
    out.sort(key=lambda r: r["liquidity_usd"] or 0, reverse=True)
    return out


def market_fields(pairs: list[dict[str, Any]], now_ms: float | None = None) -> dict[str, Any]:
    """Fields the rug check can use, derived from all Solana pairs of the token."""
    if not pairs:
        return {}
    rows = summarize_pairs(pairs)
    main = max(pairs, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)
    now_ms = now_ms or time.time() * 1000
    created = [r["created_at_ms"] for r in rows if r["created_at_ms"]]
    fields: dict[str, Any] = {
        "token_name": (main.get("baseToken") or {}).get("name"),
        "market_cap_usd": main.get("marketCap") or main.get("fdv"),
        "liquidity_usd": (main.get("liquidity") or {}).get("usd"),
        "total_pool_liquidity_usd": sum(r["liquidity_usd"] or 0 for r in rows),
        "volume_24h_usd": sum(r["volume_24h_usd"] or 0 for r in rows),
        "meteora_sol_pools": [r for r in rows if r["is_meteora_sol"]],
    }
    if created:
        fields["pool_age_minutes"] = round((now_ms - min(created)) / 60000, 1)
    return {k: v for k, v in fields.items() if v is not None}
