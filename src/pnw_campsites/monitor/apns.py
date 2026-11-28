"""Apple Push Notification service (APNs) sender for the iOS app.

Token-based auth: an ES256 JWT signed with the team's .p8 key, sent as a
bearer token over HTTP/2. Apple's rules (developer.apple.com, "Establishing a
token-based connection to APNs"): refresh the JWT no more than once every 20
minutes and no less than once every 60.

Device tokens are delivery addresses, so they never go in logs or analytics:
failures log a short hash.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import logging
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key

_logger = logging.getLogger(__name__)

HOSTS = {
    "production": "https://api.push.apple.com",
    "sandbox": "https://api.sandbox.push.apple.com",
}
DEFAULT_TOPIC = "co.campable.app"

_JWT_MAX_AGE = 50 * 60   # refresh before Apple's 60-minute limit
_JWT_MIN_AGE = 20 * 60   # Apple: no more often than every 20 minutes
_RETRY_DELAY = 1.0

# The token is gone (app deleted, token rotated) or belongs to another app.
# DeviceTokenNotForTopic is per token, not ours to fix: the topic is fixed.
_DEAD = {"BadDeviceToken", "Unregistered", "ExpiredToken", "DeviceTokenNotForTopic"}
# Our key, team or topic is wrong. Every send would fail the same way, and no
# token is at fault, so stop the cycle and delete nothing.
_PROVIDER = {
    "InvalidProviderToken", "MissingProviderToken", "BadTopic", "MissingTopic",
    "TopicDisallowed", "Forbidden", "BadCertificate", "BadCertificateEnvironment",
    "TooManyProviderTokenUpdates", "UnrelatedKeyIdInToken",
    "BadEnvironmentKeyIdInToken",
}

SendStatus = Literal["sent", "dead", "failed"]


def _now() -> float:
    return time.time()


def token_ref(token: str) -> str:
    """Short, non-reversible stand-in for a device token in logs."""
    return hashlib.sha256(token.encode()).hexdigest()[:8]


@dataclass(frozen=True)
class ApnsConfig:
    key: EllipticCurvePrivateKey
    key_id: str
    team_id: str
    topic: str
    host: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ApnsConfig | None:
        """None when APNs isn't configured here. Raises ValueError, naming the
        variable but never its contents, when the key can't be read."""
        env = os.environ if env is None else env
        key_b64 = env.get("APNS_KEY_P8_B64", "")
        key_id = env.get("APNS_KEY_ID", "")
        team_id = env.get("APNS_TEAM_ID", "")
        if not (key_b64 and key_id and team_id):
            return None
        environment = env.get("APNS_ENVIRONMENT", "production")
        if environment not in HOSTS:
            raise ValueError("APNS_ENVIRONMENT must be production or sandbox")
        try:
            key = load_pem_private_key(base64.b64decode(key_b64), password=None)
        except (ValueError, TypeError, binascii.Error):
            raise ValueError("APNS_KEY_P8_B64 is not a base64-encoded .p8 key") from None
        if not isinstance(key, EllipticCurvePrivateKey):
            raise ValueError("APNS_KEY_P8_B64 is not an EC (.p8) key")
        return cls(
            key=key, key_id=key_id, team_id=team_id,
            # Not configurable: a wrong topic makes every token answer
            # DeviceTokenNotForTopic, which deletes it.
            topic=DEFAULT_TOPIC, host=HOSTS[environment],
        )


# One JWT for the process, shared by every sender (a sender lives for one
# poll job). Minting is synchronous, so concurrent sends can't race it.
_jwt_cache: dict[str, tuple[str, float]] = {}


def reset_jwt_cache() -> None:
    _jwt_cache.clear()


def new_client() -> httpx.AsyncClient:
    """HTTP/2 client for one job. Bounded timeouts so a slow APNs can't stall
    the poll cycle."""
    return httpx.AsyncClient(
        http2=True,
        timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0),
    )


class ApnsSender:
    def __init__(self, config: ApnsConfig, client: httpx.AsyncClient | None):
        self._config = config
        self._client = client
        self._disabled = False

    def _jwt(self, *, refresh: bool = False) -> str:
        cfg = self._config
        cache_key = f"{cfg.team_id}:{cfg.key_id}"
        cached = _jwt_cache.get(cache_key)
        now = _now()
        if cached:
            token, issued = cached
            age = now - issued
            if age < _JWT_MAX_AGE and not (refresh and age >= _JWT_MIN_AGE):
                return token
        token = jwt.encode(
            {"iss": cfg.team_id, "iat": int(now)},
            cfg.key, algorithm="ES256", headers={"kid": cfg.key_id},
        )
        _jwt_cache[cache_key] = (token, now)
        return token

    async def send(
        self,
        token: str,
        payload: dict,
        *,
        collapse_id: str | None = None,
        expires_in: int = 1800,
    ) -> SendStatus:
        """Send one alert. "dead" means delete the token; "failed" keeps it."""
        if self._disabled or self._client is None:
            return "failed"
        headers = {
            "apns-topic": self._config.topic,
            "apns-push-type": "alert",
            "apns-priority": "10",
            "apns-expiration": str(int(_now()) + expires_in),
        }
        if collapse_id:
            headers["apns-collapse-id"] = collapse_id[:64]
        url = f"{self._config.host}/3/device/{token}"

        refreshed = retried = False
        while True:
            headers["authorization"] = f"bearer {self._jwt(refresh=refreshed)}"
            try:
                resp = await self._client.post(url, json=payload, headers=headers)
            except httpx.HTTPError as e:
                # The exception text contains the URL, and so the token.
                reason, status = type(e).__name__, 0
            else:
                if resp.status_code == 200:
                    return "sent"
                status = resp.status_code
                try:
                    reason = str(resp.json().get("reason", ""))
                except ValueError:
                    reason = ""

            if reason in _DEAD:
                _logger.info("APNs token %s is dead (%s)", token_ref(token), reason)
                return "dead"
            if reason == "ExpiredProviderToken" and not refreshed:
                refreshed = True
                continue
            if reason in _PROVIDER or reason == "ExpiredProviderToken":
                self._disabled = True
                _logger.error(
                    "APNs rejected our credentials (%s %s); "
                    "skipping APNs for the rest of this job", status, reason,
                )
                return "failed"
            if (status == 0 or status == 429 or status >= 500) and not retried:
                retried = True
                await asyncio.sleep(_RETRY_DELAY)
                continue
            _logger.warning(
                "APNs send to %s failed (%s %s)", token_ref(token), status, reason,
            )
            return "failed"
