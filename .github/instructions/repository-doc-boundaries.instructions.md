---
description: "Use when creating, editing, or reorganizing repository documentation, especially README.md, ARCHITECTURE.md, or AGENTS.md. Keep README focused on user-facing purpose, usage, and examples, and move developer-facing structure, architecture, and workflow guidance into the dedicated developer docs."
applyTo: "**/{README,ARCHITECTURE,AGENTS,CONTRIBUTING}.md,docs/**,website/**"
---

# Repository Documentation Boundaries

Keep `README.md` user-facing and keep developer guidance in the dedicated docs this repo already uses.

- Public handbooks (including the Developer Guide), API references and learning
  pages live in `website/docs/`. Website configuration, theme and tools live
  alongside them in `website/`; generated outputs go in ignored `website/.build/`.
- Internal architecture, design decisions and refactor plans live in root `docs/`.
  AutoSuite evidence documentation stays in `autosuite/docs/`. Do not copy these
  internal trees into the public site. Root Markdown is limited to `README.md`
  and `AGENTS.md`.

- Step 1: Put user-first content in `README.md` (purpose, audience, install, quick start, CLI/API usage, concise examples).
- Step 2: Put agent workflow rules in `AGENTS.md`, public contributor guidance in
  the website's Developer Guide, and internal model/component design in `docs/`.
- Step 3: If `README.md` starts accumulating deep architecture detail or
  contributor-only guidance, move it to the appropriate location above and leave
  a short link in `README.md`.
- Keep these docs in sync with the code they describe: when an entry point, config field, or data convention changes, update the affected doc rather than letting it drift.
