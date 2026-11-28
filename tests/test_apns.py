"""APNs sender: auth, the request Apple expects, and what each response does.

A dead token is deleted; a provider-side (key/topic) error must never delete
tokens, or one bad secret would wipe every user's phones. Device tokens never
reach logs, since they are delivery addresses.
"""

from __future__ import annotations

import base64
import json
import logging
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from pnw_campsites.monitor import apns
from pnw_campsites.monitor.apns import ApnsConfig, ApnsSender

TOKEN = "a1" * 32


@pytest.fixture(autouse=True)
def _fresh_jwt_cache():
    apns.reset_jwt_cache()
    yield
    apns.reset_jwt_cache()


@pytest.fixture
def key_pem() -> bytes:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


@pytest.fixture
def config(key_pem) -> ApnsConfig:
    return ApnsConfig.from_env({
        "APNS_KEY_P8_B64": base64.b64encode(key_pem).decode(),
        "APNS_KEY_ID": "KEYID12345",
        "APNS_TEAM_ID": "TEAMID1234",
    })


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _err(status: int, reason: str) -> httpx.Response:
    return httpx.Response(status, json={"reason": reason})


PAYLOAD = {"aps": {"alert": {"title": "t", "body": "b"}}}


class TestConfig:
    def test_missing_settings_mean_not_configured(self):
        assert ApnsConfig.from_env({}) is None
        assert ApnsConfig.from_env({"APNS_KEY_ID": "K"}) is None

    def test_production_is_the_default_host(self, config):
        assert config.host == "https://api.push.apple.com"
        assert config.topic == "co.campable.app"

    def test_sandbox_host(self, key_pem):
        cfg = ApnsConfig.from_env({
            "APNS_KEY_P8_B64": base64.b64encode(key_pem).decode(),
            "APNS_KEY_ID": "K", "APNS_TEAM_ID": "T", "APNS_ENVIRONMENT": "sandbox",
        })
        assert cfg.host == "https://api.sandbox.push.apple.com"

    def test_bad_key_raises_without_echoing_it(self):
        secret = base64.b64encode(b"-----BEGIN PRIVATE KEY-----\nnotakey\n").decode()
        with pytest.raises(ValueError) as exc:
            ApnsConfig.from_env({
                "APNS_KEY_P8_B64": secret, "APNS_KEY_ID": "K", "APNS_TEAM_ID": "T",
            })
        assert "APNS_KEY_P8_B64" in str(exc.value)
        assert secret not in str(exc.value)
        assert "notakey" not in str(exc.value)


class TestRequest:
    async def test_sends_what_apple_expects(self, config, key_pem):
        seen: list[httpx.Request] = []

        def handler(req):
            seen.append(req)
            return httpx.Response(200)

        async with _client(handler) as client:
            status = await ApnsSender(config, client).send(
                TOKEN, PAYLOAD, collapse_id="release-7", expires_in=1800,
            )
        assert status == "sent"
        req = seen[0]
        assert str(req.url) == f"https://api.push.apple.com/3/device/{TOKEN}"
        assert req.method == "POST"
        assert req.headers["apns-topic"] == "co.campable.app"
        assert req.headers["apns-push-type"] == "alert"
        assert req.headers["apns-priority"] == "10"
        assert req.headers["apns-collapse-id"] == "release-7"
        assert abs(int(req.headers["apns-expiration"]) - (time.time() + 1800)) < 5
        assert json.loads(req.content) == PAYLOAD

        scheme, token = req.headers["authorization"].split(" ")
        assert scheme == "bearer"
        assert jwt.get_unverified_header(token) == {
            "alg": "ES256", "kid": "KEYID12345", "typ": "JWT",
        }
        public = serialization.load_pem_private_key(key_pem, None).public_key()
        claims = jwt.decode(token, public, algorithms=["ES256"])
        assert claims["iss"] == "TEAMID1234"
        assert abs(claims["iat"] - time.time()) < 5

    async def test_no_collapse_header_when_not_given(self, config):
        seen = []

        async with _client(lambda r: seen.append(r) or httpx.Response(200)) as c:
            await ApnsSender(config, c).send(TOKEN, PAYLOAD)
        assert "apns-collapse-id" not in seen[0].headers

    async def test_jwt_is_reused_across_senders(self, config):
        auths = []

        def handler(req):
            auths.append(req.headers["authorization"])
            return httpx.Response(200)

        async with _client(handler) as c:
            await ApnsSender(config, c).send(TOKEN, PAYLOAD)
        async with _client(handler) as c:
            await ApnsSender(config, c).send(TOKEN, PAYLOAD)
        assert auths[0] == auths[1]


class TestResponses:
    @pytest.mark.parametrize("status,reason", [
        (410, "Unregistered"), (410, "ExpiredToken"), (400, "BadDeviceToken"),
        # Apple: "The device token doesn't match the specified topic" — a
        # token from another app or build. Our topic is a constant.
        (400, "DeviceTokenNotForTopic"),
    ])
    async def test_dead_tokens(self, config, status, reason):
        async with _client(lambda r: _err(status, reason)) as c:
            assert await ApnsSender(config, c).send(TOKEN, PAYLOAD) == "dead"

    @pytest.mark.parametrize("reason", [
        "InvalidProviderToken", "BadTopic", "TopicDisallowed", "Forbidden",
        "UnrelatedKeyIdInToken", "BadEnvironmentKeyIdInToken",
    ])
    async def test_provider_errors_disable_the_sender_and_keep_tokens(
        self, config, reason,
    ):
        calls = []

        def handler(req):
            calls.append(req)
            return _err(400 if reason in ("BadTopic", "TopicDisallowed") else 403, reason)

        async with _client(handler) as c:
            sender = ApnsSender(config, c)
            assert await sender.send(TOKEN, PAYLOAD) == "failed"
            assert await sender.send("b2" * 32, PAYLOAD) == "failed"
        assert len(calls) == 1, "a broken key must stop the cycle's sends"

    async def test_expired_provider_token_refreshes_once(self, config, monkeypatch):
        auths = []

        def handler(req):
            auths.append(req.headers["authorization"])
            if len(auths) == 1:
                return _err(403, "ExpiredProviderToken")
            return httpx.Response(200)

        # The cached token is old enough (>20 min) that Apple allows a refresh.
        clock = [time.time()]
        monkeypatch.setattr(apns, "_now", lambda: clock[0])
        async with _client(handler) as c:
            sender = ApnsSender(config, c)
            sender._jwt()  # mint
            clock[0] += 25 * 60
            assert await sender.send(TOKEN, PAYLOAD) == "sent"
        assert len(auths) == 2
        assert auths[0] != auths[1]

    async def test_jwt_refreshes_after_fifty_minutes(self, config, monkeypatch):
        clock = [time.time()]
        monkeypatch.setattr(apns, "_now", lambda: clock[0])
        sender = ApnsSender(config, None)
        first = sender._jwt()
        clock[0] += 49 * 60
        assert sender._jwt() == first
        clock[0] += 2 * 60
        assert sender._jwt() != first

    @pytest.mark.parametrize("response", [
        _err(429, "TooManyRequests"), _err(503, "ServiceUnavailable"),
        _err(500, "InternalServerError"),
    ])
    async def test_transient_errors_retry_once(self, config, response, monkeypatch):
        monkeypatch.setattr(apns, "_RETRY_DELAY", 0)
        calls = []

        def handler(req):
            calls.append(req)
            return response if len(calls) == 1 else httpx.Response(200)

        async with _client(handler) as c:
            assert await ApnsSender(config, c).send(TOKEN, PAYLOAD) == "sent"
        assert len(calls) == 2

    async def test_transient_errors_give_up_after_one_retry(self, config, monkeypatch):
        monkeypatch.setattr(apns, "_RETRY_DELAY", 0)
        calls = []

        def handler(req):
            calls.append(req)
            raise httpx.ConnectError("boom", request=req)

        async with _client(handler) as c:
            assert await ApnsSender(config, c).send(TOKEN, PAYLOAD) == "failed"
        assert len(calls) == 2

    async def test_unknown_4xx_fails_without_deleting(self, config):
        async with _client(lambda r: _err(400, "PayloadTooLarge")) as c:
            assert await ApnsSender(config, c).send(TOKEN, PAYLOAD) == "failed"


class TestLogging:
    async def test_token_never_logged(self, config, caplog, monkeypatch):
        """With the API's logging config, nothing on the send path logs a token
        (httpx logs every request URL at INFO)."""
        from pnw_campsites import api  # noqa: F401  (configures logging)

        monkeypatch.setattr(apns, "_RETRY_DELAY", 0)
        caplog.set_level(logging.INFO)

        def handler(req):
            raise httpx.ConnectError(f"failed {req.url}", request=req)

        async with _client(handler) as c:
            await ApnsSender(config, c).send(TOKEN, PAYLOAD)
        async with _client(lambda r: _err(410, "Unregistered")) as c:
            await ApnsSender(config, c).send(TOKEN, PAYLOAD)
        assert caplog.records, "failures should be logged"
        assert TOKEN not in caplog.text

    def test_httpx_request_logging_is_quiet_in_the_api(self):
        from pnw_campsites import api  # noqa: F401  (configures logging)

        assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
        assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING


class TestDoctorCheck:
    """Doctor checks the key locally and never calls APNs: each doctor run is
    a new process, and minting a JWT per run could trip Apple's
    TooManyProviderTokenUpdates for the server's sends."""

    async def test_ok_when_the_key_signs(self, monkeypatch, key_pem):
        from pnw_campsites.health import _check_apns

        monkeypatch.setenv("APNS_KEY_P8_B64", base64.b64encode(key_pem).decode())
        monkeypatch.setenv("APNS_KEY_ID", "KEYID12345")
        monkeypatch.setenv("APNS_TEAM_ID", "TEAMID1234")
        detail = await _check_apns()
        assert "production" in detail

    async def test_bad_key_fails_without_its_contents(self, monkeypatch):
        from pnw_campsites.health import _check_apns

        monkeypatch.setenv("APNS_KEY_P8_B64", "bm90IGEga2V5")
        monkeypatch.setenv("APNS_KEY_ID", "K")
        monkeypatch.setenv("APNS_TEAM_ID", "T")
        with pytest.raises(ValueError) as exc:
            await _check_apns()
        assert "bm90IGEga2V5" not in str(exc.value)

    def test_listed_as_skip_when_unconfigured(self):
        from pnw_campsites.health import CHECKS

        check = next(c for c in CHECKS if c.name == "APNs")
        assert set(check.requires) == {"APNS_KEY_P8_B64", "APNS_KEY_ID", "APNS_TEAM_ID"}
