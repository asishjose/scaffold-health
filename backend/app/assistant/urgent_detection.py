import re

# Deterministic redirect gate (PRD §5.8): any question that reads as
# symptom-related or urgent must never be answered clinically, and this
# codebase's convention is that the LLM never makes safety/routing
# decisions itself (deterministic merge routing, deterministic
# needs_review flags, deterministic contradiction detection). This
# pattern list is informed by the product's own red-flag/when-to-call
# seed content (app/rag/seed_data/clinical_guidelines/acl_general_red_flags.txt,
# app/rag/seed_data/patient_education/when_to_call_the_clinic.txt), broadened
# to any mention of the patient's own symptoms/condition rather than just
# the dangerous subset, per PRD §5.8 item 3's "any question that reads as
# symptom-related or urgent." Patterns are word-bounded (`\b`) so short
# fragments like "red" don't match inside unrelated words like "reduce".
_KEYWORD_PATTERNS: dict[str, re.Pattern[str]] = {
    label: re.compile(pattern)
    for label, pattern in {
        "pain": r"\bpains?\b",
        "hurt": r"\bhurt(s|ing)?\b",
        "ache": r"\bach(e|es|ing)\b",
        "swelling": r"\bswoll?en\b|\bswell(ing|s)?\b",
        "fever": r"\bfevers?\b",
        "redness": r"\bredness\b|\bred\b",
        "warmth": r"\bwarmth\b|\bwarm to (the )?touch\b",
        "hot to the touch": r"\bhot to (the )?touch\b",
        "numbness": r"\bnumb(ness)?\b",
        "tingling": r"\btingl\w*\b",
        "popping": r"\bpopp?(ed|ing)?\b",
        "locking": r"\block(ing|ed|s)?\b",
        "catching": r"\bcatch(ing|es)?\b",
        "giving way": r"\bgiving way\b|\bgave way\b",
        "buckling": r"\bbuckl\w*\b",
        "instability": r"\bunstable\b|\binstability\b",
        "drainage": r"\bdrainage\b|\bdraining\b",
        "pus": r"\bpus\b",
        "bleeding": r"\bbleed(ing)?\b",
        "infection": r"\binfect\w*\b",
        "calf pain": r"\bcalf\b",
        "chest pain": r"\bchest pain\b",
        "shortness of breath": r"\bshortness of breath\b|\bcan'?t breathe\b",
        "emergency": r"\bemergency\b|\burgent\b|\b911\b|\ber\b",
        "fall": r"\bfell\b|\bfall(en|ing)?\b",
        "wound": r"\bwound\b|\bincision\b",
        "worsening": r"\bworse\b|\bworsening\b",
    }.items()
}


def detect_symptom_or_urgent(question: str) -> str | None:
    """Returns the matched keyword label if `question` reads as
    symptom-related or urgent, else None. Checked before any RAG retrieval
    or LLM call — a match means the assistant never attempts to answer
    clinically at all.
    """
    for label, pattern in _KEYWORD_PATTERNS.items():
        if pattern.search(question.lower()):
            return label
    return None
