---
name: cc-router
description: Route substantial tasks to available Claude Code or Codex subagents with configurable model and reasoning effort. Use for explicit model routing or resource-aware orchestration, including independent parallel tasks when the host permits delegation.
---

# cc-router

Keep orchestration cheaper than the work it saves. Do trivial reads/edits directly.
For complex work, plan tasks, dependencies, ownership and acceptance checks; select
models only when tasks become ready. Follow host/project permissions: this skill
grants no delegation, model overrides or additional authorization.

Python reads configuration, catalogue and history. **Do not load references by
default.** Use short English `description` values for Laya, `user_language` for
reports, and only relevant context/artifact references for delegation.

## Before routing

```bash
bash <skill>/scripts/start_services.sh --check
```

Exit 0 means Laya is up. Otherwise ask the user whether to start it and wait for
the answer; on yes run `bash <skill>/scripts/start_services.sh` (the first run
downloads the checkpoint; relay its output). On no, continue: routing falls back
to the heuristic. Never start Laya without that answer.

## Single task

```bash
python <skill>/scripts/route.py --compact '{"description":"Implement parser and verify roundtrip tests","operation":"implementation","files":2,"ambiguous":false,"critical":false}'
python <skill>/scripts/justify.py <decision-id> auto
```

Use the skill's absolute path. Check `execution.status`, `failure` and
`needs_approval`. Blocked choices cannot execute. Use `auto` only without required
approval; otherwise honor existing sufficient authorization or ask and wait, then
record `approved`/`declined`. Structured reasons stay in the audit log; ordinary
progress needs only `[T2] model / effort — Executando`.

Delegate through native tools with goal, relevant context, permitted paths,
language, acceptance criterion, `decision_id` and (in a DAG) `step_id`; the
executor echoes them as `STEP`/`DECISION` so completions map back to the run. Claude uses returned `agent` as `subagent_type`;
Codex uses model/effort only if the tool permits them. `applied: false` is a proposal.
Verify actual diffs and acceptance checks, then record each attempt:

```bash
python <skill>/scripts/record.py <decision-id> success <tokens> <seconds> --no-rework true
```

Omit unknown metrics. `--no-rework true` means first attempt without corrections.
On failure, record `--failure-kind` and preserve `task_id`. Read
[protocol](references/protocol.md) for retries, refusal, host confirmation or
credential details. Never bypass restrictions or change credentials for a model.

## DAG orchestration

Read [scheduler usage](references/scheduler.md) only when a DAG is needed. Tasks
add `step_id`, `depends_on`, `write_targets` (`[]` for read-only) and `acceptance`;
declare relevant read paths/shared resources too.

```bash
python <skill>/scripts/scheduler.py init /tmp/run.json /tmp/tasks.json
python <skill>/scripts/scheduler.py next /tmp/run.json --capacity 2
```

Only `dispatch` contains new reservations. Apply approval checks per task and launch
independent reservations together. Use native completion events: validate, record,
send `finish`, then call `next` with currently free host capacity. Python releases
dependents only after verified `DONE`. No LLM watcher or model-driven polling.
Use `status` to recover; reconcile outstanding agents before any replay.
The scheduler hands off execution to native tools; it does not launch a Codex CLI.

## Conditional references

- [Scheduler](references/scheduler.md): completion, retries, context updates and
  efficiency = validated tasks / all workflow tokens, including overhead/rework.
- [Protocol](references/protocol.md): execution and recovery details.
- [Configuration](references/router-v2.md): catalogue, policy, migration and audit.
- [Examples](references/examples.md): extra commands.
- [Laya](references/laya.md): optional classifier setup/troubleshooting.
- [README](README.md): installation; Claude agents need `scripts/install.py`.

Missing/conflicting host detection needs `CC_ROUTER_OPERATOR=claude|codex`.
Model names never imply availability/billing. Unknown usage stays unknown;
do not claim savings from subagent tokens alone or invent measurements.
