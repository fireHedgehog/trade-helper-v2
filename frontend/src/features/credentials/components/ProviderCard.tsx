import { useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { ApiError } from "@/shared/api/client";
import { StatusPill } from "@/shared/components/StatusPill";

import { credentialsApi } from "../api";
import type { CredentialStatus, VerificationStatus } from "../types";

interface ProviderCardProps {
  status: CredentialStatus;
  onChanged: (next: CredentialStatus) => void;
}

const VERIFY_TONE: Record<VerificationStatus, "neutral" | "ok" | "warn" | "bad"> = {
  unverified: "warn",
  healthy: "ok",
  invalid: "bad",
};

function formatTimestamp(iso: string | null): string {
  if (!iso) return "never";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

type Feedback = { severity: "success" | "error"; text: string } | null;

function errorText(err: unknown): string {
  if (err instanceof ApiError || err instanceof Error) return err.message;
  return "Unexpected error";
}

export function ProviderCard({ status, onChanged }: ProviderCardProps) {
  const emptyForm = useMemo(
    () => Object.fromEntries(status.fields.map((f) => [f.name, ""])) as Record<string, string>,
    [status.fields],
  );
  const [form, setForm] = useState<Record<string, string>>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);

  const hasInput = Object.values(form).some((v) => v.trim() !== "");

  async function handleSave() {
    setSaving(true);
    setFeedback(null);
    try {
      const values = Object.fromEntries(
        Object.entries(form).filter(([, v]) => v.trim() !== ""),
      );
      const next = await credentialsApi.set(status.provider_key, values);
      onChanged(next);
      setForm(emptyForm);
      setFeedback({ severity: "success", text: "Saved. Run Test to verify it works." });
    } catch (err) {
      setFeedback({ severity: "error", text: errorText(err) });
    } finally {
      setSaving(false);
    }
  }

  async function handleVerify() {
    setVerifying(true);
    setFeedback(null);
    try {
      const result = await credentialsApi.verify(status.provider_key);
      onChanged({ ...status, ...result });
      setFeedback(
        result.verification_status === "healthy"
          ? {
              severity: "success",
              text: `Verified OK (${result.last_verification_detail ?? "healthy"}).`,
            }
          : {
              severity: "error",
              text: `Verification failed (${result.last_verification_detail ?? "invalid"}).`,
            },
      );
    } catch (err) {
      setFeedback({ severity: "error", text: errorText(err) });
    } finally {
      setVerifying(false);
    }
  }

  async function handleClear() {
    setFeedback(null);
    try {
      const next = await credentialsApi.clear(status.provider_key);
      onChanged(next);
      setForm(emptyForm);
      setFeedback({ severity: "success", text: "Stored credential cleared." });
    } catch (err) {
      setFeedback({ severity: "error", text: errorText(err) });
    }
  }

  return (
    <Card sx={{ mb: 2 }}>
      <CardContent>
        <Stack direction="row" spacing={1} sx={{ mb: 1, alignItems: "center" }}>
          <Typography variant="h6">{status.label}</Typography>
          <StatusPill tone={status.configured ? "ok" : "neutral"}>
            {status.configured ? "Configured" : "Not configured"}
          </StatusPill>
          <StatusPill tone={VERIFY_TONE[status.verification_status]}>
            {status.verification_status}
          </StatusPill>
        </Stack>

        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {status.description}
        </Typography>

        <Stack spacing={2}>
          {status.fields.map((field) => (
            <TextField
              key={field.name}
              type="password"
              size="small"
              fullWidth
              label={field.label}
              placeholder={field.placeholder || "Enter to set or rotate"}
              autoComplete="off"
              value={form[field.name] ?? ""}
              onChange={(e) =>
                setForm((prev) => ({ ...prev, [field.name]: e.target.value }))
              }
            />
          ))}
        </Stack>

        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
          Write-only: values are sent once to the OS keychain and never read back into this
          page. Leave a field blank to keep its current value.
        </Typography>

        <Stack direction="row" spacing={1} useFlexGap sx={{ mt: 2, flexWrap: "wrap" }}>
          <Button
            variant="contained"
            onClick={handleSave}
            disabled={saving || !hasInput}
          >
            {saving ? "Saving…" : "Save"}
          </Button>
          <Button
            variant="outlined"
            onClick={handleVerify}
            disabled={verifying || !status.configured}
          >
            {verifying ? "Testing…" : "Test"}
          </Button>
          {status.configured && (
            <Button color="inherit" onClick={handleClear} disabled={saving || verifying}>
              Clear
            </Button>
          )}
        </Stack>

        {feedback && (
          <Alert severity={feedback.severity} sx={{ mt: 2 }} onClose={() => setFeedback(null)}>
            {feedback.text}
          </Alert>
        )}

        <Box sx={{ mt: 1.5 }}>
          <Typography variant="caption" color="text.secondary">
            Last verified: {formatTimestamp(status.last_verified_at)}
            {status.last_verification_detail ? ` — ${status.last_verification_detail}` : ""}
            {" · Env fallback: "}
            <code>{status.environment_variable}</code>
          </Typography>
        </Box>
      </CardContent>
    </Card>
  );
}
