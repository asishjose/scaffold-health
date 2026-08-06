import { Loader2, Send } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'

import { useCopilotMessages, useSendCopilotMessage } from '@/shared/hooks/useCopilotChat'
import { cn, formatDateTime } from '@/shared/lib/utils'
import { Button } from '@/shared/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'
import { Textarea } from '@/shared/ui/textarea'

export function CopilotChatPanel({ patientId }: { patientId: string }) {
  const messages = useCopilotMessages(patientId)
  const send = useSendCopilotMessage(patientId)
  const [content, setContent] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages.data?.length])

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const trimmed = content.trim()
    if (!trimmed) return
    setContent('')
    send.mutate({ content: trimmed })
  }

  return (
    <Card className="flex h-[70vh] flex-col">
      <CardHeader>
        <CardTitle>Copilot chat</CardTitle>
        <CardDescription>
          Grounded in this patient's chart and clinical guidelines. Advisory only.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4 overflow-hidden">
        <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto pr-1">
          {messages.isPending && (
            <p className="text-sm text-muted-foreground">Loading conversation…</p>
          )}
          {messages.isError && (
            <p className="text-sm text-destructive">Failed to load the conversation.</p>
          )}
          {messages.isSuccess && messages.data.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No messages yet. Ask about this patient's chart, recent activity, or clinical
              guidance.
            </p>
          )}
          {messages.data?.map((message) => (
            <div
              key={message.id}
              className={cn('flex flex-col gap-1', message.role === 'therapist' && 'items-end')}
            >
              <div
                className={cn(
                  'max-w-[80%] rounded-lg px-3 py-2 text-sm',
                  message.role === 'therapist'
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-accent text-accent-foreground',
                )}
              >
                {message.content}
              </div>
              <span className="text-xs text-muted-foreground">
                {formatDateTime(message.posted_at)}
              </span>
            </div>
          ))}
        </div>

        {send.isError && (
          <p className="text-sm text-destructive">Failed to send. Please retry.</p>
        )}

        <form onSubmit={handleSubmit} className="flex items-end gap-2">
          <Textarea
            maxLength={2000}
            placeholder="Ask about this patient…"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSubmit(e)
              }
            }}
            className="min-h-[44px] flex-1 resize-none"
          />
          <Button type="submit" disabled={send.isPending || !content.trim()}>
            {send.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
