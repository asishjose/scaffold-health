import { AlertTriangle, Mail, Users, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'

import { NeedsReviewBadges } from '@/shared/components/NeedsReviewBadges'
import { usePatients } from '@/shared/hooks/usePatients'
import {
  getNeedsReviewPatients,
  getPendingInvites,
  getPhaseDistribution,
} from '@/shared/lib/dashboardMetrics'
import { phaseLabel } from '@/shared/phases'
import { Badge } from '@/shared/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/shared/ui/card'

const NEEDS_REVIEW_PREVIEW_LIMIT = 8

function StatCard({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: LucideIcon
  label: string
  value: number
  tone?: 'default' | 'warning'
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-5">
        <div
          className={
            tone === 'warning'
              ? 'flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-900'
              : 'flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent text-primary'
          }
        >
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <p className="text-2xl font-semibold leading-none">{value}</p>
          <p className="mt-1 text-xs text-muted-foreground">{label}</p>
        </div>
      </CardContent>
    </Card>
  )
}

export function Dashboard() {
  const patients = usePatients()

  if (patients.isPending) {
    return <p className="text-sm text-muted-foreground">Loading dashboard…</p>
  }
  if (patients.isError) {
    return <p className="text-sm text-destructive">Failed to load caseload. Try refreshing.</p>
  }

  if (patients.data.length === 0) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-semibold">Dashboard</h1>
          <p className="text-sm text-muted-foreground">Caseload health at a glance.</p>
        </div>
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            No patients yet.{' '}
            <Link to="/patients/new" className="text-primary underline-offset-4 hover:underline">
              Add your first patient
            </Link>{' '}
            to get started.
          </CardContent>
        </Card>
      </div>
    )
  }

  const data = patients.data
  const needsReview = getNeedsReviewPatients(data)
  const pendingInvites = getPendingInvites(data)
  const phaseDistribution = getPhaseDistribution(data)
  const maxPhaseCount = Math.max(1, ...phaseDistribution.map((p) => p.count))

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="text-sm text-muted-foreground">Caseload health at a glance.</p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard icon={Users} label="Total patients" value={data.length} />
        <StatCard
          icon={AlertTriangle}
          label="Needs review"
          value={needsReview.length}
          tone={needsReview.length > 0 ? 'warning' : 'default'}
        />
        <StatCard icon={Mail} label="Pending invites" value={pendingInvites.length} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Needs review</CardTitle>
            <CardDescription>Patients with an open flag requiring attention.</CardDescription>
          </CardHeader>
          <CardContent>
            {needsReview.length === 0 ? (
              <p className="text-sm text-muted-foreground">No patients need review right now.</p>
            ) : (
              <>
                <ul className="divide-y">
                  {needsReview.slice(0, NEEDS_REVIEW_PREVIEW_LIMIT).map((patient) => (
                    <li key={patient.id} className="flex items-center justify-between gap-3 py-3">
                      <div className="min-w-0">
                        <Link
                          to={`/patients/${patient.id}`}
                          className="truncate font-medium text-primary underline-offset-4 hover:underline"
                        >
                          {patient.name}
                        </Link>
                        <div className="mt-1">
                          <Badge variant="secondary">{phaseLabel(patient.current_phase)}</Badge>
                        </div>
                      </div>
                      <div className="flex shrink-0 flex-wrap justify-end gap-1">
                        <NeedsReviewBadges reasons={patient.needs_review} />
                      </div>
                    </li>
                  ))}
                </ul>
                {needsReview.length > NEEDS_REVIEW_PREVIEW_LIMIT && (
                  <Link
                    to="/caseload"
                    className="mt-3 inline-block text-sm text-primary underline-offset-4 hover:underline"
                  >
                    View all in Caseload →
                  </Link>
                )}
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Pending invites</CardTitle>
            <CardDescription>Patients who haven't activated their account yet.</CardDescription>
          </CardHeader>
          <CardContent>
            {pendingInvites.length === 0 ? (
              <p className="text-sm text-muted-foreground">No pending invites.</p>
            ) : (
              <ul className="divide-y">
                {pendingInvites.map((patient) => (
                  <li key={patient.id} className="flex items-center justify-between gap-3 py-3">
                    <Link
                      to={`/patients/${patient.id}`}
                      className="truncate font-medium text-primary underline-offset-4 hover:underline"
                    >
                      {patient.name}
                    </Link>
                    <Badge variant="warning">Invite pending</Badge>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Caseload by phase</CardTitle>
          <CardDescription>Where your patients currently sit in the protocol.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {phaseDistribution.map(({ phase, count }) => (
            <div key={phase} className="flex items-center gap-3">
              <span className="w-48 shrink-0 truncate text-sm text-muted-foreground">
                {phaseLabel(phase)}
              </span>
              <div className="h-2 flex-1 rounded-full bg-primary/15">
                <div
                  className="h-2 rounded-full bg-primary"
                  style={{ width: `${(count / maxPhaseCount) * 100}%` }}
                />
              </div>
              <span className="w-6 shrink-0 text-right text-sm font-medium">{count}</span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
