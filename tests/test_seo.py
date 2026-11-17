"""Tests for SEO helpers and server-rendered SEO pages."""

from __future__ import annotations

from pnw_campsites import api as api_module
from pnw_campsites.registry.db import slugify
from pnw_campsites.registry.models import BookingSystem
from pnw_campsites.routes.seo import _format_drive_time
from tests.conftest import make_campground


class TestSlugify:
    def test_normal_name(self):
        assert slugify("Deception Pass State Park") == "deception-pass-state-park"

    def test_unicode_accents(self):
        assert slugify("Caf\u00e9 Ren\u00e9") == "cafe-rene"

    def test_special_chars(self):
        assert slugify("Camp -- River & Lake!") == "camp-river-lake"

    def test_empty_string(self):
        assert slugify("") == ""

    def test_leading_trailing_spaces(self):
        assert slugify("  Hello World  ") == "hello-world"

    def test_all_special_chars(self):
        assert slugify("---!!!---") == ""

    def test_numbers_preserved(self):
        assert slugify("Site 42 Loop B") == "site-42-loop-b"


class TestFormatDriveTime:
    def test_none(self):
        assert _format_drive_time(None) == ""

    def test_minutes_only(self):
        assert _format_drive_time(45) == "45m"

    def test_hours_only(self):
        assert _format_drive_time(120) == "2h"

    def test_hours_and_minutes(self):
        assert _format_drive_time(150) == "2h 30m"

    def test_zero(self):
        assert _format_drive_time(0) == "0m"


def _seed_registry(registry):
    """Seed a registry with test campgrounds for DB query tests."""
    registry.upsert(make_campground(
        facility_id="100", name="Deception Pass State Park",
        state="WA", region="Whidbey Island",
        latitude=48.40, longitude=-122.65,
        tags=["lakeside", "kid-friendly"],
        booking_system=BookingSystem.WA_STATE,
    ))
    registry.upsert(make_campground(
        facility_id="200", name="Cape Lookout State Park",
        state="OR", region="Oregon Coast",
        latitude=45.34, longitude=-123.97,
        tags=["ocean", "kid-friendly"],
        booking_system=BookingSystem.OR_STATE,
    ))
    registry.upsert(make_campground(
        facility_id="300", name="Ohanapecosh",
        state="WA", region="Mt. Rainier NP",
        latitude=46.73, longitude=-121.57,
        tags=["lakeside", "old-growth"],
        booking_system=BookingSystem.RECGOV,
    ))


class TestGetBySlug:
    def test_found(self, registry):
        _seed_registry(registry)
        cg = registry.get_by_slug("WA", "ohanapecosh")
        assert cg is not None
        assert cg.name == "Ohanapecosh"

    def test_case_insensitive_state(self, registry):
        _seed_registry(registry)
        cg = registry.get_by_slug("wa", "ohanapecosh")
        assert cg is not None

    def test_not_found(self, registry):
        _seed_registry(registry)
        assert registry.get_by_slug("WA", "nonexistent") is None

    def test_wrong_state(self, registry):
        _seed_registry(registry)
        assert registry.get_by_slug("OR", "ohanapecosh") is None


class TestGetNearby:
    def test_returns_sorted_by_distance(self, registry):
        _seed_registry(registry)
        nearby = registry.get_nearby(46.73, -121.57, state="WA")
        assert len(nearby) >= 1
        assert nearby[0].name == "Ohanapecosh"

    def test_exclude_id(self, registry):
        _seed_registry(registry)
        ohan = registry.get_by_slug("WA", "ohanapecosh")
        nearby = registry.get_nearby(
            46.73, -121.57, state="WA", exclude_id=ohan.id,
        )
        names = [c.name for c in nearby]
        assert "Ohanapecosh" not in names

    def test_limit(self, registry):
        _seed_registry(registry)
        nearby = registry.get_nearby(47.0, -122.0, limit=1)
        assert len(nearby) == 1

    def test_state_filter(self, registry):
        _seed_registry(registry)
        nearby = registry.get_nearby(47.0, -122.0, state="OR")
        for cg in nearby:
            assert cg.state == "OR"


class TestGetAllTags:
    def test_returns_tags_with_counts(self, registry):
        _seed_registry(registry)
        tags = registry.get_all_tags()
        tag_dict = dict(tags)
        assert tag_dict["lakeside"] == 2
        assert tag_dict["kid-friendly"] == 2
        assert tag_dict["old-growth"] == 1

    def test_sorted_by_count_desc(self, registry):
        _seed_registry(registry)
        tags = registry.get_all_tags()
        counts = [c for _, c in tags]
        assert counts == sorted(counts, reverse=True)


class TestCountByState:
    def test_returns_counts(self, registry):
        _seed_registry(registry)
        counts = registry.count_by_state()
        assert counts["WA"] == 2
        assert counts["OR"] == 1


class TestSlugDisambiguation:
    def test_backfill_disambiguates_same_name_same_state(self, registry):
        """_backfill_slugs appends facility_id when two campgrounds share name+state."""
        registry.upsert(make_campground(facility_id="AAA", name="Lakeview", state="WA"))
        registry.upsert(make_campground(facility_id="BBB", name="Lakeview", state="WA"))
        # Clear slugs to simulate pre-migration state, then run backfill
        registry._conn.execute("UPDATE campgrounds SET slug = ''")
        registry._conn.commit()
        registry._backfill_slugs()
        r1 = registry.get_by_facility_id("AAA")
        r2 = registry.get_by_facility_id("BBB")
        assert r1.slug != r2.slug
        assert "lakeview" in r1.slug
        assert "lakeview" in r2.slug

    def test_same_name_different_state_ok(self, registry):
        """Same name in different states can share the base slug."""
        cg1 = make_campground(facility_id="AAA", name="Lakeview", state="WA")
        cg2 = make_campground(facility_id="BBB", name="Lakeview", state="OR")
        r1 = registry.upsert(cg1)
        r2 = registry.upsert(cg2)
        assert r1.slug == "lakeview"
        assert r2.slug == "lakeview"


class TestCampgroundProfile:
    def test_200_with_jsonld(self, seo_client):
        resp = seo_client.get("/campgrounds/wa/ohanapecosh")
        assert resp.status_code == 200
        assert "application/ld+json" in resp.text
        assert "max-age=3600" in resp.headers["Cache-Control"]

    def test_empty_pitch_leaves_out_pitch_and_vibe(self, seo_client):
        # The regen clears copy for campgrounds with no facts. The page must not
        # print an empty pitch line or fall back to the old LLM vibe for SEO.
        reg = api_module._registry
        cg = reg.get_by_facility_id("300", BookingSystem.RECGOV)
        reg.update_description(cg.id, "", "", "")
        reg.update_vibe(cg.id, "Serene old-growth haven for solitude seekers")

        resp = seo_client.get("/campgrounds/wa/ohanapecosh")

        assert resp.status_code == 200
        assert "profile__pitch" not in resp.text
        assert '<meta name="description" content="Ohanapecosh campground in' in resp.text
        assert '"description": "Ohanapecosh campground in Washington."' in resp.text

    def test_404_invalid_state(self, seo_client):
        resp = seo_client.get("/campgrounds/xx/anything")
        assert resp.status_code == 404

    def test_404_nonexistent_slug(self, seo_client):
        resp = seo_client.get("/campgrounds/wa/nonexistent")
        assert resp.status_code == 404


class TestStateIndex:
    def test_200_lists_campgrounds(self, seo_client):
        resp = seo_client.get("/campgrounds/wa")
        assert resp.status_code == 200
        assert "Ohanapecosh" in resp.text
        assert "Deception Pass" in resp.text
        assert "max-age=3600" in resp.headers["Cache-Control"]

    def test_404_invalid_state(self, seo_client):
        resp = seo_client.get("/campgrounds/zz")
        assert resp.status_code == 404


class TestCampgroundsIndex:
    def test_200_shows_states(self, seo_client):
        resp = seo_client.get("/campgrounds")
        assert resp.status_code == 200
        assert "Washington" in resp.text
        assert "Oregon" in resp.text
        assert "max-age=3600" in resp.headers["Cache-Control"]


class TestTagIndex:
    def test_200_lakeside(self, seo_client):
        resp = seo_client.get("/tags/lakeside")
        assert resp.status_code == 200
        assert "lakeside" in resp.text.lower()
        assert "max-age=3600" in resp.headers["Cache-Control"]

    def test_404_nonexistent_tag(self, seo_client):
        resp = seo_client.get("/tags/nonexistent")
        assert resp.status_code == 404


class TestThisWeekend:
    def test_200_loading_state(self, seo_client):
        resp = seo_client.get("/this-weekend")
        assert resp.status_code == 200
        assert "max-age=900" in resp.headers["Cache-Control"]


class TestSitemap:
    def test_200_contains_campground_urls(self, seo_client):
        resp = seo_client.get("/sitemap.xml")
        assert resp.status_code == 200
        assert "application/xml" in resp.headers["content-type"]
        assert "campable.co/campgrounds/wa/ohanapecosh" in resp.text
        assert "campable.co/campgrounds" in resp.text

    def test_contains_tag_urls(self, seo_client):
        resp = seo_client.get("/sitemap.xml")
        assert "campable.co/tags/lakeside" in resp.text


class TestRobotsTxt:
    def test_200_contains_sitemap(self, seo_client):
        resp = seo_client.get("/robots.txt")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers["content-type"]
        assert "Sitemap:" in resp.text
        assert "campable.co/sitemap.xml" in resp.text
