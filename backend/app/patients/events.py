STREAM_TYPE_PATIENT = "patient"

PATIENT_CREATED = "PatientCreated"
PATIENT_ACCOUNT_ACTIVATED = "PatientAccountActivated"

# Fixed for MVP; Phase 2 introduces additional MSK protocols (see PRD roadmap).
INJURY_ACL_RECONSTRUCTION = "acl_reconstruction"

# Starting point of the ACL protocol phase sequence. Forward-only advancement
# is implemented by a later milestone (phase progression / checkins module).
INITIAL_PHASE = "pre_op"
