"""Provider-agnostic LLM interface (PRD §9). Gemini is the only
implementation for MVP; callers depend only on `extract_facts`, never on
Gemini-specific types, so swapping providers later touches only this file.
"""

from pydantic import BaseModel, Field

from app.core.config import settings

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover - dependency always installed via requirements.txt
    genai = None
    genai_types = None


class ExtractedFact(BaseModel):
    field_name: str
    value: str
    confidence: float = Field(ge=0, le=1)
    source_quote: str


class _ExtractedFactsPayload(BaseModel):
    facts: list[ExtractedFact]


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

_client: "genai.Client | None" = None


def _get_client() -> "genai.Client":
    global _client
    if _client is not None:
        return _client
    if not settings.gemini_api_key:
        raise LLMExtractionError("GEMINI_API_KEY is not configured")
    if genai is None:
        raise LLMExtractionError("google-genai package is not installed")
    _client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=genai_types.HttpOptions(timeout=60_000),
    )
    return _client


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


def embed_text(text: str, *, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
    """Provider-agnostic embedding call (PRD §6.4). `task_type` defaults to
    RETRIEVAL_DOCUMENT for indexing; a retrieval-side caller should pass
    RETRIEVAL_QUERY (Gemini's asymmetric embedding convention).
    """
    return _embed(text, task_type=task_type)


def _embed(text: str, *, task_type: str) -> list[float]:
    """Thin seam around the Gemini SDK embedding call, isolated so tests
    can monkeypatch it without a network call, mirroring `_generate`.
    """
    client = _get_client()
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
    """Thin seam around the Gemini SDK call, isolated so tests can
    monkeypatch it and exercise extract_facts's parsing/filtering logic
    without a network call.
    """
    client = _get_client()
    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=text,
            config=genai_types.GenerateContentConfig(
                system_instruction=_EXTRACTION_SYSTEM_INSTRUCTION.format(
                    fields=", ".join(allowed_fields)
                ),
                response_mime_type="application/json",
                response_schema=_ExtractedFactsPayload,
            ),
        )
    except Exception as exc:
        raise LLMExtractionError(f"Gemini request failed: {exc}") from exc
    if not response.text:
        raise LLMExtractionError("Gemini returned an empty response")
    return response.text
