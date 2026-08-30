export type VerificationStatus = "unverified" | "healthy" | "invalid";

export interface CredentialFieldInfo {
  name: string;
  label: string;
  placeholder: string;
  secret: boolean;
}

export interface CredentialStatus {
  provider_key: string;
  label: string;
  description: string;
  credential_name: string;
  environment_variable: string;
  fields: CredentialFieldInfo[];
  configured: boolean;
  verification_status: VerificationStatus;
  last_verified_at: string | null;
  last_verification_detail: string | null;
}

export interface VerifyResponse {
  provider_key: string;
  verification_status: VerificationStatus;
  last_verified_at: string | null;
  last_verification_detail: string | null;
}
