from app.rag.chunking import CHUNK_OVERLAP_CHARS, CHUNK_SIZE_CHARS, chunk_text


def test_empty_text_returns_no_chunks() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_short_text_returns_one_chunk() -> None:
    text = "The patient reports mild anterior knee pain after stairs."
    chunks = chunk_text(text)
    assert chunks == [text]


def test_text_below_min_chars_is_dropped() -> None:
    assert chunk_text("Ok.") == []


def test_long_text_splits_into_multiple_chunks_with_overlap() -> None:
    sentence = "The patient demonstrates good progress with quadriceps activation. "
    text = sentence * 40  # well over CHUNK_SIZE_CHARS

    chunks = chunk_text(text)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= CHUNK_SIZE_CHARS + CHUNK_OVERLAP_CHARS

    # Consecutive chunks share trailing/leading sentence(s) as overlap.
    first_sentences = chunks[0].split(". ")
    second_sentences = chunks[1].split(". ")
    assert first_sentences[-1] in chunks[1] or first_sentences[-2] in second_sentences[0]


def test_whitespace_is_collapsed() -> None:
    text = "Full   extension\n\nachieved.   Flexion improving."
    chunks = chunk_text(text)
    assert chunks == ["Full extension achieved. Flexion improving."]


def test_sentence_boundaries_are_respected() -> None:
    text = "Pain is well controlled. Swelling has decreased. Range of motion is improving."
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text
