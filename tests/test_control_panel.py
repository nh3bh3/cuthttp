"""Tests for the administrative control panel API."""

from __future__ import annotations

import textwrap

import pytest

pytest.importorskip("httpx", reason="httpx is required for TestClient")

from fastapi.testclient import TestClient

from app.auth import create_basic_auth_header
from app.main import create_app


@pytest.fixture()
def admin_client(tmp_path):
    """Create a FastAPI test client with a temporary configuration."""

    share_dir = tmp_path / "shares" / "public"
    share_dir.mkdir(parents=True)

    config = textwrap.dedent(
        f"""
        server:
          addr: "0.0.0.0"
          port: 18080
          tls:
            enabled: false
            certfile: ""
            keyfile: ""
        shares:
          - name: "public"
            path: "{share_dir.as_posix()}"
        users:
          - name: "admin"
            pass: "admin123"
            pass_bcrypt: false
        rules:
          - who: "admin"
            allow: ["R", "W", "D"]
            roots: ["public"]
            paths: ["/"]
            ip_allow: ["*"]
            ip_deny: []
        logging:
          json: false
          file: ""
          level: "INFO"
          max_size_mb: 10
          backup_count: 1
        rateLimit:
          rps: 50
          burst: 100
          maxConcurrent: 10
        ipFilter:
          allow:
            - "*"
          deny: []
        ui:
          brand: "Test"
          title: "Test Panel"
          language: "en"
        dav:
          enabled: false
          mountPath: "/webdav"
          lockManager: false
          propertyManager: false
        hotReload:
          enabled: false
          watchConfig: false
          debounceMs: 1000
        """
    )

    config_path = tmp_path / "config.yaml"
    config_path.write_text(config, encoding="utf-8")

    app = create_app(str(config_path))
    with TestClient(app) as client:
        yield client


def test_admin_status_requires_auth(admin_client):
    """The control panel endpoint should reject anonymous access."""

    response = admin_client.get("/api/admin/status")
    assert response.status_code == 401


def test_admin_status_returns_server_snapshot(admin_client):
    """Authenticated requests receive a comprehensive status payload."""

    headers = {"Authorization": create_basic_auth_header("admin", "admin123")}
    response = admin_client.get("/api/admin/status", headers=headers)
    assert response.status_code == 200

    payload = response.json()
    assert payload["code"] == 0

    data = payload["data"]
    assert data["server"]["port"] == 18080
    assert data["server"]["scheme"] == "http"
    assert data["server"]["custom_urls"] == []
    assert data["ip_filter"]["lan_allowed"] is True
    assert any(url.startswith("http://") for url in data["server"]["lan_urls"])
    assert data["shares"][0]["name"] == "public"
