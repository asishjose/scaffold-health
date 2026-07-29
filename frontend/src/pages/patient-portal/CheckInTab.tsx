import { CheckCircle2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useOutletContext } from 'react-router-dom'

import type { PatientPortalDetail } from '@/shared/api/types'
import { useSubmitCheckIn } from '@/shared/hooks/useCheckIn'
import { Button } from '@/shared/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'
import { Label } from '@/shared/ui/label'
import { Textarea } from '@/shared/ui/textarea'

export function CheckInTab() {
  const profile = useOutletContext<PatientPortalDetail>()
  const checkIn = useSubmitCheckIn(profile.id)
  const [painLevel, setPainLevel] = useState(3)
  const [note, setNote] = useState('')

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    checkIn.mutate(
      { pain_level: painLevel, note: note.trim() || null },
      {
        onSuccess: () => setNote(''),
      },
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Daily check-in</CardTitle>
        <CardDescription>How is your pain right now?</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label htmlFor="pain">Pain level</Label>
              <span className="text-2xl font-semibold tabular-nums text-primary">{painLevel}</span>
            </div>
            <input
              id="pain"
              type="range"
              min={0}
              max={10}
              step={1}
              value={painLevel}
              onChange={(e) => setPainLevel(Number(e.target.value))}
              className="w-full accent-[hsl(var(--primary))]"
            />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>0 — No pain</span>
              <span>10 — Worst pain</span>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="note">Note (optional)</Label>
            <Textarea
              id="note"
              maxLength={2000}
              placeholder="Anything your therapist should know?"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
          {checkIn.isError && (
            <p className="text-sm text-destructive">Check-in failed. Please try again.</p>
          )}
          {checkIn.isSuccess && (
            <p className="flex items-center gap-2 text-sm text-primary">
              <CheckCircle2 className="h-4 w-4" />
              Check-in recorded. Thank you!
            </p>
          )}
          <Button type="submit" disabled={checkIn.isPending}>
            {checkIn.isPending ? 'Submitting…' : 'Submit check-in'}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
