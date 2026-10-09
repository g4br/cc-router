
# cc-router v2

Route each substantial step through `scripts/route.py`. Keep approval and verification in the main session; use `scheduler.py`
for completion-driven DAG orchestration. The router proposes a candidate; it does not
execute it or prove that the host applied its model and effort. Follow host,
project, sandbox and delegation policies. This skill grants no additional permissions.

Use the user's language for reports. Classification costs no LLM tokens: at
decomposition the orchestrator writes **one** short, faithful **English**
`description` per task (constraints and verification criteria kept; secrets and
unnecessary source code omitted), then takes `route.py`'s answer. It never reasons
about, weighs or justifies model or effort in free text. `user_language` is returned
to the orchestrator and is never sent to Laya.

Read [README.md](../README.md) for installation and configuration. Read
[references/router-v2.md](router-v2.md) for schema, policies, migration,
telemetry and limits; [references/examples.md](examples.md) for commands
for both hosts; [references/laya.md](laya.md) for the optional local service.

## Host and configuration

`CC_ROUTER_OPERATOR=claude|codex` overrides session detection. Otherwise Codex uses
`CODEX_THREAD_ID`/`CODEX_SESSION_ID`, Claude uses `CLAUDECODE`/`CLAUDE_CODE_REMOTE`;
conflicting or missing markers are errors. Credentials never identify the host.

Configuration precedence: `CC_ROUTER_CONFIG`, then `config/router.json` if present,
then `config/ladder.json`. Legacy configuration is migrated **in memory** without
changing the file. Models, effort strings, capabilities, consumption tiers and
approval rules come from configuration. No model family implies availability,
quality, subscription inclusion or supported effort. A missing host is an error;
never use the other host's candidates as a fallback.

Codex uses its native subagent tool; `agent` is a logical routing identifier.
Claude Code uses generated agents: run `scripts/install.py` after changing the
catalogue, then use the returned `agent` as `subagent_type`. Existing native
permissions and approval prompts still apply. Check the model and effort exposed
by the session before delegating. Configure unavailable combinations as unavailable
or block them in the next routing request.

## Per-step protocol

1. Decompose into steps with objective verification criteria. Do trivial reads and
   tiny edits directly. Delegate only where the benefit exceeds context transfer
   and startup costs and the host permits it.
2. Build and validate a task state, then route it:

   ```bash
   python <skill>/scripts/route.py '{"description":"Add HTTP timeout handling and verify retry tests","user_language":"pt-BR","operation":"implementation","files":2,"ambiguous":false,"critical":true}'
   ```

3. Check `execution.status`, `failure`, `excluded`, `needs_approval`, and batch
   `scheduling`. A blocked decision has no selected candidate: resolve the stated
   cause before routing again. Proposed settings have `applied: false` until the
   native host reports their execution. Unknown billing requires explicit review
   of subscription inclusion; external billing is excluded from v2 execution.
4. The router's structured `reason`, `evidence` and `nearest_alternative` stay in
   the audit log; `justify.py` records that reason itself, so the orchestrator
   writes no rationale. When approval is required or requested, show the user the
   router's `reason`, `nearest_alternative` and consumption data as returned;
   ordinary progress needs only task/model/effort/status. `below` remains a legacy
   display field. Do not invent model behavior, monetary savings or a probability
   from an uncalibrated Laya score.
5. For `needs_approval: false`, log `auto` and proceed within existing authority.
   Otherwise check whether existing user authorization already covers this
   choice. If it does not, present the choice, known consumption information and
   permitted alternative, then ask and wait before delegating. Approval of a model never authorizes dangerous operations or paid
   credentials. Without a way to obtain required approval, leave the step pending.

   ```bash
   python <skill>/scripts/justify.py <decision-id> auto
   ```

   With no text argument, `justify.py` stores the decision's own `reason`
   (hashed in v2 history). Do not pass free text.

   Use `approved` or `declined` for the user's answer. On refusal, route a new
   decision with the same `task_id` and the granted `user_ceiling` or explicit
   `allowed_candidates`. Do not seek another mechanism to run a refused candidate.
6. Delegate natively with the fixed brief from `scripts/brief.py` (see
   [Brief and report](#brief-and-report)). Claude: use the generated agent, without
   overriding its model. Codex: pass returned model/effort only if the native tool
   supports them in this session. Never use a secondary CLI, API key, paid proxy or
   `codex exec` to force an unavailable combination.
7. Verify the result in the main session: check the actual diff and re-run the
   report's `CHECK`; do not re-read unchanged files. A subagent's completion report
   alone is insufficient. Obtain the actual
   model, resolved version, effort and metrics from the host if exposed; otherwise
   leave them unknown. Host substitution must be disclosed and recorded faithfully.
8. Record one result per attempt:

   Prefer [native usage collection](native-usage.md): retain the child ID from
   delegation and use `record.py <decision-id> success --agent-id <native-id>`.
   Claude's installed stop hook collects automatically; ordinary `record.py`
   consumes its observation. Collection never replaces the verification in step 7.
   The manual metrics form remains available when native transcripts are unavailable:

   ```bash
   python <skill>/scripts/record.py <decision-id> success 48210 37.5 --no-rework true
   ```

   Omit unavailable tokens/duration. `success` asserts passed verification;
   `failure` and `escalated` do not complete the task. Use `--task-complete false`
   when a successful attempt has not completed the task criterion. Add
   `--host-confirmed --effective-candidate <id> --resolved-model <reported-version>`
   and `--effective-effort <reported-effort>` only from actual host reporting.
   `--no-rework true` is only for a first attempt with no corrections. Correct a
   later-discovered label with `feedback.py <decision-id> false`.
   Optional per-phase tokens: `--phase-tokens planning=1234 delegation=80 ...
   --tokens-source host|estimated` (see [Tokens per phase](#tokens-per-phase)).

## Brief and report

`scripts/brief.py '<task json>'` prints the whole prompt for the executor: one-sentence
goal, owned files (`write_targets`), acceptance criteria, verification command,
report language, a `STEP`/`DECISION` echo instruction and the report format below. It
carries no conversation history. Fields: `goal`, `write_targets`, `acceptance`,
`verify`, `user_language`, `decision_id`, optional `step_id`. Over `brief_max_words`
(default 250) it warns on stderr and logs a `brief_overflow` event, but still prints.

Generated Claude agents (run `scripts/install.py` after upgrading) carry the same
format in their system prompt; at most `report_max_lines` (default 15) lines:

```
RESULT: done|failed|blocked
FILES: <changed paths>
CHECK: <command> -> <result>
PENDING: <items or none>
TOKENS: <host-reported or unknown>
STEP: <step_id or none>
DECISION: <decision_id>
```

A step too ambiguous or hard for its configuration reports `blocked` with the reason in
`PENDING`. The orchestrator verifies by the diff and by re-running `CHECK`.

## Failure handling

Record a structured `--failure-kind`; do not classify from unreliable free text.
Reuse `task_id`, `failed_with` and the original criterion when routing a retry.
Existing task history supplies prior attempts; do not reset its count.

| Failure | Required response |
|---|---|
| `transient_host` | Controlled recovery with the same candidate |
| `rate_limit` | Stop or reschedule; retain existing authentication |
| `permission_denied` | Stop and request authorization through the host |
| `missing_context` | Obtain missing context before another attempt |
| `syntax_or_local_fix` | Local correction with the same candidate |
| `verification_failed` | Route again: the router climbs exactly one difficulty level |
| `design_or_reasoning_failure` | Route again: the router climbs exactly one difficulty level |
| `unavailable_model_or_effort` | Exclude unavailable candidate and route again |
| `unknown` | Inspect the failure; no automatic retry or promotion |

Retries require `idempotent: true` or explicit `retry_approved: true`, plus
`diff_verified: true` after inspecting the actual worktree and any applied patch.
After quota recovery, supplied context or an actual permission grant, set
`recovery_confirmed: true` to resume the same candidate with the same retry checks.
This flag records an external resolution; it never grants host permissions.
A dirty tree alone never authorizes replaying a patch. `max_attempts` defaults to 3.

**Economic escalation.** After `verification_failed` or `design_or_reasoning_failure`
the retry goes exactly one difficulty level up (`difficulty.level_for_rung` /
`level_candidates`), or one ladder rung when the host has no `level_to_candidate`
map or the failed rung is already at the top level. It never jumps; if no eligible
candidate exists at that step, routing fails visibly instead of picking another rung.
Environment/tool/infrastructure kinds (`transient_host`, `syntax_or_local_fix`, and
recovered `rate_limit`, `permission_denied`, `missing_context`) retry on the same
rung, at most `max_same_level_retries` times (default 2), then stop with
`same_level_retry_limit`. Every escalation adds an `escalation` object to the
decision event (`kind`, `from_level`, `to_level`, `from_candidate`, `to_candidate`);
it is the training label for the fine-tuning phase. `escalation_jump` is used only by
the legacy `limits` helper in `route.py`.
`failed_with` alone is accepted for compatibility but produces a diagnostic stop;
it does not silently jump two rungs. Never weaken verification to call a retry successful.

## Static compatibility batches

For live, lazy classification use [the scheduler](scheduler.md). The following
JSON-list interface preserves the earlier static preview contract.

Pass a JSON list. Declare `write_targets` (legacy alias `targets`) on every step;
`[]` means read-only. Optionally add `step_id`, `depends_on`, `read_targets`,
`shared_resources`, `isolation` and `host_max_parallel`. Paths are relative to
`project_root` (default current directory), normalized including symlinks. Outside
writes require prior explicit authorization (`outside_root_approved: true`).

Use only tasks in the current wave whose dependencies have **verified success**.
The static schedule does not release later waves automatically. Respect the
session's remaining concurrency as well as configured `max_parallel`. Approval
and confirmation checks apply separately to every decision.

Overlapping write/write, read/write and shared resources require dependencies or
`sequential` execution. `worktree` requires verified host support and actual native
worktree creation; the router never claims to have created one. Overlapping writes
remain conservative even with worktrees; no automatic merge is implemented.

After execution, collect actual changed paths (for example `git diff --name-only`
plus untracked files, per worktree), compare them with declared ownership using
`verify_batch.py`, review conflicts, and run the integration criterion. See the
examples. A clean ownership report is not a passed integration test. In the
scheduler, changes outside ownership do not fail the task or count as rework: it
moves to `RECHECK` for a serial re-check (see [the scheduler](scheduler.md)).

## Tokens per phase

`record.py` and the scheduler `finish` report accept optional per-phase tokens for
`planning`, `classification`, `delegation`, `execution`, `validation` and `rework`
(`--phase-tokens planning=1234 ...`, `--tokens-source host|estimated`). Report only
measured phases: an absent phase is unknown, never zero. Report each measurement once,
in `record.py` or in `finish`, since `report_tokens.py` adds both.

```bash
python <skill>/scripts/report_tokens.py [--before <commit-or-iso-date>] [--json]
```

It prints median and p90 (nearest rank) of tokens per completed, validated task, overall
and per backend and Laya level (`unknown` when not recorded), per phase with the count of
unknown tasks. Without explicit phase data, `execution` is the first attempt's tokens and
`rework` the retries' tokens (zero only for a first attempt labelled no-rework); `total`
needs all six phases known. `--before` reports tasks completed before and from that
commit or date separately.

## Authentication, helpers and privacy

Claude's credential guard blocks environment/settings credentials or providers
that would change subscription billing. The existing
`CLAUDE_CODE_REMOTE=true` cloud-session exception is retained. Verify effective
billing in the host; launching a CLI proves nothing about billing. Codex uses its
existing session authentication. Quota limits never authorize alternate credentials.

Caveman and ponytail remain optional per configured agent skills; project style,
verification, approval and host rules take precedence. Never use the caveman proxy
for routing. Install configured Claude skills before generating their agents;
Codex uses the skills/hooks actually available to its native agents.

Default history records profiles, decision reasons and outcomes, not descriptions,
source code, environment values or free-form justifications. Justification text is
hashed in v2; its structured routing rationale remains auditable. Historical v1
records remain readable and may contain the earlier full text. Use opaque task IDs
and non-sensitive configuration labels.
