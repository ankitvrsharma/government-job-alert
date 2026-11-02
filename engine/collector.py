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
        extension = urlparse(url).path.lower().rsplit(".", 1)[-1] if "." in urlparse(url).path else ""
        file_extensions = {"pdf", "zip", "xlsx", "docx", "csv"}
        is_file = extension in file_extensions
        if not (is_file or any(k in (title + " " + url).lower() for k in keywords)):
            continue
        if url in found:
            continue
        found.add(url)
        kind = "pdf" if extension == "pdf" else "file" if is_file else "web"
        items.append({"title": title[:300], "url": url, "kind": kind,
                      "source_name": name, "source_url": source_url})
        if len(items) >= 80:
            break
    time.sleep(1)
    return items


def extract_web_text(item, max_chars=60000):
    """Fetch readable page content; never send a title/URL-only placeholder to AI."""
    if not robots_allowed(item["url"]):
        raise PermissionError("robots.txt does not permit this page URL")
    response = HTTP.get(item["url"], timeout=(6, 18))
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "").lower()
    if "html" not in content_type and not response.text.lstrip().startswith("<"):
        raise ValueError("Candidate page is not HTML")
    soup = BeautifulSoup(response.text, "html.parser")
    for node in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        node.decompose()
    page_text = " ".join(soup.get_text(" ", strip=True).split())
    if len(page_text) < 250:
        raise ValueError("Candidate page contains too little readable text")
    return page_text[:max_chars]

ATTACHMENT_TYPES = {
    ".pdf": "application/pdf",
    ".zip": "application/zip",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".csv": "text/csv",
}

def download_attachment(item, folder, max_bytes=25 * 1024 * 1024):
    if not robots_allowed(item["url"]):
        raise PermissionError("robots.txt does not permit this attachment URL")
    from pathlib import Path
    extension = Path(urlparse(item["url"]).path).suffix.lower()
    if not extension and item.get("kind") == "pdf":
        extension = ".pdf"
    with HTTP.get(item["url"], timeout=(6, 25), stream=True) as response:
        response.raise_for_status()
        if not extension:
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            extension = next((ext for ext, mime_type in ATTACHMENT_TYPES.items() if mime_type == content_type), "")
        mime = ATTACHMENT_TYPES.get(extension)
        if not mime:
            raise ValueError("Unsupported official attachment type")
        size = response.headers.get("Content-Length")
        if size and int(size) > max_bytes:
            raise ValueError("Official attachment exceeds 25 MB download limit")
        digest = hashlib.sha256()
        chunks, total = [], 0
        for chunk in response.iter_content(65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("Official attachment exceeds 25 MB download limit")
            digest.update(chunk)
            chunks.append(chunk)
    data = b"".join(chunks)
    if extension == ".pdf" and not data.startswith(b"%PDF"):
        raise ValueError("Response is not a PDF")
    if extension != ".pdf" and data.lstrip().startswith(b"<html"):
        raise ValueError("Attachment URL returned an HTML page instead of a file")
    hexdigest = digest.hexdigest()
    path = folder / (hexdigest[:20] + extension)
    path.write_bytes(data)
    return path, hexdigest, mime


def download_pdf(item, folder, max_bytes=25 * 1024 * 1024):
    path, digest, _ = download_attachment(item, folder, max_bytes)
    if path.suffix.lower() != ".pdf":
        raise ValueError("Candidate is not a PDF")
    return path, digest
