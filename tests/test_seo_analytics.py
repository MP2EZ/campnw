"""Every SSR page must carry analytics (audit ANLT-04).

The SEO surface — /campgrounds, /campgrounds/{state}, the profile pages,
/tags/{tag}, /this-weekend — had no instrumentation at all. That lost the
organic funnel, but it also did something worse to every *other* channel:

A visitor arrives from search on an uninstrumented SSR page, clicks through to
the SPA, and *that* load is the first to initialise PostHog — with
document.referrer set to campable.co. First-touch attribution is therefore
$set_once'd as internal traffic. Organic search was not merely untracked, it
was misfiled as direct, and $set_once means it cannot be corrected later.

The fix has to be client-side: _cached_template sets max-age=3600, so
Cloudflare serves most of these responses without ever reaching Python.
"""

from __future__ import annotations

import pytest

SSR_PATHS = [
    ("/campgrounds", "campgrounds_index"),
    ("/campgrounds/wa", "state_index"),
    ("/tags/lakeside", "tag_index"),
    ("/this-weekend", "this_weekend"),
]


class TestEverySsrPageIsInstrumented:
    @pytest.mark.parametrize(("path", "page_type"), SSR_PATHS)
    def test_page_loads_the_analytics_script(self, seo_client, path, page_type):
        resp = seo_client.get(path)
        assert resp.status_code == 200
        body = resp.text
        assert '/seo-static/analytics.js' in body, (
            f"{path} renders no analytics — organic visits are invisible AND "
            "poison first-touch attribution for every other channel"
        )
        assert f'data-page-type="{page_type}"' in body

    def test_profile_page_is_instrumented_with_its_slug(self, seo_client):
        resp = seo_client.get("/campgrounds/wa/ohanapecosh")
        assert resp.status_code == 200
        assert '/seo-static/analytics.js' in resp.text
        assert 'data-page-type="profile"' in resp.text
        assert 'data-slug="ohanapecosh"' in resp.text
        assert 'data-state="WA"' in resp.text

    def test_script_is_deferred_so_it_does_not_block_render(self, seo_client):
        """These pages exist to rank; a blocking script would cost LCP."""
        body = seo_client.get("/campgrounds").text
        tag_start = body.index('id="seo-analytics"')
        tag = body[tag_start:body.index(">", tag_start)]
        assert "defer" in tag

    def test_state_page_carries_a_campground_count(self, seo_client):
        """Segmenting organic entries by page size is the point of the prop."""
        body = seo_client.get("/campgrounds/wa").text
        assert "data-campground-count=" in body
        assert 'data-campground-count=""' not in body


class TestAnalyticsScriptIsServed:
    def test_script_is_reachable(self, api_client):
        resp = api_client.get("/seo-static/analytics.js")
        assert resp.status_code == 200, (
            "base.html references the script but it is not served — every SSR "
            "page would 404 on it and stay uninstrumented"
        )

    def test_script_initialises_posthog_through_the_proxy(self, api_client):
        body = api_client.get("/seo-static/analytics.js").text
        # Same first-party /ingest path the SPA uses — going direct to
        # PostHog's host would be blocked by adblockers.
        assert "api_host: '/ingest'" in body
        assert "posthog.init(" in body
        assert "seo_page_viewed" in body
        assert "seo_cta_clicked" in body
