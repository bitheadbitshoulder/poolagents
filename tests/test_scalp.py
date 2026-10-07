import json
import unittest
from pathlib import Path

from poolagents.scalp import check_scalp_entry, check_scalp_exit

EX = Path(__file__).resolve().parent.parent / "examples"


def load(name):
    return json.loads((EX / name).read_text(encoding="utf-8"))


def candle(vol, nb, holders, bundler):
    return {"volume_usd": vol, "net_buy_usd": nb, "holders": holders, "bundler_pct": bundler}


class TestEntry(unittest.TestCase):
    def test_example_meets_playbook(self):
        rep = check_scalp_entry(load("scalp_entry.json"))
        self.assertTrue(rep.meets_playbook)
        self.assertEqual(set(rep.baseline), {"bundler_pct", "net_buy_usd", "holders", "volume_usd"})

    def test_volume_not_rising_fails(self):
        d = load("scalp_entry.json")
        d["candles"][1]["volume_usd"] = 30000
        self.assertFalse(check_scalp_entry(d).meets_playbook)

    def test_negative_net_buy_fails(self):
        d = load("scalp_entry.json")
        d["candles"][-1]["net_buy_usd"] = -100
        self.assertFalse(check_scalp_entry(d).meets_playbook)

    def test_bundler_rising_fails(self):
        d = load("scalp_entry.json")
        d["candles"][-1]["bundler_pct"] = 19.5
        self.assertFalse(check_scalp_entry(d).meets_playbook)

    def test_unconfirmed_manual_checks_block_entry(self):
        d = load("scalp_entry.json")
        d["confirmations"] = {}
        self.assertFalse(check_scalp_entry(d).meets_playbook)

    def test_needs_enough_candles(self):
        with self.assertRaises(ValueError):
            check_scalp_entry({"candles": [candle(1, 1, 1, 1)]})


class TestExit(unittest.TestCase):
    def run_exit(self, prev, cur, **extra):
        return check_scalp_exit({"candles": [prev, cur], **extra})

    def test_hold_when_nothing_breaks(self):
        rep = self.run_exit(candle(100, 10, 100, 20), candle(95, 0, 98, 19))
        self.assertEqual(rep.action, "HOLD")

    def test_each_trigger_alone_exits(self):
        base = candle(100, 10, 100, 20)
        cases = {
            "bundler": candle(100, 10, 100, 18),       # -2 pts
            "net buy": candle(100, -5000, 100, 20),     # <= -$5,000
            "holders": candle(100, 10, 90, 20),         # -10%
            "volume": candle(80, 10, 100, 20),          # -20%
        }
        for name, cur in cases.items():
            rep = self.run_exit(base, cur)
            self.assertEqual(rep.action, "EXIT NOW", name)
            self.assertEqual(len(rep.triggers), 1, name)

    def test_time_stop_and_range(self):
        ok = candle(100, 10, 100, 20)
        self.assertEqual(self.run_exit(ok, ok, minutes_in_trade=15).action, "EXIT NOW")
        self.assertEqual(self.run_exit(ok, ok, price_in_range=False).action, "EXIT NOW")

    def test_example_monitor_exits(self):
        rep = check_scalp_exit(load("scalp_monitor.json"))
        self.assertEqual(rep.action, "EXIT NOW")


if __name__ == "__main__":
    unittest.main()
