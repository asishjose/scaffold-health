import {
  ClipboardCheck,
  Clock,
  FileText,
  LayoutGrid,
  LineChart,
  ShieldCheck,
} from 'lucide-react'

import { NeedsReviewBadges } from '@/shared/components/NeedsReviewBadges'
import { useFlaggedQuestions, usePatient, usePendingFacts } from '@/shared/hooks/usePatients'
import { SidebarNavItem } from '@/shared/layout/SidebarNavItem'
import { phaseLabel } from '@/shared/phases'
import { Badge } from '@/shared/ui/badge'

export function PatientSidebar({ patientId }: { patientId: string }) {
  const patient = usePatient(patientId)
  const pendingFacts = usePendingFacts(patientId)
  const flaggedQuestions = useFlaggedQuestions(patientId)
  const pendingCount = (pendingFacts.data?.length ?? 0) + (flaggedQuestions.data?.length ?? 0)

  return (
    <div className="flex flex-col gap-3 p-3">
      {patient.isSuccess && (
        <div className="space-y-2 border-b px-3 pb-3">
          <p className="truncate text-sm font-semibold">{patient.data.name}</p>
          <div className="flex flex-wrap items-center gap-1">
            <Badge variant="secondary">{phaseLabel(patient.data.current_phase)}</Badge>
            <NeedsReviewBadges reasons={patient.data.needs_review} />
          </div>
        </div>
      )}

      <nav className="flex flex-col gap-1">
        <SidebarNavItem to={`/patients/${patientId}`} end icon={LayoutGrid}>
          Overview
        </SidebarNavItem>
        <SidebarNavItem to={`/patients/${patientId}/documents`} icon={FileText}>
          Documents
        </SidebarNavItem>
        <SidebarNavItem to={`/patients/${patientId}/pending-review`} icon={ClipboardCheck}>
          <span className="flex items-center justify-between gap-2">
            Pending review
            {pendingCount > 0 && (
              <span className="inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-amber-100 px-1.5 text-xs font-semibold text-amber-900">
                {pendingCount}
              </span>
            )}
          </span>
        </SidebarNavItem>
        <SidebarNavItem to={`/patients/${patientId}/checkins`} icon={LineChart}>
          Pain & Check-ins
        </SidebarNavItem>
        <SidebarNavItem to={`/patients/${patientId}/timeline`} icon={Clock}>
          Timeline
        </SidebarNavItem>
        <SidebarNavItem to={`/patients/${patientId}/provenance`} icon={ShieldCheck}>
          Provenance
        </SidebarNavItem>
      </nav>
    </div>
  )
}
