import { ArrowLeft, FileText, Loader2, Upload } from 'lucide-react'
import { useRef, useState, type ChangeEvent, type DragEvent, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'

import { ApiError } from '@/shared/api/client'
import type { PatientDetail as PatientDetailType } from '@/shared/api/types'
import { NeedsReviewBadges } from '@/shared/components/NeedsReviewBadges'
import { useDocuments, useUploadDocument } from '@/shared/hooks/useDocuments'
import { useAdvancePhase, usePatient } from '@/shared/hooks/usePatients'
import { cn, formatDate, formatDateTime, injuryLabel, weeksPostOpLabel } from '@/shared/lib/utils'
import { nextPhase, phaseLabel } from '@/shared/phases'
import { profileFieldLabel } from '@/shared/profileFields'
import { Badge } from '@/shared/ui/badge'
import { Button } from '@/shared/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'
import { Label } from '@/shared/ui/label'
import { Textarea } from '@/shared/ui/textarea'

const PAIN_TREND_LABELS: Record<string, string> = {
  improving: 'Improving',
  worsening: 'Worsening',
  stable: 'Stable',
}

const PAIN_TREND_VARIANTS: Record<string, 'success' | 'destructive' | 'secondary'> = {
  improving: 'success',
  worsening: 'destructive',
  stable: 'secondary',
}

function ProfileSummaryCards({ patient }: { patient: PatientDetailType }) {
  const fields = [
    { label: 'Injury', value: injuryLabel(patient.injury) },
    { label: 'Surgery date', value: formatDate(patient.surgery_date) },
    { label: 'Recovery', value: weeksPostOpLabel(patient.surgery_date) },
    { label: 'Date of birth', value: formatDate(patient.date_of_birth) },
    { label: 'Contact email', value: patient.contact_email },
    { label: 'Record created', value: formatDate(patient.created_at) },
  ]
  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
      {fields.map((field) => (
        <Card key={field.label}>
          <CardContent className="p-4">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">{field.label}</p>
            <p className="mt-1 truncate text-sm font-medium" title={field.value}>
              {field.value}
            </p>
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

const STATUS_BADGES = {
  processing: { variant: 'warning', label: 'Processing…' },
  extracted: { variant: 'success', label: 'Extracted' },
  failed: { variant: 'destructive', label: 'Failed' },
} as const

function DocumentsPanel({ patientId }: { patientId: string }) {
  const documents = useDocuments(patientId)
  const upload = useUploadDocument(patientId)
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = useState(false)

  function handleFiles(files: FileList | null) {
    const file = files?.[0]
    if (file) upload.mutate(file)
  }

  function handleDrop(event: DragEvent) {
    event.preventDefault()
    setDragOver(false)
    handleFiles(event.dataTransfer.files)
  }

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    handleFiles(event.target.files)
    event.target.value = ''
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Documents</CardTitle>
        <CardDescription>
          Upload PDFs (MRI reports, discharge summaries, referral notes) for extraction.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          className={cn(
            'flex w-full flex-col items-center gap-2 rounded-md border-2 border-dashed p-8 text-sm text-muted-foreground transition-colors hover:border-primary/50 hover:bg-accent/40',
            dragOver && 'border-primary bg-accent/60',
          )}
        >
          {upload.isPending ? (
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
          ) : (
            <Upload className="h-6 w-6" />
          )}
          {upload.isPending ? 'Uploading…' : 'Drag a PDF here or click to browse'}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={handleChange}
        />

        {upload.isError && (
          <p className="text-sm text-destructive">
            {upload.error instanceof ApiError && typeof upload.error.detail === 'string'
              ? upload.error.detail
              : 'Upload failed. Only PDF files are accepted.'}
          </p>
        )}

        {documents.isSuccess && documents.data.length === 0 && (
          <p className="text-sm text-muted-foreground">No documents uploaded yet.</p>
        )}

        {documents.isSuccess && documents.data.length > 0 && (
          <ul className="divide-y">
            {documents.data.map((doc) => {
              const badge = STATUS_BADGES[doc.status] ?? {
                variant: 'secondary' as const,
                label: doc.status,
              }
              return (
                <li key={doc.id} className="flex items-center justify-between gap-3 py-3">
                  <div className="flex min-w-0 items-center gap-3">
                    <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{doc.filename}</p>
                      <p className="text-xs text-muted-foreground">
                        Uploaded {formatDateTime(doc.created_at)}
                        {doc.extracted_at && ` · Extracted ${formatDateTime(doc.extracted_at)}`}
                      </p>
                    </div>
                  </div>
                  <Badge variant={badge.variant} className="shrink-0">
                    {doc.status === 'processing' && (
                      <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                    )}
                    {badge.label}
                  </Badge>
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function KnowledgeProfilePanel({ patient }: { patient: PatientDetailType }) {
  const groups = [
    { label: 'Active restrictions', values: patient.active_restrictions },
    { label: 'Active concerns', values: patient.active_concerns },
    { label: 'Milestones', values: patient.milestones },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>Knowledge profile</CardTitle>
        <CardDescription>Extracted from uploaded documents.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          {patient.pain_trend && (
            <Badge variant={PAIN_TREND_VARIANTS[patient.pain_trend]}>
              Pain trend: {PAIN_TREND_LABELS[patient.pain_trend]}
            </Badge>
          )}
          {patient.exercise_adherence !== null && (
            <span className="text-muted-foreground">
              Check-in adherence (7d):{' '}
              <span className="font-medium text-foreground">{patient.exercise_adherence}%</span>
            </span>
          )}
        </div>
        {groups.map((group) => (
          <div key={group.label}>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">{group.label}</p>
            {group.values.length === 0 ? (
              <p className="mt-1 text-sm text-muted-foreground">None extracted yet.</p>
            ) : (
              <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
                {group.values.map((value) => (
                  <li key={value}>{value}</li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

function ProvenancePanel({ patient }: { patient: PatientDetailType }) {
  const documents = useDocuments(patient.id)
  const filenameById = new Map(documents.data?.map((doc) => [doc.id, doc.filename]) ?? [])

  const fields = [...patient.profile_fields].sort(
    (a, b) => new Date(b.extracted_at).getTime() - new Date(a.extracted_at).getTime(),
  )

  return (
    <Card>
      <CardHeader>
        <CardTitle>Provenance</CardTitle>
        <CardDescription>Every extracted fact, its confidence, and its source.</CardDescription>
      </CardHeader>
      <CardContent>
        {fields.length === 0 ? (
          <p className="text-sm text-muted-foreground">No extracted facts yet.</p>
        ) : (
          <ul className="divide-y">
            {fields.map((field) => (
              <li
                key={field.id}
                className={cn(
                  'space-y-1 py-3',
                  field.is_contradiction &&
                    'rounded-md border border-destructive/40 bg-destructive/5 px-3',
                  field.superseded_at && !field.is_contradiction && 'opacity-50',
                )}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">{profileFieldLabel(field.field_name)}</Badge>
                  {field.confidence !== null && (
                    <span className="text-xs text-muted-foreground">
                      conf {field.confidence.toFixed(2)}
                    </span>
                  )}
                  {field.is_contradiction && <Badge variant="destructive">Contradiction</Badge>}
                  {field.superseded_at && <Badge variant="secondary">Superseded</Badge>}
                </div>
                <p className="text-sm font-medium">{field.value}</p>
                {field.source_quote && (
                  <p className="text-xs italic text-muted-foreground">“{field.source_quote}”</p>
                )}
                <p className="text-xs text-muted-foreground">
                  {field.source_document_id && filenameById.get(field.source_document_id)
                    ? `From ${filenameById.get(field.source_document_id)} · `
                    : ''}
                  {formatDateTime(field.extracted_at)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function PhaseAdvanceControl({ patient }: { patient: PatientDetailType }) {
  const advance = useAdvancePhase(patient.id)
  const [note, setNote] = useState('')
  const [confirming, setConfirming] = useState(false)
  const target = nextPhase(patient.current_phase)

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!target) return
    if (!confirming) {
      setConfirming(true)
      return
    }
    advance.mutate(
      { target_phase: target, note: note.trim() || null },
      {
        onSuccess: () => {
          setNote('')
          setConfirming(false)
        },
        onError: () => setConfirming(false),
      },
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Phase progression</CardTitle>
        <CardDescription>Forward-only; one step at a time.</CardDescription>
      </CardHeader>
      <CardContent>
        {target === null ? (
          <p className="text-sm text-muted-foreground">
            {phaseLabel(patient.current_phase)} is the final phase — no further advancement.
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="flex items-center gap-2 text-sm">
              <Badge variant="secondary">{phaseLabel(patient.current_phase)}</Badge>
              <span className="text-muted-foreground">→</span>
              <Badge>{phaseLabel(target)}</Badge>
            </div>
            <div className="space-y-2">
              <Label htmlFor="phase-note">Note (optional)</Label>
              <Textarea
                id="phase-note"
                maxLength={2000}
                placeholder="Reason or clinical observation for this advancement"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </div>
            {advance.isError && (
              <p className="text-sm text-destructive">
                {advance.error instanceof ApiError && advance.error.status === 409
                  ? 'The phase transition was rejected — the record may have changed. Refresh and retry.'
                  : 'Phase advancement failed. Please try again.'}
              </p>
            )}
            <div className="flex items-center gap-3">
              <Button
                type="submit"
                variant={confirming ? 'destructive' : 'default'}
                disabled={advance.isPending}
              >
                {advance.isPending
                  ? 'Advancing…'
                  : confirming
                    ? `Confirm advance to ${phaseLabel(target)}`
                    : 'Advance phase'}
              </Button>
              {confirming && !advance.isPending && (
                <Button type="button" variant="ghost" onClick={() => setConfirming(false)}>
                  Cancel
                </Button>
              )}
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  )
}

function PainHistoryPanel({ patient }: { patient: PatientDetailType }) {
  const history = [...patient.pain_history].sort(
    (a, b) => new Date(b.submitted_at).getTime() - new Date(a.submitted_at).getTime(),
  )
  return (
    <Card>
      <CardHeader>
        <CardTitle>Pain history</CardTitle>
        <CardDescription>Patient-submitted check-ins, newest first.</CardDescription>
      </CardHeader>
      <CardContent>
        {history.length === 0 ? (
          <p className="text-sm text-muted-foreground">No check-ins submitted yet.</p>
        ) : (
          <ul className="divide-y">
            {history.map((checkin) => (
              <li key={checkin.id} className="flex items-start gap-4 py-3">
                <span
                  className={cn(
                    'mt-0.5 inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-semibold',
                    checkin.pain_level >= 7
                      ? 'bg-destructive/10 text-destructive'
                      : checkin.pain_level >= 4
                        ? 'bg-amber-100 text-amber-900'
                        : 'bg-emerald-100 text-emerald-900',
                  )}
                >
                  {checkin.pain_level}
                </span>
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">
                    {formatDateTime(checkin.submitted_at)}
                  </p>
                  {checkin.note && <p className="mt-1 text-sm">{checkin.note}</p>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

export function PatientDetail() {
  const { id = '' } = useParams()
  const patient = usePatient(id)

  if (patient.isPending) {
    return <p className="text-sm text-muted-foreground">Loading patient…</p>
  }
  if (patient.isError) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-destructive">
          {patient.error instanceof ApiError && patient.error.status === 404
            ? 'Patient not found.'
            : 'Failed to load the patient record.'}
        </p>
        <Link to="/dashboard" className="text-sm text-primary underline-offset-4 hover:underline">
          Back to caseload
        </Link>
      </div>
    )
  }

  const data = patient.data

  return (
    <div className="space-y-6">
      <div>
        <Link
          to="/dashboard"
          className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Caseload
        </Link>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">{data.name}</h1>
          <Badge variant="secondary">{phaseLabel(data.current_phase)}</Badge>
          {!data.invite_accepted_at && <Badge variant="warning">Invite pending</Badge>}
          <NeedsReviewBadges reasons={data.needs_review} />
        </div>
      </div>

      <ProfileSummaryCards patient={data} />

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-6">
          <DocumentsPanel patientId={data.id} />
          <KnowledgeProfilePanel patient={data} />
          <PhaseAdvanceControl patient={data} />
        </div>
        <div className="space-y-6">
          <PainHistoryPanel patient={data} />
          <ProvenancePanel patient={data} />
        </div>
      </div>
    </div>
  )
}
