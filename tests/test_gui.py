from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chatmesh.config import Config  # noqa: E402
from chatmesh.gui import build_app  # noqa: E402


def _cfg() -> Config:
    return Config(
        broker_url="nats://127.0.0.1:4222",
        agent_name="alice",
        sidecar_path=Path("."),
        log_path=Path("."),
    )


def test_index_serves_html():
    app = build_app(_cfg())
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # agent_name interpolated into the page
    assert "alice" in r.text


def test_index_has_csp_headers():
    app = build_app(_cfg())
    client = TestClient(app)
    r = client.get("/")
    assert "Content-Security-Policy" in r.headers
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]


def test_history_empty_at_start():
    app = build_app(_cfg())
    client = TestClient(app)
    r = client.get("/history")
    assert r.status_code == 200
    assert r.json() == []


def test_send_requires_bearer_when_token_set():
    app = build_app(_cfg(), auth_token="s3cret")
    client = TestClient(app)
    r = client.post("/send", json={"to": "bob", "body": "hi"})
    assert r.status_code == 401


def test_send_reports_broker_disconnected_when_no_broker():
    app = build_app(_cfg())
    client = TestClient(app)
    r = client.post("/send", json={"to": "bob", "body": "hi"})
    assert r.status_code == 200
    assert r.json() == {"ok": False, "error": "broker not connected"}


def test_manifest_serves():
    app = build_app(_cfg())
    client = TestClient(app)
    r = client.get("/manifest.webmanifest")
    assert r.status_code == 200
    assert r.json()["name"] == "chatmesh"
