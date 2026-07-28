from app.rag.allowlist import is_allowlist_violation, normalize


def test_normalize_collapses_whitespace_and_lowercases() -> None:
    assert normalize("  Full   Extension\n") == "full extension"


def test_chunk_that_is_essentially_a_known_value_is_a_violation() -> None:
    known = {"acl_reconstruction"}
    assert is_allowlist_violation("acl_reconstruction", known) == "acl_reconstruction"


def test_chunk_containing_a_known_email_is_a_violation() -> None:
    known = {"patient@example.com"}
    chunk = "Please follow up with the patient at patient@example.com next week."
    assert is_allowlist_violation(chunk, known) == "patient@example.com"


def test_chunk_that_merely_mentions_a_known_value_in_longer_prose_is_not_flagged() -> None:
    known = {"2026-01-15"}
    chunk = (
        "The patient continues to make steady progress with range of motion "
        "and reports minimal pain during daily activities, with full extension "
        "now consistently achieved during therapy sessions."
    )
    assert is_allowlist_violation(chunk, known) is None


def test_short_known_values_require_containment_not_just_ratio() -> None:
    # "acl" is short (< 6 chars) so containment alone shouldn't trigger it;
    # unrelated prose that happens to contain "acl" as a substring must not
    # be flagged just because it's short.
    known = {"acl"}
    chunk = "Patient tolerated the visit well and had no new concerns today."
    assert is_allowlist_violation(chunk, known) is None


def test_case_and_whitespace_insensitive_matching() -> None:
    known = {"Jane Patient"}
    assert is_allowlist_violation("  jane   patient  ", known) == "Jane Patient"


def test_no_match_returns_none() -> None:
    known = {"acl_reconstruction", "2026-01-15", "patient@example.com"}
    chunk = "MRI shows no evidence of meniscal tear; graft appears well-positioned."
    assert is_allowlist_violation(chunk, known) is None


def test_empty_known_values_never_violates() -> None:
    assert is_allowlist_violation("any text at all", set()) is None
