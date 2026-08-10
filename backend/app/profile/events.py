STREAM_TYPE_PROFILE = "patient_profile"

# One event per (document, field_name) extraction batch — see commands.py.
PROFILE_FIELDS_MERGED = "ProfileFieldsMerged"

STRATEGY_OVERWRITE = "overwrite"
STRATEGY_APPEND_ONLY = "append_only"
STRATEGY_IMMUTABLE_ONCE_SET = "immutable_once_set"

# Mirrors the merge-strategy table in PRD §6.3. current_phase is deliberately
# excluded — it only ever changes via the therapist's explicit AdvancePhase
# command, never from extraction.
FIELD_MERGE_STRATEGIES = {
    "active_restrictions": STRATEGY_OVERWRITE,
    "active_concerns": STRATEGY_OVERWRITE,
    "milestones": STRATEGY_APPEND_ONLY,
    "injury": STRATEGY_IMMUTABLE_ONCE_SET,
    "surgery_date": STRATEGY_IMMUTABLE_ONCE_SET,
}

EXTRACTABLE_FIELDS = list(FIELD_MERGE_STRATEGIES)

# Typed needs_review reasons (PRD §6.3: "never a generic flag").
REASON_CONTRADICTION = "Contradiction"
REASON_ADHERENCE_DROP = "Adherence drop"
REASON_NO_CHECKIN = "No check-in"
REASON_ASSISTANT_REDIRECT = "Symptom question"
