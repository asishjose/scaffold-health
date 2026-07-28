import re
from difflib import SequenceMatcher

# Near-exact-match guard against structured data leaking into the vector
# index (PRD §6.4). Deliberately not general PHI/NER redaction — MVP
# operates on synthetic data only (PRD §10) — just a leakage check against
# values already known/stored elsewhere in the system.
NEAR_EXACT_RATIO_THRESHOLD = 0.90

_WHITESPACE_RE = re.compile(r"\s+")


def normalize(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip().lower()


def is_allowlist_violation(chunk_text: str, known_values: set[str]) -> str | None:
    """Returns the matched known value if `chunk_text` is essentially a
    restatement of one of `known_values` (a structured field or PHI value),
    else None. Two checks: whole-chunk similarity ratio (catches a chunk
    that's just the known value, or the known value plus minor formatting),
    and substring containment (catches a short known value like an email or
    DOB embedded near-verbatim inside a longer chunk).
    """
    normalized_chunk = normalize(chunk_text)
    if not normalized_chunk:
        return None

    for value in known_values:
        normalized_value = normalize(value)
        if not normalized_value:
            continue

        if normalized_value in normalized_chunk and len(normalized_value) >= 6:
            return value

        ratio = SequenceMatcher(None, normalized_chunk, normalized_value).ratio()
        if ratio >= NEAR_EXACT_RATIO_THRESHOLD:
            return value

    return None
