import unittest

from poolagents.dexscreener import SOL_MINT, is_valid_solana_address, market_fields, summarize_pairs
from poolagents.render import clean

PAIRS = [
    {"chainId": "solana", "dexId": "pumpswap", "pairAddress": "AAA",
     "baseToken": {"symbol": "TKN", "name": "Token"}, "quoteToken": {"symbol": "SOL", "address": SOL_MINT},
     "liquidity": {"usd": 90000}, "volume": {"h24": 500000, "m5": 2000},
     "marketCap": 1200000, "pairCreatedAt": 1_000_000},
    {"chainId": "solana", "dexId": "meteora", "labels": ["DLMM"], "pairAddress": "BBB",
     "baseToken": {"symbol": "TKN", "name": "Token"}, "quoteToken": {"symbol": "SOL", "address": SOL_MINT},
     "liquidity": {"usd": 30000}, "volume": {"h24": 200000, "m5": 900}, "pairCreatedAt": 2_000_000},
]


class TestDex(unittest.TestCase):
    def test_address_validation_blocks_injection(self):
        self.assertTrue(is_valid_solana_address("So11111111111111111111111111111111111111112"))
        self.assertFalse(is_valid_solana_address("../../evil?x=1"))
        self.assertFalse(is_valid_solana_address("0OIl" * 10))

    def test_meteora_sol_pools_starred(self):
        rows = summarize_pairs(PAIRS)
        self.assertEqual([r["is_meteora_sol"] for r in rows], [False, True])

    def test_market_fields(self):
        f = market_fields(PAIRS, now_ms=1_000_000 + 90 * 60000)
        self.assertEqual(f["market_cap_usd"], 1200000)
        self.assertEqual(f["total_pool_liquidity_usd"], 120000)
        self.assertEqual(f["volume_24h_usd"], 700000)
        self.assertEqual(f["pool_age_minutes"], 90.0)
        self.assertEqual(len(f["meteora_sol_pools"]), 1)

    def test_clean_strips_terminal_escapes(self):
        self.assertEqual(clean("BAD\x1b[2JNAME"), "BAD[2JNAME")


if __name__ == "__main__":
    unittest.main()
