import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.auth import commands as auth_commands
from app.briefs import commands
from app.core.config import settings
from app.core.llm_client import BriefSections
from app.patients import commands as patient_commands

FAKE_EMBEDDING = [0.1] * 768


def _make_patient(db: Session) -> tuple[uuid.UUID, uuid.UUID]:
    therapist = auth_commands.register_therapist(
        db,
        name="Dana Therapist",
        email=f"therapist-{uuid.uuid4()}@example.com",
        password="a-strong-password",
        registration_code=settings.clinic_registration_code,
    )
    patient = patient_commands.create_patient(
        db,
        therapist_id=therapist.id,
        name="Pat Patient",
        date_of_birth=date(1990, 1, 1),
        contact_email=f"patient-{uuid.uuid4()}@example.com",
        surgery_date=date.today() + timedelta(days=14),
    )
    return therapist.id, patient.id


@pytest.fixture(autouse=True)
def _stub_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(commands, "embed_text", lambda text, **kw: list(FAKE_EMBEDDING))


def _stub_llm(monkeypatch: pytest.MonkeyPatch, calls: list[dict]) -> None:
    def _fake_generate_brief_text(**kwargs):
        calls.append(kwargs)
        return BriefSections(
            since_last_visit="Nothing notable.",
            suggested_focus="Check in on pain levels.",
        )

    monkeypatch.setattr(commands, "generate_brief_text", _fake_generate_brief_text)


def test_generate_brief_returns_scoped_brief(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    therapist_id, patient_id = _make_patient(db)
    calls: list[dict] = []
    _stub_llm(monkeypatch, calls)

    brief = commands.generate_brief(db, patient_id=patient_id, therapist_id=therapist_id)

    assert brief.patient_id == patient_id
    assert brief.therapist_id == therapist_id
    assert brief.since_last_visit == "Nothing notable."
    assert brief.suggested_focus == "Check in on pain levels."
    assert brief.flags == []
    assert len(calls) == 1


def test_generate_brief_rejects_unknown_patient(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    therapist_id, _ = _make_patient(db)
    _stub_llm(monkeypatch, [])

    with pytest.raises(commands.PatientNotFound):
        commands.generate_brief(db, patient_id=uuid.uuid4(), therapist_id=therapist_id)


def test_generate_brief_rejects_non_owning_therapist(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, patient_id = _make_patient(db)
    other_therapist_id, _ = _make_patient(db)
    _stub_llm(monkeypatch, [])

    with pytest.raises(commands.PatientNotFound):
        commands.generate_brief(db, patient_id=patient_id, therapist_id=other_therapist_id)


def test_generate_brief_second_call_only_summarizes_events_since_first_brief(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    therapist_id, patient_id = _make_patient(db)
    calls: list[dict] = []
    _stub_llm(monkeypatch, calls)

    patient_commands.advance_phase(
        db, patient_id=patient_id, therapist_id=therapist_id, target_phase="phase_1_protection", note="week 1"
    )
    commands.generate_brief(db, patient_id=patient_id, therapist_id=therapist_id)
    assert "(week 1)" in calls[0]["recent_events_summary"]

    patient_commands.advance_phase(
        db,
        patient_id=patient_id,
        therapist_id=therapist_id,
        target_phase="phase_2_early_strength",
        note="week 2",
    )
    commands.generate_brief(db, patient_id=patient_id, therapist_id=therapist_id)

    assert "(week 2)" in calls[1]["recent_events_summary"]
    assert "(week 1)" not in calls[1]["recent_events_summary"]


def test_get_latest_brief_returns_none_when_no_brief_exists(db: Session) -> None:
    therapist_id, patient_id = _make_patient(db)

    result = commands.get_latest_brief(db, patient_id=patient_id, therapist_id=therapist_id)

    assert result is None


def test_get_latest_brief_returns_most_recent_row_without_calling_llm(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    therapist_id, patient_id = _make_patient(db)
    calls: list[dict] = []
    _stub_llm(monkeypatch, calls)

    first = commands.generate_brief(db, patient_id=patient_id, therapist_id=therapist_id)
    second = commands.generate_brief(db, patient_id=patient_id, therapist_id=therapist_id)
    assert len(calls) == 2

    result = commands.get_latest_brief(db, patient_id=patient_id, therapist_id=therapist_id)

    assert result is not None
    assert result.id == second.id
    assert result.id != first.id
    assert len(calls) == 2  # get_latest_brief made no additional LLM call


def test_get_latest_brief_rejects_unknown_patient(db: Session) -> None:
    therapist_id, _ = _make_patient(db)

    with pytest.raises(commands.PatientNotFound):
        commands.get_latest_brief(db, patient_id=uuid.uuid4(), therapist_id=therapist_id)


def test_get_latest_brief_rejects_non_owning_therapist(db: Session) -> None:
    _, patient_id = _make_patient(db)
    other_therapist_id, _ = _make_patient(db)

    with pytest.raises(commands.PatientNotFound):
        commands.get_latest_brief(db, patient_id=patient_id, therapist_id=other_therapist_id)


def test_generate_brief_flags_worsening_pain_trend(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.checkins import commands as checkin_commands

    therapist_id, patient_id = _make_patient(db)
    calls: list[dict] = []
    _stub_llm(monkeypatch, calls)

    for pain_level in (1, 1, 8, 9):
        checkin_commands.submit_checkin(db, patient_id=patient_id, pain_level=pain_level, note=None)

    brief = commands.generate_brief(db, patient_id=patient_id, therapist_id=therapist_id)

    assert "Pain trend: worsening" in brief.flags
