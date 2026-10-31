from pathlib import Path
import json, os

ROOT = Path(__file__).resolve().parents[1]
DATA, LOGS = ROOT / "data", ROOT / "logs"
DOWNLOADS = DATA / "downloads"
for p in (DATA, LOGS, DOWNLOADS):
    p.mkdir(parents=True, exist_ok=True)

def load_sources():
    return json.loads(
        (ROOT / "sources/sources.json").read_text(encoding="utf-8")
    )["sources"]

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Gemini 3.8 Flash is the default; override with the GEMINI_MODEL Actions variable if needed.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
