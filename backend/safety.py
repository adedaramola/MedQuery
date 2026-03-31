"""
Safety guardrails for the Medical RAG system.

All queries pass through `check_safety` before entering the LangGraph pipeline.
Checks run in this order:
  1. Scope check  — reject queries with no medical content (OUT_OF_SCOPE)
  2. Block check  — reject high-risk personal-safety queries (BLOCKED)
  3. Flag check   — allow but append disclaimer (FLAGGED)
  4. Pass through — (SAFE)
"""
import os
import re
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Risk levels
# ---------------------------------------------------------------------------

class RiskLevel(str, Enum):
    SAFE = "safe"
    FLAGGED = "flagged"          # Borderline — answer with strong disclaimer
    BLOCKED = "blocked"          # Do not answer; redirect to professional
    OUT_OF_SCOPE = "out_of_scope"  # Non-medical query — not handled by this system


@dataclass
class SafetyResult:
    risk_level: RiskLevel
    reason: Optional[str] = None
    safe_response: Optional[str] = None   # Pre-written response for BLOCKED queries


# ---------------------------------------------------------------------------
# Scope: LLM-based medical topic classifier
# ---------------------------------------------------------------------------
# Uses gpt-4o-mini (cheap, fast) to decide if a query is health/medicine-related.
# Fails open — if the classifier call errors, the query is allowed through.

def _is_medical_query(query: str) -> bool:
    """Return True if the query is related to medicine, health, or clinical research."""
    try:
        from openai import OpenAI
        from backend.config import OPENAI_API_KEY
        base_url = os.getenv("LLM_BASE_URL") or None
        client = OpenAI(api_key=OPENAI_API_KEY, base_url=base_url)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a query classifier for a medical research assistant. "
                        "Determine whether the user's question is related to medicine, "
                        "health, biology, clinical research, medical devices, "
                        "pharmaceuticals, or any health-related topic. "
                        "Reply with ONLY 'yes' or 'no'."
                    ),
                },
                {"role": "user", "content": query},
            ],
            temperature=0,
            max_tokens=5,
        )
        answer = resp.choices[0].message.content.strip().lower()
        return answer.startswith("yes")
    except Exception as e:
        logger.warning(f"Scope classifier error (failing open): {e}")
        return True  # fail open — never block a query due to a classifier error


_OUT_OF_SCOPE_RESPONSE = (
    "This system is designed exclusively for medical research queries. "
    "Your question does not appear to be related to medicine, health, or clinical research.\n\n"
    "Please ask about topics such as:\n"
    "- Diseases, conditions, or symptoms\n"
    "- Medications, treatments, or therapies\n"
    "- Clinical research or medical guidelines\n"
    "- Medical devices or procedures\n\n"
    "For non-medical questions, please use a general-purpose assistant."
)

# ---------------------------------------------------------------------------
# Pattern lists
# ---------------------------------------------------------------------------

# BLOCKED: direct personal-safety queries that we must never answer
_BLOCKED_PATTERNS: list[re.Pattern] = [re.compile(p, re.IGNORECASE) for p in [
    # Overdose intent / thresholds
    r"\b(how\s+much|what\s+dose|lethal\s+dose|ld50|maximum\s+dose).{0,40}(kill|die|death|lethal|overdose|fatal)",
    r"\b(overdose|OD).{0,30}(on purpose|intentional|want\s+to|how\s+to)",
    r"\bhow\s+many.{0,20}(pills?|tablets?|capsules?).{0,20}(kill|die|fatal|lethal)",

    # Dangerous drug combinations asked for harmful use
    r"\b(mix|combine|take\s+together).{0,40}(to\s+get\s+high|to\s+die|to\s+kill|make\s+me\s+sick)",

    # Self-harm / suicide method queries
    r"\b(how\s+to|ways?\s+to|method\s+(for|of)).{0,30}(commit\s+suicide|end\s+my\s+life|kill\s+myself)",
    r"\bsuicide\s+(method|plan|attempt|how)",

    # Explicit harm-to-others queries
    r"\b(poison|drug).{0,30}(someone|another\s+person|without\s+them\s+knowing)",
    r"\bhow\s+to.{0,30}(make|synthesize|produce).{0,30}(poison|toxin|nerve\s+agent)",
]]

# FLAGGED: high-risk topics that need a strong disclaimer but can be discussed
_FLAGGED_PATTERNS: list[re.Pattern] = [re.compile(p, re.IGNORECASE) for p in [
    r"\boverdose\b",
    r"\bsuicid(e|al)\b",
    r"\bself.?harm\b",
    r"\bdrug.{0,20}interact",
    r"\b(maximum|max)\s+(safe\s+)?dose",
    r"\bwithdrawal\s+(from|symptoms)",
    r"\b(stop|quit|discontinue)\s+(taking|using).{0,20}(cold\s+turkey|abruptly|suddenly)",
    r"\bprescription.{0,30}without.{0,30}doctor",
    r"\bbuy.{0,20}(online|without\s+prescription)",
]]

# ---------------------------------------------------------------------------
# Pre-written responses
# ---------------------------------------------------------------------------

_BLOCKED_RESPONSE = (
    "This question touches on a topic that could involve serious personal safety risk. "
    "I'm not able to provide that information. If you or someone you know is in crisis, "
    "please contact emergency services (call 911 or your local equivalent) or a crisis "
    "helpline immediately:\n\n"
    "• **US National Suicide & Crisis Lifeline**: 988 (call or text)\n"
    "• **Crisis Text Line**: Text HOME to 741741\n"
    "• **International Association for Suicide Prevention**: https://www.iasp.info/resources/Crisis_Centres/\n\n"
    "Please speak with a qualified healthcare professional for any medication or treatment questions."
)

_FLAGGED_DISCLAIMER = (
    "\n\n---\n"
    "**Safety notice**: This information is for general educational purposes only. "
    "Medication dosing, drug interactions, and discontinuation schedules must be "
    "determined by a licensed healthcare provider based on your individual medical "
    "history. Do not make any changes to your medication regimen without consulting "
    "your doctor or pharmacist."
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_safety(query: str) -> SafetyResult:
    """
    Classify a user query by risk level.

    Checks run in order: OUT_OF_SCOPE → BLOCKED → FLAGGED → SAFE.

    Returns:
        SafetyResult with risk_level, optional reason, and optional pre-written
        safe_response (populated for BLOCKED and OUT_OF_SCOPE queries).
    """
    # 1. Scope check — reject non-medical queries first
    if not _is_medical_query(query):
        logger.info(f"OUT_OF_SCOPE query rejected: {query[:60]}")
        return SafetyResult(
            risk_level=RiskLevel.OUT_OF_SCOPE,
            reason="Query does not contain medical or health-related content",
            safe_response=_OUT_OF_SCOPE_RESPONSE,
        )

    # 2. Block high-risk personal-safety queries
    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(query):
            logger.warning(f"BLOCKED query matched pattern: {pattern.pattern[:60]}")
            return SafetyResult(
                risk_level=RiskLevel.BLOCKED,
                reason="Query matched high-risk safety pattern",
                safe_response=_BLOCKED_RESPONSE,
            )

    # 3. Flag sensitive topics that need a disclaimer
    for pattern in _FLAGGED_PATTERNS:
        if pattern.search(query):
            logger.info(f"FLAGGED query matched pattern: {pattern.pattern[:60]}")
            return SafetyResult(
                risk_level=RiskLevel.FLAGGED,
                reason="Query involves a sensitive medical topic",
            )

    return SafetyResult(risk_level=RiskLevel.SAFE)


def append_safety_disclaimer(response: str, safety_result: SafetyResult) -> str:
    """Append the flagged disclaimer to a response when risk_level is FLAGGED."""
    if safety_result.risk_level == RiskLevel.FLAGGED:
        return response + _FLAGGED_DISCLAIMER
    return response
