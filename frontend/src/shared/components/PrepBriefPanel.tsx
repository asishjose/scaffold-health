import { Loader2, Sparkles } from 'lucide-react'

import { NeedsReviewBadges } from '@/shared/components/NeedsReviewBadges'
import { useGenerateBrief } from '@/shared/hooks/useBrief'
import { formatDateTime } from '@/shared/lib/utils'
import { Button } from '@/shared/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'

export function PrepBriefPanel({ patientId }: { patientId: string }) {
  const generateBrief = useGenerateBrief(patientId)
  const brief = generateBrief.data

  return (
    <Card>
      <CardHeader>
        <CardTitle>Prep brief</CardTitle>
        <CardDescription>
          Assembled from the Knowledge Profile, recent activity, and the patient's notes.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Button
          type="button"
          onClick={() => generateBrief.mutate()}
          disabled={generateBrief.isPending}
        >
          {generateBrief.isPending ? (
            <Loader2 className="mr-1 h-4 w-4 animate-spin" />
          ) : (
            <Sparkles className="mr-1 h-4 w-4" />
          )}
          {generateBrief.isPending
            ? 'Generating…'
            : brief
              ? 'Regenerate brief'
              : 'Generate brief'}
        </Button>

        {generateBrief.isError && (
          <p className="text-sm text-destructive">
            Failed to generate the brief. Please try again.
          </p>
        )}

        {brief && (
          <div className="space-y-4">
            <p className="text-xs text-muted-foreground">
              Generated {formatDateTime(brief.generated_at)}
            </p>
            <div>
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                Since last visit
              </p>
              <p className="mt-1 text-sm">{brief.since_last_visit}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Flags</p>
              {brief.flags.length === 0 ? (
                <p className="mt-1 text-sm text-muted-foreground">None.</p>
              ) : (
                <div className="mt-1 flex flex-wrap gap-2">
                  <NeedsReviewBadges reasons={brief.flags} />
                </div>
              )}
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                Suggested focus
              </p>
              <p className="mt-1 text-sm">{brief.suggested_focus}</p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
