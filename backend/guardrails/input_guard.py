"""
Input guardrails: detect prompt injection, jailbreak patterns, PII leakage.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

INJECTION_PATTERNS = [
    r"ignore (all |previous |above )?instructions?",
    r"disregard (all |previous |above )?instructions?",
    r"forget (everything|all|your instructions?)",
    r"you are now",
    r"act as (a |an )?(?!financial|budget|investment|advisor|planner)",
    r"pretend (to be|you are)",
    r"jailbreak",
    r"dan (mode|prompt)",
    r"do anything now",
    r"override (your |the )?system",
    r"bypass (your |the )?(safety|guardrail|filter|restriction)",
    r"reveal (your |the )?(system prompt|instructions?|prompt)",
    r"\\x[0-9a-fA-F]{2}",
    r"<script",
    r"eval\s*\(",
    r"exec\s*\(",
    r"__import__",
]

PII_PATTERNS = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "SSN"),
    (r"\b\d{16}\b", "Credit Card"),
    (r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b", "Credit Card"),
    (r"\b[A-Z]{2}\d{6}[A-Z]?\b", "Passport"),
]

FINANCIAL_KEYWORDS = [
    "budget", "income", "expense", "investment", "portfolio", "savings",
    "retirement", "loan", "debt", "goal", "risk", "stock", "bond",
    "fund", "crypto", "tax", "insurance", "mortgage", "interest",
    "asset", "liability", "net worth", "cash flow", "dividend",
    "financial", "money", "finance", "plan", "analyze", "help",
    "what", "how", "when", "should", "recommend",
]


@dataclass
class GuardResult:
    allowed: bool
    reason: str
    sanitized_input: Optional[str] = None
    risk_level: str = "low"


def check_injection(text: str) -> tuple[bool, str]:
    text_lower = text.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True, pattern
    return False, ""


def check_pii(text: str) -> tuple[bool, str, str]:
    masked = text
    found_types = []
    for pattern, pii_type in PII_PATTERNS:
        if re.search(pattern, text):
            found_types.append(pii_type)
            masked = re.sub(pattern, f"[REDACTED-{pii_type}]", masked)
    if found_types:
        return True, ", ".join(found_types), masked
    return False, "", text


def check_length(text: str, max_chars: int = 5000) -> tuple[bool, str]:
    if len(text) > max_chars:
        return True, f"Input exceeds {max_chars} characters"
    return False, ""


def is_relevant_to_finance(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in FINANCIAL_KEYWORDS)


def validate_input(user_input: str, enforce_finance_domain: bool = False) -> GuardResult:
    """Run all input guardrails. Returns GuardResult with allowed/blocked decision."""
    if not user_input or not user_input.strip():
        return GuardResult(allowed=False, reason="Empty input", risk_level="low")

    too_long, length_reason = check_length(user_input)
    if too_long:
        return GuardResult(allowed=False, reason=length_reason, risk_level="medium")

    is_injection, pattern = check_injection(user_input)
    if is_injection:
        logger.warning(f"Prompt injection detected: pattern='{pattern}'")
        return GuardResult(
            allowed=False,
            reason="Potential prompt injection detected. Please ask a genuine financial planning question.",
            risk_level="high",
        )

    has_pii, pii_types, sanitized = check_pii(user_input)
    if has_pii:
        logger.warning(f"PII detected: {pii_types} - masking and proceeding")
        return GuardResult(
            allowed=True,
            reason=f"PII detected ({pii_types}) and redacted for safety",
            sanitized_input=sanitized,
            risk_level="medium",
        )

    if enforce_finance_domain and not is_relevant_to_finance(user_input):
        return GuardResult(
            allowed=False,
            reason="This system handles financial planning questions only.",
            risk_level="low",
        )

    return GuardResult(allowed=True, reason="OK", sanitized_input=user_input, risk_level="low")
