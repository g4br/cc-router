---
name: cc-router
description: Route substantial tasks to available Claude Code or Codex subagents with configurable model and reasoning effort. Use for explicit model routing or resource-aware orchestration, including independent parallel tasks when the host permits delegation.
---

# cc-router

Do trivial reads/edits directly. Delegate only substantial work, and only where the
host permits it: this skill grants no delegation, model override or authorization.
Do not load references unless a step below says so.

## Before routing

```bash
bash <skill>/scripts/start_services.sh --check
```

Exit 0 means Laya is up. Otherwise ask the user whether to start it and wait; on yes
run `bash <skill>/scripts/start_services.sh`. On no, continue with the heuristic.
Never start Laya without that answer.

## Single task

Write one short English `description` (goal and acceptance criterion, no secrets),
then take the router's answer. Do not reason about, weigh or justify model or effort.

```bash
python <skill>/scripts/route.py --compact '{"description":"Implement parser and verify roundtrip tests","operation":"implementation","files":2,"ambiguous":false,"critical":false}'
python <skill>/scripts/justify.py <decision-id> auto
```

Use the skill's absolute path. Blocked choices cannot execute. Use `auto` only when
`needs_approval` is false; otherwise honor existing sufficient authorization or ask
the user and wait, then record `approved`/`declined`. `justify.py` stores the
router's own reason: write none.

## Delegate

```bash
python <skill>/scripts/brief.py '{"goal":"...","write_targets":["a.py"],"acceptance":"...","verify":"...","user_language":"pt-BR","decision_id":"<id>"}'
```

Send the printed brief as the whole prompt, with no conversation history, to the
returned `agent` (Claude: `subagent_type`; Codex: model/effort only if the tool
permits). The executor answers in the fixed `RESULT/FILES/CHECK/PENDING/TOKENS`
format plus `STEP`/`DECISION`. Verify by diff and by re-running `CHECK`, not by
re-reading unchanged files.

## Record

```bash
python <skill>/scripts/record.py <decision-id> success <tokens> <seconds> --no-rework true
```

Omit unknown metrics. On failure record `--failure-kind` and keep `task_id`.

## DAG

Read [scheduler](references/scheduler.md) only when a DAG is needed: tasks add
`step_id`, `depends_on`, `write_targets` and `acceptance`.

```bash
python <skill>/scripts/scheduler.py init /tmp/run.json /tmp/tasks.json
python <skill>/scripts/scheduler.py next /tmp/run.json --capacity 2
```

## References (read only when needed)

- [Protocol](references/protocol.md): approval, retries, escalation, refusal, brief/report, tokens per phase.
- [Scheduler](references/scheduler.md): completion, ownership re-check, efficiency.
- [Configuration](references/router-v2.md), [Examples](references/examples.md), [Laya](references/laya.md), [README](README.md) (Claude agents need `scripts/install.py`).

Host detection failures need `CC_ROUTER_OPERATOR=claude|codex`. Never bypass
restrictions or change credentials for a model. Unknown usage stays unknown.
