# Failed-rally short research v1

Frozen 2026-09-14 before candidate execution, checklist T22. This is one new
research hypothesis for the direction gap, not an inverse of a long exit and not
a selected production strategy. No threshold search is included.

Use the same market snapshot, two reporting windows, 250 prior-bar warmup,
next-open fills, fixed units, funding and normal/doubled costs as the long study.
The signal instrument is the stored adjusted equity/ETF or crypto series. The
account is synthetic short exposure, not a claim of borrow or product access.

At completed daily bar t, a flat PM confirms a short only when all are true:

1. Close[t] < SMA200[t], and SMA200[t] < SMA200[t-20].
2. The previous bar's high touched or exceeded SMA20[t-1], while its close was
   below SMA200[t-1]. This is the specified rally attempt.
3. Close[t] < low[t-1]. This confirms failure after the rally bar.

Enter at the next asset open. The fixed protective stop is entry + 3 times the
signal bar's Wilder ATR20. It is active on the entry bar, does not trail, and an
adverse gap fills at max(open, stop). Each PM holds at most one short per asset.

While held, confirm an exit on close >= SMA200 (regime exit), otherwise close >=
SMA20 (rally resumed), otherwise at the twentieth held bar's close (time exit).
The entry bar counts as held bar one; the time exit fills at the following open.
This order labels simultaneous close conditions without changing fill time.
Scheduled exits execute before intraday stops. A stopped/closed PM can confirm
a fresh entry at that day's close for tomorrow, never another intraday fill.
Open positions at the end remain marked; no invented closing fill or fee.

Comparisons: fixed production short benchmark (20/20, initial 2 ATR, Chandelier
3 ATR) and cash, starting flat at the same common decision date. Run priority and
universe funded accounts and matched asset-only accounts for full and 2020-onward
history. Both short candidates use the same frozen funding and cost convention;
cash returns zero with no interest. Normal annual synthetic borrow is 2%, stressed
4%, charged on prior close liability per calendar day. Rising prices must reduce
short equity; sale proceeds do not become free spendable capital.

Report CAGR, drawdown, losses, cash/collateral minima, exposure, borrow, turnover,
coverage and cost sensitivity. A candidate may be rejected or yield no justified
short allocation. Historical stored membership and unresolved price flags apply.
Per-symbol borrow availability, recalls, financing terms, dividend settlement,
venue/product mapping, margin calls and forced liquidation are not established by
this synthetic comparison. Instrument feasibility remains T38-T42; no executable
short or leverage sizing is inferred from these results.
