"""DLMM Scalp Playbook - 1-minute LP scalps on fresh memecoin pools.

Deliberately separate from the rug check: no rug-sheet threshold is used here.

Candles are 1-minute readings, oldest first:
    {"volume_usd": float, "net_buy_usd": float, "holders": int, "bundler_pct": float}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import load_scalp_config

REQUIRED_KEYS = ("volume_usd", "net_buy_usd", "holders", "bundler_pct")

def money(v: float, signed: bool = False) -> str:
    """$1,234 / -$1,234 / +$1,234 (signed=True shows + for positives)."""
    sign = "-" if v < 0 else ("+" if signed and v > 0 else "")
    return f"{sign}${abs(v):,.0f}"



@dataclass
class Requirement:
    name: str
    ok: bool | None  # None = needs manual confirmation
    detail: str


@dataclass
class ScalpEntryReport:
    token: str
    contract: str
    requirements: list[Requirement]
    meets_playbook: bool
    baseline: dict[str, float]
    exit_levels: dict[str, str]
    setup: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "contract": self.contract,
            "meets_playbook": self.meets_playbook,
            "requirements": [r.__dict__ for r in self.requirements],
            "baseline": self.baseline,
            "exit_levels": self.exit_levels,
            "setup": self.setup,
        }


@dataclass
class ScalpExitReport:
    action: str  # "EXIT NOW" or "HOLD"
    triggers: list[str] = field(default_factory=list)
    readings: dict[str, str] = field(default_factory=dict)
    close_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _validate(candles: list[dict[str, Any]], minimum: int) -> None:
    if len(candles) < minimum:
        raise ValueError(f"need at least {minimum} one-minute candles, got {len(candles)}")
    for i, c in enumerate(candles):
        missing = [k for k in REQUIRED_KEYS if c.get(k) is None]
        if missing:
            raise ValueError(f"candle {i} is missing {', '.join(missing)}")


def _pct_change(prev: float, now: float) -> float:
    return 0.0 if prev == 0 else (now - prev) / prev * 100


# ------------------------------------------------------------------- entry

def check_scalp_entry(data: dict[str, Any], cfg: dict[str, Any] | None = None) -> ScalpEntryReport:
    cfg = cfg or load_scalp_config()
    e, x = cfg["entry"], cfg["exit_triggers"]
    candles = data.get("candles", [])
    need = e["volume_rising_candles_min"] + 1
    _validate(candles, need)
    prev, cur = candles[-2], candles[-1]

    reqs: list[Requirement] = []

    # 1 volume rising for the last N candles
    vols = [float(c["volume_usd"]) for c in candles[-need:]]
    rising = all(b > a for a, b in zip(vols, vols[1:]))
    reqs.append(Requirement(
        f"Volume rising {e['volume_rising_candles_min']}+ candles", rising,
        " → ".join(f"${v:,.0f}" for v in vols)))

    # 2 net buy positive on current 1m
    nb = float(cur["net_buy_usd"])
    reqs.append(Requirement("Net buy positive on current 1m", nb > 0, money(nb, signed=True)))

    # 3 holders growing
    h0, h1 = int(prev["holders"]), int(cur["holders"])
    reqs.append(Requirement("Holder count growing", h1 > h0, f"{h0} → {h1}"))

    # 4 bundler stable or falling slowly
    b0, b1 = float(prev["bundler_pct"]), float(cur["bundler_pct"])
    d = b1 - b0
    ok = (-e["bundler_max_fall_pts"] < d <= e["bundler_max_rise_pts"])
    reqs.append(Requirement("Bundler stable or falling slowly", ok, f"{b0:g}% → {b1:g}% ({d:+.2f} pts)"))

    # 5 manual confirmations
    conf = data.get("confirmations", {}) or {}
    for key, label in (("ca_verified", "Contract address verified"),
                       ("authorities_ok", "Mint / freeze authorities checked"),
                       ("lp_depth_ok", "LP depth checked")):
        v = conf.get(key)
        reqs.append(Requirement(label, v if isinstance(v, bool) else None,
                                "confirmed" if v is True else ("FAILED" if v is False else "confirm manually")))

    meets = all(r.ok is True for r in reqs)

    baseline = {
        "bundler_pct": b1,
        "net_buy_usd": nb,
        "holders": h1,
        "volume_usd": float(cur["volume_usd"]),
    }
    exit_levels = {
        "bundler": f"exit if ≤ {b1 - x['bundler_drop_pts']:g}% (drop ≥ {x['bundler_drop_pts']:g} pts in 1m)",
        "net_buy": f"exit if ≤ {money(x['net_buy_at_or_below_usd'])} in 1m",
        "holders": f"exit if ≤ {int(h1 * (1 - x['holders_drop_pct'] / 100))} (drop ≥ {x['holders_drop_pct']:g}% vs prior 1m)",
        "volume": f"exit if ≤ ${baseline['volume_usd'] * (1 - x['volume_drop_pct'] / 100):,.0f} (drop ≥ {x['volume_drop_pct']:g}% vs prior 1m)",
        "time_stop": f"close after ~{x['time_stop_minutes']} min regardless",
        "range": "close if price leaves your bin range",
    }
    return ScalpEntryReport(
        token=str(data.get("token_name", "?")),
        contract=str(data.get("contract", "")),
        requirements=reqs,
        meets_playbook=meets,
        baseline=baseline,
        exit_levels=exit_levels,
        setup=cfg["setup"],
    )


# -------------------------------------------------------------------- exit

CLOSE_STEPS = [
    "Remove liquidity + claim fees (use a priority fee)",
    "Swap the memecoin side back to SOL",
    "Log the trade",
]


def check_scalp_exit(data: dict[str, Any], cfg: dict[str, Any] | None = None) -> ScalpExitReport:
    """Compare the latest 1m reading to the prior one. ONE trigger = exit now."""
    cfg = cfg or load_scalp_config()
    x = cfg["exit_triggers"]
    candles = data.get("candles", [])
    _validate(candles, 2)
    prev, cur = candles[-2], candles[-1]

    triggers: list[str] = []
    readings: dict[str, str] = {}

    d_b = float(cur["bundler_pct"]) - float(prev["bundler_pct"])
    readings["bundler"] = f"{prev['bundler_pct']:g}% → {cur['bundler_pct']:g}% ({d_b:+.2f} pts)"
    if -d_b >= x["bundler_drop_pts"]:
        triggers.append(f"Bundler dropped {-d_b:.2f} pts in 1m")

    nb = float(cur["net_buy_usd"])
    readings["net_buy"] = money(nb, signed=True)
    if nb <= x["net_buy_at_or_below_usd"]:
        triggers.append(f"Net buy {money(nb)} ≤ {money(x['net_buy_at_or_below_usd'])}")

    hc = _pct_change(float(prev["holders"]), float(cur["holders"]))
    readings["holders"] = f"{prev['holders']} → {cur['holders']} ({hc:+.1f}%)"
    if -hc >= x["holders_drop_pct"]:
        triggers.append(f"Holders dropped {-hc:.1f}%")

    vc = _pct_change(float(prev["volume_usd"]), float(cur["volume_usd"]))
    readings["volume"] = f"${prev['volume_usd']:,.0f} → ${cur['volume_usd']:,.0f} ({vc:+.1f}%)"
    if -vc >= x["volume_drop_pct"]:
        triggers.append(f"Volume dropped {-vc:.1f}%")

    mins = data.get("minutes_in_trade")
    if mins is not None and float(mins) >= x["time_stop_minutes"]:
        triggers.append(f"Time stop: {float(mins):g} min in trade")
    if data.get("price_in_range") is False:
        triggers.append("Price left the bin range")

    action = "EXIT NOW" if triggers else "HOLD"
    return ScalpExitReport(action, triggers, readings, CLOSE_STEPS if triggers else [])
