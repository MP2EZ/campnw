"""Client IP extraction behind Cloudflare → Fly.

Production traffic reaches Fly through Cloudflare's proxy, so Fly-Client-IP is
a Cloudflare edge address shared by many users. CF-Connecting-IP holds the
real client, but anyone can send that header straight to campnw.fly.dev, so it
is trusted only when the connection to Fly came from a Cloudflare range.
"""

from unittest.mock import MagicMock

from pnw_campsites.routes.deps import get_client_ip


def _fake_request(headers: dict) -> MagicMock:
    req = MagicMock()
    req.headers = headers
    req.client.host = "127.0.0.1"
    return req


def test_cloudflare_edge_uses_cf_connecting_ip():
    req = _fake_request({"Fly-Client-IP": "172.68.10.4", "CF-Connecting-IP": "203.0.113.7"})
    assert get_client_ip(req) == "203.0.113.7"


def test_cloudflare_ipv6_edge_uses_cf_connecting_ip():
    req = _fake_request({"Fly-Client-IP": "2a06:98c0:3600::103", "CF-Connecting-IP": "203.0.113.7"})
    assert get_client_ip(req) == "203.0.113.7"


def test_direct_to_fly_ignores_spoofed_cf_connecting_ip():
    req = _fake_request({"Fly-Client-IP": "198.51.100.9", "CF-Connecting-IP": "203.0.113.7"})
    assert get_client_ip(req) == "198.51.100.9"


def test_cloudflare_edge_without_cf_header_uses_fly_ip():
    req = _fake_request({"Fly-Client-IP": "172.68.10.4"})
    assert get_client_ip(req) == "172.68.10.4"


def test_unparseable_fly_ip_is_returned_as_is():
    req = _fake_request({"Fly-Client-IP": "garbage", "CF-Connecting-IP": "203.0.113.7"})
    assert get_client_ip(req) == "garbage"


def test_x_forwarded_for_is_ignored():
    """The client writes the first X-Forwarded-For entry, so it can't key a limit."""
    req = _fake_request({"X-Forwarded-For": "5.6.7.8, 10.0.0.1"})
    assert get_client_ip(req) == "127.0.0.1"


def test_falls_back_to_client_host():
    req = _fake_request({})
    assert get_client_ip(req) == "127.0.0.1"
