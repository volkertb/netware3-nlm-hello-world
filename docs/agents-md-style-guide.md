# Maintaining AGENTS.md / docs/

Guidelines for keeping `AGENTS.md` (symlinked as `CLAUDE.md`) and `docs/` effective, based on
current (2026) community best practices for agent context files.

## Keep AGENTS.md itself short

It's loaded into every session regardless of task, so it costs context budget even when irrelevant.
Target well under 200 lines — the best-performing files researchers found across public repos were
20-30 lines and stayed specific. If a section grows past a few bullets, that's the signal to move it
to a `docs/*.md` file and leave a link, not to keep expanding it in place.

## Progressive disclosure, not a knowledge dump

`AGENTS.md` should answer three questions and stop: **what** the project is, **why** its non-obvious
components exist, and **how** to build/test/verify it. Anything longer than that — stage-by-stage
rationale, historical debugging context, full option references — belongs in a linked `docs/*.md`
file that only gets read when actually relevant, not paid for on every turn.

## Only write what isn't already obvious from the repo

Don't restate what a reader (human or agent) can get for free from the code, `git log`, or
`git blame` — that content has been shown to measurably hurt rather than help. The value of these
files is capturing things that *aren't* derivable by reading the repo: hard-won "we tried X, it
failed because Y" context, non-obvious constraints, and house rules that aren't enforced by a linter.

## Write rules as direct commands, not prose suggestions

Prefer "never name a specific coding agent in a committed `.devcontainer/` file" over "we generally
try to keep things agent-neutral." Imperative phrasing (and `IMPORTANT:`/`YOU MUST` for the rules
that matter most) gets followed measurably more reliably than hedged, descriptive language.

## Treat it as a living document, not a one-time writeup

Revisit these files when a mistake repeats — that's the signal a rule is missing or unclear, not a
reason to just fix the instance and move on. Equally, prune rules that stop being relevant (a
constraint tied to a workaround that's since been removed, etc.) rather than letting them accumulate
indefinitely.

## Never commit secrets or internal-only detail

No credentials, tokens, connection strings, or infrastructure detail that shouldn't be public — these
files are regular tracked repo content, not a private scratchpad.

## Sources

- [Writing a good CLAUDE.md — HumanLayer](https://www.humanlayer.dev/blog/writing-a-good-claude-md)
- [Best practices for Claude Code — Claude Code Docs](https://code.claude.com/docs/en/best-practices)
- [AGENTS.md Spec (2026) — morphllm](https://www.morphllm.com/agents-md-guide)
- [Using CLAUDE.md files — Anthropic](https://claude.com/blog/using-claude-md-files)
