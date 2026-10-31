from pathlib import Path
import json, os

ROOT = Path(__file__).resolve().parents[1]
DATA, LOGS = ROOT / "data", ROOT / "logs"
DOWNLOADS = DATA / "downloads"
for directory in (DATA, LOGS, DOWNLOADS):
    directory.mkdir(parents=True, exist_ok=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "").strip() or "gemini-3.8-flash"

def load_sources():
    payload = json.loads((ROOT / "sources" / "sources.json").read_text(encoding="utf-8"))
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, list):
        raise ValueError("sources/sources.json must contain a 'sources' list")
    return [s for s in sources if isinstance(s, dict) and s.get("enabled")]
