"""Resolve a provider's secret field values (keychain → env fallback).

Thin wrapper over the provider registry + secret store so fetch clients do
not each reimplement the lookup. Raises if a required field is missing.
"""

from __future__ import annotations

from app.providers.base import get_provider
from app.secrets import store


class MissingCredential(RuntimeError):
    pass


def resolve_provider_secrets(provider_key: str) -> dict[str, str]:
    spec = get_provider(provider_key)
    if spec is None:
        raise MissingCredential(f"Unknown provider '{provider_key}'")

    out: dict[str, str] = {}
    missing: list[str] = []
    for field in spec.fields:
        value = store.get_secret(spec.credential_name, field.name, field.env_var)
        if value:
            out[field.name] = value
        else:
            missing.append(field.label)

    if missing:
        raise MissingCredential(
            f"{spec.label} credential is not configured (missing: {', '.join(missing)}). "
            "Set it on the Credentials page."
        )
    return out
