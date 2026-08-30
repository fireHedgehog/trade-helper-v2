import { useCallback, useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";

import { ApiError } from "@/shared/api/client";

import { credentialsApi } from "./api";
import { ProviderCard } from "./components/ProviderCard";
import type { CredentialStatus } from "./types";

export function CredentialsPage() {
  const [items, setItems] = useState<CredentialStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setItems(await credentialsApi.list());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load credentials");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleChanged = useCallback((next: CredentialStatus) => {
    setItems((prev) =>
      prev ? prev.map((it) => (it.provider_key === next.provider_key ? next : it)) : prev,
    );
  }, []);

  return (
    <div>
      <Typography variant="h5" gutterBottom>
        Credentials
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Store and rotate provider API credentials. Each credential is written straight to the
        OS keychain — it is never saved in the database, never returned by the API, never
        logged. Use <strong>Test</strong> to confirm a key actually works.
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}
      {!items && !error && <CircularProgress size={24} />}

      {items?.map((status) => (
        <ProviderCard key={status.provider_key} status={status} onChanged={handleChanged} />
      ))}
    </div>
  );
}
