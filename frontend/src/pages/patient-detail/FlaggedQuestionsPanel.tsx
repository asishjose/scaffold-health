import type { FlaggedQuestion } from '@/shared/api/types'
import { useAcknowledgeFlaggedQuestion, useFlaggedQuestions } from '@/shared/hooks/usePatients'
import { formatDateTime } from '@/shared/lib/utils'
import { Button } from '@/shared/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'

function FlaggedQuestionRow({
  patientId,
  question,
}: {
  patientId: string
  question: FlaggedQuestion
}) {
  const acknowledge = useAcknowledgeFlaggedQuestion(patientId)

  return (
    <li className="space-y-2 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-3">
      <p className="text-sm font-medium">{question.question}</p>
      <p className="text-sm text-muted-foreground">{question.answer}</p>
      <p className="text-xs text-muted-foreground">Asked {formatDateTime(question.asked_at)}</p>

      <div className="flex flex-wrap gap-2 pt-1">
        <Button
          size="sm"
          className="h-7 px-2 text-xs"
          disabled={acknowledge.isPending}
          onClick={() => acknowledge.mutate(question.id)}
        >
          {acknowledge.isPending ? 'Acknowledging…' : 'Acknowledge'}
        </Button>
      </div>
    </li>
  )
}

export function FlaggedQuestionsPanel({ patientId }: { patientId: string }) {
  const flaggedQuestions = useFlaggedQuestions(patientId)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Flagged questions</CardTitle>
        <CardDescription>
          Symptom-related or urgent questions the assistant redirected to your clinic instead of
          answering. Acknowledge once you've reviewed them.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {flaggedQuestions.isSuccess && flaggedQuestions.data.length === 0 && (
          <p className="text-sm text-muted-foreground">No flagged questions awaiting review.</p>
        )}
        {flaggedQuestions.isSuccess && flaggedQuestions.data.length > 0 && (
          <ul className="space-y-3">
            {flaggedQuestions.data.map((question) => (
              <FlaggedQuestionRow key={question.id} patientId={patientId} question={question} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
