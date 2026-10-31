from pathlib import Path
import json, os

ROOT = Path(__file__).resolve().parents[1]
DATA, LOGS = ROOT / "data", ROOT / "logs"
DOWNLOADS = DATA / "downloads"
for directory in (DATA, LOGS, DOWNLOADS):
    directory.mkdir(parents=True, exist_ok=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "").strip() or "gemini-3.8-flash"
# Ordered newest-to-older fallback chain. Override with GEMINI_FALLBACK_MODELS if needed.
_DEFAULT_FALLBACKS = ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
GEMINI_FALLBACK_MODELS = [
    model.strip() for model in (os.getenv("GEMINI_FALLBACK_MODELS", "").strip() or ",".join(_DEFAULT_FALLBACKS)).split(",")
    if model.strip() and model.strip() != GEMINI_MODEL
]
MAX_AI_REQUESTS_PER_SCAN = max(1, int(os.getenv("MAX_AI_REQUESTS_PER_SCAN", "45")))
SCAN_TIME_BUDGET_SECONDS = max(300, int(os.getenv("SCAN_TIME_BUDGET_SECONDS", "1320")))

def load_sources():
    payload = json.loads((ROOT / "sources" / "sources.json").read_text(encoding="utf-8"))
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, list):
        raise ValueError("sources/sources.json must contain a 'sources' list")
    merged = [s for s in sources if isinstance(s, dict) and s.get("enabled")]

    # Admin-added URLs live in Supabase so an administrator can add them
    # without committing source-code changes. The service key stays in Actions.
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if service_key:
        import requests
        base_url = os.getenv("SUPABASE_URL", "https://xmjstmebdbmplsdhrspt.supabase.co").rstrip("/")
        response = requests.get(
            f"{base_url}/rest/v1/tracked_sources",
            params={"select": "name,url,category,allowed_domains,keywords,enabled", "enabled": "eq.true", "order": "created_at.asc", "limit": "500"},
            headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
            timeout=15,
        )
        response.raise_for_status()
        known = {str(x.get("url", "")).rstrip("/") for x in merged}
        for row in response.json():
            url = str(row.get("url", "")).strip()
            if not url or url.rstrip("/") in known:
                continue
            merged.append({
                "name": row.get("name") or url,
                "url": url,
                "category": row.get("category") or "Admin added",
                "enabled": True,
                "allowed_domains": row.get("allowed_domains") or [],
                "keywords": row.get("keywords") or [],
            })
            known.add(url.rstrip("/"))
        print(f"Loaded {len(response.json())} admin-managed source URLs from Supabase.")
    else:
        print("SUPABASE_SERVICE_ROLE_KEY not configured; admin-added source URLs will not be loaded in this scan.")
    return merged
