# v2 implementation record

## Phase 0

Baseline: `python -m unittest discover -s tests -v`: 9 tests passed (2026-10-08).
Working tree already had edits to README, SKILL, ladder, examples, common, install,
route and test_laya_routing. These are the implementation baseline; a snapshot
was saved to `/tmp/cc-router-pre-v2.tar.gz` before editing.

Added contracts for public JSON/batch, approval/decline, atomic batch validation,
Claude credential guard and its existing cloud exception. Tests use temporary
homes and mock services; no actual host agents, configuration or paid API calls.

Intentional fixes will have corresponding tests: reject invalid input, avoid
unowned agent deletion, exclude unknown/failed legacy outcomes from completion
cost, label Laya scores as uncalibrated, and diagnose failures before escalation.

## Phase 1 — P0 core

Added a pure v1→v2 migration and host catalogue validation without writing user
configuration. Existing model IDs/active flags are retained. Explicit migration
backs up overwritten destinations. Capability provenance remains configuration,
with native host confirmation required; no unsupported model was added.

Validated inputs before events, maintained legacy public response fields and
logical/generated agent names, preserved credential guards/cloud exception, and
stopped deleting unowned agents or removing unrelated approval rules. P0 suite
passed (28 discovered cases at that point, including inherited duplicate tests;
those duplicate discoveries were subsequently removed).

## Phases 2–3 — P1 selection and outcomes

Retained heuristic/legacy functions and Laya transport, added eligible-candidate
policy selection, profile/version/source segmentation, completion consumption,
smoothed estimates and observational score-bin calibration. Fixed the old test
that treated four legacy results without a result status as successful consumption
samples: they now produce explicit insufficient-evidence fallback. Separate tests
prove evidence can select a different candidate regardless of order for both hosts.

Results now record intended/effective execution, nullable metrics, verification,
failure type and task/attempt IDs. Structured failure taxonomy replaces automatic
promotion; retries need bounded attempts, diff inspection and idempotence/approval.
Original short IDs and old event readers remain supported. P1 suite passed before
adding the dependency planner (33 discovered cases, including then-duplicated cases).

## Phase 4 — P2 planning

Added DAG waves, host/config concurrency limits, normalized paths and symlink
checks, write/read/resource conflicts, explicit sequential mode and conservative
worktree capability checks. Added actual-change ownership verification. Execution,
worktree creation, prerequisite success checks and integration remain native-host
responsibilities; no custom merge engine. Added targeted tests for cycles,
collisions, undeclared writes and isolation limitations.

## Phase 5 — documentation and benchmark

Replaced normative family ordering and probability claims with schema/policy
contracts. Preserved historical examples in `legacy-examples.md`, clearly marked
non-normative; public `examples.md` now shows equivalent host workflows. Added
reproducible offline comparison with six task profiles, two hosts and four policies.

Synthetic replay: legacy initial candidate uses 100 tokens per attempt but needs
45 attempts for 40 completions (five retries), yielding 112.5 mean completion
tokens and 4.5 seconds. The alternative uses 105 tokens per attempt, completes all
40 in one attempt and averages 3 seconds. All v2 policies select that alternative
for the six profiles on both hosts. This demonstrates completion-aware selection;
it is not a real-model savings measurement. Unmeasured regression count is null.

No actual model benchmark, native delegation or paid API was executed. Native
availability, applied settings, quota/billing and live concurrency must still be
confirmed by the host. The scripts do not promise automatic future-provider support.

## Final verification

- 39 distinct unittest cases passed, including 224 cold-start comparisons against
  the original heuristic (14 operations × 8 flag combinations × 2 hosts).
- Six concurrent writers appended 360 complete, unique events. Interrupted-line
  recovery preserved the following event.
- Native execution and metrics are fixtures; model selection is never claimed
  applied without a host report. Effective unconfirmed metrics cannot drive policy.
- HTTP tests cover local mock scores, no opinion, outage fallback, malformed data,
  HTTP errors and blocked redirects. The heuristic test forbids the network path.
- `quick_validate.py`: skill valid. `compileall`, `bash -n` and `git diff --check`
  passed. No real user configuration or host agent was installed during validation.

Changed/added implementation files: `common.py`, `route.py`, `install.py`,
`justify.py`, `record.py`, `feedback.py`, `start_services.sh`, `candidates.py`,
`state.py`, `selection.py`, `telemetry.py`, `failures.py`, `planning.py`,
`verify_batch.py`, `migrate.py`, `benchmark.py` (all under `scripts/`).
Documentation: `SKILL.md`, `README.md`, `references/examples.md`, `laya.md`,
`router-v2.md`, `legacy-examples.md`, and this implementation record.
Tests: `test_contracts.py`, `test_v2.py`, `test_laya_contracts.py`, and the updated
unknown-outcome contract in `test_laya_routing.py`.
`config/ladder.json` retains the pre-existing local changes; implementation did not
rewrite it. Existing laya_device/server and baseline tests remain in place.
