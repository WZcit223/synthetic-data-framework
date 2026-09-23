# CLAUDE.md

Claude Code entry point for this repository.

## Read this first

[`AGENTS.md`](AGENTS.md) is the authoritative instruction file for this
repository. Read it in full before starting work. This file only routes to it and
records Claude Code specifics; it does not restate or override it. If the two ever
disagree, `AGENTS.md` wins.

## Claude Code specifics

- Claude Code does not load the instruction files under
  [`.github/instructions/`](.github/instructions/) automatically. `AGENTS.md`
  requires them: read every applicable file yourself, using its `applyTo` and
  `description` to decide scope, and recheck when the task expands to new files
  or activities.
- Confirm the shell your Bash tool actually runs before relying on heredocs.
  Claude Code cloud sessions run `bash`; the project lead's local shell may
  differ. Prefer the Write and Edit tools over shell redirection for file content.
- The package is not installed by default. Either run `pip install -e ".[dev]"`
  once per session, or prefix commands with `PYTHONPATH=src` as the README does.
  The required checks are listed in `AGENTS.md` under "Required checks".
- Keep scratch files in the session scratchpad directory, never in the
  repository tree; `out/` and `*.csv` outside `data/` are gitignored but still
  should not be created inside the checkout.
- Follow the repository's PR template (`.github/pull_request_template.md`) and
  pick the correct track from `CONTRIBUTING.md`. A large refactor or a new core
  component is a directional PR: write the plan first, do not enable auto-merge,
  and end the description with the `Version:` line the branch and PR workflow
  requires.
- Do not put model names or model identifiers into commit messages, PR titles or
  bodies, code comments, or any other repository artifact.
- When a PR you opened receives bot review findings, verify each one against the
  code before acting; fix what is real, reply once with a concrete reason on what
  is not, and resolve the thread either way.
