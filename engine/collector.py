from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import hashlib, logging, time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

UA = "GovernmentJobAlertBot/1.1 (public recruitment notice monitor)"
log = logging.getLogger("job-alert")

def session():
    retry = Retry(total=1, connect=1, read=1, status=1, backoff_factor=0.4,
                  status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=frozenset(["GET"]))
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s

HTTP = session()

def allowed(url, domains):
    host = (urlparse(url).hostname or "").lower()
    return any(host == d.lower() or host.endswith("." + d.lower()) for d in domains)

def robots_allowed(url):
    p = urlparse(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    try:
        response = HTTP.get(robots_url, timeout=(5, 8))
        if response.status_code == 404:
            return True
        response.raise_for_status()
        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser.can_fetch(UA, url)
    except requests.RequestException as exc:
        log.warning("Cannot verify robots.txt for %s; skipping: %s", url, exc)
        return False

def fetch_source(source):
    source_url = source.get("url")
    name = source.get("name", source_url or "Unknown source")
    if not source_url:
        raise ValueError("Source is missing URL")
    if not robots_allowed(source_url):
        log.info("Skipped by robots policy: %s", name)
        return []
    response = HTTP.get(source_url, timeout=(6, 18))
    response.raise_for_status()
    final_url = response.url
    ctype = response.headers.get("Content-Type", "").lower()
    if "pdf" in ctype or urlparse(final_url).path.lower().endswith(".pdf"):
        return [{"title": name, "url": final_url, "kind": "pdf",
                 "source_name": name, "source_url": source_url}]
    soup = BeautifulSoup(response.text, "html.parser")
    domains = list(source.get("allowed_domains", []))
    host = urlparse(final_url).hostname
    if host and host not in domains:
        domains.append(host)
    keywords = [str(k).lower() for k in source.get("keywords", [])]
    items, found = [], set()
    for a in soup.find_all("a", href=True):
        url = urljoin(final_url, a["href"].strip()).split("#", 1)[0]
        if urlparse(url).scheme not in ("http", "https") or not allowed(url, domains):
            continue
        title = " ".join(a.get_text(" ", strip=True).split()) or url.rsplit("/", 1)[-1]
        pdf = urlparse(url).path.lower().endswith(".pdf")
        if not (pdf or any(k in (title + " " + url).lower() for k in keywords)):
            continue
        if url in found:
            continue
        found.add(url)
        items.append({"title": title[:300], "url": url, "kind": "pdf" if pdf else "web",
                      "source_name": name, "source_url": source_url})
        if len(items) >= 80:
            break
    time.sleep(1)
    return items

def download_pdf(item, folder, max_bytes=25 * 1024 * 1024):
    if not robots_allowed(item["url"]):
        raise PermissionError("robots.txt does not permit this PDF URL")
    with HTTP.get(item["url"], timeout=(6, 25), stream=True) as response:
        response.raise_for_status()
        size = response.headers.get("Content-Length")
        if size and int(size) > max_bytes:
            raise ValueError("PDF exceeds 25 MB download limit")
        digest = hashlib.sha256()
        chunks, total = [], 0
        for chunk in response.iter_content(65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("PDF exceeds 25 MB download limit")
            digest.update(chunk)
            chunks.append(chunk)
    data = b"".join(chunks)
    if not data.startswith(b"%PDF"):
        raise ValueError("Response is not a PDF")
    hexdigest = digest.hexdigest()
    path = folder / (hexdigest[:20] + ".pdf")
    path.write_bytes(data)
    return path, hexdigest
