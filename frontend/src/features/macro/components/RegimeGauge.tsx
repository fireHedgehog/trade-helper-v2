import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { Gauge, gaugeClasses } from "@mui/x-charts/Gauge";

const RED = "#d64545";
const AMBER = "#b7791f";
const GREEN = "#1f9d55";

function scoreColor(v: number): string {
  if (v < 40) return RED;
  if (v < 60) return AMBER;
  return GREEN;
}

function zoneLabel(v: number): string {
  if (v < 40) return "risk-OFF";
  if (v < 60) return "neutral";
  return "risk-ON";
}

interface RegimeGaugeProps {
  score: number | null;
  confidence: number | null;
  onVotes: number;
  offVotes: number;
  neutralVotes: number;
}

export function RegimeGauge({ score, confidence, onVotes, offVotes, neutralVotes }: RegimeGaugeProps) {
  const v = score ?? 50;
  const color = scoreColor(v);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 1 }}>
      <Box sx={{ position: "relative", width: 240, height: 150 }}>
        <Gauge
          value={v}
          startAngle={-90}
          endAngle={90}
          valueMin={0}
          valueMax={100}
          cornerRadius="50%"
          sx={{
            [`& .${gaugeClasses.valueArc}`]: { fill: color },
            [`& .${gaugeClasses.valueText}`]: { display: "none" },
          }}
        />
        <Box
          sx={{
            position: "absolute",
            inset: 0,
            top: 40,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Typography variant="h3" sx={{ color, lineHeight: 1 }}>
            {score === null ? "—" : v.toFixed(1)}
          </Typography>
          <Typography variant="caption" sx={{ color }}>
            {zoneLabel(v)}
          </Typography>
        </Box>
      </Box>

      <Box sx={{ width: "100%", maxWidth: 260 }}>
        <Typography variant="caption" color="text.secondary">
          confidence {confidence === null ? "—" : confidence.toFixed(1)}
        </Typography>
        <LinearProgress
          variant="determinate"
          value={confidence ?? 0}
          sx={{ height: 6, borderRadius: 3 }}
        />
      </Box>

      <Stack direction="row" spacing={1}>
        <Chip size="small" label={`${onVotes} ON`} color={onVotes ? "success" : "default"} variant="outlined" />
        <Chip size="small" label={`${offVotes} OFF`} color={offVotes ? "error" : "default"} variant="outlined" />
        <Chip size="small" label={`${neutralVotes} NEU`} variant="outlined" />
      </Stack>

      <Typography variant="caption" color="text.secondary" sx={{ display: "flex", gap: 3 }}>
        <span>0 · risk-OFF</span>
        <span>100 · risk-ON</span>
      </Typography>
    </Box>
  );
}
