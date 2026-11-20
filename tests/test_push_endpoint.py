"""Push subscription endpoints must point at a real browser push service.

The server POSTs to every stored endpoint when a watch fires, so an arbitrary
URL would let anyone aim server-side requests at internal hosts.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from pnw_campsites.monitor import notify
from pnw_campsites.monitor.notify import is_push_service_endpoint, send_web_push


@pytest.mark.parametrize("url", [
    "https://fcm.googleapis.com/fcm/send/abc:APA91b",
    "https://updates.push.services.mozilla.com/wpush/v2/gAAAA",
    "https://web.push.apple.com/QGuQ-abc",
    "https://wns2-by3p.notify.windows.com/w/?token=BQYAAA",
])
def test_real_push_services_allowed(url):
    assert is_push_service_endpoint(url)


@pytest.mark.parametrize("url", [
    "http://fcm.googleapis.com/fcm/send/abc",
    "https://fcm.googleapis.com:8443/fcm/send/abc",
    "https://localhost:8080/api/admin",
    "https://169.254.169.254/latest/meta-data",
    "https://campnw.internal/api",
    "https://fcm.googleapis.com.evil.example/x",
    "https://evil.example/fcm.googleapis.com",
    "https://notify.windows.com.evil.example/x",
    "not a url",
    "",
])
def test_other_urls_rejected(url):
    assert not is_push_service_endpoint(url)


def test_subscribe_rejects_non_push_endpoint(api_client: TestClient):
    resp = api_client.post(
        "/api/push/subscribe",
        json={"endpoint": "https://localhost:8080/api/admin", "p256dh": "k", "auth": "a"},
    )
    assert resp.status_code == 422


async def test_send_skips_stored_non_push_endpoint(monkeypatch):
    """Rows saved before validation existed must not be sent to."""
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "test-key")
    with patch.object(notify, "webpush") as webpush:
        await send_web_push(
            {"endpoint": "https://localhost:8080/x", "keys": {"p256dh": "k", "auth": "a"}},
            {"title": "t", "body": "b", "url": "/"},
        )
    webpush.assert_not_called()
