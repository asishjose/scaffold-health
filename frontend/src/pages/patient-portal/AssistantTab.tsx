import { Loader2, Sparkles } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useOutletContext } from 'react-router-dom'

import type { PatientPortalDetail } from '@/shared/api/types'
import { useAskAssistant } from '@/shared/hooks/useAssistant'
import { Badge } from '@/shared/ui/badge'
import { Button } from '@/shared/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'
import { Textarea } from '@/shared/ui/textarea'

export function AssistantTab() {
  const profile = useOutletContext<PatientPortalDetail>()
  const ask = useAskAssistant(profile.id)
  const [question, setQuestion] = useState('')

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!question.trim()) return
    ask.mutate({ question: question.trim() }, { onSuccess: () => setQuestion('') })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Ask a question</CardTitle>
        <CardDescription>
          General recovery questions only — for anything about your own symptoms, contact your
          clinic.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={handleSubmit} className="space-y-3">
          <Textarea
            maxLength={2000}
            placeholder="e.g. How do I use crutches?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <Button type="submit" disabled={ask.isPending || !question.trim()}>
            {ask.isPending ? (
              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="mr-1 h-4 w-4" />
            )}
            {ask.isPending ? 'Asking…' : 'Ask'}
          </Button>
        </form>

        {ask.isError && (
          <p className="text-sm text-destructive">Failed to get an answer. Please try again.</p>
        )}

        {ask.data && (
          <div className="space-y-2">
            {ask.data.redirected && <Badge variant="warning">Redirected to your clinic</Badge>}
            <p className="text-sm">{ask.data.answer}</p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
