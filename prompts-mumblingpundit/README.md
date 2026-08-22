# mumblingpundit run prompts

Fallback prompt tree for the **mumblingpundit** backend. It is selected by a
**bind mount**, not by `--env-file`: the daily/poller invocations pass
`-v .../prompts-mumblingpundit:/app/prompts` (and it's the poller's second
positional arg). `--env-file` alone only loads env vars — without the bind mount
a run uses the baked-in dennisworks `prompts/`. Resolution order and file format
are identical to `../prompts/README.md`.

mumblingpundit's real briefs come from its **own backend queue**
(`/api/research/prompt`, fed from the admin UI), which is resolved *before* any
local file. This directory exists only so an empty-queue day still has a
punditry-voiced fallback (`default.md`) — never the neutral dennisworks default.
Keep `default.md` in mumblingpundit's opinion voice.
