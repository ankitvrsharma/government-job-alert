
from urllib.parse import urljoin, urlparse
import time, requests
from bs4 import BeautifulSoup
UA = "GovernmentJobAlertBot/0.1 (public-notice monitor)"
def allowed(url, domains):
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in domains)
def fetch_source(source):
    r = requests.get(source["url"], headers={"User-Agent":UA}, timeout=25)
    r.raise_for_status()
    ct = r.headers.get("Content-Type","").lower()
    if "pdf" in ct or r.url.lower().endswith(".pdf"):
        return [{"title":source["name"],"url":r.url,"kind":"pdf","source_name":source["name"],"source_url":source["url"]}]
    soup = BeautifulSoup(r.text, "html.parser")
    out, keys = [], [k.lower() for k in source.get("keywords",[])]
    for a in soup.find_all("a", href=True):
        url = urljoin(r.url, a["href"].strip())
        title = " ".join(a.get_text(" ", strip=True).split()) or url.rsplit("/",1)[-1]
        if not allowed(url, source.get("allowed_domains",[])): continue
        pdf = urlparse(url).path.lower().endswith(".pdf")
        if pdf or any(k in (title+" "+url).lower() for k in keys):
            out.append({"title":title[:300],"url":url,"kind":"pdf" if pdf else "web","source_name":source["name"],"source_url":source["url"]})
        if len(out) >= 80: break
    time.sleep(1.5)
    return out
def download_pdf(item, folder):
    r = requests.get(item["url"], headers={"User-Agent":UA}, timeout=30)
    r.raise_for_status()
    data = r.content
    if not data.startswith(b"%PDF"): raise ValueError("Not a PDF response")
    import hashlib
    digest = hashlib.sha256(data).hexdigest()
    path = folder / (digest[:20]+".pdf")
    path.write_bytes(data)
    return path, digest
