"""Independent arithmetic audit of a simulated cash-only paper account.

Reconstruct cash and position quantities from execution entries, never prices
from future sessions. This certifies internal consistency, not price provenance.
"""
import math

def reconcile(initial_cash, ledger, held, ending_cash, tolerance=0.02):
    if not math.isfinite(initial_cash) or initial_cash <= 0:
        raise ValueError("Initial capital must be finite and positive")
    cash=float(initial_cash)
    holdings={}
    buy_count=sell_count=dividend_count=split_count=0
    for e in ledger:
        side=e.get("side")
        if side=="BUY" and "qty" in e:
            code=e["code"]
            qty=e["qty"]
            debit=e.get("total_debit")
            if (code in holdings or not isinstance(qty,int) or qty<=0
                    or debit is None or not math.isfinite(debit) or debit<=0):
                raise AssertionError("Invalid ledger buy or double position")
            cash-=debit
            holdings[code]=qty
            buy_count+=1
        elif side=="SELL" and "qty" in e:
            code=e["code"]
            qty=e["qty"]
            credit=e.get("net_credit")
            if (holdings.get(code)!=qty or credit is None
                    or not math.isfinite(credit) or credit<0):
                raise AssertionError("Invalid ledger liquidation")
            cash+=credit
            del holdings[code]
            sell_count+=1
        elif side=="ACTION" and e.get("status")=="SPLIT":
            code=e["code"]
            ratio=e["ratio"]
            q=e["qty"]
            if (code not in holdings or not math.isfinite(ratio) or ratio<=0
                    or not isinstance(q,int) or q<=0
                    or not math.isclose(holdings[code]*ratio,q,abs_tol=1e-8)):
                raise AssertionError("Split holdings mismatch")
            holdings[code]=q
            split_count+=1
        elif side=="ACTION" and e.get("status")=="DIVIDEND":
            amount=e.get("net_credit")
            if amount is None or not math.isfinite(amount) or amount<0:
                raise AssertionError("Invalid dividend credit")
            cash+=amount
            dividend_count+=1
        elif "qty" in e:
            raise AssertionError("Unrecognized execution carries quantity")
    if holdings != {code:pos["qty"] for code,pos in held.items()}:
        raise AssertionError("Ledger holdings disagree with engine holdings")
    if not math.isfinite(cash) or abs(cash-ending_cash)>tolerance:
        raise AssertionError("Independent cash replay differs from engine")
    if cash < -tolerance:
        raise AssertionError("Negative cash in long-only paper account")
    return {"audit":"INTERNAL_CASH_AND_QUANTITY_RECONCILED",
            "executed_buys":buy_count,"executed_sells":sell_count,
            "applied_splits":split_count,"paid_dividends":dividend_count,
            "remaining_positions":len(holdings),
            "note":"Arithmetic only; historical corporate action completeness and fills remain unverified."}
