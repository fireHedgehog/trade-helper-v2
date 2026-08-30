import { api } from "@/shared/api/client";

import type { CredentialStatus, VerifyResponse } from "./types";

export const credentialsApi = {
  list: () => api.get<CredentialStatus[]>("/credentials"),

  // Write-only. `values` maps field name -> raw secret. Only non-empty
  // fields are sent; the response carries metadata only, never a secret.
  set: (providerKey: string, values: Record<string, string>) =>
    api.put<CredentialStatus>(`/credentials/${providerKey}`, { values }),

  clear: (providerKey: string) =>
    api.del<CredentialStatus>(`/credentials/${providerKey}`),

  verify: (providerKey: string) =>
    api.post<VerifyResponse>(`/credentials/${providerKey}/verify`),
};
