"""Static quality audit for the official-source registry.

This checks registry completeness and configuration quality. It does NOT claim
that a website was reachable or that every notice on it was discovered.
"""
import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "sources" / "sources.json"
OUT_JSON = ROOT / "data" / "source_registry_audit.json"
OUT_CSV = ROOT / "data" / "source_registry_audit.csv"

def audit_registry(payload):
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, list):
        raise ValueError("Registry must contain a sources list")
    rows, issues, seen_urls = [], [], {}
    for index, source in enumerate(sources, start=1):
        if not isinstance(source, dict):
            issues.append({"index": index, "name": "", "issue": "Source entry is not an object"})
            continue
        name = str(source.get("name") or "").strip()
        url = str(source.get("url") or "").strip()
        parsed = urlparse(url)
        enabled = source.get("enabled") is True
        domains = source.get("allowed_domains") if isinstance(source.get("allowed_domains"), list) else []
        keywords = source.get("keywords") if isinstance(source.get("keywords"), list) else []
        category = str(source.get("category") or "").strip()
        row_issues = []
        if not name: row_issues.append("missing_name")
        if parsed.scheme != "https" or not parsed.hostname: row_issues.append("url_not_valid_https")
        if not category: row_issues.append("missing_category")
        if not domains: row_issues.append("missing_allowed_domains")
        if not keywords: row_issues.append("missing_keywords")
        if url:
            key = url.rstrip("/").lower()
            if key in seen_urls:
                row_issues.append("duplicate_url")
                issues.append({"index": index, "name": name, "issue": "duplicate_url", "duplicate_of": seen_urls[key]})
            else:
                seen_urls[key] = name or f"entry_{index}"
        for issue in row_issues:
            if issue != "duplicate_url":
                issues.append({"index": index, "name": name, "issue": issue})
        rows.append({
            "name": name, "url": url, "category": category or "Unclassified",
            "enabled": enabled, "host": parsed.hostname or "",
            "allowed_domains_count": len(domains), "keywords_count": len(keywords),
            "issues": ";".join(row_issues) or "none",
        })
    categories = Counter(r["category"] for r in rows if r["enabled"])
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "registry_version": payload.get("version") if isinstance(payload, dict) else None,
        "total_entries": len(sources),
        "valid_object_entries": len(rows),
        "enabled_entries": sum(1 for r in rows if r["enabled"]),
        "disabled_entries": sum(1 for r in rows if not r["enabled"]),
        "entries_with_issues": sum(1 for r in rows if r["issues"] != "none"),
        "issue_count": len(issues),
        "enabled_categories": dict(sorted(categories.items())),
        "issues": issues,
        "scope_note": "Registry configuration audit only; it does not test site availability, robots permission, crawl completeness, or vacancy accuracy."
    }
    return summary, rows

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Exit non-zero when registry configuration issues exist.")
    args = parser.parse_args()
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    summary, rows = audit_registry(payload)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name","url","category","enabled","host","allowed_domains_count","keywords_count","issues"])
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({k:v for k,v in summary.items() if k not in ("issues","enabled_categories")}, indent=2))
    if args.check and summary["issue_count"]:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
