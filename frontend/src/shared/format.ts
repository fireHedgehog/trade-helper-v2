const NA = "—";
const p2 = (n: number) => String(n).padStart(2, "0");

/**
 * Compact a timestamp for a dense table cell.
 *  - full ISO datetime `2026-08-31T21:35:12.425Z` → `08-31 21:35` (local)
 *  - plain date `2026-08-28` → passed through
 *  - null / empty / unparseable → `—` / the raw string
 */
export function fmtTs(v: unknown): string {
  if (v == null || v === "") return NA;
  const s = String(v);
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s; // date-only, already short
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  const now = new Date();
  const sameYear = d.getFullYear() === now.getFullYear();
  const day = sameYear ? `${p2(d.getMonth() + 1)}-${p2(d.getDate())}` : d.toISOString().slice(0, 10);
  return `${day} ${p2(d.getHours())}:${p2(d.getMinutes())}`;
}

/** Keys whose values are timestamps (for generic key/value blocks). */
export const isTsKey = (k: string) => /(_at|_date|^started$|^finished$|^computed$)$/.test(k);
