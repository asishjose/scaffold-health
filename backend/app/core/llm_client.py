"""Provider-agnostic LLM interface (PRD §9). Groq handles fact extraction
and brief generation; Gemini fills the one gap Groq's API doesn't cover
(embeddings). Callers depend only on `extract_facts` / `generate_brief_text`
/ `embed_text`, never on provider-specific types, so changing either
provider later touches only this file.
"""

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings

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


class LLMExtractionError(Exception):
    pass


EMBEDDING_DIMENSIONS = 768


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

_client: "Groq | None" = None
_embedding_client: "genai.Client | None" = None


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


def _get_embedding_client() -> "genai.Client":
    global _embedding_client
    if _embedding_client is not None:
        return _embedding_client
    if not settings.gemini_api_key:
        raise LLMExtractionError("GEMINI_API_KEY is not configured")
    if genai is None:
        raise LLMExtractionError("google-genai package is not installed")
    _embedding_client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=genai_types.HttpOptions(timeout=60_000),
    )
    return _embedding_client


def extract_facts(text: str, schema: list[str]) -> list[ExtractedFact]:
    """One structured-output LLM call over `text`, returning candidate facts
    confined to the field names in `schema`. Merge routing — which strategy
    applies, contradiction handling — happens entirely in app/profile; the
    LLM never decides how a conflict is resolved (PRD §9).
    """
    raw = _generate(text, allowed_fields=schema)
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
    raw = _generate_brief(
        profile_summary=profile_summary,
        flags=flags,
        recent_events_summary=recent_events_summary,
        note_excerpts=note_excerpts,
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
    raw = _generate_assistant_answer(question=question, education_excerpts=education_excerpts)
    try:
        return AssistantAnswer.model_validate_json(raw)
    except ValueError as exc:
        raise LLMExtractionError(f"Model returned invalid JSON: {exc}") from exc


def embed_text(text: str, *, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
    """Provider-agnostic embedding call (PRD §6.4). `task_type` defaults to
    RETRIEVAL_DOCUMENT for indexing; a retrieval-side caller should pass
    RETRIEVAL_QUERY (Gemini's asymmetric embedding convention — Gemini is
    the embeddings provider here since Groq has no embeddings API).
    """
    return _embed(text, task_type=task_type)


def _embed(text: str, *, task_type: str) -> list[float]:
    """Thin seam around the Gemini SDK embedding call, isolated so tests
    can monkeypatch it without a network call, mirroring `_generate`.
    """
    client = _get_embedding_client()
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
        raise LLMExtractionError(f"Gemini embedding request failed: {exc}") from exc
    if not response.embeddings:
        raise LLMExtractionError("Gemini returned no embeddings")
    return list(response.embeddings[0].values)


def _generate(text: str, *, allowed_fields: list[str]) -> str:
    """Thin seam around the Groq SDK call, isolated so tests can
    monkeypatch it and exercise extract_facts's parsing/filtering logic
    without a network call.
    """
    client = _get_client()
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
        raise LLMExtractionError(f"Groq request failed: {exc}") from exc
    raw = response.choices[0].message.content
    if not raw:
        raise LLMExtractionError("Groq returned an empty response")
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
    excerpts_block = "\n---\n".join(note_excerpts) if note_excerpts else "none"
    prompt = (
        f"Knowledge Profile:\n{profile_summary}\n\n"
        f"Flagged review reasons: {', '.join(flags) if flags else 'none'}\n\n"
        f"Events since last visit:\n{recent_events_summary}\n\n"
        f"Relevant note excerpts:\n{excerpts_block}"
    )
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
        raise LLMExtractionError(f"Groq request failed: {exc}") from exc
    raw = response.choices[0].message.content
    if not raw:
        raise LLMExtractionError("Groq returned an empty response")
    return raw


def _generate_assistant_answer(*, question: str, education_excerpts: list[str]) -> str:
    """Thin seam around the Groq SDK call, isolated so tests can monkeypatch
    it and exercise answer_patient_question's parsing logic without a
    network call, mirroring `_generate_brief`.
    """
    client = _get_client()
    excerpts_block = "\n---\n".join(education_excerpts) if education_excerpts else "none"
    prompt = f"Patient question:\n{question}\n\nRelevant patient-education excerpts:\n{excerpts_block}"
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
        raise LLMExtractionError(f"Groq request failed: {exc}") from exc
    raw = response.choices[0].message.content
    if not raw:
        raise LLMExtractionError("Groq returned an empty response")
    return raw
