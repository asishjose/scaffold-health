import { ChevronDown, ChevronRight, FileText } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useOutletContext } from 'react-router-dom'

import type { ProfileField, PatientDetail as PatientDetailType } from '@/shared/api/types'
import { useDocuments } from '@/shared/hooks/useDocuments'
import { cn, formatDateTime } from '@/shared/lib/utils'
import { profileFieldLabel } from '@/shared/profileFields'
import { Badge } from '@/shared/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'

const UNKNOWN_GROUP_ID = 'unknown'

interface DocumentGroup {
  documentId: string
  filename: string
  fields: ProfileField[]
  latestExtractedAt: string
}

function groupFieldsByDocument(
  fields: ProfileField[],
  filenameById: Map<string, string>,
): DocumentGroup[] {
  const groups = new Map<string, DocumentGroup>()

  for (const field of fields) {
    const documentId = field.source_document_id ?? UNKNOWN_GROUP_ID
    const filename =
      documentId === UNKNOWN_GROUP_ID
        ? 'Other sources'
        : (filenameById.get(documentId) ?? 'Unknown source')

    let group = groups.get(documentId)
    if (!group) {
      group = { documentId, filename, fields: [], latestExtractedAt: field.extracted_at }
      groups.set(documentId, group)
    }
    group.fields.push(field)
    if (new Date(field.extracted_at).getTime() > new Date(group.latestExtractedAt).getTime()) {
      group.latestExtractedAt = field.extracted_at
    }
  }

  for (const group of groups.values()) {
    group.fields.sort(
      (a, b) => new Date(b.extracted_at).getTime() - new Date(a.extracted_at).getTime(),
    )
  }

  return [...groups.values()].sort(
    (a, b) => new Date(b.latestExtractedAt).getTime() - new Date(a.latestExtractedAt).getTime(),
  )
}

function ProvenanceFactRow({ field }: { field: ProfileField }) {
  return (
    <li className={cn('space-y-1 py-3', field.superseded_at && 'opacity-50')}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{profileFieldLabel(field.field_name)}</Badge>
        {field.confidence !== null && (
          <span className="text-xs text-muted-foreground">
            conf {field.confidence.toFixed(2)}
          </span>
        )}
        {field.superseded_at && <Badge variant="secondary">Superseded</Badge>}
      </div>
      <p className="text-sm font-medium">{field.value}</p>
      {field.source_quote && (
        <p className="text-xs italic text-muted-foreground">“{field.source_quote}”</p>
      )}
      <p className="text-xs text-muted-foreground">{formatDateTime(field.extracted_at)}</p>
    </li>
  )
}

function DocumentGroupItem({
  group,
  expanded,
  onToggle,
}: {
  group: DocumentGroup
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-3 py-3 text-left hover:bg-accent/40"
      >
        <div className="flex min-w-0 items-center gap-3">
          {expanded ? (
            <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
          )}
          <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="truncate text-sm font-medium">{group.filename}</span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Badge variant="outline">
            {group.fields.length} {group.fields.length === 1 ? 'fact' : 'facts'}
          </Badge>
          <span className="text-xs text-muted-foreground">
            {formatDateTime(group.latestExtractedAt)}
          </span>
        </div>
      </button>
      {expanded && <ul className="divide-y pl-7">{group.fields.map((field) => (
        <ProvenanceFactRow key={field.id} field={field} />
      ))}</ul>}
    </li>
  )
}

function ProvenancePanel({ patient }: { patient: PatientDetailType }) {
  const documents = useDocuments(patient.id)
  const filenameById = new Map(documents.data?.map((doc) => [doc.id, doc.filename]) ?? [])

  const groups = useMemo(
    () => groupFieldsByDocument(patient.profile_fields, filenameById),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [patient.profile_fields, documents.data],
  )

  const [expanded, setExpanded] = useState<Set<string>>(
    () => new Set(groups[0] ? [groups[0].documentId] : []),
  )

  function toggle(documentId: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(documentId)) {
        next.delete(documentId)
      } else {
        next.add(documentId)
      }
      return next
    })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Provenance</CardTitle>
        <CardDescription>Extracted facts, grouped by source document.</CardDescription>
      </CardHeader>
      <CardContent>
        {groups.length === 0 ? (
          <p className="text-sm text-muted-foreground">No extracted facts yet.</p>
        ) : (
          <ul className="divide-y">
            {groups.map((group) => (
              <DocumentGroupItem
                key={group.documentId}
                group={group}
                expanded={expanded.has(group.documentId)}
                onToggle={() => toggle(group.documentId)}
              />
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
