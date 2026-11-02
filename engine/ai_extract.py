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

    today = time.strftime("%Y-%m-%d")
    prompt = f"""Today is {today}. Extract facts from this official Indian recruitment/examination notice.
Return only facts supported by the text. Never guess; use null or [] when absent. For this initial backfill, include only official calendars or notices relevant to a cycle that is still active/upcoming as of today, or a newly published result/answer key/interview/selection stage for a current recruitment cycle. Do not create posts for expired application windows or wholly past cycles unless the notice itself is a newly issued result/selection-stage update. Clearly mark tentative dates as tentative and never turn expected dates into confirmed dates.
For result notices, extract a direct result/check-result URL into result_url when the source provides one. Set result_declared=true only when the official source explicitly declares/releases the result; otherwise false. Extract cycle_label (for example June 2027, 2027 Session 1, Advt. 04/2026) when stated. Extract related_exams as a list of every specific exam and cycle materially covered by this one source document (especially multi-exam calendars); do not include generic course/admission programmes. One source file/update must remain one post even when it covers several exams. Classify this as a government recruitment/examination lifecycle notice when it contains a concrete official update relevant to a government job, recruitment process or competitive examination. Supported categories: vacancy, exam_calendar, exam_schedule, exam_date_change, exam_postponed, exam_cancelled, admit_card, application_update, corrigendum, answer_key, result, scorecard, cut_off, interview_schedule, selection_update, document_verification, other_recruitment_update. Exclude admissions, academic course calendars, generic career pages, unrelated announcements, coaching promotions and non-government events. A title/keyword alone is not proof. Extract the exact event, affected exam/recruitment, dates, changed-from/to details and official evidence. For vacancy notices, require named employment posts and explicit invitation to apply/interview. For all other categories, require event_evidence that supports the specific update. If uncertain or unrelated, set is_relevant_notice=false. Write a useful factual summary without guessing. The summary is intended for a public WhatsApp channel: write in natural, clear editorial English, as a knowledgeable human recruitment-news editor would. Lead with what happened and who it affects. Keep it to 1–3 concise sentences, avoid repeating the headline, avoid phrases like "This is to inform", "In a significant development", "candidates are advised to note", and avoid generic AI-sounding introductions or inflated language. Do not turn a list of dates into prose; dates belong in the structured important_dates field. Do not add a call to action unless the source explicitly gives an application process. Preserve whether dates are tentative/proposed.
Create a strong, reader-friendly post_title for the banner and post heading. It must identify the actual update in plain, natural Title Case, usually 4–10 words, and include the exam/recruitment name and year when explicitly available and useful. Prefer specific headlines such as “UGC NET December 2026 Exam Calendar”, “SSC CGL 2026 Application Dates Announced”, “RRB NTPC Graduate Level Admit Card Released”, “UPSC Civil Services 2027 Notification”, or “CTET July 2026 Exam Date Revised”. Do not use generic headings such as “Exam Calendar”, “Latest Update”, “Important Notice”, “Recruitment Update” or “Government Jobs” when the document provides a more specific exam, post, cycle or event. For vacancies, identify the advertised post(s) and organisation where possible; for results/admit cards/answer keys, say exactly which exam and cycle they relate to. Keep it factual, concise, readable on a landscape banner, and never invent a year, stage, number or status. If exact identifying details are unavailable, use the clearest specific title supported by the notice.
Title: {title}
URL: {url}
DOCUMENT:
{text[:60000]}"""

    schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "is_relevant_notice": types.Schema(type=types.Type.BOOLEAN),
            "is_recruitment_notice": types.Schema(type=types.Type.BOOLEAN),
            "post_category": types.Schema(type=types.Type.STRING, nullable=True),
            "event_type": types.Schema(type=types.Type.STRING, nullable=True),
            "event_evidence": types.Schema(type=types.Type.STRING, nullable=True),
            "exam_name": types.Schema(type=types.Type.STRING, nullable=True),
            "cycle_label": types.Schema(type=types.Type.STRING, nullable=True),
            "related_exams": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
            "result_url": types.Schema(type=types.Type.STRING, nullable=True),
            "result_declared": types.Schema(type=types.Type.BOOLEAN),

            "related_notice": types.Schema(type=types.Type.STRING, nullable=True),
            "event_date": types.Schema(type=types.Type.STRING, nullable=True),
            "previous_event_date": types.Schema(type=types.Type.STRING, nullable=True),
            "change_reason": types.Schema(type=types.Type.STRING, nullable=True),
            "recruitment_evidence": types.Schema(type=types.Type.STRING, nullable=True),
            "notice_type": types.Schema(type=types.Type.STRING, nullable=True),
            "post_title": types.Schema(type=types.Type.STRING, nullable=True),
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
        required=["is_relevant_notice", "is_recruitment_notice", "post_title", "post_names", "important_dates", "uncertainties"]
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
