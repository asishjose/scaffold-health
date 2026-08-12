import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core import llm_client
from app.core.llm_client import (
    LLMExtractionError,
    answer_copilot_message,
    embed_text,
    extract_facts,
    generate_brief_text,
)
from app.core.redis_client import get_redis_client


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


def test_embed_text_returns_cached_vector_without_calling_gemini(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm_client, "_get_cached_embedding", lambda key: [9.9])
    monkeypatch.setattr(llm_client, "_record_cache_stat", lambda kind, source: None)

    def _embed_should_not_be_called(text, *, task_type):
        raise AssertionError("_embed should not be called on a cache hit")

    monkeypatch.setattr(llm_client, "_embed", _embed_should_not_be_called)

    vector = embed_text("some question", task_type="RETRIEVAL_QUERY", source="briefs")

    assert vector == [9.9]


def test_embed_text_stores_result_on_cache_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_client, "_get_cached_embedding", lambda key: None)
    monkeypatch.setattr(llm_client, "_record_cache_stat", lambda kind, source: None)
    monkeypatch.setattr(llm_client, "_embed", lambda text, *, task_type: [1.0, 2.0])
    stored: dict[str, list[float]] = {}
    monkeypatch.setattr(
        llm_client, "_set_cached_embedding", lambda key, vector: stored.update(value=vector)
    )

    vector = embed_text("some question", task_type="RETRIEVAL_QUERY", source="assistant")

    assert vector == [1.0, 2.0]
    assert stored["value"] == [1.0, 2.0]


def test_embed_text_skips_cache_for_retrieval_document(monkeypatch: pytest.MonkeyPatch) -> None:
    def _cache_should_not_be_called(*args, **kwargs):
        raise AssertionError("cache should not be consulted for RETRIEVAL_DOCUMENT")

    monkeypatch.setattr(llm_client, "_get_cached_embedding", _cache_should_not_be_called)
    monkeypatch.setattr(llm_client, "_set_cached_embedding", _cache_should_not_be_called)
    monkeypatch.setattr(llm_client, "_embed", lambda text, *, task_type: [0.5])

    vector = embed_text("chunk text")

    assert vector == [0.5]


def test_embed_text_requires_source_for_retrieval_query() -> None:
    with pytest.raises(ValueError, match="source"):
        embed_text("some question", task_type="RETRIEVAL_QUERY")


def test_embedding_cache_key_normalizes_case_and_whitespace() -> None:
    key_a = llm_client._embedding_cache_key("Hello   World\n", task_type="RETRIEVAL_QUERY")
    key_b = llm_client._embedding_cache_key("hello world", task_type="RETRIEVAL_QUERY")
    key_c = llm_client._embedding_cache_key("a different question", task_type="RETRIEVAL_QUERY")

    assert key_a == key_b
    assert key_a != key_c


def test_embed_text_falls_through_when_cache_get_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FailingClient:
        def get(self, key):
            raise RedisConnectionError("redis unreachable")

        def setex(self, key, ttl, value):
            raise RedisConnectionError("redis unreachable")

        def incr(self, key):
            raise RedisConnectionError("redis unreachable")

    monkeypatch.setattr(llm_client, "get_redis_client", lambda: _FailingClient())
    monkeypatch.setattr(llm_client, "_embed", lambda text, *, task_type: [3.0])

    vector = embed_text("some question", task_type="RETRIEVAL_QUERY", source="copilot")

    assert vector == [3.0]


def test_embed_text_falls_through_when_cache_set_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FailingSetClient:
        def get(self, key):
            return None

        def setex(self, key, ttl, value):
            raise RedisConnectionError("redis unreachable")

        def incr(self, key):
            raise RedisConnectionError("redis unreachable")

    monkeypatch.setattr(llm_client, "get_redis_client", lambda: _FailingSetClient())
    monkeypatch.setattr(llm_client, "_embed", lambda text, *, task_type: [4.0])

    vector = embed_text("some question", task_type="RETRIEVAL_QUERY", source="copilot")

    assert vector == [4.0]


def test_embed_text_caches_across_real_redis_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Integration test against the real Redis service (same docker-compose
    instance the DB tests already assume is running), mirroring the DB
    fixture's "just needs the local service up" convention. Only `_embed`
    is faked; the cache key, GET/SETEX, and Redis client are all real.
    """
    calls: list[int] = []
    monkeypatch.setattr(
        llm_client, "_embed", lambda text, *, task_type: calls.append(1) or [7.0, 8.0]
    )
    key = llm_client._embedding_cache_key(
        "integration roundtrip text", task_type="RETRIEVAL_QUERY"
    )
    client = get_redis_client()
    client.delete(key)
    try:
        first = embed_text(
            "integration roundtrip text", task_type="RETRIEVAL_QUERY", source="briefs"
        )
        second = embed_text(
            "integration roundtrip text", task_type="RETRIEVAL_QUERY", source="briefs"
        )
        assert first == second == [7.0, 8.0]
        assert len(calls) == 1
    finally:
        client.delete(key)


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
