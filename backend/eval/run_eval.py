"""Golden-set evaluation for the extraction pipeline (PRD §9). Runs real
Groq calls against `golden_notes/*.txt` and scores the results against
`golden_labels.json`, reporting precision/recall/F1 per field.

Usage (from backend/, with GROQ_API_KEY set):
    python -m eval.run_eval
"""

import json
import math
import time
from collections import defaultdict
from pathlib import Path

from app.core.llm_client import ExtractedFact, LLMExtractionError, extract_facts
from app.profile.events import EXTRACTABLE_FIELDS

EVAL_DIR = Path(__file__).parent
NOTES_DIR = EVAL_DIR / "golden_notes"
LABELS_PATH = EVAL_DIR / "golden_labels.json"
RESULTS_PATH = EVAL_DIR / "results.json"

# The free tier occasionally returns a transient 503 ("model overloaded")
# under shared load — retry a few times with backoff rather than losing an
# otherwise-successful run to one flaky call.
MAX_ATTEMPTS = 4
RETRY_BACKOFF_SECONDS = 15


def _extract_facts_with_retry(text: str, schema: list[str]) -> tuple[list[ExtractedFact], float]:
    """Returns (facts, latency_seconds) where latency times only the final
    successful call — retry backoff sleep and earlier failed attempts are
    operational noise, not extraction latency.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        start = time.perf_counter()
        try:
            facts = extract_facts(text, schema=schema)
            return facts, time.perf_counter() - start
        except LLMExtractionError as exc:
            if attempt == MAX_ATTEMPTS:
                raise
            print(f"  attempt {attempt} failed ({exc}); retrying in {RETRY_BACKOFF_SECONDS}s")
            time.sleep(RETRY_BACKOFF_SECONDS)
    raise AssertionError("unreachable")


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return ordered[int(k)]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def _normalize_whitespace(value: str) -> str:
    return " ".join(value.split())


def _check_evidence(facts: list[ExtractedFact], text: str) -> tuple[int, int, list[dict]]:
    """A fact's source_quote must be a verbatim span of the note text (per
    the extraction prompt's instruction) — this is a deterministic check for
    whether the model actually quoted vs. paraphrased/hallucinated. Whitespace
    is normalized before comparing since the golden notes are hand-wrapped
    with line breaks mid-sentence, which the model naturally collapses when
    it reproduces a quote — that's a formatting artifact, not a mismatch.
    """
    normalized_text = _normalize_whitespace(text)
    valid = 0
    invalid: list[dict] = []
    for fact in facts:
        if _normalize_whitespace(fact.source_quote) in normalized_text:
            valid += 1
        else:
            invalid.append({"field_name": fact.field_name, "source_quote": fact.source_quote})
    return valid, len(facts), invalid


def _matches(value: str, keywords: list[str]) -> bool:
    lowered = value.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def score_note(
    extracted_by_field: dict[str, list[str]], labels: list[dict]
) -> dict[str, dict[str, int]]:
    """Greedy bipartite match between expected labels and extracted facts,
    per field. Each label consumes at most one extracted fact; extracted
    facts left unconsumed count as false positives (hallucinated / spurious
    extractions the golden set didn't expect).
    """
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    used: dict[str, set[int]] = defaultdict(set)

    labels_by_field: dict[str, list[dict]] = defaultdict(list)
    for label in labels:
        labels_by_field[label["field_name"]].append(label)

    for field_name, field_labels in labels_by_field.items():
        candidates = extracted_by_field.get(field_name, [])
        for label in field_labels:
            match_index = next(
                (
                    i
                    for i, value in enumerate(candidates)
                    if i not in used[field_name] and _matches(value, label["expected_keywords"])
                ),
                None,
            )
            if match_index is not None:
                used[field_name].add(match_index)
                counts[field_name]["tp"] += 1
            else:
                counts[field_name]["fn"] += 1

    for field_name, candidates in extracted_by_field.items():
        unmatched = len(candidates) - len(used[field_name])
        if unmatched:
            counts[field_name]["fp"] += unmatched

    return counts


def main() -> None:
    labels_by_note = json.loads(LABELS_PATH.read_text())
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    note_reports = []

    note_paths = sorted(NOTES_DIR.glob("*.txt"))
    skipped_notes: list[str] = []
    latencies: list[float] = []
    evidence_valid_total = 0
    evidence_checked_total = 0
    for note_path in note_paths:
        text = note_path.read_text()
        labels = labels_by_note.get(note_path.name, [])

        try:
            facts, latency = _extract_facts_with_retry(text, schema=EXTRACTABLE_FIELDS)
        except LLMExtractionError as exc:
            print(f"skipping {note_path.name}: {exc}")
            skipped_notes.append(note_path.name)
            continue
        latencies.append(latency)

        extracted_by_field: dict[str, list[str]] = defaultdict(list)
        for fact in facts:
            extracted_by_field[fact.field_name].append(fact.value)

        note_counts = score_note(extracted_by_field, labels)
        for field_name, counts in note_counts.items():
            for key in ("tp", "fp", "fn"):
                totals[field_name][key] += counts[key]

        evidence_valid, evidence_checked, invalid_quotes = _check_evidence(facts, text)
        evidence_valid_total += evidence_valid
        evidence_checked_total += evidence_checked

        note_reports.append(
            {
                "note": note_path.name,
                "extracted": {k: v for k, v in extracted_by_field.items()},
                "counts": {k: dict(v) for k, v in note_counts.items()},
                "latency_seconds": latency,
                "evidence": {
                    "valid": evidence_valid,
                    "total": evidence_checked,
                    "invalid_quotes": invalid_quotes,
                },
            }
        )
        print(f"scored {note_path.name} ({len(facts)} facts extracted, {latency:.2f}s)")

    if skipped_notes:
        print(f"\n{len(skipped_notes)} note(s) skipped after repeated failures: {skipped_notes}")

    document_success_rate = (
        (len(note_paths) - len(skipped_notes)) / len(note_paths) if note_paths else 0.0
    )
    evidence_validity_rate = (
        evidence_valid_total / evidence_checked_total if evidence_checked_total else 0.0
    )
    latency_p95 = _percentile(latencies, 0.95)
    latency_mean = sum(latencies) / len(latencies) if latencies else 0.0

    print(f"\ndocument success rate: {document_success_rate:.2%}")
    print(f"evidence validity rate: {evidence_validity_rate:.2%}")
    print(f"latency: mean {latency_mean:.2f}s, p95 {latency_p95:.2f}s")

    print()
    print(f"{'field':<22}{'precision':>10}{'recall':>10}{'f1':>10}{'tp':>6}{'fp':>6}{'fn':>6}")
    overall_tp = overall_fp = overall_fn = 0
    per_field_results = {}
    for field_name in sorted(totals):
        c = totals[field_name]
        tp, fp, fn = c["tp"], c["fp"], c["fn"]
        overall_tp += tp
        overall_fp += fp
        overall_fn += fn
        precision, recall, f1 = _prf(tp, fp, fn)
        per_field_results[field_name] = {
            "tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1
        }
        print(f"{field_name:<22}{precision:>10.2f}{recall:>10.2f}{f1:>10.2f}{tp:>6}{fp:>6}{fn:>6}")

    precision, recall, f1 = _prf(overall_tp, overall_fp, overall_fn)
    print(f"{'OVERALL':<22}{precision:>10.2f}{recall:>10.2f}{f1:>10.2f}{overall_tp:>6}{overall_fp:>6}{overall_fn:>6}")

    RESULTS_PATH.write_text(
        json.dumps(
            {
                "per_field": per_field_results,
                "overall": {
                    "tp": overall_tp,
                    "fp": overall_fp,
                    "fn": overall_fn,
                    "precision": precision,
                    "recall": recall,
                    "f1": f1,
                },
                "notes": note_reports,
                "skipped_notes": skipped_notes,
                "document_success_rate": document_success_rate,
                "evidence_validity_rate": evidence_validity_rate,
                "latency_seconds": {
                    "mean": latency_mean,
                    "p95": latency_p95,
                    "values": latencies,
                },
            },
            indent=2,
        )
    )
    print(f"\nFull results written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
