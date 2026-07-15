"""Runtime configuration resolved from environment variables.

The only required keys are the two API keys (ANTHROPIC_API_KEY, TAVILY_API_KEY);
everything else has a sensible default, so an out-of-the-box run writes articles
to a local directory with no backend to configure.
"""

import os

DEFAULT_MODEL = "anthropic:claude-opus-4-8"
DEFAULT_OUTPUT_DIR = "output"

# Provider name (as init_chat_model spells it) -> the pyproject extra to install.
PROVIDER_EXTRAS = {
    "openai": "openai",
    "google_genai": "google",
    "ollama": "ollama",
}


def model_spec() -> str:
    """Provider-prefixed chat model used for both stages, e.g. "openai:gpt-4.1".

    Passed straight to langchain's init_chat_model, so any provider it supports
    works (install the matching extra — see PROVIDER_EXTRAS). A bare model name
    still resolves when the provider is inferable (e.g. "claude-..." -> anthropic).
    """
    return os.environ.get("RESEARCH_MODEL", DEFAULT_MODEL)


def model_params() -> dict:
    """Generation params passed to the model constructor.

    max_tokens and timeout keep the original defaults. temperature, base_url,
    and api_key are included only when their env vars are set — base_url points
    an OpenAI-/Anthropic-compatible provider at a custom endpoint (Groq,
    Together, OpenRouter, a local server), and api_key overrides the provider's
    default key env var (e.g. a Groq key without touching OPENAI_API_KEY).
    """
    params: dict = {
        "max_tokens": int(os.environ.get("RESEARCH_MAX_TOKENS", "8000")),
        "timeout": int(os.environ.get("RESEARCH_TIMEOUT", "300")),
    }
    temperature = os.environ.get("RESEARCH_TEMPERATURE")
    if temperature is not None:
        params["temperature"] = float(temperature)
    base_url = os.environ.get("RESEARCH_BASE_URL")
    if base_url:
        params["base_url"] = base_url
    api_key = os.environ.get("RESEARCH_API_KEY")
    if api_key:
        params["api_key"] = api_key
    return params


def structured_method() -> str | None:
    """Optional method for with_structured_output ("json_schema", "json_mode",
    "function_calling", ...). Some models/endpoints need a specific one; None
    lets langchain pick the provider default."""
    return os.environ.get("RESEARCH_STRUCTURED_METHOD") or None


def publish_backend() -> tuple[str, str] | None:
    """(base_url, token) for an optional HTTP publish backend, or None.

    Set PUBLISH_URL + PUBLISH_TOKEN to POST finished drafts to your own
    endpoint (a CMS, review queue, etc.) instead of writing them to disk.
    The legacy DWORKS_* names are still honored so existing deployments keep
    working without a config change.
    """
    base = os.environ.get("PUBLISH_URL") or os.environ.get("DWORKS_API_URL")
    token = os.environ.get("PUBLISH_TOKEN") or os.environ.get("DWORKS_INGEST_TOKEN")
    if base and token:
        return base.rstrip("/"), token
    return None
