import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";

import type { BudgetPreset } from "../types";

const Y = "✓";
const NO = "—";

export function RegimeGuide({ budgets }: { budgets: BudgetPreset[] }) {
  return (
    <Box sx={{ py: 1 }}>
        <Stack spacing={2} sx={{ maxWidth: 820, lineHeight: 1.55 }}>
          <Typography variant="body2" color="text.secondary">
            Several analysts each argue a risk-on / risk-off case <i>independently</i>, from a
            compact <b>FRED-only macro snapshot</b> (rates, curve, inflation, credit, VIX,
            financial-conditions, oil, growth, labour — no equities/crypto). A reconciler then
            returns the 0–100 gauge. That is blended ~50/50 with the naive composite and
            calibrated to the number shown.
          </Typography>

          <Box>
            <Typography variant="overline" color="text.secondary">
              Token budget — what each unlocks
            </Typography>
            <Table
              size="small"
              sx={{ mt: 0.5, "& td, & th": { px: 1, py: 0.5 }, "& tr:last-of-type td": { border: 0 } }}
            >
              <TableHead>
                <TableRow>
                  <TableCell>Budget</TableCell>
                  <TableCell align="right">Analysts</TableCell>
                  <TableCell align="center">Web catalyst</TableCell>
                  <TableCell align="center">Rebuttal round</TableCell>
                  <TableCell align="right">Rate paths</TableCell>
                  <TableCell align="right">~Tokens</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {budgets.map((b) => (
                  <TableRow key={b.key}>
                    <TableCell sx={{ fontWeight: 600 }}>{b.label}</TableCell>
                    <TableCell align="right">{b.personas.filter((p) => p !== "macro_catalyst").length}</TableCell>
                    <TableCell align="center">
                      {b.personas.includes("macro_catalyst") ? Y : NO}
                    </TableCell>
                    <TableCell align="center">{b.rebuttal_round ? Y : NO}</TableCell>
                    <TableCell align="right">
                      {b.rate_series_points > 0 ? `${b.rate_series_points}-pt` : NO}
                    </TableCell>
                    <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>
                      {(b.est_total_tokens / 1000).toFixed(0)}k
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
              <b>Small</b> is the cheap read: 4 analysts, features-only snapshot, no live-news
              persona. <b>Medium</b> adds two more domain analysts and the{" "}
              <b>macro-catalyst</b> web-search overlay. <b>Large</b> adds full 12-obs history and a
              rebuttal round where the two advocates challenge each other.
            </Typography>
          </Box>

          <Box>
            <Typography variant="overline" color="text.secondary">
              The analysts
            </Typography>
            <Box component="ul" sx={{ m: 0, mt: 0.5, pl: 2.5, "& li": { mb: 0.5 } }}>
              <li>
                <Typography variant="body2" color="text.secondary">
                  <b>Two advocates</b> — one steelmans risk-on, one steelmans risk-off. Their
                  disagreement is the “adversarial” part.
                </Typography>
              </li>
              <li>
                <Typography variant="body2" color="text.secondary">
                  <b>Four domain analysts</b> — inflation, credit + vol, growth + labour, rates +
                  curve. Domain-weighted; the inflation weight rises as core PCE strays from the
                  ~2% target.
                </Typography>
              </li>
              <li>
                <Typography variant="body2" color="text.secondary">
                  <b>Macro-catalyst overlay</b> (Medium / Large only) — a <b>web-search</b> pass for
                  market-moving events <i>not</i> in the FRED snapshot (a geopolitical oil shock, a
                  Fed surprise). It is a separate fresh headwind / tailwind on the score, not a
                  seventh equal vote.
                </Typography>
              </li>
            </Box>
          </Box>

          <Box>
            <Typography variant="overline" color="text.secondary">
              Reading it
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              &lt; 40 risk-off · 40–60 neutral · ≥ 60 risk-on. Cached once per day — <b>Re-run</b>{" "}
              forces a fresh pass (e.g. to try a pricier model). “Show each analyst’s vote” expands
              the individual rationales.
            </Typography>
          </Box>

          <Box>
            <Typography variant="overline" color="text.secondary">
              Gotchas
            </Typography>
            <Box component="ul" sx={{ m: 0, mt: 0.5, pl: 2.5, "& li": { mb: 0.5 } }}>
              <li>
                <Typography variant="body2" color="text.secondary">
                  The snapshot is <b>FRED-only and FRED lags</b> — daily oil ~1 week, monthly data
                  weeks. Run the <b>Macro</b> + <b>Commodities</b> fetch on the Data Management page
                  before an estimate for the freshest inputs.
                </Typography>
              </li>
              <li>
                <Typography variant="body2" color="text.secondary">
                  <b>“Web search unavailable”</b> on the macro-catalyst row = the persona ran but its
                  web-search tool call failed, i.e. the selected model does not support it. Pick a
                  search-capable model, or read that overlay as “no fresh-catalyst input this run.”
                </Typography>
              </li>
              <li>
                <Typography variant="body2" color="text.secondary">
                  AI-generated, Naive-v1, not statistically validated. Not investment advice.
                </Typography>
              </li>
            </Box>
          </Box>
        </Stack>
    </Box>
  );
}
