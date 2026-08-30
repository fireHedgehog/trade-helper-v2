import Box from "@mui/material/Box";
import LinearProgress from "@mui/material/LinearProgress";
import Typography from "@mui/material/Typography";

/** A percentile (0–100) shown as a value + a filled bar. Mirrors the
 *  reference page's `EvidenceBar`. */
export function EvidenceBar({
  value,
  tone = "positive",
}: {
  value: number | null;
  tone?: "positive" | "warning";
}) {
  const clamped = value == null ? 0 : Math.max(0, Math.min(100, value));
  return (
    <Box sx={{ minWidth: 90 }}>
      <Typography variant="caption" color="text.secondary">
        {value == null ? "—" : `${value.toFixed(1)}%`}
      </Typography>
      <LinearProgress
        variant="determinate"
        value={clamped}
        color={tone === "warning" ? "warning" : "success"}
        sx={{ height: 5, borderRadius: 2 }}
      />
    </Box>
  );
}
