import { api } from "@/shared/api/client";

import type { MacroContext, RegimeZone, SizingBoard } from "./types";

interface RegimeLatest {
  score?: number | null;
  status?: string; // "ok" when a real run exists; "not_computed" / absent otherwise
  trading_date?: string;
}

interface MacroOverviewLite {
  composite: { score: number | null; zone: RegimeZone };
}

function zoneFromScore(score: number): RegimeZone {
  if (score >= 60) return "risk-on";
  if (score <= 40) return "risk-off";
  return "neutral";
}

// Prefer the adversarial-LLM regime gauge when a run exists; fall back to the
// always-on naive composite; last resort a neutral stub. Only the zone drives
// the sizing overlay — the score is shown for context.
export async function loadMacroContext(): Promise<MacroContext> {
  try {
    const r = (await api.get<RegimeLatest>("/macro/ai-regime/latest")) ?? {};
    // A real run returns a numeric score and status "ok"; the not-computed
    // shape has no score (or status !== "ok"). Either way we fall through.
    if (typeof r.score === "number" && (r.status ?? "ok") === "ok") {
      return {
        source: "ai-regime",
        score: r.score,
        zone: zoneFromScore(r.score),
        label: `AI regime ${r.score.toFixed(1)}`,
      };
    }
  } catch {
    /* fall through to the naive composite */
  }
  try {
    const o = await api.get<MacroOverviewLite>("/macro/overview");
    const score = o.composite.score;
    return {
      source: "naive-composite",
      score,
      zone: o.composite.zone,
      label: score != null ? `naive composite ${score.toFixed(1)}` : "naive composite",
    };
  } catch {
    return { source: "none", score: null, zone: "neutral", label: "no macro reading" };
  }
}

export const sizingApi = {
  board: () => api.get<SizingBoard>("/signals/board"),
  macro: loadMacroContext,
};
