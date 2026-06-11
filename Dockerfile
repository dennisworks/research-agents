# Production image for the VPS cron job. Run as:
#   docker run --rm --env-file .env research-agents
# Optional args pass through to main.py, e.g.:
#   docker run --rm --env-file .env research-agents --topic "test" --dry-run
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY research_agents/ research_agents/
COPY prompts/ prompts/
COPY main.py ./

ENTRYPOINT ["uv", "run", "--no-sync", "python", "main.py"]
