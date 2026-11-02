# Government Job Alert — Recruitment & Exam Alert System

An English-only, AI-assisted monitor for Indian government recruitment and competitive-examination notices. It scans configured official sources twice daily and creates a **manual-review queue** for new notices and meaningful changes. It never automatically publishes or sends alerts.

## Features
- Scheduled scans at 08:00 IST and 18:00 IST through GitHub Actions.
- Official-source registry in `sources/sources.json`.
- Recruitment-link discovery and PDF download/text extraction.
- Gemini-assisted structured extraction from selectable PDF text.
- URL and document-hash deduplication.
- JSON and CSV review queues; all new entries remain `pending_review` and `human_verified: false`.

## GitHub setup
1. Open **Settings → Secrets and variables → Actions → Repository secrets**.
2. Add the secret with the exact name **`GEMINI_API_KEY`** and your Google AI Studio key.
3. The optional Actions variable `GEMINI_MODEL` may be left unset; the default is `gemini-3.8-flash`.

Never put the API key in a repository file.

## Run manually
Open **Actions**, choose Morning or Evening recruitment scan, select **Run workflow**, and run it on `main`.

## Admin panel and WhatsApp sharing

The dashboard at `/admin/` uses Supabase email/password authentication. The job queue is read from a Supabase table protected by Row Level Security (RLS); only users explicitly listed in `public.admin_users` can read or change it. The browser contains only the Supabase publishable key, never a service-role key. WhatsApp sharing remains manual: the reviewer must confirm checking the official notice, then press Send in WhatsApp.

### One-time Supabase setup
1. Use the Supabase project **Government Job Alert Auth**.
2. In **Authentication → URL Configuration**, set Site URL to `https://ankitvrsharma.github.io/government-job-alert` and add `https://ankitvrsharma.github.io/**` to Redirect URLs.
3. Open `/admin/`, create an account with your email and a strong password, and confirm the email if Supabase asks.
4. The account is not authorised until its owner row is added to `public.admin_users`. Add the first administrator using the Supabase SQL Editor:
   ```sql
   insert into public.admin_users (user_id, email)
   select id, email from auth.users
   where lower(email) = lower('YOUR_EMAIL')
   on conflict (user_id) do nothing;
   ```
5. Disable public sign-ups in **Authentication → Sign In / Providers → Email** after the administrator account is created. Only authorised accounts can access queue rows because of RLS.

### Publish
Set **GitHub Settings → Pages → Build and deployment → Source: GitHub Actions**, then run the **Deploy admin panel** workflow. The expected dashboard URL is `https://ankitvrsharma.github.io/government-job-alert/admin/`.

**Repository visibility warning:** this GitHub repository is currently public, so historical copies of `data/review_queue.json` and `data/review_queue.csv` in Git history may still be publicly readable. The dashboard no longer fetches those files; its live data comes from the RLS-protected Supabase table. For full confidentiality, the queue files and their Git history must be moved out of this public repository (or the repository must be made private, subject to GitHub Pages plan support). Never commit credentials or service-role keys.

## Review
Inspect `data/review_queue.csv` or `data/review_queue.json`. Verify every field against the official notification before changing its review status. No social channel is automatically posted to.

## Add sources
Edit `sources/sources.json`. Each source supports `name`, `url`, `enabled`, `allowed_domains`, and `keywords`. The starter registry is not exhaustive; state, UT, PSU, university, autonomous-body and local recruitment portals should be added progressively.

## Limitations
- Generic HTML discovery can miss JavaScript-rendered pages, CAPTCHA-protected sites and unusual layouts.
- Image-only/scanned PDFs need OCR; this release flags PDFs without selectable text for manual handling.
- Page-specific adapters are needed for reliable extraction from many recruitment portals.
- The scanner observes `robots.txt` and skips URLs it cannot verify as permitted.
- Add legitimate external application/CDN hosts to `allowed_domains` where appropriate.
- Gemini output is only a draft. Human verification is mandatory.

## Schedule (UTC)
- `30 2 * * *` = 08:00 IST
- `30 12 * * *` = 18:00 IST


## Vacancy-only queue and Supabase sync

The scanner queues readable, evidence-backed government recruitment and exam lifecycle notices: vacancies; exam calendars and schedules; date changes, postponements and cancellations; admit cards; application updates; corrigenda; answer keys; results, scorecards and cut-offs; interview schedules; selection updates; and document verification. Admissions, generic career pages, coaching promotions, unrelated announcements and title-only links are excluded. The admin page filters incomplete records and displays relevant details for each event type.

To sync each scan into the protected Supabase admin queue:

1. In GitHub, open **Settings → Secrets and variables → Actions → New repository secret**.
2. Create the secret named `SUPABASE_SERVICE_ROLE_KEY`.
3. Copy the project's **service_role secret** from Supabase **Project Settings → API Keys**. Never put this key in source code or share it in chat.
4. Run **Actions → Morning recruitment scan → Run workflow** (or wait for the scheduled scan).

The workflow syncs only complete vacancy records to the protected Supabase table and removes stale records. If the secret is absent, the sync step safely skips database syncing.


## Change-driven post generation

The scanner fingerprints the readable content of each tracked candidate URL on every scheduled scan. Unchanged content is ignored. Existing URLs from the pre-change tracker are baselined once, so the first run does not create retroactive posts for old notices. After baselining, a post is created only when a new vacancy notice is discovered or a tracked notice changes materially.

Notices are matched by authority plus advertisement number, post names, examination name or related notice where available. Material changes to vacancy details, exam dates, schedules, event status, application dates, fees, selection process or official links create a new event/update post linked to the previous notice. Event labels distinguish exam calendars, date changes, postponements, cancellations, admit cards, answer keys, results and other lifecycle updates. Unchanged content and changes that do not alter meaningful recruitment/exam details are not posted.

The admin review page generates branded 1080×1080 PNG artwork for each post: event-specific artwork for new vacancies, notice updates, exam schedules, postponements/cancellations, results and deadline extensions. Each card has only two actions: **Share** and **Edit post**. Share uses the device's native share sheet and passes the post text plus PNG image together when the browser/platform supports file sharing; the reviewer can choose WhatsApp, Telegram or another installed share target. If combined file sharing is unavailable, the page falls back to text sharing and clearly reports that the image could not be attached in that same action. **Edit post** opens an inline editor in the card and saves the edited payload to the protected Supabase queue. Saving clears that card's session verification, so the edited notice must be checked again before sharing. Nothing is auto-published.


## Admin-managed tracked websites

Administrators can add, pause, enable or remove official websites from **Admin → Add websites to monitor**. Add the organisation name and an HTTPS recruitment/notices page URL. The URL is saved in the protected Supabase `tracked_sources` table; no source-code edit or GitHub commit is needed. New active URLs are picked up automatically by the next morning/evening scan. Existing built-in sources remain unchanged.

Only HTTPS URLs are accepted. The scanner derives the allowed host from the submitted URL, follows same-host links, checks `robots.txt`, and applies the system's recruitment/exam keywords and human-review rules. A newly added source is not scanned immediately; it enters the next scheduled run. Pausing or removing a source prevents future scans but does not delete already queued posts. The Supabase service-role key is used only in GitHub Actions and is never exposed to the browser.


### Discarding reviewed queue posts

Administrators can discard a notice from its review card when it is irrelevant or has already been shared. The item is removed from the live queue and a protected dismissal marker is retained in Supabase, so scheduled scans do not re-import the same post from the repository queue. Dismissal markers are only visible to authorised administrators and the scanner service role.

## Exam lifecycle tracking and official attachments

- Every official source file or distinct notice/update is represented by one review post. If the same update is discovered as an HTML page and a linked PDF, the PDF is attached to the existing post instead of creating a second post.
- Gemini extracts the exam/recruitment name, cycle, related exams for multi-exam calendars, result status and result-check URL. One source document can be linked to several tracked exams without duplicating the post.
- Supabase stores compact lifecycle records in `tracked_exams`, `exam_updates` and `exam_update_exams`. The applied SQL migrations are versioned under `supabase/migrations/`. The admin panel lets the reviewer follow/pause exams, inspect their update history, mark a result as declared, reopen tracking or archive an exam.
- Official PDFs and supported ZIP, DOCX, XLSX and CSV files up to 25 MB are deduplicated by SHA-256 and stored in the public `official-updates` bucket. Only the service-role scanner can upload/delete objects; public read access is limited to this bucket because these files originate from official public notifications. WhatsApp preparation attempts to share the banner and official PDF together. If no PDF is available, the post carries the official result-check page URL instead.
- The transient review queue is pruned after 45 days or when dismissed. Compact exam/update history remains available. When an exam is manually marked result-declared, it is archived after 180 days and its attached file is removed if no other active exam uses it. The small historical update metadata remains.
- The scanner never treats an AI-detected result as human-verified. The admin must check the official result and mark the exam's result as declared in the tracker.

## Release 1.2 work

- Added lifecycle tracking for examinations and recruitment cycles.
- Added exam-to-update relationships, including multi-exam calendars.
- Added official PDF upload, deduplication and WhatsApp file-sharing support.
- Added per-category visual banner motifs while keeping the channel title lockup consistent.
- Added type-specific WhatsApp caption structures and official result/admit-card/answer-key/scorecard links.
- Added automatic short-term review-queue retention and post-result attachment cleanup.
- Added regression tests for exam identity, multi-exam mapping and one-update deduplication.
