"""Guaranteed logical implication vs merely correlated price-pattern features."""
import random
import unittest

from downside_pattern_research import CATALOG, detect
from risk_pattern_normalization import (
    factor_family, implication_closure, implication_edges, normalized_or_veto,
)


def sample_chart(seed):
    rng = random.Random(seed)
    close = 100.0
    history = []
    for _ in range(21):
        previous = close
        close = max(1, close * (1 + rng.uniform(-.13, .13)))
        op = max(1, previous * (1 + rng.uniform(-.03, .03)))
        history.append({
            "adjusted_close": close, "close_price": close,
            "open_price": op, "high_price": max(op, close) * 1.012,
            "low_price": min(op, close) * .988,
            "volume": rng.randint(200, 20000),
        })
    return history


class NormalizationTests(unittest.TestCase):
    def test_catalog_is_not_mutated(self):
        self.assertEqual(len(CATALOG), 121)
        edges = implication_edges()
        self.assertGreater(len(edges), 60)
        self.assertTrue(all(a in CATALOG and b in CATALOG and a != b
                            for a, b in edges))
        self.assertTrue(all(a not in implied for a, implied
                            in implication_closure().items()))

    def test_nested_thresholds_drop_only_redundant_stronger_vetoes(self):
        result = normalized_or_veto([
            "R05_DOWN01", "R05_DOWN03", "R05_DOWN10", "R05_UP10",
            "VOLAT5_EXTREME", "VOLAT5_HIGH", "HIGH20", "HIGH10",
        ])
        self.assertEqual(result["canonical"],
                         ["HIGH10", "R05_DOWN01", "R05_UP10", "VOLAT5_HIGH"])
        self.assertIn("R05_DOWN10", result["redundant"])
        self.assertEqual(result["original_count"], 8)
        self.assertEqual(result["canonical_count"], 4)

    def test_combo_redundancy_and_no_false_equivalence(self):
        result = normalized_or_veto(["MA5_20_BULL", "HIGH20",
                                      "MA_BULL_HIGH20", "MA5_20_BEAR"])
        self.assertEqual(result["canonical"],
                         ["HIGH20", "MA5_20_BEAR", "MA5_20_BULL"])
        self.assertNotIn("MA5_20_BEAR", result["redundant"])
        self.assertEqual(factor_family("MA_BULL_HIGH20"), "intersection")
        with self.assertRaises(ValueError):
            normalized_or_veto(["NOT_A_PATTERN"])

    def test_proven_implications_hold_across_synthetic_price_paths(self):
        edges = implication_edges()
        for seed in range(200):
            found = detect(sample_chart(seed))
            for stronger, weaker in edges:
                if stronger in found:
                    self.assertIn(weaker, found,
                                  f"{stronger} failed to imply {weaker} seed={seed}")

    def test_or_veto_decisions_are_identical_after_normalization(self):
        universe = list(CATALOG)
        rng = random.Random(7129)
        for trial in range(90):
            rules = rng.sample(universe, rng.randint(3, 35))
            canonical = normalized_or_veto(rules)["canonical"]
            for seed in range(trial, trial + 5):
                tags = detect(sample_chart(seed))
                self.assertEqual(bool(tags.intersection(rules)),
                                 bool(tags.intersection(canonical)))


if __name__ == "__main__":
    unittest.main()
