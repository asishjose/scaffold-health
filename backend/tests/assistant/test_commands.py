import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.assistant import commands
from app.auth import commands as auth_commands
from app.core.config import settings
from app.core.llm_client import AssistantAnswer
from app.patients import commands as patient_commands

FAKE_EMBEDDING = [0.1] * 768


def _make_patient(db: Session) -> uuid.UUID:
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
    return patient.id


@pytest.fixture(autouse=True)
def _stub_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(commands, "embed_text", lambda text, **kw: list(FAKE_EMBEDDING))


def _stub_llm(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[dict],
    *,
    redirect: bool = False,
    answer: str = "General answer.",
) -> None:
    def _fake_answer_patient_question(**kwargs):
        calls.append(kwargs)
        return AssistantAnswer(answer=answer, redirect=redirect)

    monkeypatch.setattr(commands, "answer_patient_question", _fake_answer_patient_question)


def test_ask_assistant_returns_llm_answer_for_general_question(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    patient_id = _make_patient(db)
    calls: list[dict] = []
    _stub_llm(monkeypatch, calls, answer="Ice for 15-20 minutes at a time.")

    interaction = commands.ask_assistant(
        db, patient_id=patient_id, question="How long should I ice my knee?"
    )

    assert interaction.patient_id == patient_id
    assert interaction.answer == "Ice for 15-20 minutes at a time."
    assert interaction.redirected is False
    assert len(calls) == 1


def test_ask_assistant_redirects_symptom_question_without_calling_llm(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    patient_id = _make_patient(db)
    calls: list[dict] = []
    _stub_llm(monkeypatch, calls)

    interaction = commands.ask_assistant(
        db, patient_id=patient_id, question="My knee is red and swollen, is that normal?"
    )

    assert interaction.redirected is True
    assert interaction.answer == commands.CLINIC_REDIRECT_MESSAGE
    assert calls == []


def test_ask_assistant_redirects_when_llm_flags_it(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    patient_id = _make_patient(db)
    calls: list[dict] = []
    _stub_llm(monkeypatch, calls, redirect=True, answer="")

    interaction = commands.ask_assistant(
        db, patient_id=patient_id, question="Something ambiguous about my recovery"
    )

    assert interaction.redirected is True
    assert interaction.answer == commands.CLINIC_REDIRECT_MESSAGE
    assert len(calls) == 1


def test_ask_assistant_rejects_unknown_patient(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_llm(monkeypatch, [])

    with pytest.raises(commands.PatientNotFound):
        commands.ask_assistant(db, patient_id=uuid.uuid4(), question="How do I use crutches?")
