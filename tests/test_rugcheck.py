import json
import unittest
from pathlib import Path

from poolagents.rugcheck import Result, Verdict, run_rug_check

EX = Path(__file__).resolve().parent.parent / "examples"


def load(name):
    return json.loads((EX / name).read_text(encoding="utf-8"))


def by_number(rep, n):
    return next(c for c in rep.checks if c.number == n)


class TestExamples(unittest.TestCase):
    def test_clean_token_enters(self):
        rep = run_rug_check(load("token_enter.json"))
        self.assertEqual(rep.verdict, Verdict.ENTER)
        self.assertEqual(len(rep.checks), 15)

    def test_engineered_pump_skips_on_sellable_supply(self):
        rep = run_rug_check(load("token_skip.json"))
        self.assertEqual(rep.verdict, Verdict.SKIP)
        self.assertEqual(by_number(rep, 15).result, Result.RED)
        self.assertTrue(rep.is_pump_fun)

    def test_young_pool_watches_not_skips(self):
        rep = run_rug_check(load("token_young.json"))
        self.assertEqual(rep.verdict, Verdict.WATCH)
        self.assertEqual(by_number(rep, 11).result, Result.NA)
        self.assertEqual(by_number(rep, 13).result, Result.NA)


class TestThresholds(unittest.TestCase):
    def base(self, **over):
        d = load("token_enter.json")
        d.update(over)
        return d

    def test_tax(self):
        self.assertEqual(by_number(run_rug_check(self.base(tax_pct=0.5)), 1).result, Result.PASS)
        self.assertEqual(by_number(run_rug_check(self.base(tax_pct=3)), 1).result, Result.CAUTION)
        self.assertEqual(by_number(run_rug_check(self.base(tax_pct=5)), 1).result, Result.CAUTION)
        self.assertEqual(by_number(run_rug_check(self.base(tax_pct=5.1)), 1).result, Result.RED)

    def test_snipers_v5(self):
        self.assertEqual(by_number(run_rug_check(self.base(snipers_pct=0.9)), 6).result, Result.PASS)
        self.assertEqual(by_number(run_rug_check(self.base(snipers_pct=10)), 6).result, Result.CAUTION)
        self.assertEqual(by_number(run_rug_check(self.base(snipers_pct=10.5)), 6).result, Result.RED)

    def test_bundler(self):
        self.assertEqual(by_number(run_rug_check(self.base(bundler_pct=49)), 7).result, Result.CAUTION)
        self.assertEqual(by_number(run_rug_check(self.base(bundler_pct=51)), 7).result, Result.RED)

    def test_simple_reds(self):
        for n, key, bad in ((2, "top10_pct", 31), (3, "dev_pct", 5.5), (4, "insiders_pct", 11),
                            (5, "phishing_pct", 31)):
            rep = run_rug_check(self.base(**{key: bad}))
            self.assertEqual(by_number(rep, n).result, Result.RED, key)
            self.assertEqual(rep.verdict, Verdict.SKIP)

    def test_lp_and_authorities(self):
        self.assertEqual(by_number(run_rug_check(self.base(lp_burnt_pct=89)), 8).result, Result.RED)
        self.assertEqual(by_number(run_rug_check(self.base(mint_enabled=True)), 9).result, Result.RED)
        self.assertEqual(by_number(run_rug_check(self.base(freeze_enabled=True)), 10).result, Result.RED)

    def test_pool_quote_drop_red_even_when_young(self):
        rep = run_rug_check(self.base(pool_age_minutes=5, pool_quote_initial_sol=100, pool_quote_now_sol=40))
        self.assertEqual(by_number(rep, 11).result, Result.RED)

    def test_volume_and_mcap_minimums(self):
        rep = run_rug_check(self.base(volume_24h_usd=90000, pool_age_minutes=3000))
        self.assertEqual(by_number(rep, 13).result, Result.RED)
        rep = run_rug_check(self.base(volume_24h_usd=150000, pool_age_minutes=30))
        self.assertEqual(by_number(rep, 13).result, Result.PASS)  # young but already >= $100K
        rep = run_rug_check(self.base(market_cap_usd=99000))
        self.assertEqual(by_number(rep, 14).result, Result.RED)

    def test_sellable_supply_bands(self):
        # (bundler + sniper + dev)% x mcap / liquidity
        d = self.base(bundler_pct=10, snipers_pct=0, dev_pct=0, market_cap_usd=1_000_000,
                      total_pool_liquidity_usd=60_000)
        self.assertEqual(by_number(run_rug_check(d), 15).result, Result.CAUTION)  # 1.67x
        d["total_pool_liquidity_usd"] = 40_000
        self.assertEqual(by_number(run_rug_check(d), 15).result, Result.RED)  # 2.5x

    def test_missing_data_is_na_never_skip(self):
        d = self.base()
        del d["insiders_pct"]
        rep = run_rug_check(d)
        self.assertEqual(by_number(rep, 4).result, Result.NA)
        self.assertEqual(rep.verdict, Verdict.WATCH)


if __name__ == "__main__":
    unittest.main()
