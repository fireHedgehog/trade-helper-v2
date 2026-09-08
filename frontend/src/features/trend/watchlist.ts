import type { BoardRow, WatchSection } from "./types";

export type WatchDirection = "long" | "short";

// A flat strategy must not inherit the other account's position or trade markers.
export function watchlistForDirection(sections: WatchSection[], direction: WatchDirection): WatchSection[] {
  return sections.map((section) => ({
    ...section,
    rows: section.rows.map((row): BoardRow => {
      const state = row.directions?.[direction];
      const selected: BoardRow = state ? { ...row, ...state } : {
        ...row, state: null, state_since: null, entry_price: null,
        unrealized_pct: null, current_stop: null, pending_action: null,
      };
      return {
        ...selected,
        direction,
        chart: row.chart ? {
          ...row.chart,
          events: row.chart.events.filter((event) => event.dir === direction),
        } : row.chart,
      };
    }),
  }));
}
