import pytest

from app.assistant.urgent_detection import detect_symptom_or_urgent


@pytest.mark.parametrize(
    "question",
    [
        "My knee is red and swollen, is that normal?",
        "I have a fever today, should I be worried?",
        "My incision is draining a bit, is that ok?",
        "I felt a pop in my knee and now it feels unstable",
        "Is it normal for my calf to hurt?",
        "I fell yesterday, is my knee okay?",
        "This feels like an emergency, what should I do?",
    ],
)
def test_detects_symptom_or_urgent_questions(question: str) -> None:
    assert detect_symptom_or_urgent(question) is not None


@pytest.mark.parametrize(
    "question",
    [
        "How do I use crutches properly?",
        "What should I expect during week 2 of recovery?",
        "What does a normal home exercise program look like?",
        "When can I stop wearing the brace?",
        "How do I reduce stiffness after sitting for a while?",
    ],
)
def test_does_not_flag_general_education_questions(question: str) -> None:
    assert detect_symptom_or_urgent(question) is None
