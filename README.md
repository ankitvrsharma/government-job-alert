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
