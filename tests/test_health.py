"""Tests for the dependency health sweep.

Every test here is fully offline: the point of the sweep is that it never
crashes and always classifies correctly, and asserting that against live
services would make the suite fail for reasons unrelated to the code.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from pnw_campsites import health
from pnw_campsites.health import (
    CHECKS,
    Check,
    CheckResult,
    SkipCheck,
    run_all,
    run_check,
    summarize,
)


def _check(fn, **kwargs) -> Check:
    kwargs.setdefault("name", "probe")
    kwargs.setdefault("category", "data")
    return Check(fn=fn, **kwargs)


@pytest.fixture(autouse=True)
def _no_warmup(monkeypatch):
    """Skip module preloading — irrelevant offline and slow to import."""
    monkeypatch.setattr(health, "_preload_modules", lambda: None)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


async def test_fast_success_is_ok():
    async def fn() -> str:
        return "all good"

    result = await run_check(_check(fn, slow_ms=5000))
    assert result.status == "ok"
    assert result.detail == "all good"
    assert result.error == ""
    assert result.latency_ms is not None


async def test_success_over_threshold_is_slow():
    async def fn() -> str:
        await asyncio.sleep(0.05)
        return "sluggish"

    result = await run_check(_check(fn, slow_ms=10))
    assert result.status == "slow"
    # Slow is still a success — the detail must survive, since it is what tells
    # you whether the dependency is degraded or merely far away.
    assert result.detail == "sluggish"
    assert result.error == ""


async def test_exception_is_fail_with_one_line_error():
    async def fn() -> str:
        raise RuntimeError("upstream exploded\nstack line two")

    result = await run_check(_check(fn))
    assert result.status == "fail"
    assert result.error == "RuntimeError: upstream exploded"
    assert "\n" not in result.error


async def test_http_status_error_reports_code_and_host():
    async def fn() -> str:
        request = httpx.Request("GET", "https://api.example.com/v1/thing")
        raise httpx.HTTPStatusError(
            "boom", request=request, response=httpx.Response(503, request=request)
        )

    result = await run_check(_check(fn))
    assert result.status == "fail"
    assert result.error == "HTTP 503 from api.example.com"


async def test_timeout_is_fail_not_hang():
    async def fn() -> str:
        await asyncio.sleep(10)
        return "never"

    result = await run_check(_check(fn), timeout=0.05)
    assert result.status == "fail"
    assert "timed out" in result.error


async def test_missing_env_is_skip_not_fail(monkeypatch):
    monkeypatch.delenv("SOME_MISSING_KEY", raising=False)

    async def fn() -> str:  # pragma: no cover — must never run
        raise AssertionError("check ran despite missing config")

    result = await run_check(_check(fn, requires=("SOME_MISSING_KEY",)))
    assert result.status == "skip"
    assert "SOME_MISSING_KEY" in result.detail
    assert result.latency_ms is None


async def test_present_env_runs_the_check(monkeypatch):
    monkeypatch.setenv("SOME_PRESENT_KEY", "x")

    async def fn() -> str:
        return "ran"

    result = await run_check(_check(fn, requires=("SOME_PRESENT_KEY",)))
    assert result.status == "ok"


async def test_skipcheck_exception_is_skip():
    async def fn() -> str:
        raise SkipCheck("optional dep absent")

    result = await run_check(_check(fn))
    assert result.status == "skip"
    assert result.detail == "optional dep absent"


async def test_base_exception_still_propagates():
    """A cancellation must not be swallowed into a 'fail' row."""

    async def fn() -> str:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        await run_check(_check(fn))


# ---------------------------------------------------------------------------
# Sweep behaviour
# ---------------------------------------------------------------------------


async def test_one_failure_does_not_abort_the_sweep():
    async def ok() -> str:
        return "fine"

    async def boom() -> str:
        raise RuntimeError("down")

    results = await run_all(
        [
            _check(boom, name="first"),
            _check(ok, name="second"),
            _check(boom, name="third"),
        ]
    )
    assert [r.name for r in results] == ["first", "second", "third"]
    assert [r.status for r in results] == ["fail", "ok", "fail"]


async def test_category_filter():
    async def fn() -> str:
        return "x"

    checks = [
        _check(fn, name="a", category="data"),
        _check(fn, name="b", category="provider"),
        _check(fn, name="c", category="provider"),
    ]
    results = await run_all(checks, categories={"provider"})
    assert [r.name for r in results] == ["b", "c"]


# ---------------------------------------------------------------------------
# Summary / exit-code contract
# ---------------------------------------------------------------------------


def _results(*statuses) -> list[CheckResult]:
    return [CheckResult(f"c{i}", "data", s) for i, s in enumerate(statuses)]


def test_summary_all_ok():
    report = summarize(_results("ok", "ok"))
    assert report["status"] == "ok"
    assert report["healthy"] is True
    assert report["counts"] == {"ok": 2, "slow": 0, "fail": 0, "skip": 0}


def test_skip_does_not_make_the_sweep_unhealthy():
    report = summarize(_results("ok", "skip", "skip"))
    assert report["status"] == "ok"
    assert report["healthy"] is True


def test_slow_is_degraded_but_healthy_by_default():
    report = summarize(_results("ok", "slow"))
    assert report["status"] == "degraded"
    assert report["healthy"] is True


def test_strict_makes_slow_unhealthy():
    report = summarize(_results("ok", "slow"), strict=True)
    assert report["status"] == "degraded"
    assert report["healthy"] is False


def test_fail_dominates_slow():
    report = summarize(_results("slow", "fail", "ok"))
    assert report["status"] == "fail"
    assert report["healthy"] is False


def test_report_is_json_serializable():
    import json

    report = summarize(_results("ok", "fail"))
    assert json.loads(json.dumps(report))["checks"][0]["name"] == "c0"


# ---------------------------------------------------------------------------
# Registry sanity — cheap guards against copy-paste mistakes
# ---------------------------------------------------------------------------


def test_check_names_are_unique():
    names = [c.name for c in CHECKS]
    assert len(names) == len(set(names))


def test_categories_match_the_documented_cli_choices():
    documented = {"data", "provider", "enrich", "platform", "notify", "llm"}
    assert {c.category for c in CHECKS} <= documented


def test_every_check_is_a_coroutine_function():
    for check in CHECKS:
        assert asyncio.iscoroutinefunction(check.fn), check.name


# ---------------------------------------------------------------------------
# Admin route — GET /api/admin/health/deep
# ---------------------------------------------------------------------------


class TestAdminHealthDeep:
    """The route must be gated, and must never run a live sweep in tests."""

    @pytest.fixture(autouse=True)
    def _stub_sweep(self, monkeypatch):
        """Replace CHECKS so the route exercises routing/auth, not the network."""

        async def ok() -> str:
            return "stubbed"

        monkeypatch.setattr(
            health,
            "CHECKS",
            [
                Check(name="stub-data", category="data", fn=ok),
                Check(name="stub-provider", category="provider", fn=ok),
            ],
        )

    def test_requires_auth(self, api_client):
        assert api_client.get("/api/admin/health/deep").status_code == 401

    def test_returns_report_for_admin(self, api_client):
        from tests.test_api_coverage import _signup_and_login

        _, headers = _signup_and_login(api_client)
        resp = api_client.get("/api/admin/health/deep", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["healthy"] is True
        assert {c["name"] for c in body["checks"]} == {"stub-data", "stub-provider"}

    def test_only_filter_narrows_the_sweep(self, api_client):
        from tests.test_api_coverage import _signup_and_login

        _, headers = _signup_and_login(api_client)
        resp = api_client.get("/api/admin/health/deep?only=data", headers=headers)
        assert resp.status_code == 200
        assert [c["name"] for c in resp.json()["checks"]] == ["stub-data"]

    def test_failure_returns_503(self, api_client, monkeypatch):
        from tests.test_api_coverage import _signup_and_login

        async def boom() -> str:
            raise RuntimeError("provider down")

        monkeypatch.setattr(
            health, "CHECKS", [Check(name="stub", category="data", fn=boom)]
        )
        _, headers = _signup_and_login(api_client)
        resp = api_client.get("/api/admin/health/deep", headers=headers)
        # 503 so an external monitor can alert on the status line alone.
        assert resp.status_code == 503
        assert resp.json()["healthy"] is False
