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
    return [s for s in sources if isinstance(s, dict) and s.get("enabled")]
