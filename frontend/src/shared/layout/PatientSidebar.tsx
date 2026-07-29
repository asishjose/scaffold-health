import {
  ArrowLeft,
  Clock,
  FileText,
  LayoutGrid,
  LineChart,
  ShieldCheck,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import { NeedsReviewBadges } from '@/shared/components/NeedsReviewBadges'
import { usePatient } from '@/shared/hooks/usePatients'
import { SidebarNavItem } from '@/shared/layout/SidebarNavItem'
import { phaseLabel } from '@/shared/phases'
import { Badge } from '@/shared/ui/badge'

export function PatientSidebar({ patientId }: { patientId: string }) {
  const patient = usePatient(patientId)

  return (
    <div className="flex flex-col gap-3 p-3">
      <Link
        to="/caseload"
        className="flex items-center gap-1 px-3 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to caseload
      </Link>

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
