---
description: 'Use when starting work on a change, bug fix, refactor, upgrade, or any modification request. Covers when to create a new branch, when to stay on the current branch, when to open a pull request before continuing, how to split a complex refactor into a sequence of independently verifiable PRs, and how to decide the version bump that ends every PR and plan.'
name: 'Branch and Pull Request Workflow'
applyTo: '**'
---

# Branch and Pull Request Workflow

When the user asks for a code change, feature, fix, refactor, upgrade, or any modification, decide where to do the work by checking the current branch state **before** editing files.

## Decision Order

Check these conditions in order and stop at the first match:

1. **User explicitly opts out.** If the user says they do not want a new branch or PR (for example "just edit on main", "no PR needed", "直接改", "不用开 PR"), honor that and work wherever they indicate.

2. **Current branch already has an open PR.** Continue working on the current branch. Do not create a new branch. Push follow-up commits to the same branch so they land on the existing PR.

3. **Current branch is ahead of the default branch but has no PR yet.** Open a PR for the current branch against the default branch first, then continue working on the same branch. New commits will land on the newly opened PR.

4. **Default case (current branch is the default branch, or is in sync with it, or none of the above apply).** Create a new branch off the default branch, make the change there, and open a PR when the change is ready to share.

## Practical Rules

- Determine the current branch and its PR status before making code changes, not after. Use the repository's PR metadata (for example `currentActivePullRequest`) or `git` commands to check.
- Name new branches descriptively for the change (for example `feat/...`, `fix/...`, `docs/...`, `refactor/...`).
- Do not commit directly to the default branch unless case 1 applies.
- When case 3 applies, do not silently keep committing without a PR; open the PR first so the work is reviewable.
- When case 2 applies, do not open a second PR for the same branch.
- If it is unclear whether an existing branch is "ahead but unpushed" versus "already has a PR", prefer checking remote state before deciding.

## Version bump

Every PR, and every PR plan file created or updated after this rule landed, ends
with a version decision. Make it after the change is complete, when its real
extent is known, and apply it as the last change before requesting review. If
review fixes change the PR's extent, re-evaluate the decision after the last fix,
immediately before the merge, and update the bump and the `Version:` line when the
outcome changed. The package version is `[project].version` in the root
`pyproject.toml` and in every workspace member under `packages/`, kept identical
(lockstep); a bump changes all of them in the same PR, with
`uv version --bump <kind>` followed by `uv version --bump <kind> --package <member>`
for each member, and the documentation build refuses drift. Record the decision and its
one-sentence reason as the last section of the plan file (**Version**) and as a
`Version:` line at the end of the PR description. Earlier plan files keep their
recorded sections; add a **Version** section only when such a plan is next updated.

Choose exactly one outcome. Judge it by what the change does to code that ships
in a distribution (`src/`, `packages/*/src/`) and to the interfaces documented on
the public site. Whether any version has been tagged or released is not a
criterion; "nothing is released yet" is never a reason to skip a bump.

- **MAJOR** — requires explicit human approval. Propose the bump with its reason
  (for example a breaking change to the public author API, the semantic IR or JSON
  contract, or serialization output) and wait for the answer before committing it.
  Never bump MAJOR on your own judgment.
- **MINOR or PATCH** — decide yourself from the extent of the change to shipped
  code: MINOR for new capability, a new distribution or import path, or a change
  an author or contributor would notice; PATCH for fixes and contained changes.
- **None** — the change does not touch shipped code: documentation, instructions,
  plans, tests, tooling, reference data, comments. Leave `[project].version`
  unchanged and record `none` with the reason.

Write the decision as `Version: MINOR 0.1.0 → 0.2.0, <reason>` or
`Version: none, <reason>`. A bump alone does not create a release; release tags
follow `website/docs/developer/publication.md` and must equal the plain
`[project].version`, so never write a `-` or `+` suffix into it.

## Splitting a Complex Refactor

Treat a change as a **complex refactor** when any of these hold:

- it touches more than one layer (data pipeline, API, frontend, documentation);
- it moves or renames files that other files reference by literal path or literal string;
- its diff would mix mechanical moves with behavior changes;
- it cannot be reviewed in one sitting;
- it would leave the repository failing its own checks partway through.

For these, decide the PR sequence **before editing any file**. Do not open one branch, start changing things, and look for the seams afterward — by then the diff is already entangled.

### Plan first, in the repository

Record the plan under `docs/refactor/<refactor-slug>/` before implementation:

- `00-overview.md` — why the refactor exists, the decision with alternatives and consequences, explicit non-goals, and the ordered list of planned PRs.
- one plan file per planned PR, each with **Goal**, **Scope**, **Non-goals**, **Acceptance** and, last, **Version** sections (see [Version bump](#version-bump); plans that predate that rule gain the section when next updated). Follow the plan-filename convention in `repository-doc-boundaries.instructions.md`; documentation validation enforces it.

If the user requests a complex refactor without a plan, propose the split and get agreement before writing code.

### API and interface examples are part of the plan

When a refactor or plan designs or changes an API/interface, its design document
under `docs/` must include concrete example code before implementation begins.

- Show exact imports, names, signatures, typical calls and expected results. For
  an extension interface, also show a minimal implementation of that interface.
  Prose such as "provide a common interface" is not a substitute for examples.
- Identify one authoritative interface contract. Every affected PR plan must link
  to it rather than independently redefining names, parameters or return types.
- Label current, target and intermediate interfaces, and identify the PR after
  which each example becomes runnable. Do not describe unimplemented examples as
  already executed or supported.
- If implementation changes the agreed interface, update the contract examples,
  affected stage plans and callers in the same PR. Later PRs must use the revised
  contract rather than an obsolete example.
- Once the relevant interface exists, verify the examples with executable examples
  or focused tests. Include that verification in the implementing PR's acceptance.
  Follow the example-output documentation rules for runnable learning examples.

### Requirements for every PR in the sequence

1. **One stated purpose.** The title names a single outcome. If stating the goal requires "and", it is probably two PRs.
2. **Independently verifiable.** Each PR lists its own acceptance commands in its plan file and leaves the repository's test suite and validation checks passing when it merges. A PR that only turns green after a _later_ PR is not independently verifiable — merge it with that PR, or reorder the sequence.
3. **Independently reviewable.** Someone reading only this PR and its plan file should understand what changed and why, without reading the rest of the sequence. "Part 2 of the refactor" is not a description.
4. **Independently revertible.** Reverting one PR must not break the PRs that landed before it.
5. **No mixing of mechanical and semantic change.** A pure move/rename is one PR; a behavior change is another. But when a move breaks literal-path or literal-string references, update those references **in the same PR that moves the files** — never split a move from the reference updates it invalidates.
6. **Interface consistency.** Check implementation and callers against the linked
   authoritative code examples, and run the interface checks required by that
   stage. Update the contract in the same PR if its design changes.

### Ordering

Order the sequence so the repository stays green at every step. Prefer **introduce the new form → migrate the call sites → remove the old form**; never remove first.

Per `in-branch-api-compat.instructions.md`, do not add compatibility shims, aliases, or adapter layers merely to keep an intermediate PR green. If a step cannot be made green without a shim, the sequence is ordered wrong — reorder it.

### Sequential review and squash-merge gate

For every ordered multi-PR plan, process one PR at a time using this fixed sequence:

**review → address feedback → squash merge → begin the next PR**

The current PR is a hard gate for every later PR in the plan. Do not create the next implementation branch, start its changes in another worktree or session, or otherwise develop later stages in parallel while the current PR is open.

Before the gate may advance:

1. Finish the current PR's stated scope, run its acceptance checks, then make and apply the version decision (see [Version bump](#version-bump)) as the last change.
2. Push the complete change and wait for required CI and configured human or automated review. Passing CI alone does not complete the review gate.
3. Inspect every review surface: submitted reviews, inline review threads, and general PR comments.
4. Address every actionable comment with a code or documentation change and regression coverage where appropriate. If a suggestion should not be implemented, reply with a concrete technical reason instead of silently ignoring it.
5. Push the follow-up commits, wait for the checks on the latest head commit, reply to each handled thread, and resolve it. Recheck that no new or unresolved review thread remains. If the fixes changed the PR's extent, re-evaluate the version decision (see [Version bump](#version-bump)) before merging.
6. Squash-merge the PR. Confirm the remote PR state is `MERGED`; a local worktree warning is not evidence that the remote merge failed. Nothing is written back after the merge.
7. Fetch the merged default branch, then create the next PR's branch or worktree from that updated default branch. Never base the next stage on the unmerged predecessor branch.

Keep every later plan item pending until the preceding PR has passed this complete gate. If review requests changes or the latest checks fail, remain on the current PR and fix it; do not advance the sequence. A separately submitted refactor-plan PR is subject to the same gate before PR1 starts.

## Anti-patterns

- Creating a new branch when the user is already on a branch with an open PR for the same piece of work.
- Committing to the default branch for a non-trivial change without asking.
- Pushing follow-up commits to a feature branch that is ahead of main without ever opening a PR for it.
- Opening a new PR for in-progress follow-up work that belongs on an already-open PR.
- Starting a multi-layer refactor and only discovering the PR boundaries after the diff is already entangled.
- Landing a rename in one PR and its reference updates in another, leaving the default branch red in between.
- Bundling a mechanical move with a behavior change so a reviewer cannot tell which lines actually changed meaning.
- Splitting by file or by commit count rather than by verifiable outcome, producing PRs that individually mean nothing.
- Starting, branching or implementing a later planned PR before its predecessor is remotely confirmed as merged.
- Treating green CI as a substitute for waiting for and auditing review feedback.
- Merging while actionable comments or unresolved review threads remain.
- Advancing from a local branch state without confirming the remote squash merge and updating from the default branch.
- Bumping MAJOR without explicit human approval, or bumping PATCH for a change that does not justify it.
- Finishing a PR or plan file without a recorded version decision.
- Skipping a bump for a change to shipped code because no version has been tagged yet.
