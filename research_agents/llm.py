"""Shared LLM plumbing for the research graphs.

Both the article pipeline (agent.py) and the shows pipeline (shows.py) need the
same two primitives: build the configured chat model, and flatten Claude's
message content down to plain text. They live here so a second graph can reuse
them without importing another graph's internals.
"""

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from . import config


def _install_hint(spec: str) -> str:
    """How to get the provider for `spec` installed, for the error below."""
    if ":" not in spec:
        return (
            "Give RESEARCH_MODEL a provider prefix (e.g. 'openai:gpt-4.1') and install "
            "that provider's extra — see the README 'Using a different model'."
        )
    provider = spec.split(":", 1)[0]
    extra = config.PROVIDER_EXTRAS.get(provider)
    if extra:
        return f"Install it with `uv sync --extra {extra}` (or `pip install 'research-agents[{extra}]'`)."
    pkg = "langchain-" + provider.replace("_", "-")
    return f"Install the LangChain integration for '{provider}' (e.g. `pip install {pkg}`)."


def make_llm() -> BaseChatModel:
    """Build the chat model named by RESEARCH_MODEL, applying the shared
    generation params and (for Anthropic) the prompt-cache breakpoint."""
    spec = config.model_spec()
    params = config.model_params()
    cache_control = config.prompt_cache_control()
    if cache_control is not None:
        # Merge into model_kwargs so it rides on every request as a top-level
        # `cache_control` (Anthropic auto-caches the last eligible block). Every
        # research/extraction call goes through here, so every call caches.
        params["model_kwargs"] = {
            **params.get("model_kwargs", {}),
            "cache_control": cache_control,
        }
    try:
        return init_chat_model(spec, **params)
    except ImportError as e:
        # init_chat_model imports the provider package lazily. Surface the real
        # error (it may be an unrelated import failure) and add an install hint
        # when we recognize the provider.
        raise RuntimeError(
            f"Could not load the model provider for '{spec}': {e}\n{_install_hint(spec)}"
        ) from e


def text_of(content) -> str:
    """Flatten a message's content to text. Claude message content can be a
    string or a list of content blocks."""
    if isinstance(content, str):
        return content
    return "\n".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )
