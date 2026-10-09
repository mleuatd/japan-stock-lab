"""Verify the optimized frozen rule predicate against the reference implementation."""
import unittest
from february_walkforward import candidate_rules
from walkforward_backtest import Bar, rule_matches


class FrozenPredicateRegression(unittest.TestCase):
    def test_every_candidate_and_history_prefix(self):
        # Explicitly exercise the same computation used in the optimized loop.
        for rule in candidate_rules():
            for direction in (-1, 0, 1):
                bars = [
                    Bar(str(i), "11110", 300 + direction * i, 300 + direction * i,
                        100000 if i % 2 else 0, 300 + direction * i)
                    for i in range(35)
                ]
                for i in range(rule["lookback"], len(bars) - 2):
                    old=rule_matches(bars[:i + 1], rule)
                    previous=bars[i - rule["lookback"]].adj_close
                    current=bars[i]
                    new=(previous > 0 and
                         (current.adj_close / previous - 1) * 100 >= rule["min_return_pct"] and
                         current.volume >= rule["min_volume"])
                    self.assertEqual(old,new,(rule,i,direction))


if __name__=="__main__":
    unittest.main()
