"""Secret storage and resolution.

The raw secret value is never written to the database. It is stored in the OS
keychain (via ``keyring``) and read back from there at runtime, with an
environment variable as a read-only fallback.

Each provider field is stored under its own keychain entry:
    service = "trade-helper"
    username = "<credential_name>/<field_name>"   e.g. "trade-helper/alpaca/api_secret_key"
"""

from __future__ import annotations

import logging
import os

import keyring
from keyring.errors import KeyringError

logger = logging.getLogger(__name__)

_SERVICE = "trade-helper"


class SecretBackendError(RuntimeError):
    """The OS keychain could not be reached for a write."""


def _entry_name(credential_name: str, field_name: str) -> str:
    return f"{credential_name}/{field_name}"


def set_secret(credential_name: str, field_name: str, value: str) -> None:
    """Write (or rotate) one secret field into the OS keychain."""
    try:
        keyring.set_password(_SERVICE, _entry_name(credential_name, field_name), value)
    except KeyringError as exc:  # pragma: no cover - environment dependent
        raise SecretBackendError(
            "Could not store the secret in the OS keychain. "
            "Ensure a keyring backend is available."
        ) from exc


def delete_secret(credential_name: str, field_name: str) -> None:
    """Remove one secret field. Missing entries are ignored."""
    try:
        keyring.delete_password(_SERVICE, _entry_name(credential_name, field_name))
    except KeyringError:
        # Nothing there, or backend refused a delete of a missing key — fine.
        logger.debug("No keychain entry to delete for %s/%s", credential_name, field_name)


def get_secret(
    credential_name: str,
    field_name: str,
    env_var: str | None = None,
) -> str | None:
    """Resolve one secret field: keychain first, then the env var fallback."""
    try:
        value = keyring.get_password(_SERVICE, _entry_name(credential_name, field_name))
    except KeyringError:  # pragma: no cover - environment dependent
        value = None
    if value:
        return value
    if env_var:
        return os.environ.get(env_var) or None
    return None
