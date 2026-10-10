"""Loss-avoidance daily watchlist: test that 'no match' is never a buy order."""
import datetime as dt
import unittest
from risk_veto_daily_screen import (
    select_veto_patterns,build_shortlist,judge_symbol,verify_window,
    freshness,wilson,MODEL,primary_gate_verdict
)
def stat(pattern,segment,metric=None,value=30,n=1000,unique=250):
    r={"pattern_code":pattern,"segment":segment,"horizon":20,
       "unique_symbols":unique,"total_count":n,
       "observed_count":n,"missing_count":0,"path_complete_count":n,
       "down_pct":value,"close_loss5_pct":value,
       "touch_loss5_pct":value}
    if metric:r[metric]=value
    return r

def sample_stats(underpowered=False):
    data=[]
    for segment in ("train","holdout"):
        a=10000 if segment=="train" else 3000
        b=2000 if segment=="train" else 900
        data.extend([stat("BASE",segment,value=35,n=a),
                     stat("LOW20",segment,value=60 if segment=="train" else 54,n=b,
                          unique=35 if underpowered else 500),
                     stat("HIGH20",segment,value=31 if segment=="train" else 36,n=b,
                          unique=300)])
    return data

def bars_21(start="2026-10-01", declining=False):
    d=dt.date.fromisoformat(start)
    days=[(d+dt.timedelta(days=i)).isoformat() for i in range(21)]
    bars=[]
    for i,day in enumerate(days):
        price=200-i*2 if declining else 200+i*2
        bars.append({"day":day,"adjusted_close":price,
           "open_price":price,"high_price":price+2,
           "low_price":price-2,"close_price":price,"volume":1000})
    return days,bars

class DailyRiskVetoTests(unittest.TestCase):
    def setUp(self):
        self.model=select_veto_patterns(sample_stats(),
             "NOT_CALIBRATED_CORPORATE_ACTIONS_UNVERIFIED",
             "JPX_LISTING_RISK_INCOMPLETE")
    def test_research_only_even_when_no_risky_pattern(self):
        days,rows=bars_21()
        result=judge_symbol("11110",rows,days,self.model)
        self.assertEqual(result["status"],"NO_VETO_MATCH_RESEARCH_ONLY")
        snap=build_shortlist({"11110":rows},days,self.model,days[-1])
        self.assertEqual(snap["research_candidates"],1)
        self.assertEqual(snap["ready_to_buy"],0)
        self.assertEqual(snap["rows"][0]["execution_approval"],"NOT_APPROVED")
        self.assertEqual(snap["state"],"RESEARCH_WATCHLIST_ONLY")
    def test_loss_pattern_is_excluded(self):
        days,rows=bars_21(declining=True)
        result=judge_symbol("11110",rows,days,self.model)
        self.assertIn("LOW20",result["veto"])
        self.assertEqual(result["status"],"EXCLUDE_DOWNSIDE_PATTERN")
    def test_rule_selects_train_and_holdout_only_with_evidence(self):
        self.assertEqual([x["code"] for x in self.model["rules"]],["LOW20"])
        self.assertEqual(self.model["state"],"CONDITIONAL_RISKS_FOUND")
        s=select_veto_patterns(sample_stats(underpowered=True),
             "NOT_CALIBRATED_CORPORATE_ACTIONS_UNVERIFIED",
             "JPX_LISTING_RISK_INCOMPLETE")
        self.assertEqual(s["rules"],[])
        self.assertEqual(s["state"],"NO_VALIDATED_VETO_RULES")
    def test_holdout_failure_disqualifies_veto(self):
        rows=sample_stats()
        for row in rows:
            if row["pattern_code"]=="LOW20" and row["segment"]=="holdout":
                row.update(down_pct=31,touch_loss5_pct=31,close_loss5_pct=31)
        result=select_veto_patterns(rows,"NOT_CALIBRATED_CORPORATE_ACTIONS_UNVERIFIED",
                                    "JPX_LISTING_RISK_INCOMPLETE")
        self.assertEqual(result["rules"],[])
    def test_missing_evidence_does_not_mean_safe(self):
        days,rows=bars_21()
        missing=rows[:-1]
        r=judge_symbol("11110",missing,days,self.model)
        self.assertEqual(r["status"],"UNKNOWN_MISSING_MARKET_DAYS")
        rows[-1]["low_price"]=None
        r=judge_symbol("11110",rows,days,self.model)
        self.assertEqual(r["status"],"UNKNOWN_INVALID_CANDLES")
        no_rules=select_veto_patterns([],
          "NOT_CALIBRATED_CORPORATE_ACTIONS_UNVERIFIED",
          "JPX_LISTING_RISK_INCOMPLETE")
        self.assertEqual(no_rules["state"],"BASELINE_UNAVAILABLE")
        r=judge_symbol("11110",bars_21()[1],days,no_rules)
        self.assertEqual(r["status"],"UNKNOWN_NO_VERIFIED_NEGATIVE_RULES")
    def test_primary_loss_gate_requires_both_samples_and_same_source_day(self):
        day="2026-07-17"
        good="IMPROVED_HISTORICALLY_NOT_PROSPECTIVELY_VALIDATED"
        fail="FAIL_PRIMARY_ANY_LOSS_RATE"
        self.assertEqual(primary_gate_verdict([],day),
                         "PRIMARY_RISK_AUDIT_MISSING_NO_SCREEN")
        self.assertEqual(primary_gate_verdict([("daily",good,day)],day),
                         "PRIMARY_RISK_AUDIT_MISSING_NO_SCREEN")
        self.assertEqual(primary_gate_verdict([("daily",fail,day),
                                               ("spaced30",fail,day)],day),
                         "PRIMARY_LOSS_RATE_FAILED_NO_SCREEN")
        self.assertEqual(primary_gate_verdict([("daily",good,day),
                                               ("spaced30",good,"2026-06-30")],day),
                         "PRIMARY_RISK_AUDIT_STALE_NO_SCREEN")
        self.assertEqual(primary_gate_verdict([("daily",good,day),
                                               ("spaced30",good,day)],day),
                         "PRIMARY_RESEARCH_IMPROVEMENT_ONLY")

    def test_invalid_earlier_candles_are_never_cleared(self):
        days,rows=bars_21()
        rows[3]["low_price"]=None
        result=judge_symbol("11110",rows,days,self.model)
        self.assertEqual(result["status"],"UNKNOWN_INVALID_CANDLES")

    def test_stale_data_blocks_everything(self):
        days,rows=bars_21(start="2026-07-01")
        self.assertFalse(freshness(days[-1],"2026-10-10"))
        snap=build_shortlist({"11110":rows},days,self.model,"2026-10-10")
        self.assertEqual(snap["state"],"STALE_DATA_NO_SCREEN")
        self.assertEqual(snap["rows"],[])
        self.assertEqual(snap["ready_to_buy"],0)
    def test_known_jpx_warning_excluded(self):
        days,rows=bars_21(start="2026-05-01")
        r=judge_symbol("61730",rows,days,self.model)
        self.assertEqual(r["status"],"EXCLUDE_KNOWN_JPX_WARNING")
    def test_invalid_model_status_fails_closed(self):
        s=select_veto_patterns(sample_stats(),"APPROVED","JPX_LISTING_RISK_INCOMPLETE")
        self.assertEqual(s["rules"],[])
        self.assertEqual(s["state"],"INCOMPATIBLE_MODEL")
    def test_ddl_statements_do_not_expose_sql_comment_fragments(self):
        from pathlib import Path
        ddl=Path("sql/009_risk_veto_watchlist.sql").read_text(encoding="utf8")
        statements=[line.strip() for line in ddl.split(";") if line.strip()]
        self.assertEqual(len(statements),4)
        self.assertTrue(all("CREATE " in stmt for stmt in statements))

    def test_ci_is_broad_for_small_sample(self):
        lower,upper=wilson(7,10)
        self.assertLess(lower,70)
        self.assertGreater(upper,70)
        self.assertEqual(MODEL,"risk-veto-v1")

if __name__=="__main__":unittest.main()
