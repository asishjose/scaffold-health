import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.auth import commands as auth_commands
from app.copilot import commands
from app.copilot.events import ROLE_ASSISTANT, ROLE_THERAPIST
from app.core.config import settings
from app.core.llm_client import CopilotAnswer
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


def _stub_llm(monkeypatch: pytest.MonkeyPatch, calls: list[dict], *, answer: str = "General answer.") -> None:
    def _fake_answer_copilot_message(**kwargs):
        calls.append(kwargs)
        return CopilotAnswer(answer=answer)

    monkeypatch.setattr(commands, "answer_copilot_message", _fake_answer_copilot_message)


def test_send_message_returns_assistant_reply_and_persists_both_rows(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    therapist_id, patient_id = _make_patient(db)
    calls: list[dict] = []
    _stub_llm(monkeypatch, calls, answer="Their active restriction is no pivoting.")

    reply = commands.send_message(
        db, patient_id=patient_id, therapist_id=therapist_id, content="Any restrictions?"
    )

    assert reply.role == ROLE_ASSISTANT
    assert reply.content == "Their active restriction is no pivoting."
    assert len(calls) == 1

    thread = commands.list_messages(db, patient_id=patient_id, therapist_id=therapist_id)
    assert [m.role for m in thread] == [ROLE_THERAPIST, ROLE_ASSISTANT]
    assert thread[0].content == "Any restrictions?"
    assert thread[1].id == reply.id


def test_send_message_second_call_includes_prior_turn_in_history(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    therapist_id, patient_id = _make_patient(db)
    calls: list[dict] = []
    _stub_llm(monkeypatch, calls)

    commands.send_message(db, patient_id=patient_id, therapist_id=therapist_id, content="First question")
    commands.send_message(db, patient_id=patient_id, therapist_id=therapist_id, content="Follow-up question")

    assert calls[0]["history"] == []
    second_history = calls[1]["history"]
    assert {"role": "user", "content": "First question"} in second_history
    assert {"role": "assistant", "content": "General answer."} in second_history


def test_send_message_rejects_unknown_patient(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    therapist_id, _ = _make_patient(db)
    _stub_llm(monkeypatch, [])

    with pytest.raises(commands.PatientNotFound):
        commands.send_message(
            db, patient_id=uuid.uuid4(), therapist_id=therapist_id, content="Hello"
        )


def test_send_message_rejects_non_owning_therapist(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, patient_id = _make_patient(db)
    other_therapist_id, _ = _make_patient(db)
    _stub_llm(monkeypatch, [])

    with pytest.raises(commands.PatientNotFound):
        commands.send_message(
            db, patient_id=patient_id, therapist_id=other_therapist_id, content="Hello"
        )


def test_list_messages_rejects_non_owning_therapist(db: Session) -> None:
    _, patient_id = _make_patient(db)
    other_therapist_id, _ = _make_patient(db)

    with pytest.raises(commands.PatientNotFound):
        commands.list_messages(db, patient_id=patient_id, therapist_id=other_therapist_id)
