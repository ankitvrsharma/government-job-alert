# Government Job Alert — Release 1.1

An English-only, AI-assisted monitor for Indian government recruitment notices. It scans configured official sources twice daily and creates a **manual-review queue**. It never automatically publishes a vacancy.

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
