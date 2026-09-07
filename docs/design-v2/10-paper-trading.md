# Paper trading

The application has no connected paper-trading workflow. There is no Paper
Trading route, order-submission client, holdings reconciliation worker or
persistent paper-account journal.

Trend and Timing contain historical simulated trades. Sizing provides fresh
allocation estimates and saved historical portfolios with explicit capital,
costs and long/short funding assumptions. Those
outputs do not represent broker fills, actual positions or available cash.

The Alpaca provider supports the catalog and market-data workflow. A configured
paper API base URL does not turn research results into broker orders.

The simulation confirms entries and channel exits at the close and normally
fills them at the next open. Resting protective stops are effective during the
session; close-derived revisions apply the next session. Exiting at the next
open after an intraday stop event would be a different execution rule. The
current app makes no paper-versus-simulation performance comparison.
