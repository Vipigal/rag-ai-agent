import logging

import pytest
from fastapi.testclient import TestClient

from api import main


@pytest.fixture(autouse=True)
def no_keys(monkeypatch: pytest.MonkeyPatch):
    for name in ("OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_startup_fails_loudly_when_the_configuration_is_invalid(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.CRITICAL, logger="api.main")

    with pytest.raises(ValueError, match="OPENAI_API_KEY is not set"):
        with TestClient(main.app):
            pass

    [record] = caplog.records
    assert record.getMessage().startswith("startup failed: OPENAI_API_KEY is not set")


def test_startup_serves_when_the_configuration_validates(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(main, "validate_configuration", lambda: None)

    with TestClient(main.app) as client:
        assert client.get("/docs").status_code == 200
