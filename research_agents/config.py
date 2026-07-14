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
    "google_vertexai": "google",
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

    max_tokens and timeout keep the original defaults; temperature is included
    only when RESEARCH_TEMPERATURE is set, since some models reject the field.
    """
    params: dict = {
        "max_tokens": int(os.environ.get("RESEARCH_MAX_TOKENS", "8000")),
        "timeout": int(os.environ.get("RESEARCH_TIMEOUT", "300")),
    }
    temperature = os.environ.get("RESEARCH_TEMPERATURE")
    if temperature is not None:
        params["temperature"] = float(temperature)
    return params


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
