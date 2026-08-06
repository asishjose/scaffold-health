import { LayoutDashboard, Sparkles, Users } from 'lucide-react'

import { SidebarNavItem } from '@/shared/layout/SidebarNavItem'

export function GlobalSidebar({ patientActive }: { patientActive?: boolean }) {
  return (
    <nav className="flex flex-col gap-1 p-3">
      <SidebarNavItem to="/dashboard" icon={LayoutDashboard}>
        Dashboard
      </SidebarNavItem>
      <SidebarNavItem to="/caseload" icon={Users} forceActive={patientActive ? true : undefined}>
        Caseload
      </SidebarNavItem>
      <SidebarNavItem to="/copilot" icon={Sparkles}>
        Therapist Copilot
      </SidebarNavItem>
    </nav>
  )
}
