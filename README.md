# PoolAgents

**Pre-entry screening for Meteora DLMM pools on Solana.**
A 15-check rug sheet and a 1-minute scalp playbook, built by a full-time trader who LPs fresh memecoin pools for fee income.

> 🔒 **Read-only by design.** PoolAgents never asks for a private key, never connects a wallet, never signs and never trades. It scores data and prints a verdict. You make the call.

```
VERDICT: 🔴 SKIP
  - #15 Sellable supply vs liquidity: $368.0K sellable ÷ $40.0K liq = 9.20×
```

---

## Why

Most new Solana pools are engineered to dump on liquidity providers. The tells are usually visible *before* you deposit: bundled supply, snipers still holding, liquidity too thin to absorb what insiders can sell. PoolAgents turns a desk checklist into repeatable code, so every pool gets the same 15 checks in the same order, every time.

## What it does (v0.1)

| Command | What you get |
|---|---|
| `poolagents rug <snapshot.json>` | The 15-check **GMGN Pre-Entry Rug Check (v6)** → **ENTER / SKIP / WATCH & RE-CHECK** |
| `poolagents rug <snapshot.json> --fetch` | Same, with missing market data (mcap, liquidity, volume, pool age) filled from DexScreener |
| `poolagents pools <CA>` | Every Solana pool for a token, Meteora SOL pools starred ★ |
| `poolagents scalp-entry <snapshot.json>` | **DLMM Scalp Playbook** entry check, the 4 baseline metrics to record, and the exact exit-trigger levels |
| `poolagents scalp-exit <snapshot.json>` | Compare the last two 1-minute readings → **EXIT NOW / HOLD** |

The rug sheet and the scalp playbook are **completely separate**. A scalp verdict never uses rug-sheet thresholds, and vice versa.

Add `--json` to any command for machine-readable output. Exit codes are script-friendly: `rug` returns 0 = ENTER, 1 = WATCH, 2 = SKIP.

## Install

```bash
git clone https://github.com/<your-username>/poolagents.git
cd poolagents
pip install -e .
poolagents rug examples/token_enter.json
```

Python 3.10+. **Zero dependencies.**

## The rug sheet (v6)

One hard ❌ RED = SKIP. ⏳ N/A (missing data or a pool too young for that metric) never causes a SKIP, but blocks an ENTER.

| # | Check | ❌ RED | ⚠️ CAUTION |
|---|---|---|---|
| 1 | Token tax | > 5% | 1–5% |
| 2 | Top 10 holders | > 30% | |
| 3 | DEV holding | > 5% | |
| 4 | Insiders | > 10% | |
| 5 | Phishing | > 30% | |
| 6 | Snipers still holding | > 10% | 1–10% |
| 7 | Bundler | > 50% | 10–50% |
| 8 | LP burnt | < 90% | |
| 9 | Mint authority | enabled | |
| 10 | Freeze / blacklist | enabled | |
| 11 | Pool quote side (SOL) | down > 50% vs initial | |
| 12 | Liquidity / volume health | liq < $10K or no volume | volume > 50× liquidity |
| 13 | 24h volume | < $100K | |
| 14 | Market cap | < $100K | |
| 15 | **Sellable supply vs liquidity** | > 2× | 1–2× |

**Check #15** is the one that catches engineered pumps:

```
(bundler% + sniper% + dev%) × market cap ÷ total pool liquidity
```

If the wallets most likely to dump can sell more than twice what the pools can absorb, the LP is the exit liquidity.

**Young pools.** Pool age is never scored. A pool under 15 minutes old shows ⏳ for the quote-side swing (unless it's already down more than 50%). A pool under 24h shows ⏳ for volume, plus a 24h run-rate, until it has crossed $100K.

**Extra flags** are reported but not scored: pump.fun token (CA ends in `pump`), high GMGN Rug %, copycat tokens, missing Meteora SOL pools, and your own notes.

All thresholds live in [`poolagents/config/rugcheck_v6.json`](poolagents/config/rugcheck_v6.json). Copy that file and pass `--config my.json` to tune them. The liquidity-health numbers in #12 are starting defaults; tune them to your own experience.

## The scalp playbook

For 1-minute LP scalps on fresh pools. Suggested setup: bin step 100, 2% base fee, two-sided Spot, ~69 bins, and size only what you're willing to lose.

**Entry requires all of:** volume rising for 2+ candles · net buy positive on the current 1m · holders growing · bundler stable or falling slowly · CA, authorities and LP depth confirmed by you.

**Exit on ONE trigger, immediately, with no second confirmation:**

| Trigger (vs the prior 1m) | Level |
|---|---|
| Bundler | drops ≥ 2 pts |
| Net buy | ≤ −$5,000 |
| Holders | drop ≥ 10% |
| Volume | drops ≥ 20% |
| Time stop | ~15 min |
| Range | price leaves your bins |

`scalp-entry` prints your baseline and the absolute exit levels for the next minute, so you can write them down before you deposit.

## Snapshot format

Fill in the GMGN figures; `--fetch` can fill in the market data. See [`examples/`](examples/).

```json
{
  "token_name": "…", "contract": "…pump",
  "market_cap_usd": 800000, "liquidity_usd": 40000, "volume_24h_usd": 2900000,
  "pool_age_minutes": 300,
  "tax_pct": 0, "top10_pct": 24, "dev_pct": 3, "insiders_pct": 6, "phishing_pct": 22,
  "snipers_pct": 8, "bundler_pct": 35, "lp_burnt_pct": 100,
  "mint_enabled": false, "freeze_enabled": false,
  "pool_quote_initial_sol": 85, "pool_quote_now_sol": 140
}
```

Keep your own snapshots in `snapshots/` (git-ignored).

## Roadmap

- [x] **v0.1:** rug sheet, scalp playbook, DexScreener pool lookup, CLI, tests
- [ ] **v0.2: the agents.** A Scout finds new DLMM pools. The Rug Auditor and Scalp Analyst run the checks above. A Bull and a Bear argue the case, and a Risk Manager gives the final verdict. Same debate pattern as TradingAgents, built for DLMM.
- [ ] **v0.3:** Telegram alerts and a live 1-minute scalp monitor
- [ ] **v0.4:** trade log export (P&L, setup grade A/B/C) to learn which setups actually pay

Live trading is **not** on the roadmap as a default. If it's ever added, it will be paper mode first and require an explicit code-level opt-in.

## Security

- No keys, no wallet, no signing.
- Contract addresses are validated as base58 before any network call.
- Token names and API strings are treated as untrusted: control characters and terminal escapes are stripped before printing.
- `.env`, keypair files and personal snapshots are git-ignored.

## Disclaimer

Not financial advice. This is a screening tool. It reduces some risks and removes none. New Solana tokens are extremely high risk, and you can lose everything you put into a pool.

## License

MIT © 2026 Bruce Muirhead
