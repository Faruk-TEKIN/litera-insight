from dataclasses import dataclass
import re


GREETING_RESPONSE = (
    "As an AI assistant, I can help with academic research, literature review, "
    "writing, methodology, citations, and study support. What would you like to know?"
)
REFUSAL_RESPONSE = (
    "As an AI assistant, I cannot help with that request. "
    "The request is outside my allowed academic safety boundaries. "
    "I can only help with safe, ethical, and lawful academic or research-support tasks."
)


@dataclass(frozen=True)
class SafetyDecision:
    should_block: bool
    response: str | None = None
    reason: str | None = None


_SIMPLE_GREETING_PATTERNS = (
    r"^(hi|hello|hey|merhaba|selam|selamlar|greetings)[.!?\s]*$",
    r"^(thanks|thank you|tesekkurler|teşekkürler|sag ol|sağ ol)[.!?\s]*$",
)

_SCOPE_PATTERNS = (
    r"\bwhat can you do\b",
    r"\bhow can you help\b",
    r"\bne yapabilirsin\b",
    r"\bnasil yardimci olabilirsin\b",
    r"\bnasıl yardımcı olabilirsin\b",
)

_OUT_OF_SCOPE_PATTERNS = (
    r"\bfootball match\b",
    r"\bsoccer match\b",
    r"\bmatch commentary\b",
    r"\bcelebrity gossip\b",
    r"\bmovie recommendation\b",
    r"\bhangi takimi tutuyorsun\b",
    r"\bhangi takımı tutuyorsun\b",
    r"\bmac hakkinda ne dusunuyorsun\b",
    r"\bmaç hakkında ne düşünüyorsun\b",
)

_UNSAFE_PATTERNS = (
    r"\bmake (?:a )?(?:bomb|explosive|weapon)\b",
    r"\bbuild (?:a )?(?:bomb|explosive|weapon)\b",
    r"\bhow to (?:kill|poison|harm|hurt)\b",
    r"\bsuicide method\b",
    r"\bself[- ]harm method\b",
    r"\bwrite (?:a )?(?:malware|ransomware|spyware)\b",
    r"\bcreate (?:a )?(?:malware|ransomware|spyware|phishing)\b",
    r"\bsteal (?:passwords?|credentials?|accounts?)\b",
    r"\bbypass (?:authentication|login|rate limits?|security)\b",
    r"\bfake (?:id|passport|document)\b",
    r"\bdoxx(?:ing)?\b",
)


def evaluate_user_message_safety(message: str) -> SafetyDecision:
    normalized = _normalize(message)
    if not normalized:
        return SafetyDecision(should_block=True, response=GREETING_RESPONSE, reason="empty_or_greeting")

    if any(re.search(pattern, normalized) for pattern in _OUT_OF_SCOPE_PATTERNS):
        return SafetyDecision(should_block=True, response=REFUSAL_RESPONSE, reason="out_of_scope")

    if any(re.search(pattern, normalized) for pattern in _UNSAFE_PATTERNS):
        return SafetyDecision(should_block=True, response=REFUSAL_RESPONSE, reason="unsafe_request")

    if any(re.search(pattern, normalized) for pattern in _SIMPLE_GREETING_PATTERNS):
        return SafetyDecision(should_block=True, response=GREETING_RESPONSE, reason="simple_greeting")

    if any(re.search(pattern, normalized) for pattern in _SCOPE_PATTERNS):
        return SafetyDecision(should_block=True, response=GREETING_RESPONSE, reason="scope_question")

    return SafetyDecision(should_block=False)


def is_refusal_response(response: str) -> bool:
    return (response or "").lstrip().startswith("As an AI assistant, I cannot help with that request.")


def _normalize(message: str) -> str:
    return " ".join((message or "").lower().strip().split())
