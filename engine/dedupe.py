
import json
from urllib.parse import urlsplit,urlunsplit
def norm(url):
    p=urlsplit(url); return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip("/"),p.query,""))
def load_seen(path):
    return json.loads(path.read_text()) if path.exists() else {"urls":[],"hashes":[]}
def seen(item,digest,state):
    return norm(item["url"]) in state["urls"] or bool(digest and digest in state["hashes"])
def mark(item,digest,state):
    state["urls"]=(state["urls"]+[norm(item["url"])])[-10000:]
    if digest: state["hashes"]=(state["hashes"]+[digest])[-10000:]
