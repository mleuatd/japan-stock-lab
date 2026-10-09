#!/usr/bin/env python3
"""Fail closed when a historical replay cannot be valued. Never print rows."""
import json
import math
import sys

def evaluate(result):
    if result.get("status")!="completed":
        return False,"BACKTEST_DID_NOT_COMPLETE"
    paper=result.get("paper_result") or {}
    equity=paper.get("final_equity")
    if not isinstance(equity,(int,float)) or isinstance(equity,bool) or not math.isfinite(equity):
        return False,"UNPRICED_FINAL_EQUITY"
    if equity < 0:
        return False,"NEGATIVE_FINAL_EQUITY"
    diagnostics=paper.get("valuation_diagnostics") or {}
    if not diagnostics.get("final_equity_available",False):
        return False,"FINAL_VALUATION_UNVERIFIED"
    if (paper.get("ledger_audit") or {}).get("audit")!="INTERNAL_CASH_AND_QUANTITY_RECONCILED":
        return False,"ACCOUNTING_LEDGER_UNVERIFIED"
    if paper.get("validation_status")!="PROVISIONAL_UNVERIFIED":
        return False,"UNEXPECTED_VALIDATION_STATUS"
    return True,"PROVISIONAL_EQUITY_AVAILABLE_NOT_VERIFIED"

def main():
    with open(sys.argv[1],encoding="utf-8") as f:
        result=json.load(f)
    success,status=evaluate(result)
    print("BACKTEST_COMPLETENESS_GATE",status)
    if not success:
        print("::error::Portfolio valuation missing or inconclusive; no validated profit")
        raise SystemExit(2)

if __name__=="__main__":main()
