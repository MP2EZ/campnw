"""JWKS negative-cache behaviour (see .audit-report.md, PERF-01 auth).

`get_signing_key_from_jwt` refreshes the whole JWK set whenever it sees an
unrecognised `kid`, via a *synchronous* urllib fetch on the calling thread, and
PyJWT's internal lru_cache does not cache failures. A stream of tokens carrying
random `kid` headers therefore triggers a fresh blocking fetch every time and
can pin the single uvicorn worker.

The negative cache fixes that, but it has a dangerous failure mode that these
tests pin down: caching a `kid` after a *network* failure would turn a
transient Supabase blip into a permanent auth outage, because every user whose
key was minted after the last successful fetch would be rejected until the
process restarts. Only a genuine "the set was fetched and this kid isn't in it"
may be cached.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import jwt
import pytest
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError

from pnw_campsites import auth


def _token_with_kid(kid: str) -> str:
    return jwt.encode({"sub": "u1"}, "secret", headers={"kid": kid})


@pytest.fixture(autouse=True)
def _clear_state():
    auth._rejected_kids.clear()
    yield
    auth._rejected_kids.clear()


class TestUnknownKidIsNegativeCached:
    def test_repeated_unknown_kid_fetches_once(self):
        client = MagicMock()
        client.get_signing_key_from_jwt.side_effect = PyJWKClientError(
            'Unable to find a signing key that matches: "bogus"'
        )
        with patch.object(auth, "_get_jwks_client", return_value=client):
            for _ in range(5):
                assert auth.decode_supabase_jwt(_token_with_kid("bogus")) is None

        assert client.get_signing_key_from_jwt.call_count == 1, (
            f"JWKS was consulted "
            f"{client.get_signing_key_from_jwt.call_count} times for the same "
            "unknown kid — each one is a blocking refetch"
        )

    def test_distinct_unknown_kids_are_each_tried_once(self):
        client = MagicMock()
        client.get_signing_key_from_jwt.side_effect = PyJWKClientError("nope")
        with patch.object(auth, "_get_jwks_client", return_value=client):
            for i in range(3):
                auth.decode_supabase_jwt(_token_with_kid(f"kid-{i}"))
        assert client.get_signing_key_from_jwt.call_count == 3

    def test_rejected_set_is_bounded(self):
        client = MagicMock()
        client.get_signing_key_from_jwt.side_effect = PyJWKClientError("nope")
        with patch.object(auth, "_get_jwks_client", return_value=client):
            for i in range(auth._MAX_REJECTED_KIDS + 10):
                auth.decode_supabase_jwt(_token_with_kid(f"kid-{i}"))
        assert len(auth._rejected_kids) <= auth._MAX_REJECTED_KIDS, (
            "an attacker rotating kids could grow this set without bound"
        )


class TestConnectionFailureIsNotCached:
    """The important half. PyJWKClientConnectionError subclasses
    PyJWKClientError, so a naive `except PyJWKClientError` would swallow it and
    poison the cache."""

    def test_network_failure_does_not_poison_the_cache(self):
        client = MagicMock()
        client.get_signing_key_from_jwt.side_effect = PyJWKClientConnectionError(
            "connection refused"
        )
        with patch.object(auth, "_get_jwks_client", return_value=client):
            assert auth.decode_supabase_jwt(_token_with_kid("real-kid")) is None

        assert "real-kid" not in auth._rejected_kids, (
            "a transient fetch failure was cached as a rejected kid — every "
            "user holding that key would be locked out until restart"
        )

    def test_kid_still_works_after_a_transient_failure(self):
        """A blip followed by recovery must authenticate normally."""
        signing_key = MagicMock()
        signing_key.key = "k"
        client = MagicMock()
        client.get_signing_key_from_jwt.side_effect = [
            PyJWKClientConnectionError("blip"),
            signing_key,
        ]
        payload = {"role": "authenticated", "sub": "user-123", "email": "a@b.c"}

        with patch.object(auth, "_get_jwks_client", return_value=client), \
             patch.object(jwt, "decode", return_value=payload):
            assert auth.decode_supabase_jwt(_token_with_kid("real-kid")) is None
            assert auth.decode_supabase_jwt(_token_with_kid("real-kid")) == (
                "user-123", "a@b.c",
            )


class TestValidTokensAreUnaffected:
    def test_valid_token_decodes_and_is_not_cached(self):
        signing_key = MagicMock()
        signing_key.key = "k"
        client = MagicMock()
        client.get_signing_key_from_jwt.return_value = signing_key
        payload = {"role": "authenticated", "sub": "user-9", "email": "x@y.z"}

        with patch.object(auth, "_get_jwks_client", return_value=client), \
             patch.object(jwt, "decode", return_value=payload):
            assert auth.decode_supabase_jwt(_token_with_kid("good")) == (
                "user-9", "x@y.z",
            )
        assert auth._rejected_kids == set()

    def test_token_without_kid_still_handled(self):
        client = MagicMock()
        client.get_signing_key_from_jwt.side_effect = PyJWKClientError("no kid")
        token = jwt.encode({"sub": "u"}, "secret")
        with patch.object(auth, "_get_jwks_client", return_value=client):
            assert auth.decode_supabase_jwt(token) is None
