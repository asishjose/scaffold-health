import {
  Activity,
  Layers,
  Sparkles,
  LayoutDashboard,
  HeartHandshake,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useState } from 'react'

import { Card, CardContent } from '@/shared/ui/card'

const ROTATION_MS = 5000

type Feature = {
  icon: LucideIcon
  title: string
  description: string
  bgClassName: string
}

const FEATURES: Feature[] = [
  {
    icon: Activity,
    title: 'Real-time symptom flagging',
    description:
      "Patients flag concerning symptoms instantly, so you're alerted before small issues become setbacks.",
    bgClassName: 'bg-teal-500',
  },
  {
    icon: Layers,
    title: 'Phase-based recovery protocols',
    description:
      'Every patient follows a structured, phase-by-phase protocol from Pre-Op to Advanced Strength, so progress is visible, not guesswork.',
    bgClassName: 'bg-sky-500',
  },
  {
    icon: Sparkles,
    title: 'AI Therapist Copilot',
    description:
      'Get instant, evidence-informed suggestions for exercise adjustments and patient responses, like a second set of eyes on every case.',
    bgClassName: 'bg-violet-500',
  },
  {
    icon: LayoutDashboard,
    title: 'Caseload at a glance',
    description:
      "See your entire caseload's health in one dashboard: who needs review, who's stalled, who's thriving, no digging through charts.",
    bgClassName: 'bg-amber-500',
  },
  {
    icon: HeartHandshake,
    title: 'Built for patient engagement',
    description:
      'Simple invites, clear phase tracking, and direct communication keep patients engaged between visits for better adherence and outcomes.',
    bgClassName: 'bg-rose-500',
  },
  {
    icon: ShieldCheck,
    title: 'Secure & compliant by design',
    description:
      'Patient data is encrypted and access-controlled end-to-end, so you can focus on care, not compliance risk.',
    bgClassName: 'bg-emerald-500',
  },
]

export function FeatureCarousel() {
  const [index, setIndex] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => {
      setIndex((current) => (current + 1) % FEATURES.length)
    }, ROTATION_MS)
    return () => clearInterval(timer)
  }, [])

  const feature = FEATURES[index]
  const Icon = feature.icon

  return (
    <Card
      className={`flex h-[calc((100vh-5.5rem-1px)/2)] flex-col overflow-hidden transition-colors duration-1000 ${feature.bgClassName}`}
    >
      <CardContent className="flex flex-1 flex-col items-center justify-center gap-6 p-8 text-center">
        <div
          key={index}
          className="flex animate-in fade-in flex-col items-center gap-5 duration-1000"
        >
          <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded-full bg-white/15 text-white">
            <Icon className="h-9 w-9" />
          </div>
          <div className="max-w-xl">
            <p className="text-2xl font-semibold text-white sm:text-3xl">{feature.title}</p>
            <p className="mt-3 text-base text-white/85 sm:text-lg">{feature.description}</p>
          </div>
        </div>
        <div className="mt-4 flex justify-center gap-1.5">
          {FEATURES.map((f, i) => (
            <button
              key={f.title}
              type="button"
              aria-label={`Show feature: ${f.title}`}
              onClick={() => setIndex(i)}
              className={
                i === index
                  ? 'h-1.5 w-5 rounded-full bg-white transition-all'
                  : 'h-1.5 w-1.5 rounded-full bg-white/35 transition-all hover:bg-white/60'
              }
            />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
