import { useEffect, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import ExpandMoreRounded from "@mui/icons-material/ExpandMoreRounded";
import { api } from "@/shared/api/client";

interface Assessment {
  status: "ok" | "unavailable" | "no_families" | "not_computed";
  symbol: string;
  run_id: number;
  cutoff: string | null;
  assessed_on: string;
  coverage: { expected_pms: number; available_pms: number; expected_families: number; available_families: number };
  long_support: string[];
  short_support: string[];
  recent_long: string[];
  recent_short: string[];
  mixed: string[];
  families: { family: string; status: string }[];
  pms: {
    key: string; version: string; name: string; family: string; horizon: string;
    position: string | null; observation: string; recent: boolean;
    excluded_reason: string | null; reasons: string[];
  }[];
}

export function AssessmentPanel({ symbol, runId }: { symbol: string; runId: number }) {
  const [data, setData] = useState<Assessment | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    setData(null); setError(null);
    api.get<Assessment>(`/pms/assessment/${encodeURIComponent(symbol)}?run_id=${runId}`)
      .then(result => { if (alive) setData(result); })
      .catch(e => { if (alive) setError(e instanceof Error ? e.message : String(e)); });
    return () => { alive = false; };
  }, [symbol, runId]);
  if (error) return <Alert severity="warning" sx={{ mb: 2 }}>PM assessment unavailable: {error}</Alert>;
  if (!data) return <Typography variant="body2" sx={{ mb: 2 }}>Loading PM assessment…</Typography>;
  if (data.status === "not_computed") return null;
  const coverage = data.coverage;
  return <Accordion defaultExpanded={false} disableGutters sx={{ mb: 2 }}>
    <AccordionSummary expandIcon={<ExpandMoreRounded />} aria-controls="pm-assessment-content" id="pm-assessment-header">
      <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap", alignItems: "center" }}>
        <Typography variant="subtitle2">PM assessment</Typography>
        <Chip size="small" label={`Long ${data.long_support.length}`} />
        <Chip size="small" label={`Short ${data.short_support.length}`} />
        <Chip size="small" color={data.status === "unavailable" ? "warning" : "default"}
          label={`Families ${coverage.available_families}/${coverage.expected_families}`} />
        {data.mixed.length > 0 && <Chip size="small" color="warning" label={`Mixed ${data.mixed.length}`} />}
      </Stack>
    </AccordionSummary>
    <AccordionDetails>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Descriptive support across the saved PMs for {symbol}, through {data.cutoff ?? "an unavailable cutoff"}.
        Each family counts once. Positions and pending exits remain owned by their PM.
      </Typography>
      <Typography variant="body2" sx={{ mb: 1 }}>
        Recent agreement (five asset bars): long {data.recent_long.length}, short {data.recent_short.length}.
        Available PMs: {coverage.available_pms}/{coverage.expected_pms}, excluding benchmarks.
      </Typography>
      {data.status === "unavailable" && <Alert severity="warning" sx={{ mb: 1 }}>
        Coverage is incomplete. Unavailable PMs remain required members; their absence is not a negative vote.
      </Alert>}
      {data.mixed.length > 0 && <Alert severity="info" sx={{ mb: 1 }}>
        Conflicting presets in {data.mixed.join(", ")} count for neither direction.
      </Alert>}
      <Typography variant="caption" color="text.secondary">
        Checked {data.assessed_on} against stored prices; freshness limit seven calendar days.
        Flat PMs abstain. These observations do not allocate capital.
      </Typography>
      <Box sx={{ overflowX: "auto", mt: 1 }}>
        <Table size="small" aria-label="PM assessment evidence">
          <TableHead><TableRow>{["PM", "Family / horizon", "Position", "Observation", "Family result / reasons"].map(h => <TableCell key={h}>{h}</TableCell>)}</TableRow></TableHead>
          <TableBody>{data.pms.map(pm => {
            const search = new URLSearchParams({ pm: pm.key, version: pm.version, run: String(data.run_id) });
            return <TableRow key={`${pm.key}-${pm.version}`}>
              <TableCell><Link component={RouterLink} to={`/timing/${encodeURIComponent(symbol)}?${search}`}>{pm.name}</Link></TableCell>
              <TableCell>{pm.family} / {pm.horizon}</TableCell>
              <TableCell>{pm.position ?? "Unavailable"}</TableCell>
              <TableCell>{pm.observation.replaceAll("_", " ")}{pm.recent ? " · recent" : ""}</TableCell>
              <TableCell>{pm.excluded_reason ?? data.families.find(f => f.family === pm.family)?.status}
                {pm.reasons.map(reason => <Typography key={reason} variant="caption" sx={{ display: "block" }}>{reason}</Typography>)}
              </TableCell>
            </TableRow>;
          })}</TableBody>
        </Table>
      </Box>
    </AccordionDetails>
  </Accordion>;
}
