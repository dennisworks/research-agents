# mumblingpundit run prompts

Fallback prompt tree for the **mumblingpundit** backend, mounted at
`/app/prompts` when the container runs with `--env-file .env.mumblingpundit`.
Resolution order and file format are identical to `../prompts/README.md`.

mumblingpundit's real briefs come from its **own backend queue**
(`/api/research/prompt`, fed from the admin UI), which is resolved *before* any
local file. This directory exists only so an empty-queue day still has a
punditry-voiced fallback (`default.md`) — never the neutral dennisworks default.
Keep `default.md` in mumblingpundit's opinion voice.
