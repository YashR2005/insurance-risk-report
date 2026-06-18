"""
LLM interface.

The whole pipeline talks to the model through this one small interface, so you
can develop and demo the entire flow with NO API key (the MockLLM), then flip a
single env var to run it for real.

    LLM_PROVIDER=mock        -> deterministic, runs offline (default)
    LLM_PROVIDER=anthropic   -> uses ANTHROPIC_API_KEY
    LLM_PROVIDER=openai      -> uses OPENAI_API_KEY

Two methods are all the pipeline needs:
    complete(system, user)   -> free-text generation (used by draft.py)
    entails(claim, evidence) -> SUPPORTED / PARTIAL / UNSUPPORTED (used by verify.py)
"""

import re


class LLMClient:
    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError

    def entails(self, claim: str, evidence: str) -> tuple[str, str]:
        """Return (status, reason) where status in {SUPPORTED, PARTIAL, UNSUPPORTED}."""
        raise NotImplementedError


# --------------------------------------------------------------------------
# Mock implementation: no network, fully deterministic. Good enough to build
# and demo the architecture. Replace by setting LLM_PROVIDER once you have keys.
# --------------------------------------------------------------------------
_STOP = set("the a an of to in on for and or is are with at by from as be this that "
            "it its no not only near against per shall should must may".split())


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP and len(w) > 2}


class MockLLM(LLMClient):
    def complete(self, system: str, user: str) -> str:
        # In the skeleton, draft.py already assembles structured claims; the
        # "generation" step here just returns them. The real LLM would rephrase
        # these into polished prose. Kept deterministic so demos are reproducible.
        return user

    def entails(self, claim: str, evidence: str) -> tuple[str, str]:
        # Stand-in for real entailment: lexical overlap between the claim and the
        # cited source. A real model would judge meaning, not word overlap.
        c, e = _tokens(claim), _tokens(evidence)
        if not c:
            return "UNSUPPORTED", "Empty claim."
        overlap = len(c & e) / len(c)
        if overlap >= 0.5:
            return "SUPPORTED", f"Cited section shares key terms ({overlap:.0%} overlap)."
        if overlap >= 0.2:
            return "PARTIAL", f"Cited section is related but thin ({overlap:.0%} overlap)."
        return "UNSUPPORTED", "Cited section does not cover this claim."


# --------------------------------------------------------------------------
# Real providers. Imports are inside __init__ so the skeleton runs even when
# these packages aren't installed.
# --------------------------------------------------------------------------
class AnthropicLLM(LLMClient):
    def __init__(self, model: str | None = None):
        import anthropic
        from . import config
        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.model = model or config.get("ANTHROPIC_MODEL")

    def complete(self, system: str, user: str) -> str:
        msg = self.client.messages.create(
            model=self.model, max_tokens=1024,
            system=system, messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in msg.content if b.type == "text")

    def entails(self, claim: str, evidence: str) -> tuple[str, str]:
        out = self.complete(
            "You are a strict fact-checker for insurance risk reports. "
            "Reply with one word (SUPPORTED, PARTIAL, or UNSUPPORTED), then a dash, then a short reason.",
            f"CLAIM:\n{claim}\n\nEVIDENCE (the only source allowed):\n{evidence}",
        )
        return _parse_entailment(out)


class OpenAILLM(LLMClient):
    def __init__(self, model: str | None = None):
        from openai import OpenAI
        from . import config
        self.client = OpenAI()  # reads OPENAI_API_KEY
        self.model = model or config.get("OPENAI_MODEL")

    def complete(self, system: str, user: str) -> str:
        r = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        return r.choices[0].message.content

    def entails(self, claim: str, evidence: str) -> tuple[str, str]:
        out = self.complete(
            "You are a strict fact-checker for insurance risk reports. "
            "Reply with one word (SUPPORTED, PARTIAL, or UNSUPPORTED), then a dash, then a short reason.",
            f"CLAIM:\n{claim}\n\nEVIDENCE (the only source allowed):\n{evidence}",
        )
        return _parse_entailment(out)


def _parse_entailment(out: str) -> tuple[str, str]:
    head = out.strip().upper()
    for status in ("SUPPORTED", "PARTIAL", "UNSUPPORTED"):
        if head.startswith(status):
            reason = out.split("-", 1)[1].strip() if "-" in out else ""
            return status, reason
    return "PARTIAL", out.strip()[:120]


def get_llm() -> LLMClient:
    from . import config
    provider = config.llm_provider()
    if provider == "anthropic":
        return AnthropicLLM()
    if provider == "openai":
        return OpenAILLM()
    return MockLLM()


def friendly_llm_error(exc: Exception) -> str:
    """Map a raw provider exception to a clear, actionable message.

    Keeps the prototype from dumping a stack trace on the common failures
    (no credit, bad key, rate limit). Falls back to the exception text.
    """
    name = type(exc).__name__
    msg = str(exc)
    low = msg.lower()
    if "insufficient_quota" in low or "exceeded your current quota" in low:
        return ("The API account has no remaining quota/credits. Add billing to the "
                "provider account, switch LLM_PROVIDER, or use mock mode (unset LLM_PROVIDER).")
    if name in ("AuthenticationError",) or "invalid_api_key" in low or "401" in low:
        return "The API key was rejected. Check the key in .env for the selected LLM_PROVIDER."
    if name in ("RateLimitError",) or "rate limit" in low:
        return "Hit the provider rate limit. Wait and retry, or reduce request volume."
    if name in ("APIConnectionError", "APITimeoutError") or "connection" in low:
        return "Could not reach the LLM provider. Check your network and try again."
    return f"LLM call failed ({name}): {msg}"
