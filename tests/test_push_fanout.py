"""A push watch reaches every device the user registered: browser push
subscriptions and iPhones. Dead phone tokens are dropped; nothing else is."""

from __future__ import annotations

from pnw_campsites import api as api_module
from pnw_campsites.monitor import notify as notify_mod
from pnw_campsites.monitor import watcher as watcher_mod
from pnw_campsites.monitor.db import User, Watch, WatchDB
from pnw_campsites.monitor.notify import native_alert, push_to_user
from pnw_campsites.monitor.watcher import AvailabilityChange, PollResult

TOKEN = "a1" * 32
DEAD = "dd" * 32
WEB = {"title": "t", "body": "b", "url": "/"}
NATIVE = {"aps": {"alert": {"title": "t", "body": "b"}}}


class FakeSender:
    def __init__(self, statuses: dict[str, str] | None = None):
        self.statuses = statuses or {}
        self.sent: list[tuple[str, dict, str | None]] = []

    async def send(self, token, payload, *, collapse_id=None, expires_in=1800):
        self.sent.append((token, payload, collapse_id))
        return self.statuses.get(token, "sent")


def _user(db: WatchDB) -> int:
    return db.create_user(User(email="a@example.com", password_hash="")).id


def _web_sub(db: WatchDB, uid: int) -> None:
    db.save_push_subscription(
        uid, "", "https://web.push.apple.com/abc", "p256", "auth",
    )


class TestPushToUser:
    async def test_reaches_browsers_and_phones(self, watch_db):
        uid = _user(watch_db)
        _web_sub(watch_db, uid)
        watch_db.save_device_token(uid, TOKEN)
        web_sent = []

        async def send_web(sub, payload):
            web_sent.append((sub["endpoint"], payload))

        sender = FakeSender()
        out = await push_to_user(
            watch_db, uid, WEB, NATIVE, sender=sender, send_web=send_web,
            collapse_id="release-1",
        )
        assert web_sent == [("https://web.push.apple.com/abc", WEB)]
        assert sender.sent == [(TOKEN, NATIVE, "release-1")]
        assert out == [("web_push", "sent"), ("apns", "sent")]

    async def test_dead_tokens_are_deleted(self, watch_db):
        uid = _user(watch_db)
        watch_db.save_device_token(uid, TOKEN)
        watch_db.save_device_token(uid, DEAD)
        out = await push_to_user(
            watch_db, uid, WEB, NATIVE, sender=FakeSender({DEAD: "dead"}),
        )
        assert watch_db.get_device_tokens_for_user(uid) == [TOKEN]
        assert ("apns", "failed") in out

    async def test_failed_sends_keep_the_token(self, watch_db):
        uid = _user(watch_db)
        watch_db.save_device_token(uid, TOKEN)
        await push_to_user(
            watch_db, uid, WEB, NATIVE, sender=FakeSender({TOKEN: "failed"}),
        )
        assert watch_db.get_device_tokens_for_user(uid) == [TOKEN]

    async def test_a_send_that_raises_counts_as_failed(self, watch_db, caplog):
        """Anything the sender raises stays here: escaping would abort the
        poll loop after snapshots were saved, losing later watches' alerts."""
        uid = _user(watch_db)
        watch_db.save_device_token(uid, TOKEN)
        watch_db.save_device_token(uid, DEAD)

        class Exploding(FakeSender):
            async def send(self, token, payload, **kw):
                if token == TOKEN:
                    raise RuntimeError(f"h2 blew up sending to {token}")
                return await super().send(token, payload, **kw)

        sender = Exploding()
        out = await push_to_user(watch_db, uid, WEB, NATIVE, sender=sender)
        assert out == [("apns", "failed"), ("apns", "sent")]
        assert sorted(watch_db.get_device_tokens_for_user(uid)) == sorted([TOKEN, DEAD])
        assert TOKEN not in caplog.text

    async def test_no_sender_means_web_only(self, watch_db):
        """APNs not configured here: phones are skipped, browsers still get it."""
        uid = _user(watch_db)
        _web_sub(watch_db, uid)
        watch_db.save_device_token(uid, TOKEN)

        async def send_web(sub, payload):
            return None

        out = await push_to_user(
            watch_db, uid, WEB, NATIVE, sender=None, send_web=send_web,
        )
        assert out == [("web_push", "sent")]

    async def test_a_web_failure_does_not_stop_the_phone(self, watch_db):
        uid = _user(watch_db)
        _web_sub(watch_db, uid)
        watch_db.save_device_token(uid, TOKEN)

        async def send_web(sub, payload):
            raise RuntimeError("push service down")

        sender = FakeSender()
        out = await push_to_user(
            watch_db, uid, WEB, NATIVE, sender=sender, send_web=send_web,
        )
        assert out == [("web_push", "failed"), ("apns", "sent")]


def _result(n_sites: int = 1, dates=("2026-06-12", "2026-06-13")) -> PollResult:
    watch = Watch(
        id=42, facility_id="232465", user_id=7, booking_system="recgov",
        notification_channel="web_push", name="my secret trip <script>",
    )
    r = PollResult(watch=watch, booking_url="https://www.recreation.gov/x")
    for i in range(n_sites):
        r.changes.append(AvailabilityChange(
            watch=watch, site_id=str(i), site_name=f"{23 + i}", loop="Loop B",
            campsite_type="tent", new_dates=list(dates), max_people=4,
        ))
    return r


class TestNativeAlert:
    def test_copy_leads_with_dates_and_names_the_provider(self):
        p = native_alert(_result(), "Ohanapecosh")
        alert = p["aps"]["alert"]
        assert alert["title"] == "Ohanapecosh: site open"
        assert alert["body"] == (
            "Fri Jun 12 – Sat Jun 13 · Site 23 (Loop B). Book on Recreation.gov."
        )

    def test_more_sites(self):
        alert = native_alert(_result(n_sites=3), "Ohanapecosh")["aps"]["alert"]
        assert alert["title"] == "Ohanapecosh: 3 sites open"
        assert "Site 23 (Loop B) +2 more" in alert["body"]

    def test_single_night(self):
        alert = native_alert(_result(dates=("2026-06-12",)), "X")["aps"]["alert"]
        assert alert["body"].startswith("Fri Jun 12 · ")

    def test_long_names_are_truncated(self):
        title = native_alert(_result(), "A" * 60)["aps"]["alert"]["title"]
        assert title.startswith("A" * 29 + "…")

    def test_time_sensitive_and_threaded(self):
        aps = native_alert(_result(), "X")["aps"]
        assert aps["interruption-level"] == "time-sensitive"
        assert aps["thread-id"] == "watch-42"
        assert aps["sound"] == "default"

    def test_tap_data(self):
        p = native_alert(_result(), "X")
        assert p["watch_id"] == 42
        assert p["booking_url"] == "https://www.recreation.gov/x"
        assert "path" not in p

    def test_other_providers(self):
        r = _result()
        r.watch.booking_system = "wa_state"
        assert "Book on WA State Parks." in native_alert(r, "X")["aps"]["alert"]["body"]


class _Registry:
    def __init__(self, name):
        self.name = name

    def get_by_facility_id(self, fid):
        return type("Cg", (), {"name": self.name})() if self.name else None


class TestPollDispatch:
    async def test_push_watch_reaches_the_phone(self, watch_db, monkeypatch):
        uid = _user(watch_db)
        watch_db.save_device_token(uid, TOKEN)
        result = _result()
        result.watch.user_id = uid
        result.watch.id = watch_db.add_watch(Watch(
            facility_id="232465", name="x", start_date="2026-06-01",
            end_date="2026-06-30", user_id=uid,
        )).id
        sender = FakeSender()

        async def fake_poll_all(*a, **k):
            return [result]

        monkeypatch.setattr(watcher_mod, "poll_all", fake_poll_all)
        monkeypatch.setattr(api_module, "_watch_db", watch_db)
        monkeypatch.setattr(api_module, "_registry", _Registry("Ohanapecosh"))
        monkeypatch.setattr(notify_mod, "open_apns_sender", _fixed(sender))
        await api_module._poll_tranche()

        assert len(sender.sent) == 1
        token, payload, _ = sender.sent[0]
        assert token == TOKEN
        # The registry name, never the user-editable watch name.
        assert payload["aps"]["alert"]["title"] == "Ohanapecosh: site open"
        logged = watch_db._conn.execute(
            "SELECT channel, status FROM notification_log",
        ).fetchall()
        assert [tuple(r) for r in logged] == [("apns", "sent")]


def _fixed(sender):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def opener():
        yield sender

    return opener


class TestPollLoopSurvivesASenderError:
    async def test_later_watches_still_alert(self, watch_db, monkeypatch):
        uid = _user(watch_db)
        watch_db.save_device_token(uid, TOKEN)
        first = _result()
        first.watch.user_id = uid
        first.watch.id = watch_db.add_watch(Watch(
            facility_id="232465", name="x", start_date="2026-06-01",
            end_date="2026-06-30", user_id=uid,
        )).id
        second = _result()
        second.watch = Watch(
            id=watch_db.add_watch(Watch(
                facility_id="1", name="y", start_date="2026-06-01", end_date="2026-06-30",
            )).id,
            facility_id="1", name="y", notification_channel="ntfy", notify_topic="t",
        )
        second.changes[0].watch = second.watch

        class Exploding:
            async def send(self, *a, **k):
                raise RuntimeError("boom")

        ntfy_sent = []

        async def fake_ntfy(topic, result):
            ntfy_sent.append(result.watch.id)

        async def fake_poll_all(*a, **k):
            return [first, second]

        monkeypatch.setattr(watcher_mod, "poll_all", fake_poll_all)
        monkeypatch.setattr(notify_mod, "notify_ntfy", fake_ntfy)
        monkeypatch.setattr(api_module, "_watch_db", watch_db)
        monkeypatch.setattr(api_module, "_registry", _Registry("Ohanapecosh"))
        monkeypatch.setattr(notify_mod, "open_apns_sender", _fixed(Exploding()))
        await api_module._poll_tranche()
        assert ntfy_sent == [second.watch.id]
