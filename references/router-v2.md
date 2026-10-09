# Router v2 contracts and decisions

## Configuration and migration

Priority is `CC_ROUTER_CONFIG` > `config/router.json` if it exists >
`config/ladder.json`. Operator override is independent. A configured host must
exist; there is no fallback to another host. The bundled ladder remains the
unchanged source of existing model IDs and effort settings. No new model is added
without host evidence. In particular, this implementation adds no Terra candidate.

V1 loads through deterministic in-memory migration. Every rung, active flag,
custom field, operation table and agent skill setting is retained. Migration
creates IDs from agent names, preserves legacy ranks as cold-start priors and
uses those ranks as initial consumption tiers. Legacy active candidates retain
the old subscription policy declaration, **not proof of host billing**;
availability remains `unverified`. Verify these declarations for the actual session.

Explicit migration (Python 3.10+, standard library):

```bash
python scripts/migrate.py config/ladder.json > /tmp/router-preview.json
python scripts/migrate.py config/ladder.json --write config/router.json
```

An existing destination gets a timestamped `.bak` before replacement. No file is
changed by ordinary routing. Roll back by selecting the original file with
`CC_ROUTER_CONFIG=config/ladder.json`, removing the newly created router file, or
restoring the saved `.bak`. Installing agents is a separate, explicit action.

Minimal independent v2 catalogue (fictional IDs; not a support claim):

```json
{
  "schema_version": 2,
  "backend": "heuristic",
  "policy": "balanced",
  "hosts": {
    "codex": {
      "execution": "native",
      "capability_source": "administrator configuration; confirm in session",
      "worktree": false,
      "max_parallel": 4,
      "candidates": [
        {"id":"basic", "model":"model-from-your-host", "effort":null,
         "active":true, "approval":false, "billing_mode":"subscription",
         "capabilities":["search","implementation"], "suited_for":"Scoped changes with objective tests",
         "availability":"unverified", "consumption_tier":0, "legacy_rank":0}
      ]
    }
  }
}
```

Claude uses the same schema under `hosts.claude`; `agent` defaults to `id` and names
the generated agent file. `effort` is null or an opaque host effort identifier.
Optional `supported_combinations` is an array of exact `{model, effort}` pairs
verified for that host. Active combinations outside that list are rejected unless
marked unavailable. With no stable discovery interface, explicitly configured
capability evidence is the adapter's source; the router never launches a secondary
CLI or claims discovery. A new host needs an adapter; a new model needs only data.

Candidate fields:

| Field | Meaning |
|---|---|
| `id`, `agent` | Stable safe identifier; unique within host |
| `model`, `effort` | Host identifier and optional effort; never inspected for family |
| `active`, `approval` | Exact booleans |
| `billing_mode` | `subscription`, `unknown` (approval required), `external` (excluded) |
| `availability` | `unverified`, `supported`, `unavailable` |
| `capabilities` | List matching operation or explicit required capability tags |
| `suited_for`, `label` | Description for explanation and Laya profile |
| `resolved_model` | Optional effective version whose observed results may inform selection |
| `consumption_tier` | Configured permission ceiling/floor dimension, not model quality |
| `legacy_rank` | Legacy fallback role, not universal superiority |
| `restrictions` | Optional `operations`, `max_files`, `allow_critical` |
| `escalation_only` | Requires retry or explicit matching user floor |
| `skills` | Optional override of configured Claude agent skills |

State inputs are strictly typed and reject unknown fields. `description` is 1–8000
characters, `files` an integer from 0 to 1,000,000 (booleans rejected), `ambiguous`
and `critical` exact booleans. Identifiers/language/context have bounded length.
Operations come from `base_level_by_operation`, restricted to the existing public
operation names. `failed_with`, `user_ceiling`, `user_floor` accept candidate IDs or
legacy agent identifiers; inactive/unknown references are errors. `allowed_candidates`
is an explicit allowlist; `blocked_candidates` excludes unavailable/declined choices.
Empty batches/catalogues, duplicate IDs, invalid URL/schema/effort contracts and
path escapes fail before decision events are written.

### Laya difficulty keys

`laya_mode`: `per_candidate` (default when missing) or `difficulty`; `backend`
stays `heuristic` or `laya`. Difficulty mode uses `laya_difficulty` (`question` and
exactly five ordered `levels`), `laya_rotations` (1 to 5, default 5),
`laya_min_confidence` (0 to 1, default 0.5), `laya_min_confidence_calibrated`
(boolean, default `false`) and `level_to_candidate` (per host, one candidate ID or
agent per level; each must exist on that host ladder, with rungs that do not
decrease with difficulty). A host with Laya enabled needs a mapping in difficulty
mode. Missing keys are filled with defaults on load; `migrate.py` writes them to a
file and keeps a timestamped `.bak` of the previous content. See
[laya.md](laya.md#difficulty-mode) for the request contract and combination rules.

## Selection and policy

Stages: validate → diagnose → eligible candidates → comparable evidence → policy →
approval/host confirmation. Ineligible entries include structured reasons in
`excluded`. `eligible` is a set of **proposals**, not authorization to execute.
`execution.applied` is always false at routing time. Results record host facts.

With insufficient evidence, use the existing operation base plus one for
`files > file_limit`, ambiguity and criticality, mapped to the nearest eligible
legacy role. With migrated configuration this preserves the normal heuristic
choices, except invalid/unsafe states. `policy: legacy` also retains the first
eligible Laya score over the transitional threshold. Failure diagnosis and safety
gates apply even in legacy mode. `escalation_jump` remains parsed for old consumers;
v2 diagnoses first and does not use it to authorize retries.

Comparable data requires same host, effective candidate, resolved version, effort,
operation, file-count bucket, ambiguity, criticality and optional context class.
Unknown versions never silently combine. Configure a resolved version only from
host evidence; historical mismatches cannot influence its selection.

Minimum samples: `min_cost_samples=20`, `min_calibration_samples=20`. All candidates
in the comparison pool need enough comparable observations and measured completion
tokens/duration; otherwise deterministic fallback explains missing evidence.
Reliability uses a Laplace-smoothed success estimate and a Wilson 95% interval.
A candidate must meet the policy's minimum using the **lower bound**. For a
sufficiently populated Laya score bin, its observed first-pass interval is used.
These are descriptive observations with selection bias, not causal guarantees.

| Policy | Minimum lower bound | Tokens weight | Duration weight | Failure weight |
|---|---:|---:|---:|---:|
| economy | .70 | .80 | .10 | .10 |
| balanced | .70 | .40 | .20 | .40 |
| performance | .70 | .10 | .30 | .60 |

Each weight and minimum can be overridden under `policies.<name>`. Objective =
`tokens_weight * mean_completion_tokens/max_tokens_in_pool + duration_weight *
mean_completion_seconds/max_seconds_in_pool + failure_weight * (1-smoothed_success)`.
Choose the smallest objective; file order breaks exact ties only. Missing or
incompatible units do not get fabricated numeric priors.

Completion tokens are the sum of all observed attempts, including failures and
escalations, attributed to the initial candidate. The aggregate is the arithmetic
mean across completed comparable tasks. Failure reliability remains separately
visible, including unfinished tasks; incomplete tasks never count as successes.
This is observed completion consumption, not an unbiased prediction of all future
failures. Tokens are neither currency nor an exact subscription quota fraction.

## Events and privacy

Existing paths remain `~/.claude/cc-router/history.jsonl` and
`~/.codex/cc-router/history.jsonl`. New records have `schema_version=2`, UUID event,
decision, task and attempt identities. Reuse task IDs across retries. A task already
completed cannot be reopened as another attempt; use a new task for new work.

Decision records include the eligible/excluded set, constraints, policy, backend,
structured reason, scores, uncertainty and evidence source. Intention is separate
from effective execution. Results add verification, failure taxonomy, metrics,
rework and completion status. Absent values are null. `justify.py`, `record.py` and
`feedback.py` accept old short decision IDs. Legacy unknown outcomes stay readable
but cannot stand in for measured successful completions.

`--host-confirmed` asserts that effective fields came from the native host.
Reporting only intended settings is insufficient. `--input-tokens`, `--output-tokens`,
`--reasoning-tokens`, `--cache-tokens` are optional; reasoning is a subset of output,
cache a subset of input, and total = input + output when both are reported. Never
add reasoning/cache twice. Metrics carry source and units. Compatible token source
and unit are required even within one host; no cross-host price comparison exists.

Free-form descriptions and justification text are omitted from new JSONL records.
The latter has a SHA-256 digest; structured selection reasons remain stored. This
minimizes collection rather than pretending arbitrary text can be reliably redacted.
Use non-sensitive IDs and labels. Existing v1 logs are not rewritten or sanitized.

Run `python scripts/telemetry.py` to inspect the current host history: counts and
mean/median attempt and completion consumption are segmented by effective candidate,
version, effort, task profile and metric source/unit. Unknown rework remains null.

POSIX append uses a file lock and one `O_APPEND` write per event, with UUIDs. A
partial previous line is separated before appending; readers skip malformed lines.
No history rewrite or database is required. File locks depend on the underlying
filesystem; use local storage. The current scripts target Linux/macOS/WSL host
shells; native Windows file locking needs an adapter.

## Dependencies and limitations

The legacy `route.py` list API returns static waves and classifies all entries.
For live orchestration, use [scheduler.py](scheduler.md): it classifies only ready
tasks, persists reservations and releases dependents after validated completion.
The host supplies current free capacity and invokes native execution tools. `worktree` is
rejected unless configured as supported, then remains unapplied until the host
creates it. The router does not create worktrees, merge branches or bypass hooks.
Actual path ownership can be checked with `verify_batch.py`; integration tests
remain mandatory. The caller must collect actual changed paths from the host/tree,
including untracked files, rather than trusting intended `targets`.

Native session capacity, model override rules, substitutions, billing and final
sandbox authorization remain host responsibilities. Unknown availability is
explicitly reported, never silently reported as applied. No paid benchmark,
app-server integration, external executor or Laya weight training is included.

After an externally resolved context, permission or quota failure,
`recovery_confirmed: true` permits recovery of the same eligible candidate. Diff
inspection and idempotence/explicit retry approval are still required. This is a
caller report, never a mechanism to change native permissions.
