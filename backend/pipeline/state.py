from typing import Optional

from backend.models import GraphState


# Source-quality tiers. This is NOT a confidence score — it reflects the
# trustworthiness of the *retrieval source*, not the correctness of the answer.
# Real answer-faithfulness scoring would require RAGAS or a separate evaluator.
_SOURCE_TIER: dict[str, str] = {
    "Q&A":         "verified_corpus",   # structured, curated Q&A
    "Device":      "verified_corpus",   # device manual content
    "Web Search":  "external_web",      # unverified third-party pages
}

_TIER_LABEL: dict[str, str] = {
    "verified_corpus": "Verified corpus (structured medical data)",
    "external_web":    "External web search (unverified)",
    "unknown":         "Unknown source",
    "failed":          "Retrieval failed",
}


def compute_source_quality(state: GraphState) -> Optional[dict]:
    """
    Return a structured source-quality descriptor.

    This is intentionally NOT called 'confidence' — it describes where the
    context came from, not how likely the answer is to be correct.  For real
    answer-faithfulness scoring consider integrating RAGAS.
    """
    source = state.get("source", "")
    is_relevant = state.get("is_relevant", "No").lower() == "yes"
    iterations = state.get("iteration_count", 1)

    if "failed" in source.lower():
        tier = "failed"
    elif "Web Search" in source:
        tier = "external_web"
    elif any(k in source for k in ("Q&A", "Device")):
        tier = "verified_corpus"
    else:
        tier = "unknown"

    return {
        "tier": tier,
        "label": _TIER_LABEL[tier],
        "is_relevant": is_relevant,
        "iterations": iterations,
        "disclaimer": (
            "Source quality reflects the retrieval origin, not answer correctness. "
            "Always verify medical information with a qualified healthcare professional."
        ),
    }
