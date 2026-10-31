import csv, hashlib, json, logging, time
from datetime import datetime, timezone
from .config import DATA, LOGS, DOWNLOADS, load_sources, GEMINI_MODEL, SCAN_TIME_BUDGET_SECONDS
from .collector import fetch_source, download_pdf, extract_web_text
from .pdf_text import extract_pdf_text
from .ai_extract import extract_with_ai
from .dedupe import load_seen, seen, mark, norm

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

def is_complete_vacancy(row):
    draft = row.get("ai_draft") if isinstance(row.get("ai_draft"), dict) else {}
    posts = draft.get("post_names")
    return (
        draft.get("status") == "ai_draft"
        and draft.get("is_recruitment_notice") is True
        and isinstance(posts, list) and any(str(post).strip() for post in posts)
        and bool(str(draft.get("recruitment_evidence") or "").strip())
        and len(str(draft.get("summary") or "").strip()) >= 40
    )

def notice_key(draft):
    ad = str(draft.get('advertisement_number') or '').strip().lower()
    org = str(draft.get('organisation') or '').strip().lower()
    posts = '|'.join(sorted(str(x).strip().lower() for x in (draft.get('post_names') or []) if str(x).strip()))
    identity = ad or posts
    return hashlib.sha256((org + '|' + identity).encode('utf-8')).hexdigest() if org and identity else ''

def changed_fields(old, new):
    labels = {'post_names':'Posts','vacancy_count':'Vacancy count','qualification':'Qualification','age_limit':'Age limit','application_start_date':'Application start date','application_end_date':'Last date','application_fee':'Application fee','selection_process':'Selection process','application_url':'Application link'}
    changes = []
    for field, label in labels.items():
        before = '; '.join(old.get(field) or []) if isinstance(old.get(field), list) else str(old.get(field) or '').strip()
        after = '; '.join(new.get(field) or []) if isinstance(new.get(field), list) else str(new.get(field) or '').strip()
        if before != after and after:
            changes.append(label + ': ' + (before or 'Not stated') + ' -> ' + after)
    return changes

def main():
    queue_path, seen_path = DATA / "review_queue.json", DATA / "seen_items.json"
    old_queue = read_queue(queue_path)
    queue = [row for row in old_queue if is_complete_vacancy(row)]
    removed = len(old_queue) - len(queue)
    if removed:
        log.info("Removed %s incomplete/non-vacancy records from the review queue.", removed)
    state = load_seen(seen_path)
    ids = {x["id"] for x in queue}
    added = candidates = errors = 0
    started = time.monotonic()
    deadline = started + SCAN_TIME_BUDGET_SECONDS
    sources = load_sources()
    log.info("Scan started: %s enabled sources; Gemini model=%s", len(sources), GEMINI_MODEL)

    for source in sources:
        if time.monotonic() >= deadline:
            log.warning("Scan time budget reached; stopping discovery safely before the workflow timeout.")
            break
        name = source.get("name", "(unnamed source)")
        try:
            items = fetch_source(source)
        except Exception as exc:
            errors += 1
            log.exception("Source failed %s: %s", name, exc)
            continue
        for item in items:
            if time.monotonic() >= deadline:
                log.warning("Scan time budget reached while processing %s; remaining items will be rediscovered next run.", name)
                break
            candidates += 1
            try:
                url_key = norm(item["url"])
                digest = local = None
                if item["kind"] == "pdf":
                    local, digest = download_pdf(item, DOWNLOADS)
                    body = extract_pdf_text(local)
                else:
                    body = extract_web_text(item)
                    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()

                previous_fingerprint = state.setdefault("snapshots", {}).get(url_key)
                if previous_fingerprint == digest:
                    continue
                if previous_fingerprint is None and url_key in state["urls"]:
                    state["snapshots"][url_key] = digest
                    mark(item, digest, state)
                    log.info("Baseline fingerprint saved; no retroactive post: %s", item.get("title"))
                    continue

                draft = extract_with_ai(body, item["title"], item["url"])

                # Never queue title-only, unreadable, non-vacancy or uncertain candidates.
                if draft.get("status") != "ai_draft":
                    log.info("Not queued: extraction incomplete for %s (%s)", item.get("title"), draft.get("status"))
                    continue
                posts = draft.get("post_names")
                evidence = str(draft.get("recruitment_evidence") or "").strip()
                summary = str(draft.get("summary") or "").strip()
                if (draft.get("is_recruitment_notice") is not True
                        or not isinstance(posts, list) or not any(str(p).strip() for p in posts)
                        or not evidence or len(summary) < 40):
                    log.info("Not queued: no verifiable vacancy evidence/content for %s", item.get("title"))
                    state["snapshots"][url_key] = digest
                    mark(item, digest, state)
                    continue

                stable_key = notice_key(draft)
                registry = state.setdefault("notice_registry", {})
                prior = registry.get(stable_key) if stable_key else None
                changes = changed_fields(prior.get("draft", {}) if prior else {}, draft) if prior else []
                if prior and not changes:
                    state["snapshots"][url_key] = digest
                    mark(item, digest, state)
                    log.info("Content changed but recruitment details did not; no post generated: %s", item.get("title"))
                    continue

                ident = hashlib.sha256((item["url"] + (digest or "")).encode()).hexdigest()[:16]
                if ident in ids:
                    existing = next((row for row in queue if row.get("id") == ident), None)
                    old_draft = existing.get("ai_draft", {}) if existing else {}
                    if existing and isinstance(old_draft, dict) and old_draft.get("status") in ("ai_quota_exceeded", "ai_error", "ai_deferred") and draft.get("status") == "ai_draft":
                        existing["ai_draft"] = draft
                        log.info("Updated AI draft for previously queued candidate: %s", ident)
                    if draft.get("status") not in ("ai_quota_exceeded", "ai_deferred", "ai_error"):
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
                    "post_type": ("deadline_extension" if any(change.startswith("Last date:") for change in changes) else "update") if prior else "new",
                    "previous_post_id": prior.get("id") if prior else None,
                    "change_summary": changes,
                    "ai_draft": draft
                })
                if stable_key:
                    registry[stable_key] = {"id": ident, "draft": draft, "updated_at": datetime.now(timezone.utc).isoformat()}
                state["snapshots"][url_key] = digest
                ids.add(ident)
                if draft.get("status") not in ("ai_quota_exceeded", "ai_deferred", "ai_error"):
                    mark(item, digest, state)
                else:
                    log.info("Candidate retained for later AI retry (%s): %s", draft.get("status"), ident)
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
    log.info("Scan complete: candidates=%s added=%s queue=%s errors=%s elapsed_seconds=%.1f",
             candidates, added, len(queue), errors, time.monotonic() - started)

if __name__ == "__main__":
    main()
