import csv, hashlib, json, logging
from datetime import datetime, timezone
from .config import DATA, LOGS, DOWNLOADS, load_sources, GEMINI_MODEL
from .collector import fetch_source, download_pdf
from .pdf_text import extract_pdf_text
from .ai_extract import extract_with_ai
from .dedupe import load_seen, seen, mark

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOGS / "latest_scan.log", encoding="utf-8"),
              logging.StreamHandler()]
)
log = logging.getLogger("job-alert")

def read_queue(path):
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8").strip())
    except (json.JSONDecodeError, OSError) as exc:
        try:
            path.with_suffix(".corrupt.json").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        except OSError:
            pass
        log.error("Invalid queue JSON (%s); starting an empty queue", exc)
        return []
    if not isinstance(value, list):
        log.error("Queue JSON root is not a list; starting empty")
        return []
    return [x for x in value if isinstance(x, dict) and x.get("id")]

def write_json(path, value):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)

def main():
    queue_path, seen_path = DATA / "review_queue.json", DATA / "seen_items.json"
    queue, state = read_queue(queue_path), load_seen(seen_path)
    ids = {x["id"] for x in queue}
    added = candidates = errors = 0
    sources = load_sources()
    log.info("Scan started: %s enabled sources; Gemini model=%s", len(sources), GEMINI_MODEL)

    for source in sources:
        name = source.get("name", "(unnamed source)")
        try:
            items = fetch_source(source)
        except Exception as exc:
            errors += 1
            log.exception("Source failed %s: %s", name, exc)
            continue
        for item in items:
            candidates += 1
            try:
                if seen(item, None, state):
                    continue
                digest = local = None
                if item["kind"] == "pdf":
                    local, digest = download_pdf(item, DOWNLOADS)
                    if seen(item, digest, state):
                        mark(item, digest, state)
                        continue
                    body = extract_pdf_text(local)
                    draft = extract_with_ai(body, item["title"], item["url"])
                else:
                    body = f"Discovered page: {item['title']}\n{item['url']}"
                    draft = {"status": "needs_source_adapter",
                             "raw_text_excerpt": body,
                             "note": "Page-specific HTML extraction is not implemented yet."}
                ident = hashlib.sha256((item["url"] + (digest or "")).encode()).hexdigest()[:16]
                if ident in ids:
                    mark(item, digest, state)
                    continue
                queue.append({
                    "id": ident,
                    "detected_at_utc": datetime.now(timezone.utc).isoformat(),
                    "source_name": item.get("source_name", name),
                    "source_page": item.get("source_url"),
                    "candidate_title": item.get("title"),
                    "candidate_url": item.get("url"),
                    "document_sha256": digest,
                    "local_pdf": str(local.relative_to(DATA)) if local else None,
                    "review_status": "pending_review",
                    "human_verified": False,
                    "ai_draft": draft
                })
                ids.add(ident)
                mark(item, digest, state)
                added += 1
            except Exception as exc:
                errors += 1
                log.exception("Candidate failed %s: %s", item.get("url"), exc)

    write_json(queue_path, queue)
    write_json(seen_path, state)
    columns = ["id","detected_at_utc","source_name","candidate_title","candidate_url",
               "review_status","human_verified","notice_type","organisation",
               "advertisement_number","vacancy_count","application_end_date","summary"]
    with (DATA / "review_queue.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in queue:
            draft = row.get("ai_draft") if isinstance(row.get("ai_draft"), dict) else {}
            writer.writerow({**{k: row.get(k) for k in columns[:7]},
                             **{k: draft.get(k) for k in columns[7:]}})
    log.info("Scan complete: candidates=%s added=%s queue=%s errors=%s",
             candidates, added, len(queue), errors)

if __name__ == "__main__":
    main()
