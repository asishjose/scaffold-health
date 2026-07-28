STREAM_TYPE_PATIENT = "patient"

PATIENT_CREATED = "PatientCreated"
PATIENT_ACCOUNT_ACTIVATED = "PatientAccountActivated"
PATIENT_PHASE_ADVANCED = "PatientPhaseAdvanced"

# Fixed for MVP; Phase 2 introduces additional MSK protocols (see PRD roadmap).
INJURY_ACL_RECONSTRUCTION = "acl_reconstruction"

# Simplified placeholder ACL protocol phase sequence — the PRD specifies
# forward-only, no-skip advancement but doesn't enumerate exact phase names;
# a real clinical protocol config would replace this list.
PHASE_SEQUENCE = [
    "pre_op",
    "phase_1_protection",
    "phase_2_early_strength",
    "phase_3_progressive_strength",
    "phase_4_advanced_strength",
    "phase_5_return_to_sport",
    "discharged",
]

INITIAL_PHASE = PHASE_SEQUENCE[0]
