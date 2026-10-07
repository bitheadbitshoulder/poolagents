"""Command line: `poolagents rug | scalp-entry | scalp-exit | pools`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .config import load_rug_config, load_scalp_config
from .render import render_pools, render_rug, render_scalp_entry, render_scalp_exit
from .rugcheck import Verdict, run_rug_check
from .scalp import check_scalp_entry, check_scalp_exit


def _load(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _emit(obj: dict[str, Any], text: str, as_json: bool) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False) if as_json else text)


def cmd_rug(a: argparse.Namespace) -> int:
    data = _load(a.snapshot)
    if a.fetch:
        from .dexscreener import fetch_pairs, market_fields
        market = market_fields(fetch_pairs(data.get("contract", "")))
        # GMGN / Meteora figures you typed in win over DexScreener.
        for k, v in market.items():
            data.setdefault(k, v)
    rep = run_rug_check(data, load_rug_config(a.config))
    _emit(rep.to_dict(), render_rug(rep), a.json)
    return {Verdict.ENTER: 0, Verdict.WATCH: 1, Verdict.SKIP: 2}[rep.verdict]


def cmd_scalp_entry(a: argparse.Namespace) -> int:
    rep = check_scalp_entry(_load(a.snapshot), load_scalp_config(a.config))
    _emit(rep.to_dict(), render_scalp_entry(rep), a.json)
    return 0 if rep.meets_playbook else 2


def cmd_scalp_exit(a: argparse.Namespace) -> int:
    rep = check_scalp_exit(_load(a.snapshot), load_scalp_config(a.config))
    _emit(rep.to_dict(), render_scalp_exit(rep), a.json)
    return 2 if rep.triggers else 0


def cmd_pools(a: argparse.Namespace) -> int:
    from .dexscreener import fetch_pairs, summarize_pairs
    rows = summarize_pairs(fetch_pairs(a.contract))
    _emit({"pairs": rows}, render_pools(rows), a.json)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="poolagents",
        description="Read-only pre-entry screening for Meteora DLMM pools. Never trades, never asks for keys.")
    p.add_argument("--version", action="version", version=f"poolagents {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("rug", help="15-check rug sheet (v6) on a token snapshot -> ENTER / SKIP / WATCH")
    r.add_argument("snapshot", help="JSON snapshot (see examples/)")
    r.add_argument("--fetch", action="store_true", help="fill missing market data from DexScreener")
    r.set_defaults(func=cmd_rug)

    se = sub.add_parser("scalp-entry", help="Scalp Playbook entry check + baseline + exit levels")
    se.add_argument("snapshot")
    se.set_defaults(func=cmd_scalp_entry)

    sx = sub.add_parser("scalp-exit", help="compare the last two 1m readings -> EXIT NOW / HOLD")
    sx.add_argument("snapshot")
    sx.set_defaults(func=cmd_scalp_exit)

    po = sub.add_parser("pools", help="list a token's Solana pools, Meteora SOL pools starred")
    po.add_argument("contract")
    po.set_defaults(func=cmd_pools)

    for s in (r, se, sx, po):
        s.add_argument("--json", action="store_true", help="machine-readable output")
        s.add_argument("--config", help="custom thresholds JSON")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
