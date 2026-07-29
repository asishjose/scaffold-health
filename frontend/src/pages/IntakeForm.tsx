import { Check, Copy } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import { ApiError } from '@/shared/api/client'
import type { PatientIntakeResponse } from '@/shared/api/types'
import { useCreatePatient } from '@/shared/hooks/usePatients'
import { formatDateTime } from '@/shared/lib/utils'
import { Button, buttonVariants } from '@/shared/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'
import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'

function InviteLinkPanel({ result }: { result: PatientIntakeResponse }) {
  const [copied, setCopied] = useState(false)
  const inviteUrl = `${window.location.origin}/invite/${result.invite_token}`

  async function copy() {
    await navigator.clipboard.writeText(inviteUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{result.name} added</CardTitle>
        <CardDescription>
          Share this single-use invite link with the patient. It expires{' '}
          {formatDateTime(result.invite_expires_at)}.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex gap-2">
          <Input readOnly value={inviteUrl} className="font-mono text-xs" />
          <Button type="button" variant="outline" onClick={copy}>
            {copied ? <Check className="h-4 w-4 text-primary" /> : <Copy className="h-4 w-4" />}
            {copied ? 'Copied' : 'Copy'}
          </Button>
        </div>
        <div className="flex gap-3">
          <Link to={`/patients/${result.id}`} className={buttonVariants({ variant: 'secondary' })}>
            Open patient record
          </Link>
          <Link to="/caseload" className={buttonVariants({ variant: 'ghost' })}>
            Back to caseload
          </Link>
        </div>
      </CardContent>
    </Card>
  )
}

export function IntakeForm() {
  const [name, setName] = useState('')
  const [dateOfBirth, setDateOfBirth] = useState('')
  const [contactEmail, setContactEmail] = useState('')
  const [surgeryDate, setSurgeryDate] = useState('')
  const createPatient = useCreatePatient()

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    createPatient.mutate({
      name,
      date_of_birth: dateOfBirth,
      contact_email: contactEmail,
      surgery_date: surgeryDate,
    })
  }

  if (createPatient.isSuccess) {
    return <InviteLinkPanel result={createPatient.data} />
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">New patient intake</h1>
        <p className="text-sm text-muted-foreground">
          Creates the patient record and generates an invite link in one step.
        </p>
      </div>
      <Card>
        <CardContent className="pt-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Full name</Label>
              <Input id="name" required value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="dob">Date of birth</Label>
              <Input
                id="dob"
                type="date"
                required
                value={dateOfBirth}
                onChange={(e) => setDateOfBirth(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="contact-email">Contact email</Label>
              <Input
                id="contact-email"
                type="email"
                required
                value={contactEmail}
                onChange={(e) => setContactEmail(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                The invite link is bound to this email.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="injury">Injury type</Label>
              <Input id="injury" value="ACL reconstruction" disabled />
              <p className="text-xs text-muted-foreground">Fixed to ACL for the MVP.</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="surgery-date">Surgery date</Label>
              <Input
                id="surgery-date"
                type="date"
                required
                value={surgeryDate}
                onChange={(e) => setSurgeryDate(e.target.value)}
              />
            </div>
            {createPatient.isError && (
              <p className="text-sm text-destructive">
                {createPatient.error instanceof ApiError &&
                typeof createPatient.error.detail === 'string'
                  ? createPatient.error.detail
                  : 'Could not create the patient. Check the fields and try again.'}
              </p>
            )}
            <div className="flex gap-3">
              <Button type="submit" disabled={createPatient.isPending}>
                {createPatient.isPending ? 'Creating…' : 'Create patient & invite'}
              </Button>
              <Link to="/caseload" className={buttonVariants({ variant: 'ghost' })}>
                Cancel
              </Link>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
