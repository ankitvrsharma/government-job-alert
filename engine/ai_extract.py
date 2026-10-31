import json, logging, time
from .config import (
    GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODELS,
    MAX_AI_REQUESTS_PER_SCAN,
)

log = logging.getLogger("job-alert")
EXHAUSTED_MODELS = set()
AI_REQUESTS = 0
MODEL_CHAIN = list(dict.fromkeys([GEMINI_MODEL, *GEMINI_FALLBACK_MODELS]))

def _quota_or_rate_limit(message):
    value = message.lower()
    return any(token in value for token in (
        "resource_exhausted", "quota exceeded", "too many requests",
        "rate limit", "429", "daily limit",
    ))

def _model_unavailable(message):
    value = message.lower()
    return any(token in value for token in (
        "not found", "model is not found", "unsupported", "not supported",
        "permission denied", "403", "404",
    ))

def extract_with_ai(text, title, url):
    global AI_REQUESTS
    if not GEMINI_API_KEY:
        return {"status": "ai_unavailable", "error": "GEMINI_API_KEY is not configured"}
    if not text.strip():
        return {"status": "needs_ocr", "error": "No selectable PDF text; manual OCR/review required"}
    if AI_REQUESTS >= MAX_AI_REQUESTS_PER_SCAN:
        return {"status": "ai_deferred", "error": f"Per-scan AI request safety limit ({MAX_AI_REQUESTS_PER_SCAN}) reached; retry on next scan."}

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
    errors = []
    for model in MODEL_CHAIN:
        if model in EXHAUSTED_MODELS:
            continue
        # One request per model before falling back. This prevents repeated quota failures.
        try:
            AI_REQUESTS += 1
            log.info("Trying Gemini model %s (%s/%s)", model, MODEL_CHAIN.index(model) + 1, len(MODEL_CHAIN))
            response = client.models.generate_content(
                model=model,
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
            parsed["model"] = model
            if model != GEMINI_MODEL:
                log.warning("Primary model unavailable; successful fallback model: %s", model)
            return parsed
        except Exception as exc:
            message = str(exc)
            errors.append(f"{model}: {message}")
            if _quota_or_rate_limit(message):
                EXHAUSTED_MODELS.add(model)
                log.warning("Gemini model %s quota/rate limit exhausted; switching to next fallback.", model)
                continue
            if _model_unavailable(message):
                EXHAUSTED_MODELS.add(model)
                log.warning("Gemini model %s unavailable; switching to next fallback.", model)
                continue
            # A single short retry for transient server/network failures only.
            if any(token in message.lower() for token in ("500", "502", "503", "504", "timeout", "temporarily")) and AI_REQUESTS < MAX_AI_REQUESTS_PER_SCAN:
                try:
                    time.sleep(1)
                    AI_REQUESTS += 1
                    response = client.models.generate_content(
                        model=model, contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=schema, temperature=0.1,
                            max_output_tokens=4096,
                        ),
                    )
                    parsed = json.loads(response.text or "")
                    if isinstance(parsed, dict):
                        parsed["status"] = "ai_draft"
                        parsed["model"] = model
                        return parsed
                except Exception as retry_exc:
                    errors.append(f"{model} retry: {retry_exc}")
                    if _quota_or_rate_limit(str(retry_exc)):
                        EXHAUSTED_MODELS.add(model)
                        log.warning("Gemini model %s quota exhausted on retry; switching fallback.", model)
                        continue
            log.warning("Gemini model %s failed; trying next fallback: %s", model, exc)

        if AI_REQUESTS >= MAX_AI_REQUESTS_PER_SCAN:
            break

    if len(EXHAUSTED_MODELS) == len(MODEL_CHAIN):
        return {"status": "ai_quota_exceeded", "error": "All configured Gemini models have exhausted quota or are unavailable.", "models_tried": MODEL_CHAIN}
    return {"status": "ai_error", "error": " | ".join(errors)[-4000:], "models_tried": MODEL_CHAIN}
