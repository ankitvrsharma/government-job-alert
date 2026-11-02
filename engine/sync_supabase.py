import csv
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests

BASE_URL = os.getenv("SUPABASE_URL", "https://xmjstmebdbmplsdhrspt.supabase.co").rstrip("/")
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
QUEUE = DATA / "review_queue.json"
BUCKET = "official-updates"
QUEUE_RETENTION_DAYS = 45
RESULT_ARCHIVE_DAYS = 180
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


def headers(extra=None):
    value = {
        "apikey": KEY,
        "Authorization": f"Bearer {KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        value.update(extra)
    return value


def api_get(table, params):
    response = requests.get(f"{BASE_URL}/rest/v1/{table}", params=params,
                            headers=headers(), timeout=30)
    response.raise_for_status()
    return response.json()


def api_upsert(table, rows, conflict):
    returned = []
    for start in range(0, len(rows), 50):
        batch = rows[start:start + 50]
        response = requests.post(
            f"{BASE_URL}/rest/v1/{table}",
            params={"on_conflict": conflict},
            headers=headers({"Prefer": "resolution=merge-duplicates,return=representation"}),
            json=batch,
            timeout=45,
        )
        response.raise_for_status()
        if response.content:
            returned.extend(response.json())
    return returned


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def exam_names(draft):
    names = []
    for value in [draft.get("exam_name"), *(draft.get("related_exams") or [])]:
        name = clean(value)
        if name and name.casefold() not in {x.casefold() for x in names}:
            names.append(name)
    # Vacancy-only notices are tracked under their advertised post/recruitment.
    if not names and draft.get("is_recruitment_notice"):
        posts = [clean(x) for x in draft.get("post_names", []) if clean(x)]
        if posts:
            names.append(" / ".join(posts[:3]))
    return names[:20]


def exam_identity(name, draft):
    organisation = clean(draft.get("organisation"))
    cycle = clean(draft.get("cycle_label"))
    key_text = "|".join((organisation.casefold(), name.casefold(), cycle.casefold()))
    key_text = "".join(ch for ch in unicodedata.normalize("NFKD", key_text) if not unicodedata.combining(ch))
    key = re.sub(r"[^a-z0-9]+", "-", key_text).strip("-")[:200]
    return key, organisation, cycle


def upload_attachment(row, payload, draft):
    relative = clean(row.get("local_attachment") or row.get("local_pdf"))
    if not relative:
        return None, None, None, None
    path = (DATA / relative).resolve()
    try:
        path.relative_to(DATA.resolve())
    except ValueError:
        raise ValueError("Attachment path escapes the data directory")
    if not path.is_file():
        print(f"Attachment missing locally; retaining official source URL: {relative}")
        return None, None, None, None
    size = path.stat().st_size
    if size <= 0 or size > MAX_ATTACHMENT_BYTES:
        print(f"Attachment skipped (size {size} bytes): {relative}")
        return None, None, None, None
    digest = clean(row.get("attachment_sha256") or row.get("document_sha256")) or hashlib.sha256(path.read_bytes()).hexdigest()
    extension = path.suffix.lower()
    mime_types = {
        ".pdf": "application/pdf",
        ".zip": "application/zip",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".csv": "text/csv",
    }
    mime = clean(row.get("attachment_mime_type")) or mime_types.get(extension)
    if not mime or extension not in mime_types:
        raise ValueError("Unsupported official attachment type for storage")
    object_path = f"{digest[:2]}/{digest}{extension}"
    public_url = f"{BASE_URL}/storage/v1/object/public/{BUCKET}/{object_path}"
    exists = requests.head(public_url, timeout=20)
    if exists.status_code != 200:
        response = requests.post(
            f"{BASE_URL}/storage/v1/object/{BUCKET}/{object_path}",
            headers=headers({"Content-Type": mime, "x-upsert": "true"}),
            data=path.read_bytes(),
            timeout=90,
        )
        response.raise_for_status()
    filename = re.sub(r"[^A-Za-z0-9._-]+", "-", clean(draft.get("post_title") or row.get("candidate_title")) or "official-notice")
    filename = filename[:90].strip("-") + extension
    return object_path, public_url, filename, mime


def is_complete_notice(row):
    draft = row.get("ai_draft") if isinstance(row.get("ai_draft"), dict) else {}
    category = clean(draft.get("post_category")).lower()
    vacancy = category == "vacancy" or draft.get("is_recruitment_notice") is True
    evidence = draft.get("recruitment_evidence") if vacancy else draft.get("event_evidence")
    return (
        draft.get("status") == "ai_draft"
        and (draft.get("is_relevant_notice") is True or vacancy)
        and bool(clean(evidence))
        and len(clean(draft.get("summary"))) >= 40
        and (not vacancy or (isinstance(draft.get("post_names"), list)
                             and any(clean(x) for x in draft["post_names"])))
        and (vacancy or bool(draft.get("event_type") or category))
    )


def sync_exam_lifecycle(rows, dismissed_ids):
    updates, links, exam_rows = [], [], {}
    active_ids = set()
    for row in rows:
        if row.get("id") in dismissed_ids:
            continue
        draft = row.get("ai_draft") if isinstance(row.get("ai_draft"), dict) else {}
        if not is_complete_notice(row):
            continue
        names = exam_names(draft)
        exam_keys = []
        for name in names:
            key, organisation, cycle = exam_identity(name, draft)
            exam_keys.append(key)
            exam_rows[key] = {
                "exam_key": key,
                "exam_name": name[:240],
                "organisation": organisation[:200] or None,
                "cycle_label": cycle[:120] or None,
                "official_url": clean(draft.get("official_notification_url") or row.get("candidate_url")) or None,
                "last_update_at": row.get("detected_at_utc") or datetime.now(timezone.utc).isoformat(),
            }

        attachment_path = attachment_url = attachment_name = attachment_mime = None
        try:
            attachment_path, attachment_url, attachment_name, attachment_mime = upload_attachment(row, row, draft)
        except Exception as exc:
            print(f"Attachment upload failed for {row.get('id')}: {exc}; official URL retained.")
        if attachment_url:
            draft["attachment_url"] = attachment_url
            draft["attachment_name"] = attachment_name
            draft["attachment_mime_type"] = attachment_mime
            row["ai_draft"] = draft

        post_type = clean(row.get("post_type") or draft.get("event_type") or draft.get("post_category") or "update").lower()
        is_result = post_type in {"result", "results"} or draft.get("result_declared") is True
        result_url = clean(draft.get("result_url"))
        if is_result and not result_url and not attachment_url:
            result_url = clean(draft.get("application_url") or draft.get("official_notification_url") or row.get("candidate_url"))
        elif not result_url and is_result and attachment_url:
            result_url = ""
        facts = {
            "exam_name": clean(draft.get("exam_name")) or None,
            "cycle_label": clean(draft.get("cycle_label")) or None,
            "event_date": clean(draft.get("event_date")) or None,
            "important_dates": draft.get("important_dates") if isinstance(draft.get("important_dates"), list) else [],
            "vacancy_count": clean(draft.get("vacancy_count")) or None,
            "application_end_date": clean(draft.get("application_end_date")) or None,
            "result_declared": bool(is_result),
        }
        updates.append({
            "id": row["id"],
            "title": clean(draft.get("post_title") or row.get("candidate_title") or "Official update")[:300],
            "post_type": post_type,
            "exam_name": clean(draft.get("exam_name")) or None,
            "organisation": clean(draft.get("organisation")) or None,
            "source_name": clean(row.get("source_name")) or None,
            "source_title": clean(row.get("candidate_title")) or None,
            "source_url": clean(row.get("candidate_url")),
            "source_page_url": clean(row.get("source_page")) or None,
            "source_sha256": clean(row.get("document_sha256")) or None,
            "attachment_path": attachment_path,
            "attachment_url": attachment_url or clean(draft.get("attachment_url")) or None,
            "attachment_name": attachment_name or clean(draft.get("attachment_name")) or None,
            "attachment_mime_type": attachment_mime or clean(draft.get("attachment_mime_type")) or None,
            "result_url": result_url or None,
            "summary": clean(draft.get("summary"))[:1200] or None,
            "detected_at": row.get("detected_at_utc") or datetime.now(timezone.utc).isoformat(),
            "review_status": "verified" if row.get("human_verified") else "pending_review",
            "human_verified": bool(row.get("human_verified")),
            "result_declared": bool(is_result),
            "facts": facts,
        })
        active_ids.add(row["id"])

    returned = api_upsert("tracked_exams", list(exam_rows.values()), "exam_key")
    ids_by_key = {x["exam_key"]: x["id"] for x in returned}
    if exam_rows and len(ids_by_key) != len(exam_rows):
        # Fetch after upsert in case PostgREST returned no representation.
        existing = api_get("tracked_exams", {"select": "id,exam_key", "limit": "5000"})
        ids_by_key.update({x["exam_key"]: x["id"] for x in existing})
    for row in updates:
        source = next((x for x in rows if x.get("id") == row["id"]), {})
        draft = source.get("ai_draft") if isinstance(source.get("ai_draft"), dict) else {}
        for name in exam_names(draft):
            key, _, _ = exam_identity(name, draft)
            exam_id = ids_by_key.get(key)
            if exam_id:
                links.append({"update_id": row["id"], "exam_id": exam_id})
    api_upsert("exam_updates", updates, "id")
    api_upsert("exam_update_exams", links, "update_id,exam_id")
    return active_ids, len(exam_rows), len(updates)


def purge_dismissed_updates(dismissed_ids):
    removed = 0
    ids = list(dismissed_ids)
    for start in range(0, len(ids), 100):
        batch = ids[start:start + 100]
        rows = api_get("exam_updates", {
            "select": "id,attachment_path",
            "id": "in.(" + ",".join(batch) + ")",
            "limit": "100",
        })
        paths = [x["attachment_path"] for x in rows if x.get("attachment_path")]
        deleted = True
        if paths:
            try:
                response = requests.delete(
                    f"{BASE_URL}/storage/v1/object/{BUCKET}",
                    headers=headers(),
                    json={"prefixes": paths},
                    timeout=45,
                )
                response.raise_for_status()
            except Exception as exc:
                deleted = False
                print(f"Could not purge one or more discarded attachments; will retry next scan: {exc}")
        if rows:
            update_ids = [x["id"] for x in rows]
            patch = {"review_status": "rejected"}
            if deleted:
                patch.update({"attachment_path": None, "attachment_url": None})
                removed += len(paths)
            response = requests.patch(
                f"{BASE_URL}/rest/v1/exam_updates",
                params={"id": "in.(" + ",".join(update_ids) + ")"},
                headers=headers({"Prefer": "return=minimal"}),
                json=patch,
                timeout=30,
            )
            response.raise_for_status()
    return removed

def archive_completed_exams():
    now = datetime.now(timezone.utc).isoformat()
    completed = api_get("tracked_exams", {
        "select": "id",
        "lifecycle_status": "eq.result_declared",
        "archive_after": "lte." + now,
        "limit": "1000",
    })
    if not completed:
        return 0, 0
    ids = [x["id"] for x in completed]
    update_ids = set()
    for exam_id in ids:
        for link in api_get("exam_update_exams", {
            "select": "update_id", "exam_id": "eq." + exam_id, "limit": "5000"
        }):
            update_ids.add(link["update_id"])
    purged_files, failed_exam_ids = 0, set()
    for update_id in update_ids:
        links = api_get("exam_update_exams", {
            "select": "exam_id", "update_id": "eq." + update_id, "limit": "100"
        })
        linked_ids = [x["exam_id"] for x in links]
        states = api_get("tracked_exams", {
            "select": "id,lifecycle_status", "id": "in.(" + ",".join(linked_ids) + ")",
            "limit": "100",
        }) if linked_ids else []
        if states and any(x["lifecycle_status"] != "archived" and x["id"] not in ids for x in states):
            continue
        rows = api_get("exam_updates", {
            "select": "attachment_path", "id": "eq." + update_id, "limit": "1"
        })
        path = rows[0].get("attachment_path") if rows else None
        if path:
            try:
                delete = requests.delete(
                    f"{BASE_URL}/storage/v1/object/{BUCKET}",
                    headers=headers(),
                    json={"prefixes": [path]},
                    timeout=30,
                )
                delete.raise_for_status()
                purged_files += 1
            except Exception as exc:
                failed_exam_ids.update(x for x in linked_ids if x in ids)
                print(f"Attachment cleanup failed for archived exam update {update_id}; will retry: {exc}")
                continue
        patch = requests.patch(
            f"{BASE_URL}/rest/v1/exam_updates",
            params={"id": "eq." + update_id},
            headers=headers({"Prefer": "return=minimal"}),
            json={"review_status": "archived", "attachment_path": None, "attachment_url": None},
            timeout=30,
        )
        patch.raise_for_status()
    archive_ids = [x for x in ids if x not in failed_exam_ids]
    if archive_ids:
        response = requests.patch(
            f"{BASE_URL}/rest/v1/tracked_exams",
            params={"id": "in.(" + ",".join(archive_ids) + ")"},
            headers=headers({"Prefer": "return=minimal"}),
            json={"lifecycle_status": "archived", "is_following": False},
            timeout=30,
        )
        response.raise_for_status()
    return len(archive_ids), purged_files

def main():
    if not KEY:
        print("SUPABASE_SERVICE_ROLE_KEY is not configured; skipping database sync.")
        return
    rows = json.loads(QUEUE.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Review queue must be a JSON array")
    dismissed_response = requests.get(
        f"{BASE_URL}/rest/v1/dismissed_job_posts",
        params={"select": "id", "limit": "5000"},
        headers=headers(),
        timeout=30,
    )
    dismissed_response.raise_for_status()
    dismissed_ids = {row["id"] for row in dismissed_response.json()}

    # Preserve compact lifecycle history before pruning full review payloads.
    active_ids, exam_count, update_count = sync_exam_lifecycle(rows, dismissed_ids)
    rejected_updates = purge_dismissed_updates(dismissed_ids)
    archived_exams, purged_files = archive_completed_exams()

    # Keep the full review queue short-lived; old items remain as compact exam history.
    cutoff = datetime.now(timezone.utc) - timedelta(days=QUEUE_RETENTION_DAYS)
    retained = []
    pruned_count = 0
    for row in rows:
        detected = row.get("detected_at_utc")
        try:
            age = datetime.fromisoformat(str(detected).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            age = datetime.now(timezone.utc)
        if row.get("id") in dismissed_ids or age < cutoff:
            pruned_count += 1
            continue
        retained.append(row)

    valid = []
    for row in retained:
        if is_complete_notice(row):
            valid.append({"id": row["id"], "payload": row})

    for start in range(0, len(valid), 50):
        batch = valid[start:start + 50]
        response = requests.post(
            f"{BASE_URL}/rest/v1/job_alert_queue",
            params={"on_conflict": "id"},
            headers=headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
            json=batch,
            timeout=30,
        )
        response.raise_for_status()

    existing_response = requests.get(
        f"{BASE_URL}/rest/v1/job_alert_queue",
        params={"select": "id", "limit": "5000"},
        headers=headers(),
        timeout=30,
    )
    existing_response.raise_for_status()
    keep = {row["id"] for row in valid}
    stale = [row["id"] for row in existing_response.json() if row["id"] not in keep]
    for start in range(0, len(stale), 100):
        ids = stale[start:start + 100]
        response = requests.delete(
            f"{BASE_URL}/rest/v1/job_alert_queue",
            params={"id": "in.(" + ",".join(quote(x, safe="") for x in ids) + ")"},
            headers=headers(),
            timeout=30,
        )
        response.raise_for_status()

    if pruned_count:
        temp = QUEUE.with_suffix(".json.tmp")
        temp.write_text(json.dumps(retained, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temp.replace(QUEUE)
        columns = ["id", "detected_at_utc", "source_name", "candidate_title", "candidate_url",
                   "review_status", "human_verified", "notice_type", "organisation",
                   "advertisement_number", "vacancy_count", "application_end_date", "summary"]
        with (DATA / "review_queue.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            for row in retained:
                draft = row.get("ai_draft") if isinstance(row.get("ai_draft"), dict) else {}
                writer.writerow({**{k: row.get(k) for k in columns[:7]},
                                 **{k: draft.get(k) for k in columns[7:]}})
        print(f"Pruned {pruned_count} dismissed or older-than-{QUEUE_RETENTION_DAYS}-day queue records; compact exam history retained.")

    print(
        f"Supabase sync complete: pending={len(valid)}; tracked_exams={exam_count}; "
        f"exam_updates={update_count}; stale_queue_rows_removed={len(stale)}; "
        f"dismissed_ids_suppressed={len(dismissed_ids)}; local_queue_pruned={pruned_count}; "
        f"rejected_updates_cleaned={rejected_updates}; completed_exams_archived={archived_exams}; "
        f"old_attachments_purged={purged_files}."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Supabase queue/lifecycle sync failed: {exc}", file=sys.stderr)
        raise
