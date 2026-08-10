import { useOutletContext } from 'react-router-dom'

import type { PatientDetail as PatientDetailType } from '@/shared/api/types'
import { useDocuments } from '@/shared/hooks/useDocuments'
import { useAcknowledgeContradiction } from '@/shared/hooks/usePatients'
import { cn, formatDateTime } from '@/shared/lib/utils'
import { profileFieldLabel } from '@/shared/profileFields'
import { Badge } from '@/shared/ui/badge'
import { Button } from '@/shared/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'

function ProvenancePanel({ patient }: { patient: PatientDetailType }) {
  const documents = useDocuments(patient.id)
  const filenameById = new Map(documents.data?.map((doc) => [doc.id, doc.filename]) ?? [])
  const acknowledge = useAcknowledgeContradiction(patient.id)

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
                    !field.acknowledged_at &&
                    'rounded-md border border-destructive/40 bg-destructive/5 px-3',
                  ((field.superseded_at && !field.is_contradiction) || field.acknowledged_at) &&
                    'opacity-50',
                )}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">{profileFieldLabel(field.field_name)}</Badge>
                  {field.confidence !== null && (
                    <span className="text-xs text-muted-foreground">
                      conf {field.confidence.toFixed(2)}
                    </span>
                  )}
                  {field.is_contradiction && (
                    <Badge variant={field.acknowledged_at ? 'secondary' : 'destructive'}>
                      Contradiction
                    </Badge>
                  )}
                  {field.is_contradiction && field.acknowledged_at && (
                    <span className="text-xs text-muted-foreground">
                      Acknowledged {formatDateTime(field.acknowledged_at)}
                    </span>
                  )}
                  {field.is_contradiction && !field.acknowledged_at && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 px-2 text-xs"
                      disabled={acknowledge.isPending}
                      onClick={() => acknowledge.mutate(field.id)}
                    >
                      {acknowledge.isPending && acknowledge.variables === field.id
                        ? 'Acknowledging…'
                        : 'Acknowledge'}
                    </Button>
                  )}
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

export function ProvenanceTab() {
  const patient = useOutletContext<PatientDetailType>()
  return <ProvenancePanel patient={patient} />
}
