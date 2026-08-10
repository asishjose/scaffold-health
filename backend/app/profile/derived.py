"""Derived/recomputed Knowledge Profile fields (PRD §6.3): never directly
settable by extraction or any command, always recalculated from history.
Pure functions over plain values so they're trivially unit-testable without
touching the database or the LLM.
"""

from datetime import datetime, timedelta, timezone
from statistics import mean

from app.profile.events import (
    REASON_ADHERENCE_DROP,
    REASON_ASSISTANT_REDIRECT,
    REASON_NO_CHECKIN,
    REASON_PENDING_EXTRACTION,
)

PAIN_TREND_IMPROVING = "improving"
PAIN_TREND_WORSENING = "worsening"
PAIN_TREND_STABLE = "stable"

# A 1-point average shift on the 0-10 scale between the earlier and later
# half of a patient's check-in history counts as a meaningful trend.
MEANINGFUL_PAIN_SHIFT = 1

ADHERENCE_WINDOW_DAYS = 7
MIN_ACCOUNT_AGE_DAYS_FOR_ADHERENCE_CHECK = 7
LOW_ADHERENCE_CHECKIN_THRESHOLD = 2


def compute_pain_trend(pain_levels_by_time: list[tuple[datetime, int]]) -> str | None:
    """Splits check-ins chronologically in half and compares the average
    pain level of each half. None until there's enough history to compare.
    """
    if len(pain_levels_by_time) < 2:
        return None
    ordered = sorted(pain_levels_by_time, key=lambda item: item[0])
    midpoint = len(ordered) // 2
    earlier = ordered[:midpoint] or ordered[:1]
    later = ordered[midpoint:]
    diff = mean(level for _, level in later) - mean(level for _, level in earlier)
    if diff <= -MEANINGFUL_PAIN_SHIFT:
        return PAIN_TREND_IMPROVING
    if diff >= MEANINGFUL_PAIN_SHIFT:
        return PAIN_TREND_WORSENING
    return PAIN_TREND_STABLE


def compute_exercise_adherence(
    checkin_timestamps: list[datetime], *, now: datetime | None = None
) -> float:
    """% of the last 7 days with at least one check-in. No exercise-log
    entity exists in the MVP (motion tracking is explicitly out of scope
    per the PRD), so check-in cadence is the only adherence signal available.
    """
    now = now or datetime.now(timezone.utc)
    window_start = now - timedelta(days=ADHERENCE_WINDOW_DAYS)
    days_with_checkin = {ts.date() for ts in checkin_timestamps if ts >= window_start}
    return round(len(days_with_checkin) / ADHERENCE_WINDOW_DAYS * 100, 1)


def compute_needs_review_reasons(
    *,
    has_pending_extraction: bool,
    has_recent_assistant_redirect: bool,
    invite_accepted_at: datetime | None,
    is_discharged: bool,
    recent_checkin_count: int,
    now: datetime | None = None,
) -> list[str]:
    """Typed needs_review reasons (PRD §6.3: "never a generic flag").
    Multiple reasons can apply at once; the caller decides how many badges
    to render.
    """
    reasons = []
    if has_pending_extraction:
        reasons.append(REASON_PENDING_EXTRACTION)
    if has_recent_assistant_redirect:
        reasons.append(REASON_ASSISTANT_REDIRECT)

    now = now or datetime.now(timezone.utc)
    account_active_long_enough = (
        invite_accepted_at is not None
        and not is_discharged
        and (now - invite_accepted_at) >= timedelta(days=MIN_ACCOUNT_AGE_DAYS_FOR_ADHERENCE_CHECK)
    )
    if account_active_long_enough:
        if recent_checkin_count == 0:
            reasons.append(REASON_NO_CHECKIN)
        elif recent_checkin_count <= LOW_ADHERENCE_CHECKIN_THRESHOLD:
            reasons.append(REASON_ADHERENCE_DROP)

    return reasons
