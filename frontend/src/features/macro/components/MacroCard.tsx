import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { SparkLineChart } from "@mui/x-charts/SparkLineChart";

import type { MacroCardData } from "../types";

const GREEN = "#1f9d55";
const RED = "#d64545";
const GREY = "#9aa0aa";

function releaseText(days: number | null): string {
  if (days === null) return "next: unknown";
  if (days <= 0) return "next: due";
  if (days === 1) return "next: ~1 day";
  return `next: ~${days} days`;
}

function fmtValue(v: number | null): string {
  if (v === null) return "—";
  const abs = Math.abs(v);
  const digits = abs >= 1000 ? 0 : abs >= 10 ? 2 : 3;
  return v.toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function MacroCard({ data }: { data: MacroCardData }) {
  const values = data.spark.map((p) => p.value);
  const sign = data.composite_sign; // +1 = higher ⇒ risk-on, -1 = higher ⇒ risk-off

  // Colour the line by which way the recent move points on the risk axis:
  // (recent direction) × (fixed sign). Green = drifting risk-on, red = risk-off.
  let moveColor = GREY;
  if (values.length >= 2 && sign) {
    const dir = Math.sign(values[values.length - 1] - values[0]);
    moveColor = dir * sign > 0 ? GREEN : dir * sign < 0 ? RED : GREY;
  }

  const conf = data.composite_confidence;
  const dirLabel =
    sign === 1
      ? `↑ = risk-on${conf ? ` · ${conf}` : ""}`
      : sign === -1
        ? `↑ = risk-off${conf ? ` · ${conf}` : ""}`
        : "not scored";
  const dirColor = sign === 1 ? GREEN : sign === -1 ? RED : GREY;
  const dirTip =
    sign === null
      ? "Not enough history to score this series — it is not in the composite."
      : [
          `Composite sign ${sign > 0 ? "+1" : "−1"} (${data.composite_feature}, ` +
            `confidence ${conf}): a ${sign > 0 ? "higher" : "lower"} reading is the ` +
            `risk-ON side; the opposite is risk-OFF / the short side.`,
          data.composite_rationale ? `Why: ${data.composite_rationale}` : "",
          data.composite_caveat ? `Caveat: ${data.composite_caveat}` : "",
          "Line colour = which way the last 10 points are drifting on that axis.",
        ]
          .filter(Boolean)
          .join("\n\n");

  return (
    <Paper sx={{ p: 1.5, display: "flex", flexDirection: "column", gap: 0.5, height: "100%" }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 1 }}>
        <Typography variant="body2" noWrap title={data.label} sx={{ fontWeight: 600 }}>
          {data.label}
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ flexShrink: 0 }}>
          {data.series_id}
        </Typography>
      </Box>

      <Box sx={{ height: 44 }}>
        {values.length >= 2 ? (
          <SparkLineChart data={values} height={44} curve="natural" color={moveColor} showHighlight />
        ) : (
          <Typography variant="caption" color="text.secondary">
            no data — run “Fetch macro data”
          </Typography>
        )}
      </Box>

      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <Typography variant="body2">
          {fmtValue(data.latest_value)}
          {data.units_short ? (
            <Typography component="span" variant="caption" color="text.secondary">
              {" "}
              {data.units_short}
            </Typography>
          ) : null}
        </Typography>
        {data.change_1m_pct !== null && (
          <Typography variant="caption" sx={{ color: data.change_1m_pct >= 0 ? GREEN : RED }}>
            {data.change_1m_pct >= 0 ? "+" : ""}
            {data.change_1m_pct.toFixed(2)}% 1m
          </Typography>
        )}
      </Box>

      <Typography variant="caption" color="text.secondary">
        {data.latest_date ?? "—"} · {data.frequency ?? ""}
      </Typography>

      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", mt: "auto" }}>
        <Typography
          variant="caption"
          color={data.next_release_in_days !== null && data.next_release_in_days <= 0 ? "warning.main" : "text.secondary"}
        >
          {releaseText(data.next_release_in_days)}
        </Typography>
        <Tooltip
          title={<span style={{ whiteSpace: "pre-line" }}>{dirTip}</span>}
          placement="top"
          slotProps={{ tooltip: { sx: { maxWidth: 340 } } }}
        >
          <Typography variant="caption" sx={{ color: dirColor, fontWeight: 600, cursor: "help" }}>
            {dirLabel}
          </Typography>
        </Tooltip>
      </Box>
    </Paper>
  );
}
