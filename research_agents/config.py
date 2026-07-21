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

    max_tokens and timeout keep the original defaults; temperature is added only
    when set. base_url and api_key target an OpenAI-compatible endpoint (Groq,
    Together, OpenRouter, a local server) and are only valid with the openai
    provider — setting them with any other RESEARCH_MODEL raises, rather than
    passing unsupported kwargs or silently hitting the wrong endpoint.
    """
    params: dict = {
        "max_tokens": int(os.environ.get("RESEARCH_MAX_TOKENS", "8000")),
        "timeout": int(os.environ.get("RESEARCH_TIMEOUT", "300")),
    }
    temperature = os.environ.get("RESEARCH_TEMPERATURE")
    if temperature is not None:
        params["temperature"] = float(temperature)

    base_url = os.environ.get("RESEARCH_BASE_URL")
    api_key = os.environ.get("RESEARCH_API_KEY")
    if base_url or api_key:
        spec = model_spec()
        provider = spec.split(":", 1)[0] if ":" in spec else ""
        if provider != "openai":
            raise RuntimeError(
                "RESEARCH_BASE_URL / RESEARCH_API_KEY are only supported with the "
                "openai provider — set RESEARCH_MODEL=openai:<model> (for an "
                f"OpenAI-compatible host like Groq/Together/OpenRouter). "
                f"Current RESEARCH_MODEL='{spec}'."
            )
        if base_url:
            params["base_url"] = base_url
        if api_key:
            params["api_key"] = api_key
    return params


def _provider(spec: str) -> str:
    """Provider that init_chat_model resolves `spec` to.

    An explicit prefix wins ("openai:gpt-4.1" -> "openai"); a bare "claude-*"
    name infers anthropic, matching init_chat_model's own inference.
    """
    if ":" in spec:
        return spec.split(":", 1)[0]
    return "anthropic" if spec.startswith("claude") else ""


def prompt_cache_control() -> dict | None:
    """Anthropic prompt-cache breakpoint to apply to model requests, or None.

    Returned as a top-level `cache_control` on the direct Anthropic API, which
    auto-caches the last eligible block of each request. Across the multi-turn
    research loop that means every step re-reads the cached system prompt and
    prior tool results at ~0.1x input cost instead of paying full price every
    turn. Only the Anthropic provider accepts the field, so it's gated on the
    provider; set RESEARCH_PROMPT_CACHE=0 to turn it off.
    """
    if os.environ.get("RESEARCH_PROMPT_CACHE", "1") == "0":
        return None
    if _provider(model_spec()) != "anthropic":
        return None
    return {"type": "ephemeral"}


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
