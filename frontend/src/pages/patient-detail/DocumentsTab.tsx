import { FileText, Loader2, Upload } from 'lucide-react'
import { useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import { useOutletContext } from 'react-router-dom'

import { ApiError } from '@/shared/api/client'
import type { PatientDetail as PatientDetailType } from '@/shared/api/types'
import { useDocuments, useUploadDocument } from '@/shared/hooks/useDocuments'
import { cn, formatDateTime } from '@/shared/lib/utils'
import { Badge } from '@/shared/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'

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

export function DocumentsTab() {
  const patient = useOutletContext<PatientDetailType>()
  return <DocumentsPanel patientId={patient.id} />
}
