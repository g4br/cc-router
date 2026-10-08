# Current routing examples

Model IDs and effort support come only from your configuration and actual host.
The following commands work with the existing catalogue for both operators.
[Archived v1 task examples](legacy-examples.md) are retained as historical material,
not as current availability, price or capability claims.

## Equivalent single-step workflows

```bash
CC_ROUTER_OPERATOR=codex python scripts/route.py '{"description":"Implement a CSV parser with quoted-field tests","user_language":"pt-BR","operation":"implementation","files":2,"ambiguous":false,"critical":false}'
CC_ROUTER_OPERATOR=claude python scripts/route.py '{"description":"Implement a CSV parser with quoted-field tests","user_language":"pt-BR","operation":"implementation","files":2,"ambiguous":false,"critical":false}'
```

Claude requires `CC_ROUTER_OPERATOR=claude python scripts/install.py` first.
Codex installation generates no agent files. Inspect `selected`, `eligible`,
`excluded`, `needs_approval`, `reason`, `nearest_alternative`, `execution` and
`failure`. Both hosts produce proposals, not proof of execution.

Set `CC_ROUTER_OPERATOR` consistently on the following helper commands if the host
cannot be detected. Replace placeholders with actual returned IDs:

```bash
CC_ROUTER_OPERATOR=codex python scripts/justify.py <decision-id> auto 'Quoted fields require verified parser behavior; the chosen profile fits this scope'
CC_ROUTER_OPERATOR=codex python scripts/record.py <decision-id> success --no-rework true
CC_ROUTER_OPERATOR=claude python scripts/justify.py <decision-id> auto 'Quoted fields require verified parser behavior; the chosen profile fits this scope'
CC_ROUTER_OPERATOR=claude python scripts/record.py <decision-id> success --no-rework true
```

Execute and verify through the native host **between** justification and result.
The absence of numbers means unknown metrics. A result with known metrics:

```bash
python scripts/record.py <decision-id> success 300 4.2 --no-rework true --input-tokens 100 --output-tokens 200 --reasoning-tokens 50 --cache-tokens 20 --host-confirmed --effective-candidate <reported-candidate-id> --resolved-model <reported-version> --effective-effort <reported-effort>
```

Reasoning/cache are already included; total remains 300. Omit unsupported fields,
including effective effort when the host does not expose it.

## Approval and refusal

If `needs_approval` is true, present the reason and permitted alternative in the
user's language and wait. After an actual answer:

```bash
python scripts/justify.py <decision-id> approved 'User approved this candidate for the stated task'
python scripts/justify.py <other-decision-id> declined 'User selected the permitted alternative'
```

A declined decision cannot receive a result or later approval. Re-route using its
`task_id` and the granted `user_ceiling`/`allowed_candidates`. Candidate IDs and
legacy agent identifiers are both accepted. External billing is excluded even
with approval; no paid executor exists in this version.

## Failure before escalation

```bash
python scripts/record.py <decision-id> failure 200 5.0 --failure-kind rate_limit
python scripts/route.py '{"description":"Implement a CSV parser with quoted-field tests","operation":"implementation","files":2,"ambiguous":false,"critical":false,"task_id":"<same-task-id>","failed_with":"<candidate-id>","failure_kind":"rate_limit"}'
```

The decision is blocked with `stop_or_reschedule`; it never switches credentials.
For a local syntax correction, use `failure_kind: syntax_or_local_fix`. After
inspecting actual differences and establishing idempotence, add `diff_verified:
true` and `idempotent: true`; the same eligible candidate is selected. Non-idempotent
retries require explicit `retry_approved: true`. `verification_failed` and
`design_or_reasoning_failure` reconsider candidates after those same safety checks.
Unknown causes stop for diagnosis. The same behavior applies to both hosts.

## Static batch compatibility preview

For actual orchestration, prefer [the event-driven scheduler](scheduler.md).
The legacy list interface below classifies every entry in advance and returns
a static schedule; it does not consume completion events.

Save as `/tmp/steps.json`, substituting the real project root if needed:

```json
[
  {"step_id":"search","description":"Locate parser call sites","operation":"search","files":1,"ambiguous":false,"critical":false,"write_targets":[],"read_targets":["src/parser.py"]},
  {"step_id":"patch","depends_on":["search"],"description":"Update parser and run unit tests","operation":"implementation","files":1,"ambiguous":false,"critical":false,"write_targets":["src/parser.py"],"isolation":"sequential"}
]
```

Pass its JSON contents as the CLI argument (a shell variable avoids modifying the
JSON). The result has `scheduling.wave` and `scheduling.ready`. Verify `search`
before starting `patch`. Failed prerequisites keep dependent steps pending.
Independent conflicting writes are rejected. Worktree requests require configured
host support and actual host-created isolation; no automatic merge is performed.

After collecting **actual** changed files, save `/tmp/changes.json` as
`{"search":[],"patch":["src/parser.py"]}` and run:

```bash
python scripts/verify_batch.py /tmp/steps.json /tmp/changes.json
```

Unexpected files, missing reports and overlaps return a nonzero exit status. Run
integration checks separately, even when ownership passes.

## Profiling reference tasks

| Operation | Objective check | Typical flags |
|---|---|---|
| search | Exact symbol locations match fixture | files=1 |
| mechanical_edit | Only intended diff; formatter passes | files=1 |
| implementation | Parser roundtrip tests pass | files=2 |
| debugging | Reproduced regression test passes after correction | files=2, critical as appropriate |
| review | Planted defect identified with evidence | files=2 |
| architecture | Dependency and interface invariants pass | files=2, ambiguous as appropriate |

The offline benchmark uses these six profiles for both hosts with fictional
configuration data. `legacy` and all three v2 policies see the same observations.
Read its `source` and `limitations` before interpreting the result.
