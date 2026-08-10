// Mirrors backend/app/*/schemas.py response models.

export type Role = 'therapist' | 'patient'

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface TherapistSignupResponse {
  id: string
  name: string
  email: string
}

export interface InvitePreviewResponse {
  email: string
  expires_at: string
}

export interface AcceptInviteResponse {
  id: string
  email: string
}

export interface PatientListItem {
  id: string
  name: string
  current_phase: string
  surgery_date: string
  invite_accepted_at: string | null
  needs_review: string[]
}

export interface CheckIn {
  id: string
  pain_level: number
  note: string | null
  submitted_at: string
}

export type PainTrend = 'improving' | 'worsening' | 'stable'

export interface ProfileField {
  id: string
  field_name: string
  value: string
  confidence: number | null
  source_quote: string | null
  source_document_id: string | null
  extracted_at: string
  is_contradiction: boolean
  superseded_at: string | null
  acknowledged_at: string | null
}

export interface PatientDetail {
  id: string
  therapist_id: string
  name: string
  date_of_birth: string
  contact_email: string
  injury: string
  surgery_date: string
  current_phase: string
  invite_accepted_at: string | null
  created_at: string
  pain_history: CheckIn[]
  active_restrictions: string[]
  active_concerns: string[]
  milestones: string[]
  pain_trend: PainTrend | null
  exercise_adherence: number | null
  needs_review: string[]
  profile_fields: ProfileField[]
}

export interface PatientPortalDetail {
  id: string
  name: string
  injury: string
  surgery_date: string
  current_phase: string
  pain_trend: PainTrend | null
}

export interface PatientIntakeResponse {
  id: string
  name: string
  invite_token: string
  invite_expires_at: string
}

export interface PhaseAdvanceResponse {
  id: string
  current_phase: string
}

export type DocumentStatus = 'processing' | 'extracted' | 'failed'

export interface DocumentListItem {
  id: string
  filename: string
  content_type: string
  status: DocumentStatus
  created_at: string
  extracted_at: string | null
}

export interface Brief {
  id: string
  patient_id: string
  since_last_visit: string
  flags: string[]
  suggested_focus: string
  generated_at: string
}

export type TimelineEntryType = 'phase_advance' | 'milestone' | 'document_extracted'

export interface TimelineEntry {
  id: string
  entry_type: TimelineEntryType
  occurred_at: string
  from_phase: string | null
  to_phase: string | null
  note: string | null
  value: string | null
  confidence: number | null
  source_quote: string | null
  source_document_id: string | null
  filename: string | null
  document_id: string | null
}

export interface TimelinePortalEntry {
  id: string
  entry_type: TimelineEntryType
  occurred_at: string
  from_phase: string | null
  to_phase: string | null
  note: string | null
  value: string | null
  filename: string | null
}

export interface AssistantAnswer {
  id: string
  patient_id: string
  question: string
  answer: string
  redirected: boolean
  asked_at: string
}

export type CopilotMessageRole = 'therapist' | 'assistant'

export interface CopilotMessage {
  id: string
  patient_id: string
  role: CopilotMessageRole
  content: string
  posted_at: string
}
