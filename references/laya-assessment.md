# Laya assessment: Phase 0

Date: 2026-10-09. Repository state: `main` at `cf881a3`, clean working tree.
Laya: `laya` 0.3.26 installed locally; `laya-serve` answers on `127.0.0.1:8001`
with checkpoint `english` on CPU (`/health`: `"loaded":["english"]`).

Scope: this document checks seven findings (D1–D7) against the code. It also
records a baseline and describes the telemetry. It changes no existing file.
Line numbers refer to `cf881a3`.

Empirical data comes from `~/.claude/cc-router/history.jsonl`, the path from
`common.py:89-90` (`history_path`). The file holds 147 events from
2026-10-04 to 2026-10-09. 145 events are schema v1, from an older 12-rung ladder.
Only 2 events are schema v2. `~/.codex/cc-router/history.jsonl` does not exist.

## Summary

| ID | Verdict | Short reason |
|----|---------|--------------|
| D1 | Confirmed, with a count correction | One question per *eligible* candidate: usually 12 on Claude, 8 on Codex. |
| D2 | Partially confirmed | Scores are not monotone. "First above threshold" applies only to `policy: legacy`, which is not the default. |
| D3 | Confirmed | Laya only filters, and the heuristic picks among the candidates that pass. |
| D4 | Confirmed | "yes" is always `A`, the first slot. The 0.8 threshold is fixed. laya-serve supports `option_order` for debiasing. |
| D5 | Confirmed, and worse than stated | With the shipped config, calibration and estimates are structurally impossible. Volume does not change this. |
| D6 | Not verifiable from the repo | The repo has no benchmark numbers. It only says that scores are unvalidated and uncalibrated. |
| D7 | Confirmed | README says 8000. Config, code and `laya.md` say 8001. Port 8000 is used by another service on this machine. |

## D1: one binary question per rung, with the profile text in the question

**Verdict: confirmed, with a count correction.**

Evidence:
- `scripts/route.py:70-79`: `laya_probabilities` builds one `choice` question for
  each entry in `config['ladder']`. The instruction is
  `config['laya_question'].format(label=..., suited_for=...)`.
- `config/ladder.json:14`: the question is "Given this task and the model
  profile, is {label} suited to completing it on the first attempt without
  rework? Profile: {suited_for}".
- `config/ladder.json:15`: two options. `A` is yes and `B` is no.
- `scripts/route.py:219`: the v2 path (`route_one`) calls
  `laya_probabilities(state, dict(config, ladder=eligible))`. Questions therefore
  cover only the **eligible** candidates, not the full ladder.
  `references/laya.md:37` says the same.
- Counts with the shipped config, measured with `eligible_candidates`:
  - Claude: 12 of 13 candidates for every operation except `security`, which
    gets 8. `exec-opus-max` is excluded as `escalation_only`
    (`selection.py:46`), and `security` has a ceiling of 8 (`ladder.json:78`).
  - Codex: 8 of 8 for every operation.
- Local data supports the claim that the score measures text similarity, not
  capability. Across 22 v1 decisions with 12 scores each, the mean per rung is
  flat (0.582–0.713). The two ends score lowest: `exec-haiku` at 0.603 and
  `exec-fable-xhigh` at 0.582. A capability signal would rise with the ladder.
  The v2 decision `2233dbdb…` shows the same pattern: `exec-haiku-low` 0.4075,
  `exec-fable-xhigh` 0.4614, mid-ladder rungs 0.62–0.72.

Token effect: Laya runs locally and uses no LLM tokens. The cost is 8–12 local
inferences per decision on CPU. This latency is not recorded (see Telemetry).
The real token effect is indirect: a bad score can route to the wrong rung.
The median execution attempt in the history uses 84,055 tokens.

Correction to the PRD: count "up to 12 on Claude (8 for `security`) and 8 on
Codex per decision", not 13. Any redesign that keeps one question per candidate
gets the eligible set, not the ladder.

## D2: capability question, niche profiles, no monotonicity, first-above-threshold

**Verdict: partially confirmed.**

Confirmed part:
- The question asks about capability: "first attempt without rework"
  (`ladder.json:14`).
- Many `suited_for` texts describe niches, not capability levels. Examples:
  `ladder.json:18` (haiku-low: "one-shot read, extraction…"),
  `ladder.json:26` (opus-max: "prone to overthinking") and
  `ladder.json:27` (fable-low: "step that failed on Opus").
- No code enforces or checks monotonicity. Neither `laya_probabilities`
  (`route.py:70-97`) nor `select` (`selection.py:68-80`) checks it.
- Observed data: 22 of 22 v1 score vectors are non-monotone up the ladder, and
  so is the one v2 vector.

Refuted part, the claim that the default path picks the first rung above the
threshold:
- `first_above_threshold` (`route.py:99-106`) is called only from `choose_level`
  (`route.py:132-174`). `choose_level` has no production caller. Only
  `tests/test_v2.py:377-393` uses it, as a regression oracle with
  `backend='heuristic'`.
- The production equivalent is `route.py:228-233`. It picks
  `min(above, key=legacy_rank)`, but only when `policy == 'legacy'`.
- The default policy is `balanced`. `ladder.json` has no `policy` key, and
  `candidates.py:78` sets the default.
- In the default policy, `select` keeps the candidates that pass the threshold.
  Among them, `fallback` picks the one nearest the heuristic baseline, with ties
  going to the lower rank (`selection.py:65`). This can under-route: suppose the
  heuristic rung scores below 0.8 and a cheaper rung scores above it. The
  cheaper rung then wins. It can also over-route, because the nearest passing
  rung may be above the baseline.

Token effect: under `policy: legacy`, under-routing raises rework tokens. Under
`balanced`, the effect has no fixed direction, and it is rare because of D3.

Correction to the PRD: describe the under-routing mechanism as "nearest passing
candidate to the heuristic, ties downward" (default) and "first passing rung"
(only for `policy: legacy`). `choose_level` and `first_above_threshold` are
legacy and test-only code. Do not spend Phase 1 effort on them.

## D3: in v2, Laya only filters; fallback picks nearest to the heuristic

**Verdict: confirmed.**

Evidence:
- `selection.py:70`: `chosen = fallback(...)` before any score is read.
- `selection.py:73-80`: when scores exist, the pool shrinks to candidates with
  `scores >= success_threshold`. `fallback` then picks again. With no candidate
  above the threshold, the choice stays the heuristic one.
- `selection.py:60-65`: `fallback` returns the eligible candidate whose
  `legacy_rank` is nearest the heuristic baseline.
- `selection.py:85-90`: the observational branch needs sufficient evidence for
  every candidate in the pool. This never holds (D5). So the result of
  `fallback` is final in practice.
- `tests/test_laya_routing.py:21,70`: the mock gives 0.9 to `sol-medium` and
  `sol-high`. The choice is `sol-medium`, which is also the heuristic baseline.
- Laya changes the choice only in one case: the heuristic-nearest candidate
  fails the threshold and another candidate passes. If all candidates pass, or
  none pass, the result is the heuristic choice.
- Observed: no candidate passed 0.8 in 14 of 22 v1 decisions. No decision had
  all candidates passing. The single v2 decision was `laya (no opinion)`, with a
  maximum score of 0.7202.

Token effect: in most decisions, the Laya call adds latency and changes nothing.
How often Laya moved the choice away from the heuristic is not computed: the v1
records use another base table and ladder.

Correction to the PRD: none. For Phase 1, Laya must produce an ordering or a
rung estimate that can move the choice. A filter is not enough.

## D4: "yes" is always option A; fixed threshold 0.8

**Verdict: confirmed.**

Evidence:
- `config/ladder.json:15`: `{"A": "yes, …", "B": "no, …"}`. The yes option is
  always first.
- `route.py:91`: only `probabilities['A']` is read.
- `ladder.json:8` sets `success_threshold` to 0.8, and `candidates.py:84` uses
  0.8 as the default. `git log -S` shows the value has not changed since the
  first commit (`73c0531`).
- `candidates.py:112-113` requires `laya_criteria` to have exactly the keys
  `A` and `B`. A rename or reorder is possible, but no swap is ever done.
- `route.py:71-72`: the code comment says `choice` with neutral keys was chosen
  because the `noul` type "tends to follow the true/false labels". Label and
  position bias were therefore already a known concern.
- No test measures position bias. The mocks return fixed values
  (`tests/test_laya_routing.py:21`, `tests/test_laya_contracts.py:46`).

Token effect: indirect. A position bias shifts every score the same way, which
moves the threshold crossing (D3).

Note for later phases: option order equals key order in `criteria`. This is
verified in the installed laya-serve 0.3.26:
- `laya/common.py:107-122`: `render_options` renders `crit.items()` in dict
  insertion order. JSON objects keep key order in Python.
- `laya/agent.py:1352-1358`: the answer maps `zip(keys, p)` to the same key
  order.
- laya-serve accepts an `option_order` permutation for each question
  (`laya/agent.py:1084-1098`, `1121-1124`). It un-permutes the probabilities
  before returning them (`laya/common.py:455-468`, `agent.py:1335`). Two passes
  with `[0,1]` and `[1,0]` could average out position bias, with no new
  dependency. `serve.py` does not mention `option_order` itself. It passes the
  question dict through, so check this over HTTP before relying on it.
- The repo itself states nothing about option order. `references/laya.md` does
  not mention it. The test mock servers ignore the order and return fixed `A`
  values.

## D5: observational calibration needs ≥20 samples per cell; labels are censored

**Verdict: confirmed, and stronger than stated.** With the shipped config,
calibration and observational estimates can never complete.

Evidence:
- `telemetry.py:101-111`: a calibration cell is (candidate, score bin of 10).
  It needs `min_calibration_samples` labelled rows (`candidates.py:81`,
  default 20). Each row must also satisfy `matches`.
- `telemetry.py:78-81`: `matches` requires all of the following:
  - `host_confirmed`
  - a candidate with `resolved_model is not None`
  - the same operator and the same task profile (`telemetry.py:6-9`: operation,
    file bucket, ambiguous, critical, context class)
  - the same effective candidate, resolved model and effort
- **Blocking issue:** no candidate in `config/ladder.json` sets
  `resolved_model`. The v1 migration does not add one (`candidates.py:59-62`),
  and `install.py` does not set one. So `c.get('resolved_model') is not None` is
  always false, and every candidate gets `samples=0`, `completion_tokens=None`
  and `calibration=None`, whatever the history contains.
  `references/router-v2.md:106-107` says so: "Configure a resolved version only
  from host evidence".
- `selection.py:85-87`: the observational branch also needs **every** candidate
  in the pool to be sufficient. Labels are censored: `record.py:76-106` records
  an outcome only for the chosen decision. So cheap and expensive candidates
  never collect 20 samples per profile at the same time, unless an explicit
  exploration policy exists. None exists.
- Labels are also missing from the current history. All 42 results are v1, with
  no `host_confirmed`, `resolved_model` or `metrics` fields. They cannot match,
  even after a config fix.
- `references/laya.md:47-54` and `references/router-v2.md:110-115` describe the
  ≥20-sample requirement and the selection bias.

Token effect: the `economy`, `balanced` and `performance` policies, which weigh
tokens, never activate. Every decision is the heuristic fallback with
`confidence: low`. The v2 decision `2233dbdb…` shows "insufficient comparable
completion evidence".

Correction to the PRD: the problem is not slow convergence. The path is
disabled until candidates have `resolved_model` and results are recorded with
`--host-confirmed`. A calibration plan must start there. It also needs a source
of counterfactual or exploration labels, because the per-profile × per-bin ×
per-candidate cell count (12 × 10 × the number of profiles) is out of reach at
the current volume of about 10 decisions per day.

## D6: base checkpoint zero-shot below the majority-class baseline (0.36 vs 0.46)

**Verdict: not verifiable from the repo.**

What the repo assumes:
- `README.md:168`: "Laya's zero-shot scores for this model-selection question
  are unvalidated locally, so continue to verify outcomes."
- `references/laya.md:40-42`: the returned number is an "uncalibrated score",
  and the threshold is a "transitional heuristic".
- `references/laya.md:61`: "The public checkpoint is not trained or fine-tuned
  by this project."
- `README.md:16`, `README.md:210` and `references/protocol.md:59` say the same:
  the scores are not probabilities.

The repo has no Laya benchmark figures. A search for `0.36`, `0.46`,
`majority` and `zero-shot` found only the README sentence above. The repo
neither cites nor tests the published accuracy numbers.

Local evidence is weak. 13 results link to a v1 decision with scores. The mean
score of the chosen rung is 0.744 when `no_rework=true` (n=10) and 0.648 when
`no_rework=false` (n=3). This sample is too small and too censored to estimate
accuracy. No conclusion is drawn from it.

Correction to the PRD: cite the Laya publication directly for the 0.36/0.46
figures. Phase 1 can reproduce a local check only after D5 labels exist.

## D7: README says port 8000; config and laya.md say 8001

**Verdict: confirmed.**

Evidence:
- `README.md:164`: "The server listens on `127.0.0.1:8000`".
- `README.md:168`: "Both operators use `http://127.0.0.1:8000/v1/systemone` by
  default".
- `config/ladder.json:3-4`: `laya_url` and both `laya_urls` use 8001.
- `scripts/candidates.py:88`: the default `laya_url` uses 8001.
- `references/laya.md:22-23`: "the bundled file currently uses 8001".
- `scripts/start_services.sh:19-25` reads the port from the config and refuses
  mismatched ports.
- Runtime check on this machine: `127.0.0.1:8001/health` returns Laya.
  `127.0.0.1:8000/health` returns a different service
  (`{"status":"ok","version":"1.1.0",…,"qc_store":null}`). A user who follows
  the README would point the router at the wrong service. `README.md:166` says
  such an error stops routing.

Related documentation drift found during this check (not fixed here):
- `README.md:168` and `references/laya.md:3` say "the shipped default is
  `heuristic`". The committed `config/ladder.json:2` is `"backend": "laya"`,
  because `install.py:66-69` rewrites the file in place.
- `README.md:166` links to `references/laya.md#choose-an-available-port`. No
  such heading exists in `laya.md`.

Token effect: none directly. A wrong port gives an HTTP error and stops routing.

## Baseline

Full output: `references/baseline-phase0.txt`.

- Tests: `python -m unittest discover -s tests -v` (Python 3.13.9, repo root)
  printed `Ran 48 tests in 80.728s` and `OK`. That is 48 passed, 0 failed,
  0 errors and 0 skipped. All Laya tests use local mock HTTP servers. None of
  them call the running laya-serve.
- Benchmark: `python scripts/benchmark.py` (CLI `[-h] [--output OUTPUT]`) exited
  with status 0. It produced 48 rows (2 hosts × 6 operations × 4 policies),
  with `api_calls: 0` and `real_model_runs: 0`.
  - `legacy` selects `baseline` in 12 of 12 rows (confidence `heuristic`,
    completion tokens 112.5, duration 4.5 s).
  - `economy`, `balanced` and `performance` each select `measured` in 12 of 12
    rows (confidence `observational`, completion tokens 105, duration 3 s).
  - Median selector latency is 0.0119 ms (max 0.0362 ms).
  - Limit: the benchmark is a synthetic fixture. It passes `scores=None` and
    sets `resolved_model` on its fixture candidates, so it **does not exercise
    Laya** and does not represent the shipped config (see D5). It cannot be the
    baseline for Laya quality.

## Telemetry: per-phase token accounting

What exists in `~/.claude/cc-router/history.jsonl` (147 events):

| Event | Count | Fields present |
|-------|-------|----------------|
| `decision` | 53 (52 v1, 1 v2) | v1: `date, event, operator, id, batch, state, agent, level, needs_approval, backend, probabilities`. v2 adds `task_id, attempt_id, eligible, excluded, failure, task_profile, policy, attempt_count, constraints, selected, model, effort, evidence, objectives, scores, score_kind, execution, reason, …` |
| `justification` | 52 (51 v1, 1 v2) | `id, agent, answer, justification` (v2 adds `justification_sha256`, `task_id`, `attempt_id`) |
| `result` | 42 (all v1) | `id, agent, result, no_rework, tokens, duration_s` |
| `workflow_started` / `workflow_usage` / `task_completed` | 0 | n/a |

Decision backends: 27 `heuristic (laya unavailable)`, 22 `laya`,
3 `heuristic`, 1 `laya (no opinion)`. Operations: 37 `implementation`,
10 `tweak`, 2 `mechanical_edit`, 2 `writing`, 1 `long_task`, 1 `review`.

What can be computed:
- **Execution, per delegated attempt:** 42 results, all `success`. Tokens are
  known for all 42: sum 4,479,209, median 84,055, minimum 45,398 and maximum
  408,191. It is a single total (v1 `tokens`), with no input/output/cache split
  and no `metrics.source`. Because no result has `host_confirmed`, none can
  feed `estimates`.
- **Rework as retries:** 0 decisions have `failed_with` or `attempt_count > 1`,
  so retry tokens recorded by the router are 0 attempts. This does **not** mean
  rework cost 0. 7 of the 42 results have `no_rework=false`, so rework happened
  outside the router, and its tokens were never recorded. Rework tokens are
  **unknown**.

What cannot be computed (unknown, not zero):
- **Planning, classification, delegation, validation.** These phases are only
  recorded through `scheduler.py usage` (`scheduler.py:24`, `:170-177`), which
  emits `workflow_usage` with cumulative host-reported overhead. The history
  contains no workflow events. `telemetry.py:197-198` would report these phases
  as `None`.
- **Classification by Laya.** It uses no LLM tokens, but its cost is latency.
  `routing_seconds` exists only inside a scheduler run file
  (`scheduler.py:36`, `:91`, `:186`). It is not written to `history.jsonl`, and
  no decision records Laya latency.
- **Main-session (orchestrator) tokens.** The router cannot meter them
  (`references/scheduler.md:173-174`). Only the host can report them.
- **Tasks per token.** `workflow_efficiency` (`telemetry.py:131-164`) returns
  `total_tokens=None` when any phase is missing. That is the case for all
  history here.

Missing for per-phase accounting:
1. A `workflow_started` event and `workflow_usage` reports for each run. Today
   only scheduler runs produce them, and the history contains none.
2. Laya call latency and the number of questions, written into each decision
   record.
3. Results recorded with `--host-confirmed`, `--resolved-model`,
   `--input-tokens` and `--output-tokens` (`record.py:17-26`). Today none have
   them.
4. A way to record rework tokens when rework happens outside a routed retry
   (the 7 results with `no_rework=false`).

## Plan adjustments

1. **D1 count:** design for "eligible candidates per decision" (12 or 8 on
   Claude, 8 on Codex), not 13.
2. **D2 mechanism:** `first_above_threshold` and `choose_level` are test-only.
   The live mechanism is `selection.fallback` over the candidates that pass
   (`selection.py:60-80`), plus `route.py:228-233` for `policy: legacy`. Aim
   changes there.
3. **D4 tooling:** use laya-serve's existing `option_order` for permutation
   debiasing before changing the question format. Verify first over HTTP that
   `serve.py` passes it through.
4. **D5 precondition:** calibration and the token-aware policies are
   structurally off, because `ladder.json` has no `resolved_model` and no
   result is host-confirmed. Fix that before any calibration phase, or the
   calibration phase measures nothing. Also plan for censored labels, for
   example deliberate exploration or a counterfactual label source.
5. **D6:** take the 0.36/0.46 figures from Laya's publication. Do not cite
   this repo for them.
6. **D7:** fix the README port. In the same doc pass, fix the "shipped default
   is heuristic" statement and the broken `laya.md` anchor.
7. **Baseline:** the existing benchmark does not involve Laya. A Laya-quality
   baseline needs a new labelled offline set. The current history cannot
   provide one (42 results, all v1, censored).
