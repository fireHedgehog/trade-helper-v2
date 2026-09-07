"""Isolate historical chart accounting on identical current fills.

The historical formula is from production engine 4e84c4d, not old experiments.
This counterfactual does not recreate the original strategy's trade sequence.
"""
import json
import math
from datetime import date
from experiment import STEP1, OUTPUT, tasks
from app.features.signals import engine, metrics
from app.features.signals.params import SignalParams


def historical_chart(bars, trades):
    index = {b["date"]: i for i, b in enumerate(bars)}
    exposure = [0] * len(bars)
    for tr in trades:
        start = index[tr["entry_date"]]
        stop = index[tr["exit_date"]] if tr["exit_date"] else len(bars)
        for i in range(start, stop):
            exposure[i] = 1 if tr["direction"] == "long" else -1
    return math.prod(1 + exposure[i] * (bars[i]["c"] / bars[i-1]["c"] - 1)
                     for i in range(1, len(bars))) - 1


def main():
    baseline = json.loads((STEP1 / "results.json").read_text(encoding="utf-8"))
    selected = {s["symbol"]: s for s in baseline["summary"]}
    output = []
    for s, bars in tasks(selected, {"SPY", "QQQ", "BTC/USD", "ETH/USD", "TLT"}):
        params = SignalParams(**s["params"])
        actual = engine.run(bars, params)
        no_cost = engine.run(bars, params.model_copy(update={"cost_bps": 0, "slippage_atr": 0}))
        years = (date.fromisoformat(bars[-1]["date"]) - date.fromisoformat(bars[0]["date"])).days / 365.25
        net = engine.compound([d["strat_ret"] for d in actual.daily])[-1] - 1
        cagr = (1 + net) ** (1 / years) - 1
        app_cagr = metrics.summarise(actual.trades, actual.daily, bars)["strategy"]["cagr"]
        assert abs(cagr - app_cagr) < 1e-12
        index = {b["date"]: i for i, b in enumerate(bars)}
        examples = []
        for tr in no_cost.trades:
            if tr["direction"] != "long" or not tr["exit_date"]:
                continue
            old = historical_chart(bars, [tr])
            if tr["return_pct"] < 0 < old:
                i, j = index[tr["entry_date"]], index[tr["exit_date"]]
                examples.append({"entry_date": tr["entry_date"], "entry_price": tr["entry_price"],
                                 "exit_date": tr["exit_date"], "exit_price": tr["exit_price"],
                                 "prior_close": bars[i-1]["c"], "last_held_close": bars[j-1]["c"],
                                 "old_chart_gross": old, "actual_fill_gross": tr["return_pct"]})
        examples.sort(key=lambda t: t["old_chart_gross"] - t["actual_fill_gross"], reverse=True)
        row = {"symbol": s["symbol"], "years": years, "net_return": net,
               "ending_10000": 10000 * (1+net), "calendar_cagr": cagr,
               "incorrect_252_bar_cagr": (1+net) ** (252 / len(bars)) - 1,
               "gross_from_actual_fills": engine.compound([d["strat_ret"] for d in no_cost.daily])[-1]-1,
               "old_chart_formula_gross_same_fills": historical_chart(bars, no_cost.trades),
               "trade_examples": examples[:2]}
        output.append(row)
        print(json.dumps(row), flush=True)
    (OUTPUT / "return-check.json").write_text(json.dumps(output, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
