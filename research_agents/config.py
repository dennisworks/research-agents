"""Runtime configuration resolved from environment variables.

The only required keys are the two API keys (ANTHROPIC_API_KEY, TAVILY_API_KEY);
everything else has a sensible default, so an out-of-the-box run writes articles
to a local directory with no backend to configure.
"""

import os

DEFAULT_MODEL = "claude-opus-4-8"
DEFAULT_OUTPUT_DIR = "output"


def model() -> str:
    """Claude model used for both the research and writing stages."""
    return os.environ.get("RESEARCH_MODEL", DEFAULT_MODEL)


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
