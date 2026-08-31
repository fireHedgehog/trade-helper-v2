import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { Link as RouterLink } from "react-router-dom";
import Link from "@mui/material/Link";

import { SLEEVE_SHORT } from "../constants";
import type { SizingRow, Verdict } from "../types";

const VERDICT: Record<
  Verdict,
  { color: "success" | "warning" | "error" | "default"; variant: "filled" | "outlined" }
> = {
  ADD: { color: "success", variant: "filled" },
  LIGHT: { color: "warning", variant: "outlined" },
  HOLD: { color: "default", variant: "outlined" },
  WAIT: { color: "error", variant: "outlined" },
};

const pct = (v: number) => `${v.toFixed(1)}%`;
const usd = (v: number) =>
  v >= 1e6 ? `$${(v / 1e6).toFixed(2)}M` : v >= 1e3 ? `$${(v / 1e3).toFixed(1)}k` : `$${v.toFixed(0)}`;

// The full "why" — the waterfall + the notes — lives here, one hover away,
// so the table body stays a clean 6 columns.
function WhyTooltip({ r }: { r: SizingRow }) {
  const step = (label: string, val: number, bold?: boolean) => (
    <>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="caption" sx={{ fontWeight: bold ? 700 : 400, fontVariantNumeric: "tabular-nums" }}>
        {pct(val)}
      </Typography>
    </>
  );
  return (
    <Box sx={{ minWidth: 210 }}>
      <Typography variant="caption" sx={{ fontWeight: 700 }}>
        {r.symbol}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {" "}
        · {SLEEVE_SHORT[r.sleeve]} · {r.state === "long" ? "long" : "short"}
        {r.momentum != null ? ` · mom ${Math.round(r.momentum)}` : ""} · vol{" "}
        {Math.round(r.vol60d * 100)}%
      </Typography>
      <Box
        sx={{
          mt: 0.75,
          display: "grid",
          gridTemplateColumns: "1fr auto",
          columnGap: 1.5,
          rowGap: 0.25,
        }}
      >
        {step("inverse-vol", r.invVolRawPct)}
        {step("after caps", r.afterSectorCapPct)}
        {step("after vol-target", r.afterVolTargetPct)}
        {step("after macro → target", r.targetPct, true)}
      </Box>
      {r.notes.length > 0 && (
        <>
          <Divider sx={{ my: 0.75 }} />
          <Box component="ul" sx={{ m: 0, pl: 2 }}>
            {r.notes.map((n, i) => (
              <li key={i}>
                <Typography variant="caption" color="text.secondary">
                  {n}
                </Typography>
              </li>
            ))}
          </Box>
        </>
      )}
    </Box>
  );
}

export function SizingTable({ rows }: { rows: SizingRow[] }) {
  if (!rows.length) {
    return (
      <Typography color="text.secondary" sx={{ p: 2 }}>
        No on-signal names in scope. Widen the scope on the left, or run the Trend backtest first.
      </Typography>
    );
  }
  return (
    <Box sx={{ overflowX: "auto" }}>
      <Table size="small" sx={{ "& td, & th": { whiteSpace: "nowrap", borderColor: "divider" } }}>
        <TableHead>
          <TableRow>
            <TableCell>Symbol</TableCell>
            <Tooltip title="Annualised 60-day return volatility" arrow>
              <TableCell align="right">Vol</TableCell>
            </Tooltip>
            <Tooltip title="Target weight after every step. Hover the verdict for the full waterfall." arrow>
              <TableCell align="right">Target</TableCell>
            </Tooltip>
            <TableCell align="right">Target&nbsp;$</TableCell>
            <TableCell align="right">Shares</TableCell>
            <TableCell>Verdict</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((r) => {
            const v = VERDICT[r.verdict];
            return (
              <TableRow key={r.symbol} hover>
                <TableCell sx={{ py: 0.75 }}>
                  <Link
                    component={RouterLink}
                    to={`/timing/${encodeURIComponent(r.symbol)}`}
                    sx={{ fontWeight: 600 }}
                  >
                    {r.symbol}
                  </Link>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ display: "block", lineHeight: 1.2 }}
                  >
                    {SLEEVE_SHORT[r.sleeve]}
                    {" · "}
                    <Box
                      component="span"
                      sx={{ color: r.state === "long" ? "success.main" : "error.main", fontWeight: 600 }}
                    >
                      {r.state === "long" ? "L" : "S"}
                    </Box>
                    {r.momentum != null ? ` · m${Math.round(r.momentum)}` : ""}
                  </Typography>
                </TableCell>
                <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums", color: "text.secondary" }}>
                  {Math.round(r.vol60d * 100)}%
                </TableCell>
                <TableCell align="right" sx={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                  {pct(r.targetPct)}
                </TableCell>
                <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>
                  {usd(r.targetUsd)}
                </TableCell>
                <TableCell align="right" sx={{ fontVariantNumeric: "tabular-nums" }}>
                  {r.shares.toLocaleString()}
                </TableCell>
                <TableCell sx={{ py: 0.75 }}>
                  <Tooltip
                    arrow
                    title={<WhyTooltip r={r} />}
                    slotProps={{
                      tooltip: {
                        sx: {
                          bgcolor: "background.paper",
                          color: "text.primary",
                          border: "1px solid",
                          borderColor: "divider",
                          boxShadow: 3,
                          p: 1.25,
                          maxWidth: 300,
                        },
                      },
                      arrow: { sx: { color: "background.paper" } },
                    }}
                  >
                    <Chip
                      size="small"
                      label={r.verdict}
                      color={v.color}
                      variant={v.variant}
                      sx={{ cursor: "help" }}
                    />
                  </Tooltip>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Box>
  );
}
