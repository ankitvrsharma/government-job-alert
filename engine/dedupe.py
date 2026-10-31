import json
from urllib.parse import urlsplit, urlunsplit

def norm(url):
    p = urlsplit(str(url).strip())
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/"), p.query, ""))

def load_seen(path):
    if not path.exists():
        return {"urls": [], "hashes": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8").strip())
    except (json.JSONDecodeError, OSError):
        return {"urls": [], "hashes": []}
    if not isinstance(value, dict):
        return {"urls": [], "hashes": []}
    urls, hashes = value.get("urls", []), value.get("hashes", [])
    return {
        "urls": [norm(x) for x in urls if isinstance(x, str)] if isinstance(urls, list) else [],
        "hashes": [x for x in hashes if isinstance(x, str)] if isinstance(hashes, list) else []
    }

def seen(item, digest, state):
    return norm(item["url"]) in state["urls"] or bool(digest and digest in state["hashes"])

def mark(item, digest, state):
    url = norm(item["url"])
    if url not in state["urls"]:
        state["urls"] = (state["urls"] + [url])[-10000:]
    if digest and digest not in state["hashes"]:
        state["hashes"] = (state["hashes"] + [digest])[-10000:]
