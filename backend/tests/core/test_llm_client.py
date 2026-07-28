import pytest

from app.core import llm_client
from app.core.llm_client import LLMExtractionError, embed_text, extract_facts, generate_brief_text


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
    monkeypatch.setattr(llm_client.settings, "gemini_api_key", None)
    monkeypatch.setattr(llm_client, "_client", None)

    with pytest.raises(LLMExtractionError, match="GEMINI_API_KEY"):
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
    monkeypatch.setattr(llm_client, "_client", None)

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

    monkeypatch.setattr(llm_client, "_client", _StubClient())
    monkeypatch.setattr(llm_client.settings, "gemini_api_key", "fake-key")

    with pytest.raises(LLMExtractionError, match="no embeddings"):
        embed_text("text")
