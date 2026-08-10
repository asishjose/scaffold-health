import pytest

from app.core import llm_client
from app.core.llm_client import (
    LLMExtractionError,
    answer_copilot_message,
    embed_text,
    extract_facts,
    generate_brief_text,
)


def test_extract_facts_parses_valid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_client,
        "_generate",
        lambda text, *, allowed_fields: (
            '{"facts": [{"field_name": "milestones", "value": "Full extension", '
            '"confidence": 0.9, "source_quote": "quote"}]}'
        ),
    )

    facts = extract_facts("some clinical text", schema=["milestones"])

    assert len(facts) == 1
    assert facts[0].field_name == "milestones"
    assert facts[0].value == "Full extension"
    assert facts[0].confidence == 0.9


def test_extract_facts_filters_out_fields_outside_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_client,
        "_generate",
        lambda text, *, allowed_fields: (
            '{"facts": ['
            '{"field_name": "milestones", "value": "in schema", "confidence": 0.9, "source_quote": "q"},'
            '{"field_name": "current_phase", "value": "hallucinated", "confidence": 0.9, "source_quote": "q"}'
            "]}"
        ),
    )

    facts = extract_facts("text", schema=["milestones"])

    assert [f.field_name for f in facts] == ["milestones"]


def test_extract_facts_raises_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_client, "_generate", lambda text, *, allowed_fields: "not json")

    with pytest.raises(LLMExtractionError):
        extract_facts("text", schema=["milestones"])


def test_extract_facts_raises_when_api_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    # Both providers unconfigured, so the Gemini fallback can't paper over
    # the missing Groq key either — this exercises the "both failed" path
    # without making a real network call.
    monkeypatch.setattr(llm_client.settings, "groq_api_key", None)
    monkeypatch.setattr(llm_client, "_client", None)
    monkeypatch.setattr(llm_client.settings, "gemini_api_key", None)
    monkeypatch.setattr(llm_client, "_gemini_client", None)

    with pytest.raises(LLMExtractionError, match="GROQ_API_KEY"):
        extract_facts("text", schema=["milestones"])


def test_generate_brief_text_parses_valid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_client,
        "_generate_brief",
        lambda **kwargs: (
            '{"since_last_visit": "No new activity.", "suggested_focus": "Ask about pain."}'
        ),
    )

    sections = generate_brief_text(
        profile_summary="Injury: acl_reconstruction",
        flags=[],
        recent_events_summary="No new activity recorded since the last visit.",
        note_excerpts=[],
    )

    assert sections.since_last_visit == "No new activity."
    assert sections.suggested_focus == "Ask about pain."


def test_generate_brief_text_raises_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_client, "_generate_brief", lambda **kwargs: "not json")

    with pytest.raises(LLMExtractionError):
        generate_brief_text(
            profile_summary="Injury: acl_reconstruction",
            flags=[],
            recent_events_summary="",
            note_excerpts=[],
        )


def test_answer_copilot_message_parses_valid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_client,
        "_generate_copilot_answer",
        lambda **kwargs: '{"answer": "No active restrictions noted."}',
    )

    result = answer_copilot_message(
        question="Any restrictions?",
        profile_summary="Injury: acl_reconstruction",
        recent_activity_summary="No recent activity recorded.",
        patient_note_excerpts=[],
        guideline_excerpts=[],
        history=[],
    )

    assert result.answer == "No active restrictions noted."


def test_answer_copilot_message_raises_on_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_client, "_generate_copilot_answer", lambda **kwargs: "not json")

    with pytest.raises(LLMExtractionError):
        answer_copilot_message(
            question="Any restrictions?",
            profile_summary="",
            recent_activity_summary="",
            patient_note_excerpts=[],
            guideline_excerpts=[],
            history=[],
        )


def test_embed_text_returns_vector(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm_client,
        "_embed",
        lambda text, *, task_type: [0.1, 0.2, 0.3],
    )

    vector = embed_text("some clinical text")

    assert vector == [0.1, 0.2, 0.3]


def test_embed_text_raises_when_api_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_client.settings, "gemini_api_key", None)
    monkeypatch.setattr(llm_client, "_gemini_client", None)

    with pytest.raises(LLMExtractionError, match="GEMINI_API_KEY"):
        embed_text("text")


def test_embed_text_raises_when_response_has_no_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    class _EmptyResponse:
        embeddings: list = []

    class _StubModels:
        def embed_content(self, *, model, contents, config):
            return _EmptyResponse()

    class _StubClient:
        models = _StubModels()

    monkeypatch.setattr(llm_client, "_gemini_client", _StubClient())
    monkeypatch.setattr(llm_client.settings, "gemini_api_key", "fake-key")

    with pytest.raises(LLMExtractionError, match="no embeddings"):
        embed_text("text")


def test_extract_facts_falls_back_to_gemini_when_groq_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def _groq_fails(text, *, allowed_fields):
        raise LLMExtractionError("Groq request failed: boom")

    monkeypatch.setattr(llm_client, "_generate", _groq_fails)
    monkeypatch.setattr(
        llm_client,
        "_generate_gemini",
        lambda text, *, allowed_fields: (
            '{"facts": [{"field_name": "milestones", "value": "Full extension", '
            '"confidence": 0.9, "source_quote": "quote"}]}'
        ),
    )

    facts = extract_facts("some clinical text", schema=["milestones"])

    assert len(facts) == 1
    assert facts[0].value == "Full extension"


def test_extract_facts_raises_when_both_providers_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    def _groq_fails(text, *, allowed_fields):
        raise LLMExtractionError("Groq request failed: boom")

    def _gemini_fails(text, *, allowed_fields):
        raise LLMExtractionError("Gemini request failed: boom")

    monkeypatch.setattr(llm_client, "_generate", _groq_fails)
    monkeypatch.setattr(llm_client, "_generate_gemini", _gemini_fails)

    with pytest.raises(LLMExtractionError, match="Groq failed .*Gemini fallback also failed"):
        extract_facts("text", schema=["milestones"])
