import pytest

from app.core import llm_client
from app.core.llm_client import LLMExtractionError, extract_facts


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
