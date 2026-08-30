"""HTTP routes for the Credentials page.

    GET    /api/credentials                      list provider status
    GET    /api/credentials/{provider_key}       one provider's status
    PUT    /api/credentials/{provider_key}       set / rotate secret(s)  (write-only)
    DELETE /api/credentials/{provider_key}       clear stored secret(s)
    POST   /api/credentials/{provider_key}/verify  test the stored secret(s)

No route returns a secret value.
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.db.connection import db_dependency
from app.features.credentials import service
from app.features.credentials.schemas import (
    CredentialStatus,
    SetCredentialRequest,
    VerifyResponse,
)

router = APIRouter(prefix="/api/credentials", tags=["credentials"])


def _handle(exc: service.CredentialError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("", response_model=list[CredentialStatus])
def list_credentials(conn: sqlite3.Connection = Depends(db_dependency)):
    return service.list_statuses(conn)


@router.get("/{provider_key}", response_model=CredentialStatus)
def get_credential(
    provider_key: str,
    conn: sqlite3.Connection = Depends(db_dependency),
):
    try:
        return service.get_status(conn, provider_key)
    except service.CredentialError as exc:
        raise _handle(exc)


@router.put("/{provider_key}", response_model=CredentialStatus)
def set_credential(
    provider_key: str,
    body: SetCredentialRequest,
    conn: sqlite3.Connection = Depends(db_dependency),
):
    try:
        return service.set_credential(conn, provider_key, body.values)
    except service.CredentialError as exc:
        raise _handle(exc)


@router.delete("/{provider_key}", response_model=CredentialStatus)
def clear_credential(
    provider_key: str,
    conn: sqlite3.Connection = Depends(db_dependency),
):
    try:
        return service.clear_credential(conn, provider_key)
    except service.CredentialError as exc:
        raise _handle(exc)


@router.post("/{provider_key}/verify", response_model=VerifyResponse)
async def verify_credential(
    provider_key: str,
    conn: sqlite3.Connection = Depends(db_dependency),
):
    try:
        return await service.verify_credential(conn, provider_key)
    except service.CredentialError as exc:
        raise _handle(exc)
