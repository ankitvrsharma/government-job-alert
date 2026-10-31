import json, logging, time
from .config import GEMINI_API_KEY, GEMINI_MODEL

log = logging.getLogger("job-alert")

def extract_with_ai(text, title, url):
    if not GEMINI_API_KEY:
        return {"status": "ai_unavailable", "error": "GEMINI_API_KEY is not configured"}
    if not text.strip():
        return {"status": "needs_ocr", "error": "No selectable PDF text; manual OCR/review required"}
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        return {"status": "ai_unavailable", "error": str(exc)}

    prompt = f"""Extract facts from this official Indian recruitment notice.
Return only facts supported by the text. Never guess; use null or [] when absent.
Keep the output in English. This is an unverified draft requiring human review.
Title: {title}
URL: {url}
DOCUMENT:
{text[:60000]}"""

    schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "notice_type": types.Schema(type=types.Type.STRING, nullable=True),
            "organisation": types.Schema(type=types.Type.STRING, nullable=True),
            "post_names": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
            "advertisement_number": types.Schema(type=types.Type.STRING, nullable=True),
            "vacancy_count": types.Schema(type=types.Type.STRING, nullable=True),
            "qualification": types.Schema(type=types.Type.STRING, nullable=True),
            "age_limit": types.Schema(type=types.Type.STRING, nullable=True),
            "application_start_date": types.Schema(type=types.Type.STRING, nullable=True),
            "application_end_date": types.Schema(type=types.Type.STRING, nullable=True),
            "application_fee": types.Schema(type=types.Type.STRING, nullable=True),
            "selection_process": types.Schema(type=types.Type.STRING, nullable=True),
            "official_notification_url": types.Schema(type=types.Type.STRING, nullable=True),
            "application_url": types.Schema(type=types.Type.STRING, nullable=True),
            "important_dates": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
            "summary": types.Schema(type=types.Type.STRING, nullable=True),
            "uncertainties": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
        },
        required=["post_names", "important_dates", "uncertainties"]
    )
    client = genai.Client(api_key=GEMINI_API_KEY)
    last_error = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0.1,
                    max_output_tokens=4096,
                ),
            )
            parsed = json.loads(response.text or "")
            if not isinstance(parsed, dict):
                raise ValueError("Gemini did not return a JSON object")
            parsed["status"] = "ai_draft"
            parsed["model"] = GEMINI_MODEL
            return parsed
        except Exception as exc:
            last_error = exc
            log.warning("Gemini attempt %s failed: %s", attempt + 1, exc)
            if attempt < 2:
                time.sleep(2 ** attempt)
    return {"status": "ai_error", "error": str(last_error), "model": GEMINI_MODEL}
