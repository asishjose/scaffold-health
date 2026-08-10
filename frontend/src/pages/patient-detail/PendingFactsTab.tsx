import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'

import type { PatientDetail as PatientDetailType, PendingProfileFact } from '@/shared/api/types'
import { useDocuments } from '@/shared/hooks/useDocuments'
import { useApprovePendingFact, usePendingFacts, useRejectPendingFact } from '@/shared/hooks/usePatients'
import { formatDateTime } from '@/shared/lib/utils'
import { profileFieldLabel } from '@/shared/profileFields'
import { Badge } from '@/shared/ui/badge'
import { Button } from '@/shared/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'
import { Textarea } from '@/shared/ui/textarea'

// Fields whose merge is atomic per document (mirrors backend
// FIELD_MERGE_STRATEGIES' overwrite strategy) — approving one still waits
// for every fact in the same document's batch to be decided before any of
// them reach the Knowledge Profile.
const ATOMIC_BATCH_FIELDS = new Set(['active_restrictions', 'active_concerns'])

function PendingFactRow({
  patientId,
  fact,
  filename,
}: {
  patientId: string
  fact: PendingProfileFact
  filename: string | undefined
}) {
  const approve = useApprovePendingFact(patientId)
  const reject = useRejectPendingFact(patientId)
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(fact.value)
  const busy = approve.isPending || reject.isPending

  return (
    <li className="space-y-2 rounded-md border border-amber-300/60 bg-amber-50/40 px-3 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{profileFieldLabel(fact.field_name)}</Badge>
        <span className="text-xs text-muted-foreground">conf {fact.confidence.toFixed(2)}</span>
        {fact.is_contradiction && <Badge variant="destructive">Contradiction</Badge>}
        {fact.is_low_confidence && <Badge variant="warning">Low confidence</Badge>}
        {ATOMIC_BATCH_FIELDS.has(fact.field_name) && (
          <span className="text-xs text-muted-foreground">
            Applies once every fact from this document for this field is reviewed
          </span>
        )}
      </div>

      {editing ? (
        <Textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          rows={2}
          className="text-sm"
        />
      ) : (
        <p className="text-sm font-medium">{fact.value}</p>
      )}

      {fact.source_quote && (
        <p className="text-xs italic text-muted-foreground">“{fact.source_quote}”</p>
      )}
      <p className="text-xs text-muted-foreground">
        {filename ? `From ${filename} · ` : ''}
        {formatDateTime(fact.extracted_at)}
      </p>

      <div className="flex flex-wrap gap-2 pt-1">
        {editing ? (
          <>
            <Button
              size="sm"
              className="h-7 px-2 text-xs"
              disabled={busy}
              onClick={() => approve.mutate({ factId: fact.id, value })}
            >
              {approve.isPending ? 'Approving…' : 'Approve edit'}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 px-2 text-xs"
              disabled={busy}
              onClick={() => {
                setValue(fact.value)
                setEditing(false)
              }}
            >
              Cancel
            </Button>
          </>
        ) : (
          <>
            <Button
              size="sm"
              className="h-7 px-2 text-xs"
              disabled={busy}
              onClick={() => approve.mutate({ factId: fact.id })}
            >
              {approve.isPending ? 'Approving…' : 'Approve'}
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 px-2 text-xs"
              disabled={busy}
              onClick={() => setEditing(true)}
            >
              Edit
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="h-7 px-2 text-xs text-destructive"
              disabled={busy}
              onClick={() => reject.mutate(fact.id)}
            >
              {reject.isPending ? 'Rejecting…' : 'Reject'}
            </Button>
          </>
        )}
      </div>
    </li>
  )
}

function PendingFactsPanel({ patientId }: { patientId: string }) {
  const pendingFacts = usePendingFacts(patientId)
  const documents = useDocuments(patientId)
  const filenameById = new Map(documents.data?.map((doc) => [doc.id, doc.filename]) ?? [])

  return (
    <Card>
      <CardHeader>
        <CardTitle>Pending review</CardTitle>
        <CardDescription>
          Facts extraction couldn't confidently apply — a contradiction with an existing value,
          or low model confidence. Nothing here reaches the Knowledge Profile until you approve
          or reject it.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {pendingFacts.isSuccess && pendingFacts.data.length === 0 && (
          <p className="text-sm text-muted-foreground">No facts awaiting review.</p>
        )}
        {pendingFacts.isSuccess && pendingFacts.data.length > 0 && (
          <ul className="space-y-3">
            {pendingFacts.data.map((fact) => (
              <PendingFactRow
                key={fact.id}
                patientId={patientId}
                fact={fact}
                filename={filenameById.get(fact.source_document_id)}
              />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

export function PendingFactsTab() {
  const patient = useOutletContext<PatientDetailType>()
  return <PendingFactsPanel patientId={patient.id} />
}
