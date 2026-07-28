import re

# Deterministic sentence-packing chunker (PRD §6.4: no LLM decision-making
# in this pipeline). Chunk size/overlap chosen for short clinical narrative
# text at MVP scale, not tuned against a large corpus.
CHUNK_SIZE_CHARS = 800
CHUNK_OVERLAP_CHARS = 150
MIN_CHUNK_CHARS = 40

_WHITESPACE_RE = re.compile(r"\s+")
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


def chunk_text(text: str) -> list[str]:
    """Splits `text` into overlapping, sentence-aligned chunks of roughly
    `CHUNK_SIZE_CHARS`. Pure function, no I/O, fully deterministic for a
    given input.
    """
    normalized = _WHITESPACE_RE.sub(" ", text).strip()
    if not normalized:
        return []

    sentences = [s for s in _SENTENCE_BOUNDARY_RE.split(normalized) if s]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for sentence in sentences:
        sentence_len = len(sentence) + (1 if current else 0)
        if current and current_len + sentence_len > CHUNK_SIZE_CHARS:
            chunks.append(" ".join(current))
            current = _carry_overlap(current)
            current_len = len(" ".join(current))
            sentence_len = len(sentence) + (1 if current else 0)
        current.append(sentence)
        current_len += sentence_len

    if current:
        chunks.append(" ".join(current))

    return [c for c in chunks if len(c) >= MIN_CHUNK_CHARS]


def _carry_overlap(sentences: list[str]) -> list[str]:
    """Carries trailing sentences forward into the next chunk, up to
    CHUNK_OVERLAP_CHARS, for retrieval-context continuity across chunk
    boundaries.
    """
    carried: list[str] = []
    carried_len = 0
    for sentence in reversed(sentences):
        next_len = len(sentence) + (1 if carried else 0)
        if carried and carried_len + next_len > CHUNK_OVERLAP_CHARS:
            break
        carried.insert(0, sentence)
        carried_len += next_len
    return carried
