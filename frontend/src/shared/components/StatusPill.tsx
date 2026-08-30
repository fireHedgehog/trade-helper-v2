import Chip from "@mui/material/Chip";
import type { ReactNode } from "react";

type Tone = "neutral" | "ok" | "warn" | "bad";

const COLOR: Record<Tone, "default" | "success" | "warning" | "error"> = {
  neutral: "default",
  ok: "success",
  warn: "warning",
  bad: "error",
};

export function StatusPill({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <Chip size="small" variant="outlined" color={COLOR[tone]} label={children} />;
}
