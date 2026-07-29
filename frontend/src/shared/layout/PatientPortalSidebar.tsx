import { Clock, LayoutGrid, LineChart, MessageCircle } from 'lucide-react'

import { SidebarNavItem } from '@/shared/layout/SidebarNavItem'

export function PatientPortalSidebar() {
  return (
    <nav className="flex flex-col gap-1 p-3">
      <SidebarNavItem to="/patient" end icon={LayoutGrid}>
        Overview
      </SidebarNavItem>
      <SidebarNavItem to="/patient/checkin" icon={LineChart}>
        Check-in
      </SidebarNavItem>
      <SidebarNavItem to="/patient/timeline" icon={Clock}>
        Timeline
      </SidebarNavItem>
      <SidebarNavItem to="/patient/assistant" icon={MessageCircle}>
        Ask Assistant
      </SidebarNavItem>
    </nav>
  )
}
