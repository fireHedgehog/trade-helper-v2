import { useCallback, useEffect, useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { ApiError } from "@/shared/api/client";

import { macroApi } from "./api";
import { CategoryGrid } from "./components/CategoryGrid";
import { CompositeReadout } from "./components/CompositeReadout";
import { RegimePanel } from "./components/RegimePanel";
import type { MacroOverview } from "./types";

export function MacroPage() {
  const [data, setData] = useState<MacroOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await macroApi.overview());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load macro overview");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const hasData = data && data.categories.some((c) => c.series.some((s) => s.point_count > 0));

  return (
    <div>
      <Typography variant="h5" gutterBottom>
        Macro
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Current macro-financial regime, in plain terms — not a forecast, not a trade signal. Reads
        the FRED series fetched on{" "}
        <Link component={RouterLink} to="/data-management">
          Data management
        </Link>
        {data?.as_of ? ` · as of ${data.as_of}` : ""}.
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}
      {!data && !error && <CircularProgress size={24} />}

      {data && !hasData && (
        <Alert severity="info" sx={{ mb: 2 }}>
          No observations yet — run <strong>Fetch macro data</strong> on the Data management page.
        </Alert>
      )}

      {data && (
        <>
          <Stack spacing={2} sx={{ mb: 3 }}>
            <RegimePanel naiveScore={data.composite.score} />
            <CompositeReadout composite={data.composite} factors={data.factors} />
          </Stack>

          <Box>
            {data.categories.map((c) => (
              <CategoryGrid key={c.key} category={c} />
            ))}
          </Box>
        </>
      )}
    </div>
  );
}
