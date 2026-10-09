# Native execution usage: Codex and Claude Code

Use host transcripts to collect the model, effort and token counters actually
reported for a routed execution. No provider API, additional model call, login
change or agent execution is involved. Collection does not assert task success.

## Execution identity

Generate the delegation prompt with `brief.py`, which adds
`CC_ROUTER_DECISION: <decision-id>`. Retain the native agent ID returned by the
host. A router candidate such as `exec-sol-medium` is **not** a native agent ID.

The collector requires the marker in a user input to the executor, checks the
native thread/subagent identity and excludes parent transcripts. An assistant's
`TOKENS`, `DECISION` or completion prose is never measurement evidence. Delegate
one attempt per child; route retries with a new decision ID. Reused Claude agents
containing several decision markers are rejected. Codex can select a marked turn
explicitly with `--turn-id` when a thread has multiple matching turns.

## Codex

After the child finishes and the orchestrator verifies the result:

```bash
CC_ROUTER_OPERATOR=codex python scripts/record.py <decision-id> success --agent-id <native-thread-id> --no-rework true
```

Discovery searches `$CODEX_HOME/sessions` and `archived_sessions`, defaulting to
`~/.codex`. Exactly one filename must match the native thread ID, and its internal
identity must agree. There is no “latest session” guess. If necessary, supply
`--transcript /absolute/path/rollout.jsonl` and `--turn-id <native-turn-id>`.

The adapter reads runtime `turn_context.model` and `effort`, and deduplicates
`token_usage_record` by response ID. The turn ID scopes counters to the delegated
turn; inherited parent totals are not charged to the child. Older rollouts with
only `token_count` use cumulative differences with a checked baseline. Counter
resets, unfinished turns, model changes within a turn and ambiguous attribution
are rejected. A host-reported model ID is not proof of an undisclosed backend
version or server-side substitution; provenance remains attached to the result.

For a separate collection step before verification:

```bash
CC_ROUTER_OPERATOR=codex python scripts/usage.py <decision-id> --agent-id <native-thread-id>
# Inspect diff and run acceptance checks, then:
CC_ROUTER_OPERATOR=codex python scripts/record.py <decision-id> success
```

## Claude Code

For an already installed skill, activate just the usage hook:

```bash
python scripts/usage.py --install-claude-hook
```

This preserves existing settings and saves a timestamped backup before changing
them. It does not regenerate agents or change the routing backend. The existing
full installer also includes the hook:

```bash
CC_ROUTER_OPERATOR=claude python scripts/install.py
```

It preserves existing settings and registers an idempotent `SubagentStop` command
hook for `exec-` agents. The hook reads `agent_transcript_path`, verifies
`agent_id`, finds the router marker, and appends a `host_usage` observation.
Unrelated agents are ignored. Hook failures produce an error instead of inventing
metrics; they never mark a task successful or request that an agent continue.
Follow the host's hook reload requirements for the current session.

After checking the actual work, the ordinary result command consumes that observation:

```bash
CC_ROUTER_OPERATOR=claude python scripts/record.py <decision-id> success --no-rework true
```

Without the hook, `record.py ... --agent-id <native-agent-id>` collects directly.
Discovery searches `$CLAUDE_CONFIG_DIR/projects`, defaulting to `~/.claude`, for
`agent-<id>.jsonl`; `--transcript` overrides discovery. Wait for the agent to finish.
The transcript supplies `message.model`, `perTurnEffort` (or `effort` when the
per-turn value is absent), and `message.usage`. Missing effort stays null.
Repeated streaming blocks with the same message ID count once, retaining the
largest reported output counter. Conflicting input counters are rejected.

## Normalized metrics and evidence

- `input_tokens` includes all input, including cache reads and writes. For Claude,
  this is `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`.
  Codex already includes cache in its input total.
- `total_tokens = input_tokens + output_tokens`. Reasoning output and cached input
  are subsets; neither is added again. Cache writes are also exposed separately.
- Missing fields remain null. An incomplete Claude cache breakdown leaves total
  input and total tokens unknown rather than reporting an artificially low cost.
- The transcript timestamp span supplies duration with
  `duration_source: transcript_timestamps`; it is not provider compute time.
- Multiple Claude model/effort pairs remain in `execution_segments`; scalar
  model/effort and candidate are null for mixed executions. `telemetry.py` exposes
  these segments in `native_executions` without adding their tokens twice.
- `effective_candidate` is set only for a unique model/version and effort match,
  or when Claude reports a configured `agent_type` with the observed effort.
  An unknown candidate never gets replaced with the intended one.

`usage.py` stores measurements separately from outcomes. Repeated identical
collection is a no-op; updated snapshots for the same execution can replace the
observation used by `record.py` until a result exists. Different executions require
different attempts. Per-decision locks prevent concurrent result commands from
recording the same attempt twice. A native observation cannot be mixed with manual
model/token flags. Approval and verification checks still apply to results.

History stores counters, runtime identifiers, provenance and a transcript SHA-256;
it does not copy prompts, outputs, source code, absolute transcript paths or
credentials. Transcript parsing is read-only. Neither adapter measures parent
planning, delegation or validation tokens; report those phases separately.

If local transcripts are unavailable, the existing manual host-report flags still
work. Do not substitute the routing proposal or assistant estimates for evidence.
Older results are not retroactively rewritten. For observational selection, set
the candidate's `resolved_model` from verified host evidence and collect the
required comparable samples; collection does not auto-change model configuration.

## Sources and compatibility

The adapters use local JSONL formats observed in this environment, which can
change between host releases. Unsupported shapes fail visibly; fixtures cover
the supported contracts. Official documentation describes
[Codex usage notifications](https://learn.chatgpt.com/docs/app-server),
[Claude SubagentStop fields](https://code.claude.com/docs/en/hooks#subagentstop),
and [Claude cache accounting](https://platform.claude.com/docs/en/build-with-claude/prompt-caching#tracking-cache-performance).
