"""Nightly + PR security scan: normalize scanner output, apply the allowlist,
gate, and plan GitHub issues.

Used by .github/workflows/security-scan.yml. Scanners write JSON into one
directory; this script reads whatever is there:

    pip-audit.json  npm-audit.json  zizmor.json  trivy.json  live.json

Subcommands:
    live         run the read-only campable.co checks, write live.json
    check        gate: exit 1 on any unallowlisted finding, expired allowlist
                 entry, or missing scanner output; writes findings.json
    file-issues  open/close GitHub issues from findings.json (nightly only)

A scanner whose output is missing or unreadable is reported as broken, never
as "no findings".
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path

PROD = "campable.co"
ORIGIN = "campnw.fly.dev"
APP_MARKER = '<div id="root">'
TLS_MIN_DAYS = 21
TITLE_PREFIX = "[security] "
BROKEN_TITLE = f"{TITLE_PREFIX}Nightly security scan is broken"

# scanner file -> issue category it feeds
SCANNERS = {
    "pip-audit.json": "dep-cve",
    "npm-audit.json": "dep-cve",
    "zizmor.json": "actions",
    "trivy.json": "image-cve",
    "live.json": "live-config",
}


@dataclass(frozen=True)
class Finding:
    id: str
    category: str  # dep-cve | image-cve | actions | live-config
    ecosystem: str
    package: str
    severity: str
    fixed: str = ""
    aliases: tuple[str, ...] = ()
    detail: str = ""

    @property
    def title(self) -> str:
        return f"{TITLE_PREFIX}{self.id} in {self.package} ({self.ecosystem})"


# ── allowlist ────────────────────────────────────────────────────────────


def load_allowlist(text: str, today: date) -> tuple[dict[str, dict], list[dict]]:
    """Return (live entries by id, expired-or-undated entries)."""
    allowed: dict[str, dict] = {}
    expired: list[dict] = []
    for entry in tomllib.loads(text).get("allow", []):
        exp = entry.get("expires")
        if not isinstance(exp, date) or exp < today:
            expired.append(entry)
        else:
            allowed[entry["id"]] = entry
    return allowed, expired


def apply_allowlist(
    findings: list[Finding], allowed: dict[str, dict]
) -> tuple[list[Finding], list[Finding]]:
    kept, suppressed = [], []
    for f in findings:
        ids = {f.id, *f.aliases}
        (suppressed if ids & allowed.keys() else kept).append(f)
    return kept, suppressed


# ── parsers ──────────────────────────────────────────────────────────────


def parse_pip_audit(data: dict) -> list[Finding]:
    # pip-audit reports no severity, so every known vuln counts (as before).
    out = []
    for dep in data["dependencies"]:
        for v in dep.get("vulns", []):
            out.append(Finding(
                id=v["id"], category="dep-cve", ecosystem="pypi",
                package=dep["name"], severity="UNKNOWN",
                fixed=", ".join(v.get("fix_versions") or []),
                aliases=tuple(v.get("aliases") or ()),
                detail=f"installed {dep.get('version', '?')}",
            ))
    return out


def parse_npm_audit(data: dict) -> list[Finding]:
    if "error" in data:  # npm writes {"error": ...} when the audit endpoint fails
        raise ValueError(f"npm audit error: {data['error']}")
    seen: dict[str, Finding] = {}
    for vuln in data["vulnerabilities"].values():
        for via in vuln.get("via", []):
            if not isinstance(via, dict) or via.get("severity") not in ("high", "critical"):
                continue
            ghsa = via["url"].rstrip("/").rsplit("/", 1)[-1]
            seen.setdefault(ghsa, Finding(
                id=ghsa, category="dep-cve", ecosystem="npm", package=via["name"],
                severity=via["severity"].upper(),
                fixed="available" if vuln.get("fixAvailable") else "",
                detail=via.get("title", ""),
            ))
    return list(seen.values())


def parse_trivy(data: dict) -> list[Finding]:
    """HIGH/CRITICAL with a fix available, plus any CRITICAL. One per CVE."""
    if "ArtifactName" not in data:
        raise ValueError("not a trivy report")
    by_id: dict[str, dict] = {}
    for result in data.get("Results") or []:
        for v in result.get("Vulnerabilities") or []:
            sev, fixed = v.get("Severity"), v.get("FixedVersion") or ""
            if not (sev == "CRITICAL" or (sev == "HIGH" and fixed)):
                continue
            row = by_id.setdefault(v["VulnerabilityID"], {
                "sev": sev, "fixed": fixed, "pkgs": set(),
                "eco": result.get("Type", "image"), "title": v.get("Title", ""),
            })
            row["pkgs"].add(v["PkgName"])
    return [
        Finding(id=cve, category="image-cve", ecosystem=r["eco"],
                package=", ".join(sorted(r["pkgs"])), severity=r["sev"],
                fixed=r["fixed"], detail=r["title"])
        for cve, r in by_id.items()
    ]


def parse_zizmor(data: list) -> list[Finding]:
    seen: dict[tuple[str, str], Finding] = {}
    for item in data:
        if item.get("determinations", {}).get("severity") != "High":
            continue
        loc = item["locations"][0]
        local = loc["symbolic"]["key"]["Local"]
        path = local.get("verbatim_path") or local["given_path"]
        line = loc["concrete"]["location"]["start_point"]["row"] + 1
        key = (item["ident"], path)
        if key not in seen:
            seen[key] = Finding(
                id=f"zizmor/{item['ident']}", category="actions", ecosystem="actions",
                package=path, severity="HIGH", detail=f"first at line {line}",
            )
    return list(seen.values())


def parse_live(data: list) -> list[Finding]:
    return [Finding(**{**d, "aliases": tuple(d.get("aliases", ()))}) for d in data]


PARSERS = {
    "pip-audit.json": parse_pip_audit,
    "npm-audit.json": parse_npm_audit,
    "zizmor.json": parse_zizmor,
    "trivy.json": parse_trivy,
    "live.json": parse_live,
}


# ── issue planning ───────────────────────────────────────────────────────


def plan_issues(
    findings: list[Finding],
    ok: set[str],
    open_issues: list[dict],
    broken: list[str] | None = None,
) -> dict:
    """Decide issue actions. `ok` = categories whose scanners all ran cleanly;
    an issue is only closed when the scanner that would re-find it ran."""
    broken = broken or []
    by_title = {i["title"]: i for i in open_issues}
    current = {f.title for f in findings}
    plan: dict[str, list] = {"create": [], "close": [], "comment": []}

    for f in findings:
        if f.title not in by_title:
            plan["create"].append({
                "title": f.title,
                "labels": ["security", f.category],
                "body": _finding_body(f),
            })

    for issue in open_issues:
        # Only touch issues this scan filed; hand-filed ones may share labels.
        if issue["title"] == BROKEN_TITLE or not issue["title"].startswith(TITLE_PREFIX):
            continue
        cat = next((lbl for lbl in issue["labels"] if lbl in SCANNERS.values()), None)
        if cat in ok and issue["title"] not in current:
            plan["close"].append(issue["number"])

    broken_issue = by_title.get(BROKEN_TITLE)
    if broken:
        text = "\n".join(f"- {b}" for b in broken)
        if broken_issue:
            plan["comment"].append({"number": broken_issue["number"], "body": f"Still broken:\n{text}"})
        else:
            plan["create"].append({
                "title": BROKEN_TITLE,
                "labels": ["security", "scan-broken"],
                "body": ("The nightly security scan could not complete, so its "
                         f"results are incomplete — not clean.\n\n{text}"),
            })
    elif broken_issue:
        plan["close"].append(broken_issue["number"])
    return plan


def _finding_body(f: Finding) -> str:
    rows = [
        ("Advisory", f.id), ("Package", f.package), ("Ecosystem", f.ecosystem),
        ("Severity", f.severity), ("Fixed in", f.fixed or "no fix yet"),
    ]
    if f.aliases:
        rows.append(("Aliases", ", ".join(f.aliases)))
    if f.detail:
        rows.append(("Detail", f.detail))
    table = "\n".join(f"| {k} | {v} |" for k, v in rows)
    return (
        f"Found by the nightly security scan.\n\n| | |\n|---|---|\n{table}\n\n"
        "Fix it, or accept it with an expiring entry in "
        "`.github/security-allowlist.toml`. The scan closes this issue once "
        "the finding is gone."
    )


# ── live checks ──────────────────────────────────────────────────────────


def _live(id_: str, package: str, detail: str) -> dict:
    return asdict(Finding(id=id_, category="live-config", ecosystem="live",
                          package=package, severity="HIGH", detail=detail))


def check_http(c) -> list[dict]:
    """Headers, exposed paths and origin bypass, through client `c`."""
    import httpx

    out: list[dict] = []
    root = c.get(f"https://{PROD}/")
    # A WAF challenge or error page would make every probe read "not exposed".
    if root.status_code != 200 or APP_MARKER not in root.text:
        raise RuntimeError(f"{PROD}/ is not serving the app (HTTP {root.status_code})")
    h = root.headers
    csp = h.get("content-security-policy", "")
    required = {
        "strict-transport-security": "strict-transport-security" in h,
        "content-security-policy": bool(csp),
        "x-content-type-options": h.get("x-content-type-options", "").lower() == "nosniff",
        "frame protection": "x-frame-options" in h or "frame-ancestors" in csp,
    }
    for name, present in required.items():
        if not present:
            out.append(_live("missing-header", f"{PROD} {name}", f"{name} not set on /"))

    # The SPA answers unknown paths with index.html + 200, so judge by body.
    probes = {
        "/openapi.json": lambda r: "application/json" in r.headers.get("content-type", ""),
        "/docs": lambda r: "swagger-ui" in r.text.lower(),
        "/.git/HEAD": lambda r: r.text.startswith("ref:"),
        "/.env": lambda r: r.status_code == 200 and "<html" not in r.text[:500].lower(),
    }
    for path, exposed in probes.items():
        r = c.get(f"https://{PROD}{path}")
        if r.status_code == 200 and exposed(r):
            out.append(_live("exposed-path", f"{PROD}{path}", f"served with {r.headers.get('content-type')}"))

    try:
        r = c.get(f"https://{ORIGIN}/healthz")
    except httpx.TransportError:
        return out  # origin not reachable directly: no bypass
    if r.status_code == 200:
        out.append(_live("origin-bypass", ORIGIN,
                         "Fly origin answers directly, skipping Cloudflare WAF/cache/rate rules"))
    return out


def run_live_checks() -> list[dict]:
    import httpx  # project dependency; deferred so `check` needs no install

    out: list[dict] = []

    ctx = ssl.create_default_context()
    with (
        socket.create_connection((PROD, 443), timeout=15) as sock,
        ctx.wrap_socket(sock, server_hostname=PROD) as tls,
    ):
        not_after = tls.getpeercert()["notAfter"]
    expires = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
    days = (expires - datetime.now(UTC)).days
    if days < TLS_MIN_DAYS:
        out.append(_live("tls-expiring", PROD, f"certificate expires in {days} days ({not_after})"))

    with httpx.Client(timeout=20, follow_redirects=False) as c:
        out += check_http(c)
    return out


# ── CLI ──────────────────────────────────────────────────────────────────


def collect(scan_dir: Path, expect: list[str]) -> tuple[list[Finding], set[str], list[str]]:
    findings: list[Finding] = []
    broken: list[str] = []
    failed_cats: set[str] = set()
    for name in expect:
        path = scan_dir / name
        try:
            findings += PARSERS[name](json.loads(path.read_text()))
        except Exception as e:  # missing, empty or malformed = scanner broke
            broken.append(f"{name}: {type(e).__name__}: {e}")
            failed_cats.add(SCANNERS[name])
    ok = {SCANNERS[n] for n in expect} - failed_cats
    return findings, ok, broken


def write_summary(kept, suppressed, expired, broken) -> None:
    lines = [f"### Security scan: {len(kept)} finding(s)\n"]
    if kept:
        lines += ["| Severity | Advisory | Package | Fixed in |", "|---|---|---|---|"]
        lines += [f"| {f.severity} | {f.id} | {f.package} ({f.ecosystem}) | {f.fixed or '—'} |" for f in kept]
    for e in expired:
        lines.append(f"- ❌ allowlist entry `{e['id']}` expired or has no `expires` — re-review it")
    for b in broken:
        lines.append(f"- ❌ scanner broken: {b}")
    if suppressed:
        lines.append(f"\n{len(suppressed)} allowlisted: " + ", ".join(sorted({f.id for f in suppressed})))
    text = "\n".join(lines)
    print(text)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a") as fh:
            fh.write(text + "\n")


def cmd_check(args) -> int:
    allowed, expired = load_allowlist(Path(args.allowlist).read_text(), date.today())
    findings, ok, broken = collect(Path(args.dir), args.expect)
    kept, suppressed = apply_allowlist(findings, allowed)
    broken += [f"allowlist entry {e['id']} expired or undated" for e in expired]
    write_summary(kept, suppressed, expired, broken[:len(broken) - len(expired)])
    Path(args.out).write_text(json.dumps({
        "findings": [asdict(f) for f in kept], "ok": sorted(ok), "broken": broken,
    }, indent=2))
    return 1 if kept or broken else 0


def _gh(*args: str, input_: str | None = None) -> str:
    return subprocess.run(["gh", *args], check=True, text=True,
                          capture_output=True, input=input_).stdout


def cmd_file_issues(args) -> int:
    data = json.loads(Path(args.findings).read_text())
    findings = [Finding(**{**f, "aliases": tuple(f["aliases"])}) for f in data["findings"]]
    raw = json.loads(_gh("issue", "list", "--label", "security", "--state", "open",
                         "--limit", "200", "--json", "number,title,labels"))
    open_issues = [{**i, "labels": [lbl["name"] for lbl in i["labels"]]} for i in raw]
    plan = plan_issues(findings, set(data["ok"]), open_issues, data["broken"])
    for c in plan["create"]:
        for label in c["labels"]:
            _gh("label", "create", label, "--force", "--color", "B60205")
        url = _gh("issue", "create", "--title", c["title"], "--body", c["body"],
                  *[x for lbl in c["labels"] for x in ("--label", lbl)]).strip()
        print(f"opened {url}")
    for c in plan["comment"]:
        _gh("issue", "comment", str(c["number"]), "--body", c["body"])
    for n in plan["close"]:
        _gh("issue", "close", str(n), "--comment", "No longer found by the nightly security scan.")
        print(f"closed #{n}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    live = sub.add_parser("live")
    live.add_argument("--out", required=True)
    chk = sub.add_parser("check")
    chk.add_argument("--dir", required=True)
    chk.add_argument("--allowlist", default=".github/security-allowlist.toml")
    chk.add_argument("--expect", nargs="+", choices=sorted(PARSERS), required=True)
    chk.add_argument("--out", default="findings.json")
    fi = sub.add_parser("file-issues")
    fi.add_argument("findings")
    args = p.parse_args()

    if args.cmd == "live":
        Path(args.out).write_text(json.dumps(run_live_checks(), indent=2))
        return 0
    if args.cmd == "check":
        return cmd_check(args)
    return cmd_file_issues(args)


if __name__ == "__main__":
    sys.exit(main())
