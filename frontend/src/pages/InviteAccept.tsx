import { Activity } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ApiError } from '@/shared/api/client'
import { useAcceptInvite, useInvitePreview } from '@/shared/hooks/useAuth'
import { formatDateTime } from '@/shared/lib/utils'
import { Button } from '@/shared/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'
import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'

export function InviteAccept() {
  const { token = '' } = useParams()
  const preview = useInvitePreview(token)
  const accept = useAcceptInvite(token)
  const navigate = useNavigate()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [mismatch, setMismatch] = useState(false)

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (password !== confirm) {
      setMismatch(true)
      return
    }
    setMismatch(false)
    accept.mutate(
      { password },
      {
        onSuccess: () => {
          navigate('/login', {
            state: { notice: 'Your account is activated. Sign in with your new password.' },
          })
        },
      },
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <Activity className="mb-1 h-8 w-8 text-primary" />
          <CardTitle>Welcome to Scaffold Health</CardTitle>
          <CardDescription>
            Your therapist invited you to activate your patient account.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {preview.isPending && <p className="text-sm text-muted-foreground">Checking invite…</p>}

          {preview.isError && (
            <div className="space-y-4 text-center">
              <p className="text-sm text-destructive">
                {preview.error instanceof ApiError && typeof preview.error.detail === 'string'
                  ? preview.error.detail
                  : 'This invite link is invalid or has expired. Ask your therapist for a new one.'}
              </p>
              <Link to="/login" className="text-sm text-primary underline-offset-4 hover:underline">
                Go to sign in
              </Link>
            </div>
          )}

          {preview.isSuccess && (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" value={preview.data.email} disabled />
                <p className="text-xs text-muted-foreground">
                  Invite valid until {formatDateTime(preview.data.expires_at)}.
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Choose a password</Label>
                <Input
                  id="password"
                  type="password"
                  required
                  minLength={8}
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">At least 8 characters.</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="confirm">Confirm password</Label>
                <Input
                  id="confirm"
                  type="password"
                  required
                  autoComplete="new-password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                />
              </div>
              {mismatch && <p className="text-sm text-destructive">Passwords do not match.</p>}
              {accept.isError && (
                <p className="text-sm text-destructive">
                  {accept.error instanceof ApiError && typeof accept.error.detail === 'string'
                    ? accept.error.detail
                    : 'Activation failed. Please try again.'}
                </p>
              )}
              <Button type="submit" className="w-full" disabled={accept.isPending}>
                {accept.isPending ? 'Activating…' : 'Activate account'}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
