# PR 3 — The audit log keeps everything

## Goal

The durable audit log answers "what exactly ran, with what, producing what"
after the fact, while the in-memory trace shown in answers and on the dashboard
stays short.

## Scope

- `observability.RunLogger`: the JSONL sink receives each entry's full inputs
  and output, converted to JSON-safe values (dataclasses as dicts, datetimes as
  ISO strings, anything else as its string form). The in-memory `entries`, and
  so every trace returned by the agent, the workflow and the API, keep today's
  shortened form. The last line of a run is a summary record.
- The CLI's `agent` and `pipeline` commands gain `--audit-log PATH`, which
  appends the run's full log to `PATH`.
- Tests: a logged list longer than three items and a string longer than 240
  characters reach the sink whole; the trace in memory is unchanged; the
  summary line closes the run; each of the two CLI options writes the file.

## Non-goals

- No OpenTelemetry or other tracing backend (the marker at the logger stays).
- No log rotation or retention policy.

## Acceptance

```bash
uv run ruff check && uv run ruff format --check
uv run pytest
uv run sdf agent "should I reorder?" --audit-log "$SCRATCH/agent.jsonl"   # full entries in the file
uv run sdf pipeline --audit-log "$SCRATCH/pipeline.jsonl"                  # full step outputs in the file
```

## Version

`Version: MINOR 1.2.0 → 1.3.0` — the audit log's content changes and two CLI
commands gain an option.
