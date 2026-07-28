"""Golden-set evaluation for the extraction pipeline (PRD §9). Runs real
Gemini calls against `golden_notes/*.txt` and scores the results against
`golden_labels.json`, reporting precision/recall/F1 per field.

Usage (from backend/, with GEMINI_API_KEY set):
    python -m eval.run_eval
"""

import json
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


def _extract_facts_with_retry(text: str, schema: list[str]) -> list[ExtractedFact]:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return extract_facts(text, schema=schema)
        except LLMExtractionError as exc:
            if attempt == MAX_ATTEMPTS:
                raise
            print(f"  attempt {attempt} failed ({exc}); retrying in {RETRY_BACKOFF_SECONDS}s")
            time.sleep(RETRY_BACKOFF_SECONDS)
    raise AssertionError("unreachable")


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
    for note_path in note_paths:
        text = note_path.read_text()
        labels = labels_by_note.get(note_path.name, [])

        try:
            facts = _extract_facts_with_retry(text, schema=EXTRACTABLE_FIELDS)
        except LLMExtractionError as exc:
            print(f"skipping {note_path.name}: {exc}")
            skipped_notes.append(note_path.name)
            continue

        extracted_by_field: dict[str, list[str]] = defaultdict(list)
        for fact in facts:
            extracted_by_field[fact.field_name].append(fact.value)

        note_counts = score_note(extracted_by_field, labels)
        for field_name, counts in note_counts.items():
            for key in ("tp", "fp", "fn"):
                totals[field_name][key] += counts[key]

        note_reports.append(
            {
                "note": note_path.name,
                "extracted": {k: v for k, v in extracted_by_field.items()},
                "counts": {k: dict(v) for k, v in note_counts.items()},
            }
        )
        print(f"scored {note_path.name} ({len(facts)} facts extracted)")

    if skipped_notes:
        print(f"\n{len(skipped_notes)} note(s) skipped after repeated failures: {skipped_notes}")

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
            },
            indent=2,
        )
    )
    print(f"\nFull results written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
