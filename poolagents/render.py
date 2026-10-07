"""Plain-text reports for the terminal (no third-party dependencies)."""

from __future__ import annotations

import re

from .rugcheck import RugReport, Verdict
from .scalp import ScalpEntryReport, ScalpExitReport, money

# Token names and API strings are untrusted: strip control chars / ANSI escapes.
_UNSAFE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def clean(s: object, limit: int = 80) -> str:
    text = _UNSAFE.sub("", str(s))
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _table(rows: list[list[str]], headers: list[str]) -> str:
    widths = [max(len(str(r[i])) for r in rows + [headers]) for i in range(len(headers))]
    line = "  ".join("-" * w for w in widths)
    out = ["  ".join(h.ljust(w) for h, w in zip(headers, widths)), line]
    out += ["  ".join(str(c).ljust(w) for c, w in zip(r, widths)) for r in rows]
    return "\n".join(out)


def render_rug(rep: RugReport) -> str:
    age = "unknown" if rep.pool_age_minutes is None else f"{rep.pool_age_minutes / 60:.1f}h"
    rows = [[f"#{c.number}", c.name, c.reading, f"{c.result.icon} {c.result.value}",
             clean(c.note, 60)] for c in rep.checks]
    counts = rep.counts()
    badge = {Verdict.ENTER: "🟢", Verdict.SKIP: "🔴", Verdict.WATCH: "🟡"}[rep.verdict]
    parts = [
        f"GMGN PRE-ENTRY RUG CHECK (v6) - {clean(rep.token)}",
        f"CA: {clean(rep.contract, 60)}   pool age: {age}   pump.fun: {'YES' if rep.is_pump_fun else 'no'}",
        "",
        _table(rows, ["#", "Check", "Reading", "Result", "Note"]),
        "",
        f"pass {counts['PASS']} · caution {counts['CAUTION']} · red {counts['RED']} · n/a {counts['N/A']}",
        "",
        "Extra flags:",
        *[f"  • {clean(f, 120)}" for f in rep.extra_flags],
        "",
        f"VERDICT: {badge} {rep.verdict.value}",
        *[f"  - {clean(r, 120)}" for r in rep.reasons],
    ]
    if rep.verdict is Verdict.WATCH:
        parts.append("  Re-check in 1–2h, or once the ⏳ items have usable data.")
    parts += ["", "Not financial advice. Screening reduces risk; it does not remove it."]
    return "\n".join(parts)


def render_scalp_entry(rep: ScalpEntryReport) -> str:
    rows = [[("✅" if r.ok else "❌" if r.ok is False else "❔"), r.name, clean(r.detail, 70)]
            for r in rep.requirements]
    b = rep.baseline
    parts = [
        f"DLMM SCALP PLAYBOOK - ENTRY CHECK - {clean(rep.token)}",
        "(scalp rules only - rug-sheet thresholds are not used here)",
        "",
        _table(rows, ["", "Requirement", "Reading"]),
        "",
        f"ENTRY: {'🟢 MEETS PLAYBOOK' if rep.meets_playbook else '🔴 DOES NOT MEET PLAYBOOK'}",
        "",
        "Baseline to record before deposit:",
        f"  bundler  {b['bundler_pct']:g}%",
        f"  net buy  {money(b['net_buy_usd'], signed=True)}",
        f"  holders  {int(b['holders'])}",
        f"  volume   ${b['volume_usd']:,.0f} (1m)",
        "",
        "Exit triggers - check every 1m, ONE trigger = close immediately:",
        *[f"  {k:<9} {v}" for k, v in rep.exit_levels.items()],
        "",
        "Setup: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in rep.setup.items()),
        "",
        "Not financial advice.",
    ]
    return "\n".join(parts)


def render_scalp_exit(rep: ScalpExitReport) -> str:
    parts = [f"SCALP MONITOR: {'🔴 EXIT NOW' if rep.triggers else '🟢 HOLD'}", ""]
    parts += [f"  {k:<8} {v}" for k, v in rep.readings.items()]
    if rep.triggers:
        parts += ["", "Triggered:", *[f"  ✖ {t}" for t in rep.triggers],
                  "", "Close:", *[f"  {i}. {s}" for i, s in enumerate(rep.close_steps, 1)]]
    return "\n".join(parts)


def render_pools(rows: list[dict]) -> str:
    if not rows:
        return "No Solana pairs found on DexScreener (it can lag - check Meteora directly)."
    table = [[("★" if r["is_meteora_sol"] else ""), clean(r["dex"], 12), clean(r["pair"], 20),
              f"${(r['liquidity_usd'] or 0):,.0f}", f"${(r['volume_24h_usd'] or 0):,.0f}",
              clean(r["address"], 44)] for r in rows]
    return (_table(table, ["", "DEX", "Pair", "Liquidity", "Vol 24h", "Address"])
            + "\n\n★ = Meteora SOL pool. DexScreener can lag; Meteora's own figures win.")
