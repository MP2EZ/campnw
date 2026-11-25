"""Tests for scripts/security_scan.py: parsing, allowlist and issue planning."""

from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from security_scan import (
    PRIVATE_TITLE,
    Finding,
    apply_allowlist,
    load_allowlist,
    parse_npm_audit,
    parse_pip_audit,
    parse_trivy,
    parse_zizmor,
    plan_issues,
)

TODAY = date(2026, 11, 23)


class TestAllowlist:
    def test_live_and_expired_entries_split(self):
        text = """
[[allow]]
id = "CVE-1"
reason = "no fix"
expires = 2027-01-01

[[allow]]
id = "GHSA-old"
reason = "stale"
expires = 2026-11-01
"""
        allowed, expired = load_allowlist(text, TODAY)
        assert set(allowed) == {"CVE-1"}
        assert [e["id"] for e in expired] == ["GHSA-old"]

    def test_entry_without_expiry_is_rejected(self):
        text = '[[allow]]\nid = "CVE-1"\nreason = "x"\n'
        _, expired = load_allowlist(text, TODAY)
        assert [e["id"] for e in expired] == ["CVE-1"]

    def test_alias_match_suppresses(self):
        f = Finding(id="PYSEC-1", category="dep-cve", ecosystem="pypi",
                    package="pip", severity="UNKNOWN", aliases=("CVE-1",))
        kept, suppressed = apply_allowlist([f], {"CVE-1": {}})
        assert kept == [] and suppressed == [f]


class TestParsers:
    def test_pip_audit_every_vuln_counts(self):
        data = {"dependencies": [
            {"name": "jinja2", "version": "3.1.0", "vulns": [
                {"id": "GHSA-a", "fix_versions": ["3.1.6"], "aliases": ["CVE-9"]}]},
            {"name": "httpx", "version": "0.28.1", "vulns": []},
        ]}
        [f] = parse_pip_audit(data)
        assert (f.id, f.package, f.ecosystem, f.fixed) == ("GHSA-a", "jinja2", "pypi", "3.1.6")
        assert f.aliases == ("CVE-9",)

    def test_pip_audit_skipped_deps_ignored(self):
        data = {"dependencies": [{"name": "local", "skip_reason": "not on PyPI"}]}
        assert parse_pip_audit(data) == []

    def test_npm_audit_keeps_high_and_critical_once_per_advisory(self):
        adv = {"source": 1, "name": "picomatch", "severity": "high",
               "url": "https://github.com/advisories/GHSA-fc5q-39xc-vjpf"}
        data = {"vulnerabilities": {
            "picomatch": {"severity": "high", "via": [adv], "fixAvailable": True},
            "vite": {"severity": "high", "via": ["picomatch"], "fixAvailable": True},
            "x": {"severity": "moderate", "fixAvailable": False, "via": [
                {"name": "x", "severity": "moderate", "url": "https://github.com/advisories/GHSA-mod"}]},
        }}
        [f] = parse_npm_audit(data)
        assert (f.id, f.package, f.severity) == ("GHSA-fc5q-39xc-vjpf", "picomatch", "HIGH")

    def test_trivy_keeps_fixable_high_and_any_critical(self):
        data = {"ArtifactName": "img", "Results": [{"Target": "debian", "Class": "os-pkgs", "Type": "debian",
                             "Vulnerabilities": [
            {"VulnerabilityID": "CVE-fix", "PkgName": "zlib1g", "Severity": "HIGH", "FixedVersion": "1.2"},
            {"VulnerabilityID": "CVE-nofix", "PkgName": "openssl", "Severity": "HIGH"},
            {"VulnerabilityID": "CVE-crit", "PkgName": "libc", "Severity": "CRITICAL", "FixedVersion": ""},
            {"VulnerabilityID": "CVE-fix", "PkgName": "zlib-dev", "Severity": "HIGH", "FixedVersion": "1.2"},
        ]}]}
        found = parse_trivy(data)
        assert sorted(f.id for f in found) == ["CVE-crit", "CVE-fix"]
        fix = next(f for f in found if f.id == "CVE-fix")
        assert fix.package == "zlib-dev, zlib1g"
        assert all(f.category == "image-cve" for f in found)

    def test_zizmor_keeps_high_only(self):
        data = [
            {"ident": "unpinned-uses", "determinations": {"severity": "High"},
             "locations": [{"symbolic": {"key": {"Local": {"verbatim_path": ".github/workflows/a.yml"}}},
                            "concrete": {"location": {"start_point": {"row": 12}}}}]},
            {"ident": "artipacked", "determinations": {"severity": "Medium"}, "locations": []},
        ]
        [f] = parse_zizmor(data)
        # Keyed by file, not line, so an unrelated edit doesn't reopen the issue.
        assert f.id == "zizmor/unpinned-uses" and f.package == ".github/workflows/a.yml"
        assert "line 13" in f.detail
        assert f.category == "actions"


def _f(id_, category="dep-cve", eco="npm", pkg="p"):
    return Finding(id=id_, category=category, ecosystem=eco, package=pkg, severity="HIGH")


class TestPlanIssues:
    def test_new_finding_opens_issue_existing_is_left_alone(self):
        open_issues = [{"number": 5, "title": "[security] GHSA-a in p (npm)", "labels": ["security", "dep-cve"]}]
        plan = plan_issues([_f("GHSA-a"), _f("GHSA-b")], ok={"dep-cve"}, open_issues=open_issues)
        assert [c["title"] for c in plan["create"]] == ["[security] GHSA-b in p (npm)"]
        assert plan["close"] == []

    def test_cleared_finding_closes_only_when_its_scanner_ran(self):
        open_issues = [
            {"number": 5, "title": "[security] GHSA-a in p (npm)", "labels": ["security", "dep-cve"]},
            {"number": 6, "title": "[security] CVE-x in zlib (debian)", "labels": ["security", "image-cve"]},
        ]
        plan = plan_issues([], ok={"dep-cve"}, open_issues=open_issues)
        assert plan["close"] == [5]

    def test_failed_scanner_opens_one_broken_issue(self):
        plan = plan_issues([], ok=set(), open_issues=[], broken=["image: trivy.json missing"])
        [c] = plan["create"]
        assert c["title"] == "[security] Nightly security scan is broken"
        assert "trivy.json missing" in c["body"]

    def test_broken_issue_gets_comment_while_open_and_closes_when_healthy(self):
        broken_issue = {"number": 9, "title": "[security] Nightly security scan is broken",
                        "labels": ["security", "scan-broken"]}
        still = plan_issues([], ok=set(), open_issues=[broken_issue], broken=["x"])
        assert still["create"] == [] and [c["number"] for c in still["comment"]] == [9]
        healthy = plan_issues([], ok={"dep-cve"}, open_issues=[broken_issue], broken=[])
        assert healthy["close"] == [9]


class TestScannerFailureIsNotClean:
    """A scanner that errored must surface as broken, never as zero findings."""

    def test_npm_error_payload_raises(self):
        import pytest
        with pytest.raises(ValueError):
            parse_npm_audit({"error": {"code": "ENOAUDIT"}})

    def test_pip_audit_without_dependencies_raises(self):
        import pytest
        with pytest.raises(KeyError):
            parse_pip_audit({})

    def test_trivy_non_report_raises(self):
        import pytest
        with pytest.raises(ValueError):
            parse_trivy({})

    def test_missing_file_marks_category_broken(self, tmp_path):
        from security_scan import collect
        (tmp_path / "npm-audit.json").write_text('{"vulnerabilities": {}}')
        findings, ok, broken = collect(tmp_path, ["npm-audit.json", "pip-audit.json"])
        assert findings == [] and ok == set()
        assert broken and broken[0].startswith("pip-audit.json")


class TestReviewFixes:
    def test_close_ignores_hand_filed_issue_with_same_labels(self):
        open_issues = [{"number": 7, "title": "Pin remaining actions by SHA",
                        "labels": ["security", "actions"]}]
        plan = plan_issues([], ok={"actions"}, open_issues=open_issues)
        assert plan["close"] == []

    def test_check_summary_names_the_broken_scanner(self, tmp_path, capsys):
        import argparse

        from security_scan import cmd_check
        allow = tmp_path / "allow.toml"
        allow.write_text("")
        rc = cmd_check(argparse.Namespace(
            allowlist=str(allow), dir=str(tmp_path), expect=["pip-audit.json"],
            out=str(tmp_path / "findings.json")))
        assert rc == 1
        assert "scanner broken: pip-audit.json" in capsys.readouterr().out

    def test_live_root_not_serving_the_app_is_broken_not_clean(self):
        import httpx
        import pytest
        from security_scan import check_http
        def challenge(req):
            return httpx.Response(403, text="Just a moment...")
        with httpx.Client(transport=httpx.MockTransport(challenge)) as c, \
                pytest.raises(RuntimeError):
            check_http(c)

    def test_origin_unreachable_means_no_bypass(self):
        import httpx
        from security_scan import check_http
        def handler(req):
            if req.url.host == "campnw.fly.dev":
                raise httpx.ConnectError("no address")
            return httpx.Response(200, text='<html><div id="root"></div></html>', headers={
                "strict-transport-security": "max-age=1", "content-security-policy": "frame-ancestors 'none'",
                "x-content-type-options": "nosniff", "content-type": "text/html"})
        with httpx.Client(transport=httpx.MockTransport(handler)) as c:
            assert check_http(c) == []


class TestPrivateFindingsStayOutOfPublicView:
    """Repo is public: live-config and image-cve details never reach issues,
    step summaries or logs. Only a count does."""

    def _private(self):
        return [_f("exposed-path", "live-config", "live", "campable.co/.env"),
                _f("CVE-2026-1", "image-cve", "debian", "zlib1g")]

    def test_private_findings_open_one_count_only_issue(self):
        plan = plan_issues(self._private() + [_f("GHSA-a")],
                           ok={"dep-cve", "live-config", "image-cve"}, open_issues=[])
        titles = [c["title"] for c in plan["create"]]
        assert "[security] GHSA-a in p (npm)" in titles
        [priv] = [c for c in plan["create"] if c["title"] == PRIVATE_TITLE]
        text = priv["title"] + priv["body"]
        assert "2 private finding" in text
        for leak in (".env", "zlib1g", "CVE-2026-1", "exposed-path"):
            assert leak not in text
        assert len(titles) == 2

    def test_private_issue_closes_only_when_private_scanners_ran_clean(self):
        issue = {"number": 3, "title": PRIVATE_TITLE, "labels": ["security", "private"]}
        assert plan_issues([], ok={"dep-cve"}, open_issues=[issue])["close"] == []
        assert plan_issues([], ok={"live-config", "image-cve"}, open_issues=[issue])["close"] == [3]
        still = plan_issues(self._private(), ok={"live-config", "image-cve"}, open_issues=[issue])
        assert still["close"] == [] and still["create"] == []

    def test_summary_counts_private_findings_without_details(self, capsys):
        from security_scan import write_summary
        write_summary(self._private() + [_f("GHSA-a")], [], [], [])
        out = capsys.readouterr().out
        assert "GHSA-a" in out and "2 private finding" in out
        for leak in (".env", "zlib1g", "CVE-2026-1", "exposed-path"):
            assert leak not in out
