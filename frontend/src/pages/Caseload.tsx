import { UserPlus } from 'lucide-react'
import { Link } from 'react-router-dom'

import { NeedsReviewBadges } from '@/shared/components/NeedsReviewBadges'
import { usePatients } from '@/shared/hooks/usePatients'
import { weeksPostOpLabel } from '@/shared/lib/utils'
import { phaseLabel } from '@/shared/phases'
import { Badge } from '@/shared/ui/badge'
import { buttonVariants } from '@/shared/ui/button'
import { Card, CardContent } from '@/shared/ui/card'

export function Caseload() {
  const patients = usePatients()

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Caseload</h1>
          <p className="text-sm text-muted-foreground">
            {patients.data ? `${patients.data.length} patient${patients.data.length === 1 ? '' : 's'}` : ' '}
          </p>
        </div>
        <Link to="/patients/new" className={buttonVariants()}>
          <UserPlus className="h-4 w-4" />
          Add patient
        </Link>
      </div>

      {patients.isPending && <p className="text-sm text-muted-foreground">Loading caseload…</p>}
      {patients.isError && (
        <p className="text-sm text-destructive">Failed to load caseload. Try refreshing.</p>
      )}

      {patients.isSuccess && patients.data.length === 0 && (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            No patients yet. Add your first patient to generate an invite link.
          </CardContent>
        </Card>
      )}

      {patients.isSuccess && patients.data.length > 0 && (
        <Card>
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="px-6 py-3 font-medium">Name</th>
                  <th className="px-6 py-3 font-medium">Phase</th>
                  <th className="px-6 py-3 font-medium">Recovery</th>
                  <th className="px-6 py-3 font-medium">Account</th>
                  <th className="px-6 py-3 font-medium">Needs review</th>
                </tr>
              </thead>
              <tbody>
                {patients.data.map((patient) => (
                  <tr key={patient.id} className="border-b last:border-0 hover:bg-muted/50">
                    <td className="px-6 py-3">
                      <Link
                        to={`/patients/${patient.id}`}
                        className="font-medium text-primary underline-offset-4 hover:underline"
                      >
                        {patient.name}
                      </Link>
                    </td>
                    <td className="px-6 py-3">
                      <Badge variant="secondary">{phaseLabel(patient.current_phase)}</Badge>
                    </td>
                    <td className="px-6 py-3 text-muted-foreground">
                      {weeksPostOpLabel(patient.surgery_date)}
                    </td>
                    <td className="px-6 py-3">
                      {patient.invite_accepted_at ? (
                        <Badge variant="success">Active</Badge>
                      ) : (
                        <Badge variant="warning">Invite pending</Badge>
                      )}
                    </td>
                    <td className="px-6 py-3">
                      <div className="flex flex-wrap gap-1">
                        <NeedsReviewBadges reasons={patient.needs_review} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
