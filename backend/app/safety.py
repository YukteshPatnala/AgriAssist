"""Escalation rules: decide when the bot must NOT generate a free-form answer."""
from __future__ import annotations

import re
from dataclasses import dataclass

# Queries matching these describe possible poisoning, injury or self-harm.
# They are escalated BEFORE any text is sent to the language model.
RISK_PATTERNS = [
    r"poison",
    r"(swallow|swallowed|drank|drunk|ate|eaten|consumed|drink)\b.*\b(pesticide|insecticide|herbicide|weedicide|fungicide|spray|chemical|kerosene|fertili[sz]er)",
    r"\b(pesticide|insecticide|herbicide|weedicide|fungicide|chemical)\b.*\b(skin|eyes?|mouth|inhaled|breath)",
    r"snake ?bite|bitten by|scorpion sting",
    r"chemical burn",
    r"difficulty breathing|trouble breathing|can'?t breathe|unconscious|seizure|convulsion",
    r"suicid|kill myself|end my life|self[- ]harm",
]
_RISK_RE = [re.compile(p, re.IGNORECASE) for p in RISK_PATTERNS]

ESCALATION_MESSAGES = {
    "risk": (
        "This may be a medical or safety emergency involving a chemical or an injury. "
        "Please do not rely on this chatbot. Call 112 (India emergency number) now or go to "
        "the nearest hospital, and take the pesticide label or container with you. "
        "If you are thinking about harming yourself, call Tele-MANAS on 14416."
    ),
    "low_confidence": (
        "I could not find reliable information in the knowledge base for this question, so I "
        "will not guess. Please contact your local Krishi Vigyan Kendra (KVK) or agriculture "
        "officer, or call the Kisan Call Centre on 1800-180-1551 (toll-free)."
    ),
}


@dataclass(frozen=True)
class Decision:
    escalate: bool
    reason: str | None  # "risk", "low_confidence" or None
    confidence: float


def find_risk_matches(question: str) -> list[str]:
    return [p.pattern for p in _RISK_RE if p.search(question)]


def assess(question: str, top_score: float, min_confidence: float) -> Decision:
    if find_risk_matches(question):
        return Decision(escalate=True, reason="risk", confidence=top_score)
    if top_score < min_confidence:
        return Decision(escalate=True, reason="low_confidence", confidence=top_score)
    return Decision(escalate=False, reason=None, confidence=top_score)
