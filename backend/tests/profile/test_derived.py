from datetime import datetime, timedelta, timezone

from app.profile.derived import (
    PAIN_TREND_IMPROVING,
    PAIN_TREND_STABLE,
    PAIN_TREND_WORSENING,
    compute_exercise_adherence,
    compute_needs_review_reasons,
    compute_pain_trend,
)
from app.profile.events import REASON_ADHERENCE_DROP, REASON_CONTRADICTION, REASON_NO_CHECKIN

NOW = datetime(2026, 7, 16, tzinfo=timezone.utc)


def _at(days_ago: int) -> datetime:
    return NOW - timedelta(days=days_ago)


def test_pain_trend_none_with_fewer_than_two_checkins() -> None:
    assert compute_pain_trend([]) is None
    assert compute_pain_trend([(_at(1), 5)]) is None


def test_pain_trend_improving_when_later_average_is_lower() -> None:
    levels = [(_at(10), 8), (_at(9), 7), (_at(2), 3), (_at(1), 2)]
    assert compute_pain_trend(levels) == PAIN_TREND_IMPROVING


def test_pain_trend_worsening_when_later_average_is_higher() -> None:
    levels = [(_at(10), 2), (_at(9), 3), (_at(2), 7), (_at(1), 8)]
    assert compute_pain_trend(levels) == PAIN_TREND_WORSENING


def test_pain_trend_stable_within_threshold() -> None:
    levels = [(_at(4), 4), (_at(3), 5), (_at(2), 4), (_at(1), 5)]
    assert compute_pain_trend(levels) == PAIN_TREND_STABLE


def test_pain_trend_ignores_submission_order_in_input() -> None:
    # Same data, shuffled — the function must sort chronologically itself.
    levels = [(_at(1), 2), (_at(10), 8), (_at(2), 3), (_at(9), 7)]
    assert compute_pain_trend(levels) == PAIN_TREND_IMPROVING


def test_exercise_adherence_zero_with_no_checkins() -> None:
    assert compute_exercise_adherence([], now=NOW) == 0.0


def test_exercise_adherence_counts_distinct_days_in_last_7() -> None:
    timestamps = [_at(0), _at(1), _at(1), _at(8)]  # day-8 checkin is outside the window
    assert compute_exercise_adherence(timestamps, now=NOW) == round(2 / 7 * 100, 1)


def test_exercise_adherence_full_week() -> None:
    timestamps = [_at(d) for d in range(7)]
    assert compute_exercise_adherence(timestamps, now=NOW) == 100.0


def test_needs_review_empty_when_nothing_flagged() -> None:
    reasons = compute_needs_review_reasons(
        has_contradiction=False,
        invite_accepted_at=_at(30),
        is_discharged=False,
        recent_checkin_count=5,
        now=NOW,
    )
    assert reasons == []


def test_needs_review_contradiction_always_reported() -> None:
    reasons = compute_needs_review_reasons(
        has_contradiction=True,
        invite_accepted_at=None,
        is_discharged=False,
        recent_checkin_count=0,
        now=NOW,
    )
    assert reasons == [REASON_CONTRADICTION]


def test_needs_review_no_checkin_reported_after_grace_period() -> None:
    reasons = compute_needs_review_reasons(
        has_contradiction=False,
        invite_accepted_at=_at(30),
        is_discharged=False,
        recent_checkin_count=0,
        now=NOW,
    )
    assert reasons == [REASON_NO_CHECKIN]


def test_needs_review_adherence_drop_below_threshold() -> None:
    reasons = compute_needs_review_reasons(
        has_contradiction=False,
        invite_accepted_at=_at(30),
        is_discharged=False,
        recent_checkin_count=1,
        now=NOW,
    )
    assert reasons == [REASON_ADHERENCE_DROP]


def test_needs_review_suppressed_before_grace_period_elapses() -> None:
    reasons = compute_needs_review_reasons(
        has_contradiction=False,
        invite_accepted_at=_at(2),
        is_discharged=False,
        recent_checkin_count=0,
        now=NOW,
    )
    assert reasons == []


def test_needs_review_suppressed_once_discharged() -> None:
    reasons = compute_needs_review_reasons(
        has_contradiction=False,
        invite_accepted_at=_at(30),
        is_discharged=True,
        recent_checkin_count=0,
        now=NOW,
    )
    assert reasons == []


def test_needs_review_combines_multiple_reasons() -> None:
    reasons = compute_needs_review_reasons(
        has_contradiction=True,
        invite_accepted_at=_at(30),
        is_discharged=False,
        recent_checkin_count=0,
        now=NOW,
    )
    assert reasons == [REASON_CONTRADICTION, REASON_NO_CHECKIN]
