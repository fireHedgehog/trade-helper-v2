"""End-to-end tests for the Credentials feature against a temp database."""

from __future__ import annotations

import pytest


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_list_seeds_providers_unconfigured(client):
    body = client.get("/api/credentials").json()
    by_key = {row["provider_key"]: row for row in body}

    assert set(by_key) == {"fred", "alpaca", "openai"}
    assert by_key["fred"]["configured"] is False
    assert by_key["fred"]["verification_status"] == "unverified"
    assert [f["name"] for f in by_key["fred"]["fields"]] == ["api_key"]
    assert [f["name"] for f in by_key["openai"]["fields"]] == ["api_key"]
    assert [f["name"] for f in by_key["alpaca"]["fields"]] == [
        "api_key_id",
        "api_secret_key",
    ]
    # No secret material anywhere in the payload.
    assert "value" not in by_key["fred"]["fields"][0]


def test_set_fred_marks_configured_and_resets_verification(client):
    resp = client.put("/api/credentials/fred", json={"values": {"api_key": "abc123"}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is True
    assert data["verification_status"] == "unverified"


def test_set_alpaca_requires_both_fields_for_configured(client):
    # Only the key id -> not fully configured yet.
    client.put("/api/credentials/alpaca", json={"values": {"api_key_id": "PKONLY"}})
    assert client.get("/api/credentials/alpaca").json()["configured"] is False

    # Add the secret -> configured.
    client.put(
        "/api/credentials/alpaca",
        json={"values": {"api_secret_key": "shh"}},
    )
    assert client.get("/api/credentials/alpaca").json()["configured"] is True


def test_set_rejects_unknown_field(client):
    resp = client.put("/api/credentials/fred", json={"values": {"nope": "x"}})
    assert resp.status_code == 400


def test_set_rejects_unknown_provider(client):
    resp = client.put("/api/credentials/bogus", json={"values": {"k": "v"}})
    assert resp.status_code == 404


def test_clear_credential(client):
    client.put("/api/credentials/fred", json={"values": {"api_key": "abc123"}})
    resp = client.delete("/api/credentials/fred")
    assert resp.status_code == 200
    assert resp.json()["configured"] is False


def test_verify_without_credential_is_rejected(client):
    resp = client.post("/api/credentials/fred/verify")
    assert resp.status_code == 400


def test_verify_records_status(client, monkeypatch):
    client.put("/api/credentials/fred", json={"values": {"api_key": "abc123"}})

    async def fake_verify(values, spec):
        assert values["api_key"] == "abc123"
        return "healthy", "HTTP 200"

    from app.providers.base import get_provider

    monkeypatch.setattr(get_provider("fred"), "verifier", fake_verify)

    resp = client.post("/api/credentials/fred/verify")
    assert resp.status_code == 200
    data = resp.json()
    assert data["verification_status"] == "healthy"
    assert data["last_verification_detail"] == "HTTP 200"
    assert data["last_verified_at"] is not None


@pytest.mark.parametrize("provider", ["fred", "alpaca", "openai"])
def test_get_single_provider(client, provider):
    assert client.get(f"/api/credentials/{provider}").json()["provider_key"] == provider
