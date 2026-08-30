"""Request/response models for the Credentials API.

No response model here ever carries a secret value — by design.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FieldInfo(BaseModel):
    name: str
    label: str
    placeholder: str = ""
    # Every field is a secret today; kept explicit for the frontend.
    secret: bool = True


class CredentialStatus(BaseModel):
    provider_key: str
    label: str
    description: str
    credential_name: str
    environment_variable: str
    fields: list[FieldInfo]
    configured: bool
    verification_status: str  # "unverified" | "healthy" | "invalid"
    last_verified_at: str | None = None
    last_verification_detail: str | None = None


class SetCredentialRequest(BaseModel):
    # field name -> raw secret value. Only non-empty values are written; a
    # provider with multiple fields can be rotated one field at a time.
    values: dict[str, str] = Field(default_factory=dict)


class VerifyResponse(BaseModel):
    provider_key: str
    verification_status: str
    last_verified_at: str | None = None
    last_verification_detail: str | None = None
