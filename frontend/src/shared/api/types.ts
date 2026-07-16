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
}

export interface CheckIn {
  id: string
  pain_level: number
  note: string | null
  submitted_at: string
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
}

export interface PatientPortalDetail {
  id: string
  name: string
  injury: string
  surgery_date: string
  current_phase: string
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
