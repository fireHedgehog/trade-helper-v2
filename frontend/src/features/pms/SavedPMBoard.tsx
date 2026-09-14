import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import ExpandMoreRounded from "@mui/icons-material/ExpandMoreRounded";
import type { PMBoard, PMRow } from "./api";

const num = (v: number | null | undefined) => v == null ? "—" : v.toFixed(2);

function AssetLink({ row, runId }: { row: PMRow; runId: number }) {
  const search = new URLSearchParams({ pm: row.pm_key, version: row.pm_version, run: String(runId) });
  return <Link component={RouterLink} to={`/timing/${encodeURIComponent(row.symbol)}?${search}`}>{row.symbol}</Link>;
}

export function SavedPMBoard({ board, selected }: { board: PMBoard | null; selected: string }) {
  const [showFlat, setShowFlat] = useState(false);
  if (!board) return <Typography>Loading saved PMs…</Typography>;
  if (board.status === "not_computed") return <Alert severity="info">Run all enabled PMs to save independent strategy results.</Alert>;
  const rows = board.rows.filter(r => selected === "all" || r.pm_key === selected);
  const pending = rows.filter(r => r.pending_action);
  const visible = rows.filter(r => showFlat || r.state === "long" || r.state === "short" || r.pending_action || r.status !== "ok");
  const groups = [
    { title: "Long signals", direction: "long", action: "enter" },
    { title: "Long exit signals", direction: "long", action: "exit" },
    { title: "Short signals", direction: "short", action: "enter" },
    { title: "Short exit signals", direction: "short", action: "exit" },
  ];
  return <>
    {board.run_status !== "succeeded" && <Alert severity="warning" sx={{ mb: 2 }}>
      This saved PM run is {board.run_status}. Missing or failed results are shown explicitly.
    </Alert>}
    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
      {rows.length} independent PM results. Each PM owns its position, signals and exits.
      Dates refer to the saved run; open an asset to inspect its PM and check for changed prices.
    </Typography>
    <Accordion defaultExpanded={false} disableGutters sx={{ mb: 2 }}>
      <AccordionSummary expandIcon={<ExpandMoreRounded />} id="pm-signals-header" aria-controls="pm-signals-content">
        <Typography variant="subtitle2">Today's signals ({pending.length})</Typography>
      </AccordionSummary>
      <AccordionDetails>
        <Typography variant="caption" color="text.secondary">Confirmed at the displayed date's close, pending the next open. A held position in another PM does not cancel a new signal.</Typography>
        <Box sx={{ overflowX: "auto", mt: 2 }}><Box sx={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(280px, 1fr))", gap: 2 }}>
          {groups.map(group => {
            const signals = pending.filter(r => r.pending_action?.direction === group.direction && r.pending_action.action === group.action);
            return <Paper key={group.title} variant="outlined" sx={{ alignSelf: "start" }}>
              <Typography variant="subtitle2" sx={{ p: 1.5 }}>{group.title} ({signals.length})</Typography>
              <Table size="small" aria-label={group.title}>
                <TableHead><TableRow><TableCell>Asset / PM</TableCell><TableCell>Signal date</TableCell></TableRow></TableHead>
                <TableBody>{signals.map(row => <TableRow key={`${row.symbol}-${row.pm_key}-${row.pm_version}`}>
                  <TableCell><AssetLink row={row} runId={board.run_id!} /><Typography variant="caption" sx={{ display: "block" }}>{row.pm_name}</Typography></TableCell>
                  <TableCell sx={{ whiteSpace: "nowrap" }}>{row.pending_action?.signal_date}</TableCell>
                </TableRow>)}{signals.length === 0 && <TableRow><TableCell colSpan={2}>No signals</TableCell></TableRow>}</TableBody>
              </Table>
            </Paper>;
          })}
        </Box></Box>
      </AccordionDetails>
    </Accordion>
    <Paper sx={{ p: 2 }}>
      <Typography variant="subtitle2">Independent PM positions</Typography>
      <Button size="small" onClick={() => setShowFlat(v => !v)}>{showFlat ? "Hide flat PMs" : "Show flat PMs"}</Button>
      <Box sx={{ overflowX: "auto" }}><Table size="small" aria-label="Independent PM positions">
        <TableHead><TableRow>{["Asset", "PM", "Status / position", "Since", "Entry", "Last", "Stop", "Price date"].map(h => <TableCell key={h}>{h}</TableCell>)}</TableRow></TableHead>
        <TableBody>{visible.map(row => <TableRow key={`${row.symbol}-${row.pm_key}-${row.pm_version}`}>
          <TableCell><AssetLink row={row} runId={board.run_id!} /></TableCell><TableCell>{row.pm_name}</TableCell>
          <TableCell>{row.status === "ok" ? row.state : row.status}<Typography variant="caption" sx={{ display: "block" }}>{row.error}</Typography></TableCell>
          <TableCell sx={{ whiteSpace: "nowrap" }}>{row.state_since ?? "—"}</TableCell>
          <TableCell>{num(row.entry_price)}</TableCell><TableCell>{num(row.last_close)}</TableCell><TableCell>{num(row.current_stop)}</TableCell>
          <TableCell sx={{ whiteSpace: "nowrap" }}>{row.last_date ?? "—"}</TableCell>
        </TableRow>)}{visible.length === 0 && <TableRow><TableCell colSpan={8}>No held positions or pending signals in this view.</TableCell></TableRow>}</TableBody>
      </Table></Box>
    </Paper>
  </>;
}
