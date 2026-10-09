# Event-driven orchestration

Use `route.py --compact` for one substantial task. Small reads/edits stay in the
main session when delegation would cost more. The main model decomposes complex
work once; Python validates and schedules the DAG. No separate planner, classifier
LLM or watcher agent is required. The optional Laya backend remains available.

## Plan and reserve

Save a JSON list to a local plan file. For example:

```json
[
  {"step_id":"contract","description":"Define parser input and output contract","operation":"implementation","files":1,"ambiguous":false,"critical":false,"write_targets":["contract.md"],"acceptance":"Contract covers invalid input and output schema"},
  {"step_id":"reader","depends_on":["contract"],"description":"Implement the parser","operation":"implementation","files":1,"ambiguous":false,"critical":false,"read_targets":["contract.md"],"write_targets":["reader.py"],"acceptance":"Roundtrip and malformed input tests pass"},
  {"step_id":"cache","depends_on":["contract"],"description":"Implement bounded memory cache","operation":"implementation","files":1,"ambiguous":false,"critical":false,"read_targets":["contract.md"],"write_targets":["cache.py"],"acceptance":"Eviction and repeat-read tests pass"},
  {"step_id":"integration","depends_on":["reader","cache"],"description":"Test reader and cache together","operation":"implementation","files":1,"ambiguous":false,"critical":false,"read_targets":["reader.py","cache.py"],"write_targets":["test_integration.py"],"acceptance":"Integration suite passes and changes respect declared ownership"}
]
```

Use literal paths, declare all writes, and set `project_root` if not using the
current directory. `shared_resources` protects non-file resources; `isolation:
sequential` prevents simultaneous reservations. Unsafe unordered ownership is
rejected. Native worktrees still require verified support and actual host creation.
The same list supports one task when persistent tracking is useful.

```bash
python <skill>/scripts/scheduler.py init /tmp/run.json /tmp/tasks.json
python <skill>/scripts/scheduler.py next /tmp/run.json --capacity 2
```

`init` validates the whole graph but classifies **nothing**. `next` routes only
pending tasks with all dependencies `DONE`, within configured limits and the
**currently free** host slots passed as `capacity`. Zero capacity is valid. Count
other host agents when determining free slots. The scheduler also counts its own
outstanding reservations. It does not know other runs' reservations; one main
orchestrator must allocate host capacity across runs.
In Laya difficulty mode, `next` sends all tasks it routes in that cycle in one
batch request (at most 64 per request).

The response separates `dispatch` (new reservations) from `reserved` (outstanding
ones, IDs only except in `status`) and `tasks` (statuses). **Execute only newly dispatched tasks.** Follow
`needs_approval` and host confirmation exactly as for single tasks. An ordinary
choice can be justified using the router's structured reason without new prose:

```bash
python <skill>/scripts/justify.py <decision-id> auto
```

Existing sufficient user authorization may be recorded as `approved`; otherwise
ask for required authorization before recording that answer. Declines are recorded
as `declined`. Neither the scheduler nor this flag grants host permissions.

The dispatcher here is a handoff to native tools in the current session. Start the
independent returned tasks together. Use native completion events, not an LLM
watcher or a loop of model-generated status requests. The scheduler is an event
consumer, not a background daemon: invoke it when the host reports completion.

## Nested runs

A step may itself orchestrate: its executor runs `init`/`next`/`finish` on its own
run file (`/tmp/run-<step_id>.json`) and dispatches sub-subagents the same way,
with the same `justify`/`record`/`finish` protocol. The parent sees only that
step's `finish`, whose `changed_paths` must cover everything the child run
changed; `verify_changes` rejects paths outside the parent step's `write_targets`,
so every child `write_targets` stays inside them. The parent's `--capacity` does
not see the child's agents: reserve one slot for the sub-orchestrator and give the
child tasks a smaller `host_max_parallel`. Keep depth at two levels; each level
is its own context and the parent cannot observe the child, only its report.
`run_id` in every event keeps parent and child apart in the audit log.

## Validate and deliver completion

Review actual changes (including untracked files and deletions), verify ownership
and run the task's acceptance check **before** recording success. `verify_batch.py`
can check the plan and a complete map of actual changed paths. Never infer actual
changes from the plan alone. Keep integration tests as an explicit dependent task.

```bash
python <skill>/scripts/record.py <decision-id> success 300 4.2 --no-rework true
python <skill>/scripts/scheduler.py finish /tmp/run.json reader '{"decision_id":"<decision-id>","changed_paths":["reader.py"],"evidence":"/tmp/reader-tests.log","output_ref":"/tmp/reader-result.md"}'
python <skill>/scripts/scheduler.py next /tmp/run.json --capacity 1
```

Use actual returned IDs and actual metrics; omit unavailable numbers.
`evidence` is a bounded reference/description of the check the main host performed;
`output_ref` points to the artifact needed by dependents. Python checks the
recorded outcome, passed verification, complete task criterion and declared path
ownership. It does **not** run tests or prove that a caller-provided report is true.
Read-only tasks report `changed_paths: []`. False or premature success reports
must not be used to release dependencies.

A verified completion emits `task_completed`, moves to `DONE` and releases only
its dependents. There is no global wave barrier: a short branch can release its
next task while an unrelated slow branch continues. Repeating the same `finish`
is idempotent; stale IDs or changed completion reports are rejected.

For failure, first use `record.py ... failure --failure-kind <kind>`, then send
`finish` with just `{"decision_id":"..."}`. Failed tasks do not release dependents.
Retry diagnosis uses the existing policy and attempt limit:

```bash
python <skill>/scripts/scheduler.py retry /tmp/run.json reader '{"idempotent":true,"diff_verified":true}'
python <skill>/scripts/scheduler.py next /tmp/run.json --capacity 1
```

Assert idempotence and inspected diff only when true. Non-idempotent replay needs
existing explicit retry authorization. Context/permission/quota recovery needs
`recovery_confirmed: true` after resolution; unknown failures need diagnosis.
Fresh diff/recovery attestations are required per retry. The same task identity
and cumulative attempt count are preserved. A blocked decision cannot execute.
After refusal, `retry` requires the granted ceiling/allowlist and excludes the
refused candidate. A reservation is never timed out into automatic replay.

Before first classification, update a pending task's description and profile if
its prerequisites change the assessed difficulty:

```bash
python <skill>/scripts/scheduler.py update /tmp/run.json reader '{"description":"Implement parser using the verified v2 contract","files":3}'
```

Acceptance, dependencies and ownership stay fixed; create a new plan if those
change. Retries retain the original task profile, consistent with task history.
Only bounded dependency artifact references enter the routing description; read
relevant contents in the host and use `update` if semantic discoveries affect
classification. Full previous transcripts are never copied automatically.

## Recovery and audit

```bash
python <skill>/scripts/scheduler.py status /tmp/run.json
```

Run files contain task descriptions, acceptance checks and artifact references.
They are private (0600), written atomically and serialized with a local file lock.
Use local storage, omit secrets, and remove the run file and its `.lock` when no
longer needed. Audit history omits task descriptions and free-form validation
reports. A persisted outbox replays audit events by stable event identity after a
process interruption. `status` may flush this pending audit data.

`RESERVED` includes awaiting approval, running and awaiting validation. On a
restart, reconcile these with actual host agents; do not relaunch from `status`.
If an executor never started, preserve that evidence and record the actual failure
before an explicitly checked retry. An unknown execution outcome is not proof of
failure. A wrong success claim cannot be silently converted into a new attempt.

For detailed decision evidence, inspect the run file or omit `--compact` when
routing a standalone task. The old `route.py` JSON-list API remains a static
compatibility preview: it classifies the whole list and does not manage live
state. Use `scheduler.py` for lazy classification and completion-driven dispatch.

## Full-workflow efficiency

Execution tokens come from `record.py` outcomes, including failed and unfinished
tasks. Retry execution is counted once in `rework`; first execution is counted in
`execution`. Report cumulative, **disjoint** overhead measurements from the host:

```bash
python <skill>/scripts/scheduler.py usage /tmp/run.json '{"planning":120,"classification":0,"delegation":80,"validation":60}'
python <skill>/scripts/scheduler.py status /tmp/run.json
```

Numbers above are illustrative. Count bootstrap/context loading and decomposition
in planning; include final consolidation there too. Classification includes any
metered classifier work; zero is appropriate for the Python heuristic, while
unmeasured Laya consumption stays unknown. Count context transfer and dispatch
messages in delegation and main-session checking in validation. For retries, keep
planning/delegation/validation overhead in their respective phases. If a host
execution total already includes an activity, do not add it again as overhead.
Reasoning and cache subsets are never added again to the reported total.

The output reports `phase_tokens`, `known_tokens`, `missing_measurements`,
`total_tokens`, and `tasks_per_token = validated_tasks / total_tokens`. Missing
measurements make total/efficiency null; an unknown value is never zero. Update
cumulative overhead after all work, including consolidation. These are host
measurements, not inferred estimates; the router cannot meter the main model
itself. `routing_seconds` measures Python classification wall time separately.
Compare equivalent scopes and acceptance checks: splitting a task into more nodes
alone must not be interpreted as improved efficiency.

## Executor boundary

Classification and scheduling have no executor-specific command construction.
This implementation supplies a native-tool handoff for Claude Code and Codex.
An external `codex exec` / app-server adapter is **not implemented or launched**;
adding one requires explicit configuration of available model/effort combinations,
existing authentication, sandbox/approval semantics, cancellation, result/usage
parsing and outcome validation. It must not be a fallback that forces combinations
unavailable in the native session. No external integration was exercised by tests.
