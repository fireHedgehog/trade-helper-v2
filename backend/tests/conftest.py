"""Test fixtures: a throwaway SQLite file and an in-memory secret backend."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.sqlite3"))
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:5173"]')

    # Reload settings + config-dependent modules so the env vars take effect.
    from app.core import config

    config.get_settings.cache_clear()

    # Swap the OS keychain for a process-local dict.
    from app.secrets import store

    fake: dict[tuple[str, str], str] = {}

    class FakeKeyring:
        @staticmethod
        def set_password(service, username, value):
            fake[(service, username)] = value

        @staticmethod
        def get_password(service, username):
            return fake.get((service, username))

        @staticmethod
        def delete_password(service, username):
            fake.pop((service, username), None)

    monkeypatch.setattr(store, "keyring", FakeKeyring)

    import app.main as main

    importlib.reload(main)

    from fastapi.testclient import TestClient

    with TestClient(main.app) as c:
        yield c

    config.get_settings.cache_clear()
