import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import type { MacroCategory } from "../types";
import { MacroCard } from "./MacroCard";

export function CategoryGrid({ category }: { category: MacroCategory }) {
  return (
    <Box sx={{ mb: 3 }}>
      <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 700 }}>
        {category.label}
        <Typography component="span" variant="caption" color="text.secondary">
          {" "}
          · {category.series.length}
        </Typography>
      </Typography>
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))",
          gap: 1.5,
        }}
      >
        {category.series.map((s) => (
          <MacroCard key={s.series_id} data={s} />
        ))}
      </Box>
    </Box>
  );
}
