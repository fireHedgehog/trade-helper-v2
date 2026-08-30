import BrightnessAutoIcon from "@mui/icons-material/BrightnessAuto";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import LightModeIcon from "@mui/icons-material/LightMode";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import { useColorScheme } from "@mui/material/styles";

const NEXT = { system: "light", light: "dark", dark: "system" } as const;

// Cycles OS → light → dark → OS. Choice is persisted by MUI in localStorage.
export function ColorModeToggle() {
  const { mode, setMode } = useColorScheme();

  // Not mounted yet (first client render) — render a stable placeholder.
  if (!mode) {
    return (
      <IconButton disabled size="small">
        <BrightnessAutoIcon fontSize="small" />
      </IconButton>
    );
  }

  const icon =
    mode === "light" ? (
      <LightModeIcon fontSize="small" />
    ) : mode === "dark" ? (
      <DarkModeIcon fontSize="small" />
    ) : (
      <BrightnessAutoIcon fontSize="small" />
    );

  return (
    <Tooltip title={`Theme: ${mode} (click to change)`}>
      <IconButton size="small" onClick={() => setMode(NEXT[mode])} aria-label="Toggle color mode">
        {icon}
      </IconButton>
    </Tooltip>
  );
}
