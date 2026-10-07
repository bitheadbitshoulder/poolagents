"""GMGN Pre-Entry Rug Check (v6) - 15 checks, one hard RED = SKIP.

Input is a plain dict (usually loaded from a JSON snapshot you fill in from
GMGN / Meteora). Any missing reading is marked N/A, which can never cause a
SKIP but does stop an ENTER.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .config import load_rug_config


class Result(str, Enum):
    PASS = "PASS"
    CAUTION = "CAUTION"
    RED = "RED"
    NA = "N/A"

    @property
    def icon(self) -> str:
        return {"PASS": "✅", "CAUTION": "⚠️ ", "RED": "❌", "N/A": "⏳"}[self.value]


class Verdict(str, Enum):
    ENTER = "ENTER"
    SKIP = "SKIP"
    WATCH = "WATCH & RE-CHECK"


@dataclass
class CheckResult:
    number: int
    name: str
    threshold: str
    reading: str
    result: Result
    note: str = ""


@dataclass
class RugReport:
    token: str
    contract: str
    checks: list[CheckResult]
    verdict: Verdict
    reasons: list[str]
    extra_flags: list[str] = field(default_factory=list)
    is_pump_fun: bool = False
    pool_age_minutes: float | None = None

    def counts(self) -> dict[str, int]:
        out = {r.value: 0 for r in Result}
        for c in self.checks:
            out[c.result.value] += 1
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "contract": self.contract,
            "is_pump_fun": self.is_pump_fun,
            "pool_age_minutes": self.pool_age_minutes,
            "verdict": self.verdict.value,
            "reasons": self.reasons,
            "extra_flags": self.extra_flags,
            "checks": [
                {
                    "number": c.number,
                    "name": c.name,
                    "threshold": c.threshold,
                    "reading": c.reading,
                    "result": c.result.value,
                    "note": c.note,
                }
                for c in self.checks
            ],
        }


# ---------------------------------------------------------------- helpers

def _num(data: dict[str, Any], key: str) -> float | None:
    v = data.get(key)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct(v: float | None) -> str:
    return "no data" if v is None else f"{v:g}%"


def _usd(v: float | None) -> str:
    if v is None:
        return "no data"
    if abs(v) >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"${v / 1_000:.1f}K"
    return f"${v:,.0f}"


def _missing(n: int, name: str, threshold: str) -> CheckResult:
    return CheckResult(n, name, threshold, "no data", Result.NA, "fill this in and re-run")


def _simple_red_above(n, name, value, limit, fmt=_pct) -> CheckResult:
    threshold = f"RED > {fmt(limit)}"
    if value is None:
        return _missing(n, name, threshold)
    res = Result.RED if value > limit else Result.PASS
    return CheckResult(n, name, threshold, fmt(value), res)


def _tiered(n, name, value, red_above, caution_from) -> CheckResult:
    threshold = f"RED > {red_above:g}%, CAUTION {caution_from:g}–{red_above:g}%"
    if value is None:
        return _missing(n, name, threshold)
    if value > red_above:
        res = Result.RED
    elif value >= caution_from:
        res = Result.CAUTION
    else:
        res = Result.PASS
    return CheckResult(n, name, threshold, _pct(value), res)


def _flag(n, name, enabled) -> CheckResult:
    threshold = "RED if enabled"
    if enabled is None:
        return _missing(n, name, threshold)
    return CheckResult(n, name, threshold, "enabled" if enabled else "disabled",
                       Result.RED if enabled else Result.PASS)


# ---------------------------------------------------------------- the check

def run_rug_check(data: dict[str, Any], cfg: dict[str, Any] | None = None) -> RugReport:
    cfg = cfg or load_rug_config()
    contract = str(data.get("contract", "")).strip()
    age = _num(data, "pool_age_minutes")
    mcap = _num(data, "market_cap_usd")
    liq = _num(data, "liquidity_usd")
    total_liq = _num(data, "total_pool_liquidity_usd") or liq
    vol = _num(data, "volume_24h_usd")
    dev = _num(data, "dev_pct")
    snipers = _num(data, "snipers_pct")
    bundler = _num(data, "bundler_pct")

    checks: list[CheckResult] = []

    # 1 Token tax
    c = cfg["token_tax"]
    checks.append(_tiered(1, "Token tax", _num(data, "tax_pct"), c["red_above"], c["caution_from"]))
    # 2-5 simple percentage reds
    checks.append(_simple_red_above(2, "Top 10 holders", _num(data, "top10_pct"), cfg["top10_pct"]["red_above"]))
    checks.append(_simple_red_above(3, "DEV holding", dev, cfg["dev_pct"]["red_above"]))
    checks.append(_simple_red_above(4, "Insiders", _num(data, "insiders_pct"), cfg["insiders_pct"]["red_above"]))
    checks.append(_simple_red_above(5, "Phishing", _num(data, "phishing_pct"), cfg["phishing_pct"]["red_above"]))
    # 6 Snipers, 7 Bundler
    c = cfg["snipers_pct"]
    checks.append(_tiered(6, "Snipers still holding", snipers, c["red_above"], c["caution_from"]))
    c = cfg["bundler_pct"]
    checks.append(_tiered(7, "Bundler", bundler, c["red_above"], c["caution_from"]))

    # 8 LP burnt
    burnt = _num(data, "lp_burnt_pct")
    limit = cfg["lp_burnt_pct"]["red_below"]
    if burnt is None:
        checks.append(_missing(8, "LP burnt", f"RED < {limit:g}%"))
    else:
        checks.append(CheckResult(8, "LP burnt", f"RED < {limit:g}%", _pct(burnt),
                                  Result.RED if burnt < limit else Result.PASS))

    # 9, 10 authorities
    checks.append(_flag(9, "Mint authority", data.get("mint_enabled")))
    checks.append(_flag(10, "Freeze / blacklist", data.get("freeze_enabled")))

    # 11 Pool quote side vs initial (young pools: noise unless already >50% down)
    c = cfg["pool_quote_drop_pct"]
    q0, q1 = _num(data, "pool_quote_initial_sol"), _num(data, "pool_quote_now_sol")
    thr = f"RED if down > {c['red_above']:g}% vs initial"
    if q0 is None or q1 is None or q0 <= 0:
        checks.append(_missing(11, "Pool quote side (SOL)", thr))
    else:
        drop = (q0 - q1) / q0 * 100
        reading = f"{q0:g} → {q1:g} SOL ({-drop:+.1f}%)"
        if drop > c["red_above"]:
            res, note = Result.RED, ""
        elif age is not None and age < c["young_pool_minutes"]:
            res, note = Result.NA, f"pool < {c['young_pool_minutes']} min old - swings are noise"
        else:
            res, note = Result.PASS, ""
        checks.append(CheckResult(11, "Pool quote side (SOL)", thr, reading, res, note))

    # 12 Liquidity / volume health
    c = cfg["liquidity_health"]
    thr = (f"RED if liq < {_usd(c['red_liquidity_below_usd'])} or no volume; "
           f"CAUTION if vol/liq > {c['caution_volume_to_liquidity_above']:g}×")
    if liq is None or vol is None:
        checks.append(_missing(12, "Liquidity / volume health", thr))
    else:
        ratio = vol / liq if liq > 0 else float("inf")
        reading = f"liq {_usd(liq)}, vol {_usd(vol)} ({ratio:.1f}× liq)"
        if liq < c["red_liquidity_below_usd"] or vol <= 0:
            res = Result.RED
        elif ratio > c["caution_volume_to_liquidity_above"]:
            res = Result.CAUTION
        else:
            res = Result.PASS
        checks.append(CheckResult(12, "Liquidity / volume health", thr, reading, res))

    # 13 24h volume (young pools: since-launch figure, report run-rate)
    c = cfg["volume_24h_usd"]
    thr = f"RED < {_usd(c['red_below'])}"
    if vol is None:
        checks.append(_missing(13, "24h volume", thr))
    elif vol >= c["red_below"]:
        checks.append(CheckResult(13, "24h volume", thr, _usd(vol), Result.PASS))
    elif age is not None and age < c["young_pool_hours"] * 60:
        hours = max(age / 60, 1 / 60)
        run_rate = vol / hours * 24
        checks.append(CheckResult(13, "24h volume", thr, f"{_usd(vol)} in {hours:.1f}h", Result.NA,
                                  f"pool < 24h old; run-rate ≈ {_usd(run_rate)}/24h"))
    else:
        checks.append(CheckResult(13, "24h volume", thr, _usd(vol), Result.RED))

    # 14 Market cap
    c = cfg["market_cap_usd"]
    thr = f"RED < {_usd(c['red_below'])}"
    if mcap is None:
        checks.append(_missing(14, "Market cap", thr))
    else:
        checks.append(CheckResult(14, "Market cap", thr, _usd(mcap),
                                  Result.RED if mcap < c["red_below"] else Result.PASS))

    # 15 Sellable supply vs liquidity = (bundler% + sniper% + dev%) × mcap ÷ total pool liquidity
    c = cfg["sellable_vs_liquidity"]
    thr = f"RED > {c['red_above']:g}×, CAUTION {c['caution_from']:g}–{c['red_above']:g}×"
    if None in (bundler, snipers, dev, mcap, total_liq) or not total_liq:
        checks.append(_missing(15, "Sellable supply vs liquidity", thr))
    else:
        sellable_usd = (bundler + snipers + dev) / 100 * mcap
        ratio = sellable_usd / total_liq
        reading = f"{_usd(sellable_usd)} sellable ÷ {_usd(total_liq)} liq = {ratio:.2f}×"
        if ratio > c["red_above"]:
            res = Result.RED
        elif ratio >= c["caution_from"]:
            res = Result.CAUTION
        else:
            res = Result.PASS
        checks.append(CheckResult(15, "Sellable supply vs liquidity", thr, reading, res))

    # ---------------- extra flags (reported, never scored)
    is_pump = contract.lower().endswith("pump")
    extra: list[str] = []
    extra.append("pump.fun token (CA ends in 'pump')" if is_pump else "Not a pump.fun token")
    rug = _num(data, "gmgn_rug_pct")
    if rug is not None and rug >= cfg["extra_flags"]["gmgn_rug_pct_high"]:
        extra.append(f"GMGN Rug % high: {rug:g}% (low confidence on brand-new tokens)")
    copy = _num(data, "copycat_count")
    if copy:
        extra.append(f"{int(copy)} same-name / reused-avatar tokens - confirm the contract")
    pools = data.get("meteora_sol_pools")
    if pools is not None:
        if pools:
            extra.append(f"{len(pools)} Meteora SOL pool(s) listed")
        else:
            extra.append("No Meteora SOL pool listed in the snapshot - check Meteora directly, not just GMGN")
    for note in data.get("notes", []) or []:
        extra.append(str(note))

    # ---------------- verdict
    reds = [x for x in checks if x.result is Result.RED]
    nas = [x for x in checks if x.result is Result.NA]
    cautions = [x for x in checks if x.result is Result.CAUTION]
    reasons: list[str] = []
    if reds:
        verdict = Verdict.SKIP
        reasons = [f"#{x.number} {x.name}: {x.reading}" for x in reds]
    elif nas or len(cautions) >= cfg["verdict"]["watch_if_cautions_at_least"]:
        verdict = Verdict.WATCH
        reasons = ([f"#{x.number} {x.name} not usable yet ({x.note or x.reading})" for x in nas]
                   + [f"#{x.number} {x.name} CAUTION: {x.reading}" for x in cautions])
    else:
        verdict = Verdict.ENTER
        reasons = [f"#{x.number} {x.name} CAUTION: {x.reading}" for x in cautions] or ["All checks passed"]

    return RugReport(
        token=str(data.get("token_name", "?")),
        contract=contract,
        checks=checks,
        verdict=verdict,
        reasons=reasons,
        extra_flags=extra,
        is_pump_fun=is_pump,
        pool_age_minutes=age,
    )
