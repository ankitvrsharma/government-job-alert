import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

import requests

BASE_URL = "https://xmjstmebdbmplsdhrspt.supabase.co"
KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
QUEUE = Path(__file__).resolve().parents[1] / "data" / "review_queue.json"

def main():
    if not KEY:
        print("SUPABASE_SERVICE_ROLE_KEY is not configured; skipping database sync.")
        return
    rows = json.loads(QUEUE.read_text(encoding="utf-8"))
    headers = {
        "apikey": KEY,
        "Authorization": f"Bearer {KEY}",
        "Content-Type": "application/json",
    }
    valid = []
    for row in rows:
        draft = row.get("ai_draft") if isinstance(row.get("ai_draft"), dict) else {}
        posts = draft.get("post_names")
        vacancy = draft.get("post_category") == "vacancy" or draft.get("is_recruitment_notice") is True
        evidence = draft.get("recruitment_evidence") if vacancy else draft.get("event_evidence")
        if (draft.get("status") == "ai_draft"
                and (draft.get("is_relevant_notice") is True or vacancy)
                and (not vacancy or (isinstance(posts, list) and any(str(p).strip() for p in posts)))
                and str(evidence or "").strip()
                and len(str(draft.get("summary") or "").strip()) >= 40
                and (vacancy or draft.get("event_type") or draft.get("post_category"))):
            valid.append({"id": row["id"], "payload": row})

    dismissed_response = requests.get(
        f"{BASE_URL}/rest/v1/dismissed_job_posts",
        params={"select": "id", "limit": "5000"},
        headers=headers,
        timeout=30,
    )
    dismissed_response.raise_for_status()
    dismissed_ids = {row["id"] for row in dismissed_response.json()}
    valid = [row for row in valid if row["id"] not in dismissed_ids]

    # Upsert current records first, so a transient cleanup failure never loses current data.
    for start in range(0, len(valid), 50):
        batch = valid[start:start + 50]
        response = requests.post(
            f"{BASE_URL}/rest/v1/job_alert_queue",
            params={"on_conflict": "id"},
            headers={**headers, "Prefer": "resolution=merge-duplicates,return=minimal"},
            json=batch,
            timeout=30,
        )
        response.raise_for_status()

    existing_response = requests.get(
        f"{BASE_URL}/rest/v1/job_alert_queue",
        params={"select": "id", "limit": "1000"},
        headers=headers,
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
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
    print(f"Supabase queue sync complete: {len(valid)} active recruitment/exam notices; {len(dismissed_ids)} admin-dismissed posts suppressed; {len(stale)} stale records removed.")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Supabase queue sync failed: {exc}", file=sys.stderr)
        raise
