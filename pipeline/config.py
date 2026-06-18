"""
Central configuration.

One place to read the few environment switches the pipeline understands, so the
CLI (`run.py`), the UI (`app.py`), and the eval harness all agree. Everything has
a safe, offline default — the prototype runs with zero setup, and you flip one env
var at a time to turn on each real component.

    LLM_PROVIDER    mock (default) | anthropic | openai
    ANTHROPIC_MODEL default claude-sonnet-4-6   (when LLM_PROVIDER=anthropic)
    OPENAI_MODEL    default gpt-4o-mini         (when LLM_PROVIDER=openai)
    RETRIEVAL_MODE  embeddings (default; falls back to keyword if deps absent) | keyword
    EMBED_MODEL     default all-MiniLM-L6-v2    (when RETRIEVAL_MODE=embeddings)
    WHISPER_MODEL   default base                (voice capture)

Secrets (ANTHROPIC_API_KEY / OPENAI_API_KEY) and any of the switches above can be
placed in a `.env` file at the project root — it is loaded automatically on import
(and is gitignored). Real environment variables always take precedence over `.env`.
"""

import os

# Load .env from the project root if python-dotenv is installed. Optional: the
# pipeline still runs from real env vars (or defaults) when it isn't present.
try:
    from dotenv import load_dotenv

    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_ROOT, ".env"))  # does not override real env vars
except ImportError:
    pass

DEFAULTS = {
    "LLM_PROVIDER": "mock",
    "ANTHROPIC_MODEL": "claude-sonnet-4-6",
    "OPENAI_MODEL": "gpt-4o-mini",
    "RETRIEVAL_MODE": "embeddings",
    "EMBED_MODEL": "all-MiniLM-L6-v2",
    "WHISPER_MODEL": "base",
}


def get(key: str) -> str:
    """Read a setting from the environment, falling back to the documented default."""
    return os.environ.get(key, DEFAULTS[key])


def llm_provider() -> str:
    return get("LLM_PROVIDER").lower()


def retrieval_mode() -> str:
    return get("RETRIEVAL_MODE").lower()
