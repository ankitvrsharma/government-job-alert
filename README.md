# Government Job Alert — Release 1

A scheduled monitor for Indian government recruitment pages. It discovers likely recruitment links and PDFs, extracts PDF text, optionally uses AI to create structured drafts, and places every candidate in a manual-review queue. **Nothing is auto-published.**

## Included
- Official-source registry (`sources/sources.json`)
- Twice-daily GitHub Actions scans: 08:00 and 18:00 IST
- Same-domain link filtering, polite request delay and timeouts
- PDF download and text extraction using PyMuPDF
- Optional Gemini structured extraction with evidence snippets
- URL/hash duplicate detection
- JSON and CSV review queues
- Manual workflow dispatch

## Create the GitHub repository
Create a new repository named `government-job-alert` on GitHub. Upload the contents of this ZIP to its root, then enable Actions.

Alternatively, extract locally and run:
```bash
git init
git add .
git commit -m "Initial Government Job Alert Release 1"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/government-job-alert.git
git push -u origin main
```

## Configure Gemini AI (optional but recommended)
Repository → Settings → Secrets and variables → Actions → New repository secret:
- `Gemini_API_KEY`: your API key

Optional repository variable:
- `GEMINI_MODEL`: model name; defaults to `gemini-3.8-flash`

Without the key, the scanner still collects candidate links and PDFs, but AI fields remain unavailable.

## Run locally
Python 3.11+:
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m engine.run_scan
```
Set `GEMINI_API_KEY` in your shell before running for AI extraction.

## Outputs
- `data/review_queue.json` — complete records; all `review_status` values are `pending_review`
- `data/review_queue.csv` — spreadsheet-friendly index
- `data/seen_items.json` — deduplication state
- `data/downloads/` — downloaded PDFs during local runs
- `logs/latest_scan.log` — run log

Download the repository or workflow artifact to inspect PDFs. The scheduled workflow commits queue metadata and logs, not downloaded PDFs.

## Add sources
Edit `sources/sources.json`. Every source has a URL, allowed hostnames, keywords and enabled flag. Confirm each official URL and permitted crawling conditions before enabling it. Some sites use JavaScript, CAPTCHA, image-only PDFs or changing layouts; these need custom adapters and may not be detected by this generic scanner.

## Important
- AI extraction is a draft, not verification. Check every date, eligibility condition, vacancy count, fee and link against the original official notification.
- The scanner does not bypass CAPTCHA, login walls, access controls or robots restrictions.
- It does not submit applications or publish to WhatsApp.
- This release is a working collector prototype, not exhaustive nationwide coverage.
- GitHub Actions schedule can be delayed during high load; use Actions → Run workflow for an immediate scan.
- Never commit API keys.

## Release 2
Add source-specific adapters, OCR for scanned PDFs, authenticated review dashboard, database persistence and reviewer notifications.


## Gemini free-tier notes
The project uses Google's `google-genai` Python SDK and defaults to `gemini-3.8-flash`. Gemini API free-tier availability and rate limits depend on the model, region, account and current Google terms. Check Google AI Studio's usage page. On the free tier, submitted prompts may be used by Google to improve its products; avoid sending private or sensitive documents. Here the intended input is publicly available recruitment-notification text.

- Gemini API setup: https://ai.google.dev/gemini-api/docs/get-started
- Model availability: https://ai.google.dev/gemini-api/docs/models
- Pricing and free-tier details: https://ai.google.dev/gemini-api/docs/pricing


## Gemini free-tier notes
This project uses Google's `google-genai` Python SDK and defaults to `gemini-3.8-flash`. Free-tier availability and rate limits depend on the selected model, region, account and current Google terms. Check Google AI Studio usage. On the free tier, submitted prompts may be used by Google to improve its products; avoid sending private or sensitive documents. The intended inputs here are publicly available recruitment notices.

- API setup: https://ai.google.dev/gemini-api/docs/get-started
- Model availability: https://ai.google.dev/gemini-api/docs/models
- Pricing and free-tier details: https://ai.google.dev/gemini-api/docs/pricing
