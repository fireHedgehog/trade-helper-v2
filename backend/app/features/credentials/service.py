"""Credentials business logic: read status, store/rotate secrets, verify."""

from __future__ import annotations

import sqlite3

from app.features.credentials import repository as repo
from app.features.credentials.schemas import CredentialStatus, FieldInfo, VerifyResponse
from app.providers.base import ProviderSpec, all_providers, get_provider
from app.secrets import store


class CredentialError(Exception):
    """Domain error -> mapped to an HTTP 4xx by the router."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def _to_status(row: sqlite3.Row, spec: ProviderSpec) -> CredentialStatus:
    return CredentialStatus(
        provider_key=spec.key,
        label=spec.label,
        description=spec.description,
        credential_name=row["credential_name"],
        environment_variable=row["environment_variable"],
        fields=[
            FieldInfo(name=f.name, label=f.label, placeholder=f.placeholder, secret=True)
            for f in spec.fields
        ],
        configured=bool(row["configured"]),
        verification_status=row["verification_status"],
        last_verified_at=row["last_verified_at"],
        last_verification_detail=row["last_verification_detail"],
    )


def _require(provider_key: str) -> ProviderSpec:
    spec = get_provider(provider_key)
    if spec is None:
        raise CredentialError(f"Unknown provider '{provider_key}'", status_code=404)
    return spec


def list_statuses(conn: sqlite3.Connection) -> list[CredentialStatus]:
    rows = {row["provider_key"]: row for row in repo.list_all(conn)}
    out: list[CredentialStatus] = []
    for spec in all_providers():
        row = rows.get(spec.key)
        if row is None:
            # Registry has a provider with no seed row yet — skip rather than
            # invent one; the fix is a schema migration seed.
            continue
        out.append(_to_status(row, spec))
    return out


def get_status(conn: sqlite3.Connection, provider_key: str) -> CredentialStatus:
    spec = _require(provider_key)
    row = repo.get(conn, provider_key)
    if row is None:
        raise CredentialError(f"No credential row for '{provider_key}'", status_code=404)
    return _to_status(row, spec)


def set_credential(
    conn: sqlite3.Connection,
    provider_key: str,
    values: dict[str, str],
) -> CredentialStatus:
    spec = _require(provider_key)

    submitted = {k: v for k, v in values.items() if v and v.strip()}
    if not submitted:
        raise CredentialError("No non-empty values submitted")

    unknown = sorted(set(submitted) - set(spec.field_names()))
    if unknown:
        raise CredentialError(f"Unknown field(s) for {spec.label}: {', '.join(unknown)}")

    for field_name, raw in submitted.items():
        store.set_secret(spec.credential_name, field_name, raw.strip())

    # Consider the provider configured only once every field resolves to a
    # value (keychain or env fallback).
    if _all_fields_present(spec):
        repo.mark_configured(conn, provider_key)
    else:
        # Partial rotation of a multi-field provider — keep prior configured
        # state but reset verification so the user re-tests.
        repo.record_verification(conn, provider_key, "unverified", "credential updated")

    return get_status(conn, provider_key)


def clear_credential(conn: sqlite3.Connection, provider_key: str) -> CredentialStatus:
    spec = _require(provider_key)
    for f in spec.fields:
        store.delete_secret(spec.credential_name, f.name)
    repo.clear(conn, provider_key)
    return get_status(conn, provider_key)


async def verify_credential(
    conn: sqlite3.Connection,
    provider_key: str,
) -> VerifyResponse:
    spec = _require(provider_key)

    resolved = _resolve_all(spec)
    missing = [f.label for f in spec.fields if not resolved.get(f.name)]
    if missing:
        raise CredentialError(
            f"Cannot verify {spec.label}: missing {', '.join(missing)}"
        )

    status, detail = await spec.verifier(resolved, spec)
    repo.record_verification(conn, provider_key, status, detail)

    row = repo.get(conn, provider_key)
    return VerifyResponse(
        provider_key=provider_key,
        verification_status=row["verification_status"],
        last_verified_at=row["last_verified_at"],
        last_verification_detail=row["last_verification_detail"],
    )


def _resolve_all(spec: ProviderSpec) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in spec.fields:
        value = store.get_secret(spec.credential_name, f.name, f.env_var)
        if value:
            out[f.name] = value
    return out


def _all_fields_present(spec: ProviderSpec) -> bool:
    resolved = _resolve_all(spec)
    return all(f.name in resolved for f in spec.fields)
