"""Explainable exit research: historical next-open fill, no leakage, train-only rules."""
import copy
import unittest
from collections import defaultdict
from datetime import date, timedelta

from conditional_exit_discovery import (
    ATOMS, BIT, FEATURES, MAX_HOLD, analyze, describe_conditional_day,
    discover, effect, evidence_rank, feature_mask, policy_exit,
    sample_episode, summarize_effect,
)


def candle(close=100.0, op=None, vol=1000):
    op = close if op is None else op
    return (close, vol, op, max(close, op) + 2, min(close, op) - 2)


def hist():
    return {i: candle(100.) for i in range(55)}


class ExplainableStateTests(unittest.TestCase):
    def test_independent_prelabeled_families(self):
        self.assertGreaterEqual(len(ATOMS), 17)
        self.assertEqual(len(FEATURES), len(BIT))
        self.assertEqual(len({BIT[x] for x in BIT}), len(BIT))
        self.assertTrue(all(v & (v - 1) == 0 for v in BIT.values()))

    def test_day1_observes_close_and_not_day2_price(self):
        norm = hist()
        t = 20
        norm[t+1] = candle(101.,100)
        mask = feature_mask(t,1,norm,100.,101.)
        self.assertTrue(mask & BIT["AGE_01_05"])
        self.assertTrue(mask & BIT["PNL_GAIN0_2"])
        norm[t+2] = candle(100000.)
        self.assertEqual(mask,feature_mask(t,1,norm,100.,101.))

    def test_state_extreme_risk_can_be_observed(self):
        norm = hist()
        t = 20
        norm[t+4] = candle(90.)
        norm[t+5] = candle(90.)
        norm[t+6] = candle(87.)
        norm[t+7] = candle(83.)
        mask = feature_mask(t,7,norm,100.,100.)
        self.assertTrue(mask & BIT["AGE_06_15"])
        self.assertTrue(mask & BIT["PNL_LOSS5"])
        self.assertTrue(mask & BIT["DRAWDOWN5"])
        self.assertTrue(mask & BIT["MOM3_DOWN3"])
        self.assertTrue(mask & BIT["RED2"])
        self.assertTrue(mask & BIT["MA5_BELOW20"])

    def test_gap_does_not_fake_a_limit_order(self):
        norm = hist()
        t = 20
        norm[t+1] = candle(97.,100.)
        norm[t+2] = candle(95.,91.)
        norm[t+30] = candle(93.,94.)
        s = sample_episode(t,norm)
        self.assertIsNotNone(s)
        self.assertEqual(len(s[1]),28)
        new,day = policy_exit(s,BIT["PNL_LOSS2_5"])
        self.assertEqual(day,2)
        self.assertLess(new,-9) # gap opening below previous close
        self.assertAlmostEqual(s[0],100*(94*.999/(100*1.001)-1))

    def test_missing_future_makes_episode_unknown_not_a_win(self):
        n=hist()
        n[25] = None
        self.assertIsNone(sample_episode(20,n))
        n=hist()
        n[50] = (100,0,100,102,98)
        self.assertIsNone(sample_episode(20,n))

    def test_first_match_exit_and_nonmatch_hold(self):
        sample=(-3.,[
            (BIT["AGE_01_05"] | BIT["PNL_GAIN0_2"], +1.5, 2),
            (BIT["AGE_01_05"] | BIT["PNL_LOSS2_5"], -3.0, 3),
        ])
        self.assertEqual(policy_exit(sample,BIT["PNL_LOSS2_5"]),(-3.0,3))
        self.assertEqual(policy_exit(sample,BIT["PNL_GAIN5"]),(-3.0,30))
        row=effect([sample],BIT["PNL_GAIN0_2"])
        self.assertEqual((row["prevented"],row["introduced"]),(1,0))
        self.assertEqual(row["exit_count"],1)

    def test_loss_prevention_not_artificially_claimed_from_bigger_losses(self):
        s=[(-1.,[(BIT["PNL_LOSS5"],-6.,2)]) for _ in range(200)]
        row=effect(s,BIT["PNL_LOSS5"])
        self.assertEqual(row["prevented"],0)
        self.assertEqual(row["introduced"],0)
        self.assertIsNone(evidence_rank(row))

    def test_train_a_frozen_before_holdout(self):
        a=[(-2.,[(BIT["AGE_01_05"]|BIT["PNL_LOSS2_5"],+1.,2)])
           for _ in range(180)]
        b=[(-2.,[(BIT["AGE_01_05"]|BIT["PNL_LOSS2_5"],+1.,2)])
           for _ in range(180)]
        hold=[(+2.,[(BIT["AGE_01_05"]|BIT["PNL_LOSS2_5"],-10.,2)])
              for _ in range(180)]
        episodes={("TRAIN_A","ALL"):a,("TRAIN_B","ALL"):b,
                  ("HOLDOUT","ALL"):hold}
        before,_=discover(episodes)
        self.assertTrue(before["selected"])
        self.assertEqual(before["state"],
                         "REPEATED_ANY_LOSS_REDUCTION_RETROSPECTIVE_ONLY")
        episodes[("HOLDOUT","ALL")]=[(-5.,[(0,+30.,2)])]*10000
        after,_=discover(episodes)
        self.assertEqual(before,after)

    def test_future_veto_filter_cannot_change_training_selection(self):
        # A model fitted using later training months may label SURVIVOR after
        # the fact. The primary discovery result must ignore that cohort.
        a = [(-3., [(BIT["AGE_01_05"], 1.5, 2)]) for _ in range(180)]
        later = [(-3., [(BIT["AGE_01_05"], 1.5, 2)]) for _ in range(180)]
        episodes = {("TRAIN_A","ALL"): a, ("TRAIN_B","ALL"): later,
                    ("TRAIN_A","SURVIVOR"): [], ("TRAIN_B","SURVIVOR"): []}
        before, _ = discover(episodes)
        self.assertIsNotNone(before["selected"])
        episodes[("TRAIN_A","SURVIVOR")] = [(5., [(BIT["AGE_01_05"], -9., 2)])]*999
        episodes[("TRAIN_B","SURVIVOR")] = [(5., [(BIT["AGE_01_05"], -9., 2)])]*999
        after, _ = discover(episodes)
        self.assertEqual(before, after)

    def test_second_factor_cannot_form_a_contradiction(self):
        a=[(-2.,[(BIT["AGE_01_05"]|BIT["PNL_LOSS2_5"],+1.,2)])
           for _ in range(180)]
        z={("TRAIN_A","ALL"):a,("TRAIN_B","ALL"):a}
        chosen,_=discover(z)
        # A combined candidate is permitted only across two feature families.
        if " & " in chosen["selected"]:
            p,q=chosen["selected"].split(" & ")
            self.assertNotEqual(FEATURES[p][0],FEATURES[q][0])

    def test_daily_state_report_counts_baseline_and_next_open_paired(self):
        sample=(-3.,[(BIT["AGE_01_05"] | BIT["PNL_GAIN2_5"],1.,2),
                      (BIT["AGE_01_05"] | BIT["PNL_LOSS2_5"],-5.,3)])
        d=describe_conditional_day({("TRAIN_A","SURVIVOR"):[sample]},
                                     "TRAIN_A","SURVIVOR")
        self.assertEqual(d[(1,"PNL_GAIN2_5")]["prevented"],1)
        self.assertEqual(d[(2,"PNL_LOSS2_5")]["exit_loss"],1)
        self.assertEqual(d[(1,"PNL_GAIN2_5")]["n"],1)

    def test_sample_baseline_not_affected_by_session_30_close(self):
        n=hist()
        t=20
        n[t+30]=candle(500.,101.)
        a=sample_episode(t,n)
        n[t+30]=candle(1.,101.)
        b=sample_episode(t,n)
        self.assertEqual(a,b)

    def test_ddl_is_private_and_exposes_conditional_views(self):
        from pathlib import Path
        s=Path("sql/016_conditional_exit_discovery.sql").read_text()
        self.assertEqual(s.count("CREATE TABLE IF NOT EXISTS"),3)
        self.assertEqual(s.count("CREATE OR REPLACE VIEW"),2)
        self.assertNotIn("DROP TABLE",s)


if __name__ == "__main__":
    unittest.main()
