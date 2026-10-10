"""
Output guardrails: validate agent responses for safety,
hallucinated guarantees, system prompt leakage, and unsafe financial advice.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

GUARANTEE_PATTERNS = [
    r"guaranteed? (return|profit|gain|income|yield)",
    r"you (will|shall|are going to) (definitely|certainly|absolutely) (make|earn|profit|gain)",
    r"(100%|guaranteed?) (safe|secure|risk.?free)",
    r"no (risk|loss) (whatsoever|at all|guaranteed?)",
    r"definitely (make|earn|profit|return)",
    r"certain(ly)? (profit|gain|return)",
    r"cannot (lose|fail)",
]

SYSTEM_PROMPT_LEAK_PATTERNS = [
    r"my (system |)prompt (is|says|states)",
    r"i (was|am) (instructed|told|configured|programmed) to",
    r"my (instructions?|directive|rules?) (are|say|state|include)",
    r"confidential (system |)prompt",
]

UNSAFE_ADVICE_PATTERNS = [
    r"invest (all|everything|100%) (of |your )?(money|savings|funds|assets)",
    r"take out (a |)(loan|mortgage|debt) to (invest|buy|trade)",
    r"(put|place) (all|everything) (on|in) (one|a single)",
    r"(insider|secret) (trading|information|tip)",
    r"(evade|avoid) (taxes?|irs|hmrc) (illegally|fraudulently)",
    r"launder",
    r"(pyramid|ponzi) scheme",
]

DISCLAIMER = (
    "\n\n---\n*Disclaimer: This AI provides general financial information only and does not "
    "constitute professional financial advice. Please consult a certified financial advisor "
    "before making investment decisions.*"
)


@dataclass
class OutputGuardResult:
    safe: bool
    reason: str
    sanitized_output: Optional[str] = None
    risk_flags: list = field(default_factory=list)


def check_false_guarantees(text: str) -> list[str]:
    return [f"false_guarantee:{p}" for p in GUARANTEE_PATTERNS if re.search(p, text, re.IGNORECASE)]


def check_system_prompt_leak(text: str) -> list[str]:
    return [f"system_prompt_leak:{p}" for p in SYSTEM_PROMPT_LEAK_PATTERNS if re.search(p, text, re.IGNORECASE)]


def check_unsafe_advice(text: str) -> list[str]:
    return [f"unsafe_advice:{p}" for p in UNSAFE_ADVICE_PATTERNS if re.search(p, text, re.IGNORECASE)]


def validate_output(agent_output: str, agent_name: str = "unknown") -> OutputGuardResult:
    """Validate agent output for safety issues."""
    if not agent_output or not agent_output.strip():
        return OutputGuardResult(
            safe=False, reason="Empty agent output",
            sanitized_output="I was unable to generate a response. Please try again.",
        )

    risk_flags = []
    risk_flags.extend(check_false_guarantees(agent_output))
    risk_flags.extend(check_system_prompt_leak(agent_output))
    risk_flags.extend(check_unsafe_advice(agent_output))

    if risk_flags:
        logger.warning(f"[{agent_name}] Output guard flags: {risk_flags}")

    leak_flags = [f for f in risk_flags if "system_prompt_leak" in f]
    if leak_flags:
        return OutputGuardResult(
            safe=False,
            reason="System prompt leakage detected",
            sanitized_output="I'm unable to share that information. How can I help with your financial planning?",
            risk_flags=risk_flags,
        )

    if risk_flags:
        return OutputGuardResult(
            safe=True,
            reason="Risk flags detected; disclaimer appended",
            sanitized_output=agent_output + DISCLAIMER,
            risk_flags=risk_flags,
        )

    return OutputGuardResult(
        safe=True, reason="OK",
        sanitized_output=agent_output + DISCLAIMER,
        risk_flags=[],
    )
