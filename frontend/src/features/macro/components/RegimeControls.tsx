import type { ReactNode } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import FormControl from "@mui/material/FormControl";
import InputLabel from "@mui/material/InputLabel";
import ListSubheader from "@mui/material/ListSubheader";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";

import type { BudgetPreset, ModelOption } from "../types";

interface RegimeControlsProps {
  models: ModelOption[];
  budgets: BudgetPreset[];
  model: string;
  budget: "small" | "medium" | "large";
  onModel: (id: string) => void;
  onBudget: (b: "small" | "medium" | "large") => void;
  onRun: () => void;
  running: boolean;
  hasRunToday: boolean;
}

export function RegimeControls({
  models,
  budgets,
  model,
  budget,
  onModel,
  onBudget,
  onRun,
  running,
  hasRunToday,
}: RegimeControlsProps) {
  const families = [...new Set(models.map((m) => m.family))];
  const items: ReactNode[] = [];
  for (const fam of families) {
    items.push(<ListSubheader key={`h-${fam}`}>{fam}</ListSubheader>);
    for (const m of models.filter((x) => x.family === fam && x.enabled)) {
      items.push(
        <MenuItem key={m.id} value={m.id}>
          {m.label} · {m.tier}
          {m.available_on_account === false ? " · not on account" : ""}
        </MenuItem>,
      );
    }
  }

  const chosen = budgets.find((b) => b.key === budget);

  return (
    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2, alignItems: "flex-end" }}>
      <FormControl size="small" sx={{ minWidth: 220 }}>
        <InputLabel id="regime-model-label">Model</InputLabel>
        <Select
          labelId="regime-model-label"
          label="Model"
          value={models.some((m) => m.id === model) ? model : ""}
          onChange={(e) => onModel(e.target.value)}
        >
          {items}
        </Select>
      </FormControl>

      <Box>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
          Token budget
        </Typography>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={budget}
          onChange={(_, v) => v && onBudget(v)}
        >
          {budgets.map((b) => (
            <ToggleButton key={b.key} value={b.key}>
              {b.label}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </Box>

      <Button variant="contained" onClick={onRun} disabled={running}>
        {running ? "Running…" : hasRunToday ? "Re-run" : "Run estimate"}
      </Button>

      {chosen && (
        <Typography variant="caption" color="text.secondary">
          {chosen.personas.length} personas
          {chosen.rebuttal_round ? " + rebuttal" : ""} + reconciler ·{" "}
          {chosen.rate_series_points > 0 ? `${chosen.rate_series_points}-pt rate arrays · ` : ""}~
          {(chosen.est_total_tokens / 1000).toFixed(0)}k tokens
        </Typography>
      )}
    </Box>
  );
}
