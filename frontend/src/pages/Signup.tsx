import { Activity } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError } from '@/shared/api/client'
import { useSignup } from '@/shared/hooks/useAuth'
import { Button } from '@/shared/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'
import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'

function signupErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (typeof error.detail === 'string') return error.detail
    if (error.status === 422) return 'Please check the form fields and try again.'
  }
  return 'Signup failed. Please try again.'
}

export function Signup() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [registrationCode, setRegistrationCode] = useState('')
  const signup = useSignup()
  const navigate = useNavigate()

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    signup.mutate(
      { name, email, password, registration_code: registrationCode },
      {
        onSuccess: () => {
          navigate('/login', { state: { notice: 'Account created. Sign in to continue.' } })
        },
      },
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <Activity className="mb-1 h-8 w-8 text-primary" />
          <CardTitle>Therapist signup</CardTitle>
          <CardDescription>Requires your clinic registration code</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Full name</Label>
              <Input
                id="name"
                required
                autoComplete="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
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
              <Label htmlFor="registration-code">Clinic registration code</Label>
              <Input
                id="registration-code"
                required
                value={registrationCode}
                onChange={(e) => setRegistrationCode(e.target.value)}
              />
            </div>
            {signup.isError && (
              <p className="text-sm text-destructive">{signupErrorMessage(signup.error)}</p>
            )}
            <Button type="submit" className="w-full" disabled={signup.isPending}>
              {signup.isPending ? 'Creating account…' : 'Create account'}
            </Button>
          </form>
          <p className="mt-4 text-center text-sm text-muted-foreground">
            Already have an account?{' '}
            <Link to="/login" className="text-primary underline-offset-4 hover:underline">
              Sign in
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
