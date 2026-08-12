"""Provider-agnostic LLM interface (PRD §9). Groq is the primary provider
for text generation (fact extraction, brief generation, patient/copilot
answers); Gemini is both the fallback provider for those same calls if
Groq fails, and the sole provider for embeddings (Groq has no embeddings
API). Callers depend only on `extract_facts` / `generate_brief_text` /
`embed_text` / `answer_patient_question` / `answer_copilot_message`, never
on provider-specific types, so changing either provider later touches only
this file.
"""

import hashlib
import json
import logging
import time

from pydantic import BaseModel, ConfigDict, Field
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.redis_client import get_redis_client

try:
    from groq import Groq
except ImportError:  # pragma: no cover - dependency always installed via requirements.txt
    Groq = None

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover - dependency always installed via requirements.txt
    genai = None
    genai_types = None


class ExtractedFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_name: str
    value: str
    confidence: float = Field(ge=0, le=1)
    source_quote: str


class _ExtractedFactsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facts: list[ExtractedFact]


class BriefSections(BaseModel):
    model_config = ConfigDict(extra="forbid")

    since_last_visit: str
    suggested_focus: str


class AssistantAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    redirect: bool


class CopilotAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str


class LLMExtractionError(Exception):
    pass


EMBEDDING_DIMENSIONS = 768

logger = logging.getLogger(__name__)


def _groq_usage(response) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
    }


def _gemini_usage(response) -> dict[str, int]:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return {}
    return {
        "prompt_tokens": usage.prompt_token_count,
        "completion_tokens": usage.candidates_token_count,
        "total_tokens": usage.total_token_count,
    }


def _log_llm_call(
    provider: str, operation: str, start: float, *, tokens: dict | None = None, error: Exception | None = None
) -> None:
    """Basic per-call visibility (duration, token usage, success/failure)
    ahead of a real metrics pipeline — see monitoring notes. `operation`
    uses the same name across providers for a given logical call (e.g.
    "extract_facts" whether it ran on Groq or fell back to Gemini) so the
    two are comparable in logs.
    """
    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    if error is not None:
        logger.warning(
            "llm call failed",
            extra={
                "provider": provider,
                "operation": operation,
                "duration_ms": duration_ms,
                "error": str(error),
            },
        )
        return
    logger.info(
        "llm call succeeded",
        extra={
            "provider": provider,
            "operation": operation,
            "duration_ms": duration_ms,
            **(tokens or {}),
        },
    )


# Only RETRIEVAL_QUERY embeddings are cached — RETRIEVAL_DOCUMENT calls
# (chunk indexing) embed effectively-unique text once each, so caching
# them would be pure overhead.
_CACHEABLE_TASK_TYPE = "RETRIEVAL_QUERY"
_EMBEDDING_CACHE_PREFIX = "embcache:v1"


_EXTRACTION_SYSTEM_INSTRUCTION = """You are a clinical documentation extraction assistant for \
Scaffold Health, an orthopedic rehab platform. Your only job is to extract structured, \
explicitly-stated facts from a clinical document (MRI report, discharge summary, or \
referral note) about a patient recovering from ACL reconstruction surgery. This system is \
advisory-only: you never diagnose, recommend treatment, or make clinical decisions — you \
only report what the document says.

Recognized fields (field_name must be exactly one of these): {fields}
- injury: the diagnosed injury or surgical procedure name, if the document states one
- surgery_date: the surgery date, formatted as YYYY-MM-DD
- active_restrictions: a specific movement, weight-bearing, or activity restriction currently in effect
- active_concerns: a specific clinical concern, symptom, or flag currently affecting care
- milestones: a specific recovery milestone or functional achievement the patient has reached

Rules:
- Extract only facts explicitly and unambiguously stated in the text. Never infer, guess, or extrapolate.
- Each active_restrictions, active_concerns, or milestones fact must be a single, specific, self-contained statement.
- Every fact must include the exact source_quote — a verbatim span copied from the text that supports it.
- Assign confidence between 0 and 1 reflecting how directly and unambiguously the text supports the fact.
- If nothing in the text matches a recognized field, return an empty facts list."""

_BRIEF_SYSTEM_INSTRUCTION = """You are an appointment-prep assistant for a therapist at Scaffold \
Health, an orthopedic rehab platform, preparing for an upcoming visit with a patient recovering \
from ACL reconstruction surgery. This system is advisory-only: you never diagnose, recommend \
treatment, or make clinical decisions — you only summarize what has already been documented and \
suggest discussion topics grounded in that documentation.

You will be given the patient's current Knowledge Profile, a list of already-flagged review \
reasons, a summary of clinically relevant events since the last prep brief (or since intake, if \
this is the first brief), and relevant excerpts from the patient's own notes/documents.

Produce exactly two sections as JSON:
- since_last_visit: a concise narrative summary (2-4 sentences) of what has changed or happened \
since the last visit, grounded only in the provided events and profile — never invent events.
- suggested_focus: 2-4 concrete, non-diagnostic discussion points or things to check on during \
the upcoming visit, grounded in the flags, profile, and note excerpts provided.

If no meaningful activity occurred since the last visit, say so plainly in since_last_visit \
rather than fabricating detail."""

_ASSISTANT_SYSTEM_INSTRUCTION = """You are a patient-education assistant for Scaffold Health, an \
orthopedic rehab platform, answering a single question from a patient recovering from ACL \
reconstruction surgery. This system is advisory-only: you never diagnose, evaluate symptoms, \
recommend treatment, or make any clinical claim — you only share general educational \
information grounded in the provided excerpts.

You will be given the patient's question and relevant excerpts from a shared patient-education \
corpus (general recovery information, not this specific patient's records).

Produce your response as JSON with exactly two fields:
- redirect: true if the question is, in any way, about the patient's own symptoms, pain, \
swelling, wound appearance, or anything that reads as urgent or concerning rather than general \
education — in that case, set answer to an empty string, since a fixed clinic-referral message \
will be shown instead, never your own text.
- answer: when redirect is false, a concise, plain-language answer grounded only in the \
provided excerpts — never invent information beyond them. If the excerpts don't cover the \
question, say so plainly rather than guessing.

When in doubt about whether a question concerns the patient's own condition, set redirect to \
true — it is always safer to refer the patient to their clinic than to answer with anything \
that could be read as clinical guidance."""

_COPILOT_SYSTEM_INSTRUCTION = """You are a clinical copilot for a therapist at Scaffold Health, \
an orthopedic rehab platform, answering the therapist's own questions about one specific patient \
recovering from ACL reconstruction surgery. This system is advisory-only: you never diagnose, \
recommend treatment, or make clinical decisions — you only surface and discuss what has already \
been documented, and share general clinical-guideline information, to support the therapist's \
own judgment.

You will be given the patient's current Knowledge Profile, a summary of their recent activity, \
relevant excerpts from the patient's own notes/documents, relevant excerpts from a shared \
clinical-guidelines corpus, and the recent conversation history. Answer the therapist's latest \
question grounded only in what's provided — never invent facts about this patient. If the \
provided material doesn't cover the question, say so plainly rather than guessing.

Produce your response as JSON with exactly one field:
- answer: a concise, plain-language answer for the therapist."""

_client: "Groq | None" = None
_gemini_client: "genai.Client | None" = None


def _get_client() -> "Groq":
    global _client
    if _client is not None:
        return _client
    if not settings.groq_api_key:
        raise LLMExtractionError("GROQ_API_KEY is not configured")
    if Groq is None:
        raise LLMExtractionError("groq package is not installed")
    _client = Groq(api_key=settings.groq_api_key, timeout=60.0)
    return _client


def _get_gemini_client() -> "genai.Client":
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client
    if not settings.gemini_api_key:
        raise LLMExtractionError("GEMINI_API_KEY is not configured")
    if genai is None:
        raise LLMExtractionError("google-genai package is not installed")
    _gemini_client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=genai_types.HttpOptions(timeout=60_000),
    )
    return _gemini_client


def _with_fallback(primary, fallback) -> str:
    """Run `primary` (Groq), falling back to `fallback` (Gemini) only if
    the primary call itself raises — auth failure, timeout, rate limit, or
    any other request-level error. A downstream JSON-parsing error is not
    retried here: that happens outside this helper, since a malformed
    response from one provider says nothing about whether the other would
    do better, and re-running the same-shaped prompt against a fallback
    provider is the only case where switching providers can plausibly help.
    """
    try:
        return primary()
    except LLMExtractionError as primary_exc:
        try:
            return fallback()
        except LLMExtractionError as fallback_exc:
            raise LLMExtractionError(
                f"Groq failed ({primary_exc}); Gemini fallback also failed ({fallback_exc})"
            ) from fallback_exc


def extract_facts(text: str, schema: list[str]) -> list[ExtractedFact]:
    """One structured-output LLM call over `text`, returning candidate facts
    confined to the field names in `schema`. Merge routing — which strategy
    applies, contradiction handling — happens entirely in app/profile; the
    LLM never decides how a conflict is resolved (PRD §9).
    """
    raw = _with_fallback(
        lambda: _generate(text, allowed_fields=schema),
        lambda: _generate_gemini(text, allowed_fields=schema),
    )
    try:
        payload = _ExtractedFactsPayload.model_validate_json(raw)
    except ValueError as exc:
        raise LLMExtractionError(f"Model returned invalid JSON: {exc}") from exc
    return [fact for fact in payload.facts if fact.field_name in schema]


def generate_brief_text(
    *,
    profile_summary: str,
    flags: list[str],
    recent_events_summary: str,
    note_excerpts: list[str],
) -> BriefSections:
    """One structured-output LLM call narrating a therapist prep brief from
    already-computed inputs (PRD §9) — the LLM only narrates and suggests
    discussion points; it never decides flags or clinical facts itself.
    """
    raw = _with_fallback(
        lambda: _generate_brief(
            profile_summary=profile_summary,
            flags=flags,
            recent_events_summary=recent_events_summary,
            note_excerpts=note_excerpts,
        ),
        lambda: _generate_brief_gemini(
            profile_summary=profile_summary,
            flags=flags,
            recent_events_summary=recent_events_summary,
            note_excerpts=note_excerpts,
        ),
    )
    try:
        return BriefSections.model_validate_json(raw)
    except ValueError as exc:
        raise LLMExtractionError(f"Model returned invalid JSON: {exc}") from exc


def answer_patient_question(*, question: str, education_excerpts: list[str]) -> AssistantAnswer:
    """One structured-output LLM call answering a patient's single-turn question \
    against patient-education excerpts (PRD §5.8/§9). This is a defense-in-depth \
    check only — the authoritative redirect decision is the deterministic keyword \
    gate in app/assistant/urgent_detection.py, checked before this is ever called.
    """
    raw = _with_fallback(
        lambda: _generate_assistant_answer(question=question, education_excerpts=education_excerpts),
        lambda: _generate_assistant_answer_gemini(
            question=question, education_excerpts=education_excerpts
        ),
    )
    try:
        return AssistantAnswer.model_validate_json(raw)
    except ValueError as exc:
        raise LLMExtractionError(f"Model returned invalid JSON: {exc}") from exc


def answer_copilot_message(
    *,
    question: str,
    profile_summary: str,
    recent_activity_summary: str,
    patient_note_excerpts: list[str],
    guideline_excerpts: list[str],
    history: list[dict[str, str]],
) -> CopilotAnswer:
    """One structured-output LLM call answering a therapist's message in the
    per-patient copilot chat, grounded in that patient's Knowledge Profile,
    recent activity, notes, and the shared clinical-guidelines corpus, plus
    `history` (prior turns of this same conversation, oldest first) for
    multi-turn continuity.
    """
    raw = _with_fallback(
        lambda: _generate_copilot_answer(
            question=question,
            profile_summary=profile_summary,
            recent_activity_summary=recent_activity_summary,
            patient_note_excerpts=patient_note_excerpts,
            guideline_excerpts=guideline_excerpts,
            history=history,
        ),
        lambda: _generate_copilot_answer_gemini(
            question=question,
            profile_summary=profile_summary,
            recent_activity_summary=recent_activity_summary,
            patient_note_excerpts=patient_note_excerpts,
            guideline_excerpts=guideline_excerpts,
            history=history,
        ),
    )
    try:
        return CopilotAnswer.model_validate_json(raw)
    except ValueError as exc:
        raise LLMExtractionError(f"Model returned invalid JSON: {exc}") from exc


def embed_text(
    text: str, *, task_type: str = "RETRIEVAL_DOCUMENT", source: str | None = None
) -> list[float]:
    """Provider-agnostic embedding call (PRD §6.4). `task_type` defaults to
    RETRIEVAL_DOCUMENT for indexing; a retrieval-side caller should pass
    RETRIEVAL_QUERY (Gemini's asymmetric embedding convention — Gemini is
    the embeddings provider here since Groq has no embeddings API).

    RETRIEVAL_QUERY calls are cached in Redis, keyed on normalized text +
    model + task_type + dimensions — the vector is a deterministic function
    of those, so a cache hit is always correct, never stale. `source`
    identifies the calling feature (e.g. "briefs", "assistant", "copilot")
    for per-call-site hit/miss visibility and is required for RETRIEVAL_QUERY
    calls; letting it silently default would defeat the point of tracking it.
    A Redis outage degrades this to a live call on every request rather than
    failing it — see `_get_cached_embedding`/`_set_cached_embedding`.
    """
    if task_type != _CACHEABLE_TASK_TYPE:
        return _embed(text, task_type=task_type)

    if not source:
        raise ValueError("source is required when task_type is RETRIEVAL_QUERY")

    key = _embedding_cache_key(text, task_type=task_type)
    cached = _get_cached_embedding(key)
    if cached is not None:
        _record_cache_stat("hit", source)
        return cached

    _record_cache_stat("miss", source)
    vector = _embed(text, task_type=task_type)
    _set_cached_embedding(key, vector)
    return vector


def _embedding_cache_key(text: str, *, task_type: str) -> str:
    """Content-based key: normalized text + model + task_type + output dims
    hashed together, never stored verbatim — query text (patient/therapist
    questions) can be PHI-adjacent clinical text, and Redis keys are visible
    via KEYS/MONITOR/persistence dumps. `v1` lets a future change to the
    normalization/key scheme ship as v2 without an explicit cache flush.
    """
    normalized = " ".join(text.lower().split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return (
        f"{_EMBEDDING_CACHE_PREFIX}:{settings.gemini_embedding_model}:"
        f"{task_type}:{EMBEDDING_DIMENSIONS}:{digest}"
    )


def _get_cached_embedding(key: str) -> list[float] | None:
    try:
        raw = get_redis_client().get(key)
    except RedisError as exc:
        logger.warning("embedding cache GET failed, falling through to Gemini: %s", exc)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None  # corrupt entry: treat as a miss, never raise


def _set_cached_embedding(key: str, vector: list[float]) -> None:
    try:
        get_redis_client().setex(key, settings.embedding_cache_ttl_seconds, json.dumps(vector))
    except RedisError as exc:
        logger.warning("embedding cache SET failed (result still returned): %s", exc)


def _record_cache_stat(kind: str, source: str) -> None:
    """Best-effort hit/miss counters for manual inspection (`redis-cli GET
    embcache:stats:hit:<source>`) — not a metrics system, just enough
    visibility to decide later whether further caching layers are worth it.
    """
    try:
        get_redis_client().incr(f"embcache:stats:{kind}:{source}")
    except RedisError:
        pass


def _embed(text: str, *, task_type: str) -> list[float]:
    """Thin seam around the Gemini SDK embedding call, isolated so tests
    can monkeypatch it without a network call, mirroring `_generate`.
    """
    client = _get_gemini_client()
    start = time.perf_counter()
    try:
        response = client.models.embed_content(
            model=settings.gemini_embedding_model,
            contents=text,
            config=genai_types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=EMBEDDING_DIMENSIONS,
            ),
        )
    except Exception as exc:
        _log_llm_call("gemini", "embed_text", start, error=exc)
        raise LLMExtractionError(f"Gemini embedding request failed: {exc}") from exc
    if not response.embeddings:
        error = LLMExtractionError("Gemini returned no embeddings")
        _log_llm_call("gemini", "embed_text", start, error=error)
        raise error
    metadata = getattr(response, "metadata", None)
    tokens = {"billable_characters": metadata.billable_character_count} if metadata else None
    _log_llm_call("gemini", "embed_text", start, tokens=tokens)
    return list(response.embeddings[0].values)


def _brief_prompt(
    *,
    profile_summary: str,
    flags: list[str],
    recent_events_summary: str,
    note_excerpts: list[str],
) -> str:
    excerpts_block = "\n---\n".join(note_excerpts) if note_excerpts else "none"
    return (
        f"Knowledge Profile:\n{profile_summary}\n\n"
        f"Flagged review reasons: {', '.join(flags) if flags else 'none'}\n\n"
        f"Events since last visit:\n{recent_events_summary}\n\n"
        f"Relevant note excerpts:\n{excerpts_block}"
    )


def _assistant_prompt(*, question: str, education_excerpts: list[str]) -> str:
    excerpts_block = "\n---\n".join(education_excerpts) if education_excerpts else "none"
    return f"Patient question:\n{question}\n\nRelevant patient-education excerpts:\n{excerpts_block}"


def _copilot_prompt(
    *,
    question: str,
    profile_summary: str,
    recent_activity_summary: str,
    patient_note_excerpts: list[str],
    guideline_excerpts: list[str],
) -> str:
    notes_block = "\n---\n".join(patient_note_excerpts) if patient_note_excerpts else "none"
    guidelines_block = "\n---\n".join(guideline_excerpts) if guideline_excerpts else "none"
    return (
        f"Knowledge Profile:\n{profile_summary}\n\n"
        f"Recent activity:\n{recent_activity_summary}\n\n"
        f"Relevant patient note excerpts:\n{notes_block}\n\n"
        f"Relevant clinical guideline excerpts:\n{guidelines_block}\n\n"
        f"Therapist's question:\n{question}"
    )


def _generate(text: str, *, allowed_fields: list[str]) -> str:
    """Thin seam around the Groq SDK call, isolated so tests can
    monkeypatch it and exercise extract_facts's parsing/filtering logic
    without a network call.
    """
    client = _get_client()
    start = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {
                    "role": "system",
                    "content": _EXTRACTION_SYSTEM_INSTRUCTION.format(
                        fields=", ".join(allowed_fields)
                    ),
                },
                {"role": "user", "content": text},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "extracted_facts",
                    "schema": _ExtractedFactsPayload.model_json_schema(),
                    "strict": True,
                },
            },
        )
    except Exception as exc:
        _log_llm_call("groq", "extract_facts", start, error=exc)
        raise LLMExtractionError(f"Groq request failed: {exc}") from exc
    raw = response.choices[0].message.content
    if not raw:
        error = LLMExtractionError("Groq returned an empty response")
        _log_llm_call("groq", "extract_facts", start, error=error)
        raise error
    _log_llm_call("groq", "extract_facts", start, tokens=_groq_usage(response))
    return raw


def _generate_brief(
    *,
    profile_summary: str,
    flags: list[str],
    recent_events_summary: str,
    note_excerpts: list[str],
) -> str:
    """Thin seam around the Groq SDK call, isolated so tests can
    monkeypatch it and exercise generate_brief_text's parsing logic without
    a network call, mirroring `_generate`.
    """
    client = _get_client()
    prompt = _brief_prompt(
        profile_summary=profile_summary,
        flags=flags,
        recent_events_summary=recent_events_summary,
        note_excerpts=note_excerpts,
    )
    start = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": _BRIEF_SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "brief_sections",
                    "schema": BriefSections.model_json_schema(),
                    "strict": True,
                },
            },
        )
    except Exception as exc:
        _log_llm_call("groq", "generate_brief", start, error=exc)
        raise LLMExtractionError(f"Groq request failed: {exc}") from exc
    raw = response.choices[0].message.content
    if not raw:
        error = LLMExtractionError("Groq returned an empty response")
        _log_llm_call("groq", "generate_brief", start, error=error)
        raise error
    _log_llm_call("groq", "generate_brief", start, tokens=_groq_usage(response))
    return raw


def _generate_copilot_answer(
    *,
    question: str,
    profile_summary: str,
    recent_activity_summary: str,
    patient_note_excerpts: list[str],
    guideline_excerpts: list[str],
    history: list[dict[str, str]],
) -> str:
    """Thin seam around the Groq SDK call, isolated so tests can monkeypatch
    it and exercise answer_copilot_message's parsing logic without a
    network call, mirroring `_generate_assistant_answer`. Unlike the other
    calls here, prior conversation turns are passed as real message-array
    entries rather than folded into the prompt string, so Groq sees actual
    turn-taking history.
    """
    client = _get_client()
    prompt = _copilot_prompt(
        question=question,
        profile_summary=profile_summary,
        recent_activity_summary=recent_activity_summary,
        patient_note_excerpts=patient_note_excerpts,
        guideline_excerpts=guideline_excerpts,
    )
    start = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": _COPILOT_SYSTEM_INSTRUCTION},
                *history,
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "copilot_answer",
                    "schema": CopilotAnswer.model_json_schema(),
                    "strict": True,
                },
            },
        )
    except Exception as exc:
        _log_llm_call("groq", "copilot_answer", start, error=exc)
        raise LLMExtractionError(f"Groq request failed: {exc}") from exc
    raw = response.choices[0].message.content
    if not raw:
        error = LLMExtractionError("Groq returned an empty response")
        _log_llm_call("groq", "copilot_answer", start, error=error)
        raise error
    _log_llm_call("groq", "copilot_answer", start, tokens=_groq_usage(response))
    return raw


def _generate_assistant_answer(*, question: str, education_excerpts: list[str]) -> str:
    """Thin seam around the Groq SDK call, isolated so tests can monkeypatch
    it and exercise answer_patient_question's parsing logic without a
    network call, mirroring `_generate_brief`.
    """
    client = _get_client()
    prompt = _assistant_prompt(question=question, education_excerpts=education_excerpts)
    start = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": _ASSISTANT_SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "assistant_answer",
                    "schema": AssistantAnswer.model_json_schema(),
                    "strict": True,
                },
            },
        )
    except Exception as exc:
        _log_llm_call("groq", "assistant_answer", start, error=exc)
        raise LLMExtractionError(f"Groq request failed: {exc}") from exc
    raw = response.choices[0].message.content
    if not raw:
        error = LLMExtractionError("Groq returned an empty response")
        _log_llm_call("groq", "assistant_answer", start, error=error)
        raise error
    _log_llm_call("groq", "assistant_answer", start, tokens=_groq_usage(response))
    return raw


def _gemini_generate(
    *, operation: str, system_instruction: str, contents, schema: type[BaseModel]
) -> str:
    """Thin seam around the Gemini SDK text-generation call, shared by all
    four fallback functions below, mirroring the Groq `_generate*` seams so
    tests can monkeypatch each fallback independently without a network call.
    `operation` uses the same name as the corresponding Groq seam (e.g.
    "extract_facts"), so the two providers' logs are comparable.
    """
    client = _get_gemini_client()
    start = time.perf_counter()
    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
    except Exception as exc:
        _log_llm_call("gemini", operation, start, error=exc)
        raise LLMExtractionError(f"Gemini request failed: {exc}") from exc
    raw = response.text
    if not raw:
        error = LLMExtractionError("Gemini returned an empty response")
        _log_llm_call("gemini", operation, start, error=error)
        raise error
    _log_llm_call("gemini", operation, start, tokens=_gemini_usage(response))
    return raw


def _generate_gemini(text: str, *, allowed_fields: list[str]) -> str:
    return _gemini_generate(
        operation="extract_facts",
        system_instruction=_EXTRACTION_SYSTEM_INSTRUCTION.format(fields=", ".join(allowed_fields)),
        contents=text,
        schema=_ExtractedFactsPayload,
    )


def _generate_brief_gemini(
    *,
    profile_summary: str,
    flags: list[str],
    recent_events_summary: str,
    note_excerpts: list[str],
) -> str:
    return _gemini_generate(
        operation="generate_brief",
        system_instruction=_BRIEF_SYSTEM_INSTRUCTION,
        contents=_brief_prompt(
            profile_summary=profile_summary,
            flags=flags,
            recent_events_summary=recent_events_summary,
            note_excerpts=note_excerpts,
        ),
        schema=BriefSections,
    )


def _generate_assistant_answer_gemini(*, question: str, education_excerpts: list[str]) -> str:
    return _gemini_generate(
        operation="assistant_answer",
        system_instruction=_ASSISTANT_SYSTEM_INSTRUCTION,
        contents=_assistant_prompt(question=question, education_excerpts=education_excerpts),
        schema=AssistantAnswer,
    )


def _generate_copilot_answer_gemini(
    *,
    question: str,
    profile_summary: str,
    recent_activity_summary: str,
    patient_note_excerpts: list[str],
    guideline_excerpts: list[str],
    history: list[dict[str, str]],
) -> str:
    """Gemini uses "model" rather than Groq/OpenAI's "assistant" as the
    role name for prior turns, so `history` is remapped before being sent.
    """
    gemini_history = [
        {
            "role": "model" if turn["role"] == "assistant" else "user",
            "parts": [{"text": turn["content"]}],
        }
        for turn in history
    ]
    prompt = _copilot_prompt(
        question=question,
        profile_summary=profile_summary,
        recent_activity_summary=recent_activity_summary,
        patient_note_excerpts=patient_note_excerpts,
        guideline_excerpts=guideline_excerpts,
    )
    return _gemini_generate(
        operation="copilot_answer",
        system_instruction=_COPILOT_SYSTEM_INSTRUCTION,
        contents=[*gemini_history, {"role": "user", "parts": [{"text": prompt}]}],
        schema=CopilotAnswer,
    )
