"""Test IP extraction prefers Fly-Client-IP."""

from unittest.mock import MagicMock
from pnw_campsites.routes.deps import get_client_ip


def _fake_request(headers: dict) -> MagicMock:
    req = MagicMock()
    req.headers = headers
    req.client.host = "127.0.0.1"
    return req


def test_fly_client_ip_preferred():
    req = _fake_request({
        "Fly-Client-IP": "1.2.3.4",
        "X-Forwarded-For": "5.6.7.8, 10.0.0.1",
    })
    assert get_client_ip(req) == "1.2.3.4"


def test_falls_back_to_x_forwarded_for():
    req = _fake_request({"X-Forwarded-For": "5.6.7.8, 10.0.0.1"})
    assert get_client_ip(req) == "5.6.7.8"


def test_falls_back_to_client_host():
    req = _fake_request({})
    assert get_client_ip(req) == "127.0.0.1"
