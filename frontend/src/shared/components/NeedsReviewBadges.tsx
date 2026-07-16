import { needsReviewVariant } from '@/shared/profileFields'
import { Badge } from '@/shared/ui/badge'

export function NeedsReviewBadges({ reasons }: { reasons: string[] }) {
  return (
    <>
      {reasons.map((reason) => (
        <Badge key={reason} variant={needsReviewVariant(reason)}>
          {reason}
        </Badge>
      ))}
    </>
  )
}
