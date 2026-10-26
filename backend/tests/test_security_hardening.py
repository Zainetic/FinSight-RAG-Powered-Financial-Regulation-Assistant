"""
FinSight RegTech - Security Hardening Test Suite
=================================================
Tests:
1. JWT Secret Enforcement: The app refuses to start and raises RuntimeError if JWT_SECRET_KEY is unset.
2. CORS Exact Origin Enforcement: Arbitrary Vercel subdomains (https://*.vercel.app) are rejected,
   and only exact configured origins from FRONTEND_ORIGINS (or defaults) are permitted.
"""

import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


def test_jwt_secret_key_refuses_to_start_when_unset(monkeypatch):
    """Verifies that removing JWT_SECRET_KEY causes get_jwt_secret_key() to raise RuntimeError."""
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    from src.core.auth import get_jwt_secret_key

    with pytest.raises(RuntimeError) as exc_info:
        get_jwt_secret_key()

    assert "Critical Security Error: JWT_SECRET_KEY environment variable is not set" in str(exc_info.value)
    assert "insecure" in str(exc_info.value) or "refuses to start" in str(exc_info.value)


def test_jwt_secret_key_returns_value_when_set(monkeypatch):
    """Verifies that get_jwt_secret_key() returns the configured key when present."""
    test_key = "super-secure-test-signing-key-minimum-32-chars-long"
    monkeypatch.setenv("JWT_SECRET_KEY", test_key)

    from src.core.auth import get_jwt_secret_key

    assert get_jwt_secret_key() == test_key


def test_cors_allows_exact_configured_frontend_origins():
    """Verifies that exact configured frontend origins are allowed with credentials."""
    from src.api.main import app

    client = TestClient(app)

    # 1. Localhost frontend
    res_local = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res_local.status_code == 200
    assert res_local.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert res_local.headers.get("access-control-allow-credentials") == "true"

    # 2. Production Vercel domain
    res_prod = client.options(
        "/health",
        headers={
            "Origin": "https://finsight-phi-ten.vercel.app",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res_prod.status_code == 200
    assert res_prod.headers.get("access-control-allow-origin") == "https://finsight-phi-ten.vercel.app"
    assert res_prod.headers.get("access-control-allow-credentials") == "true"


def test_cors_rejects_arbitrary_unauthorized_vercel_subdomains():
    """Verifies that wildcard Vercel subdomains (e.g. https://attacker.vercel.app) are blocked."""
    from src.api.main import app

    client = TestClient(app)

    malicious_origins = [
        "https://malicious-phishing-app.vercel.app",
        "https://evil-hacker.vercel.app",
        "https://random-tenant.vercel.app",
        "http://attacker.com",
    ]

    for evil_origin in malicious_origins:
        res = client.options(
            "/health",
            headers={
                "Origin": evil_origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        # CORS middleware does not return Access-Control-Allow-Origin for unauthorized origins
        assert res.headers.get("access-control-allow-origin") != evil_origin
