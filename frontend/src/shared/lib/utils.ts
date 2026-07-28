import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export function formatDateTime(value: string): string {
  return new Date(value).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

const INJURY_LABELS: Record<string, string> = {
  acl_reconstruction: 'ACL Reconstruction',
}

export function injuryLabel(injury: string): string {
  return INJURY_LABELS[injury] ?? injury
}

/** Whole weeks since surgery; negative when surgery is in the future. */
export function weeksPostOp(surgeryDate: string): number {
  const ms = Date.now() - new Date(surgeryDate + 'T00:00:00').getTime()
  return Math.floor(ms / (7 * 24 * 60 * 60 * 1000))
}

export function weeksPostOpLabel(surgeryDate: string): string {
  const weeks = weeksPostOp(surgeryDate)
  if (weeks < 0) return 'Pre-op'
  return `${weeks} wk post-op`
}
