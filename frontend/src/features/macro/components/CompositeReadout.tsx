import { useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";

import type { CompositeReadout as Readout, MacroFactor } from "../types";

const ZONE_COLOR = {
  "risk-off": "error",
  neutral: "default",
  "risk-on": "success",
} as const;

export function CompositeReadout({
  composite,
  factors,
}: {
  composite: Readout & { reading?: string };
  factors: MacroFactor[];
}) {
  const [open, setOpen] = useState(false);
  const used = factors.filter((f) => f.contribution !== null);
  const sorted = [...used].sort((a, b) => (b.contribution ?? 0) - (a.contribution ?? 0));

  return (
    <Paper sx={{ p: 2.5, width: "100%" }}>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 3, alignItems: "flex-start" }}>
        <Box sx={{ minWidth: 150 }}>
          <Typography variant="overline" color="text.secondary">
            Naive composite (baseline)
          </Typography>
          <Box sx={{ display: "flex", alignItems: "baseline", gap: 1.5, mt: 0.5 }}>
            <Typography variant="h3" component="span">
              {composite.score ?? "—"}
            </Typography>
            <Chip label={composite.zone} color={ZONE_COLOR[composite.zone]} />
          </Box>
          <Typography variant="caption" color="text.secondary">
            0 · risk-off — 50 · neutral — 100 · risk-on
          </Typography>
        </Box>

        <Box sx={{ flex: 1, minWidth: 300 }}>
          <Typography variant="body2">
            {composite.reading ?? composite.note}
          </Typography>
          <Button size="small" onClick={() => setOpen((v) => !v)} sx={{ mt: 0.5, px: 0 }}>
            {open ? "Hide" : "Show"} factor breakdown ({composite.n_used} series)
          </Button>
        </Box>
      </Box>

      <Collapse in={open}>
        <Box sx={{ overflowX: "auto", mt: 1 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Series</TableCell>
                <TableCell>Feature</TableCell>
                <TableCell align="right">z</TableCell>
                <TableCell align="right">sign</TableCell>
                <TableCell align="right">contribution</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {sorted.map((f) => (
                <TableRow key={f.series_id}>
                  <TableCell>{f.series_id}</TableCell>
                  <TableCell>{f.feature}</TableCell>
                  <TableCell align="right">{f.z?.toFixed(2) ?? "—"}</TableCell>
                  <TableCell align="right">{f.sign > 0 ? "+" : "−"}</TableCell>
                  <TableCell
                    align="right"
                    sx={{ color: (f.contribution ?? 0) >= 0 ? "success.main" : "error.main" }}
                  >
                    {f.contribution?.toFixed(2) ?? "—"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      </Collapse>
    </Paper>
  );
}
