import { useState, type MouseEvent } from "react";
import Box from "@mui/material/Box";
import Popover from "@mui/material/Popover";

/**
 * A long string in a dense table cell: shows a truncated preview; click opens a
 * popover with the full text (monospace, wrapped). Short strings render inline.
 */
export function TextPeek({ value, maxChars = 36 }: { value: unknown; maxChars?: number }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  if (value == null || value === "") return <>{"—"}</>;
  const s = String(value);
  if (s.length <= maxChars) return <>{s}</>;

  const open = (e: MouseEvent<HTMLElement>) => {
    e.stopPropagation();
    setAnchor(e.currentTarget);
  };
  return (
    <>
      <Box
        component="span"
        onClick={open}
        sx={{
          cursor: "pointer",
          textDecoration: "underline dotted",
          textUnderlineOffset: 2,
          whiteSpace: "nowrap",
        }}
      >
        {s.slice(0, maxChars)}…
      </Box>
      <Popover
        open={!!anchor}
        anchorEl={anchor}
        onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        slotProps={{ paper: { sx: { p: 1.25, maxWidth: 480 } } }}
      >
        <Box
          sx={{
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            fontSize: 12,
            lineHeight: 1.5,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {s}
        </Box>
      </Popover>
    </>
  );
}
