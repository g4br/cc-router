# Optional local Laya backend

The bundled `config/ladder.json` ships with `backend: heuristic` and
`laya_mode: per_candidate`. These defaults reflect the [gate](#gate) below: the Laya
difficulty mode has not passed it, so Laya is off until you opt in. `install.py` asks
(default no, or `--backend laya|heuristic`) before it installs Laya and downloads the
public English checkpoint.
Routing never starts it during a unit test or ordinary decision: the skill runs
`start_services.sh --check` on invocation and asks the user before starting. The operator supplies a faithful English summary
and keeps the user's language for reports.

## Installation and startup

```bash
python3 -m pip install "laya[serve]"
scripts/start_services.sh
```

Startup may download the public checkpoint and requires user-authorized network
access. It probes available GPUs in a separate process and falls back to CPU.
The existing launcher, `serve_laya.py` and `laya_device.py` are retained. Routing
itself depends only on Python standard library.

The launcher uses `CC_ROUTER_CONFIG`, then `config/router.json` if present, then
`config/ladder.json`. Use the configured local port (the bundled file currently
uses 8001). If occupied by another service, it asks before changing ports; a yes
backs up the configuration and updates `laya_url`/`laya_urls`. An empty answer
changes nothing. The log remains under `${XDG_STATE_HOME:-~/.local/state}/cc-router`.

Set `backend` to `laya` and include the intended hosts in
`laya_enabled_operators`. One local instance can serve both. The optional
`LAYA_API_KEY` authenticates this local service only; it is not a provider billing
credential. The selector accepts only loopback HTTP URLs, disables proxy use and
rejects redirects. It does not contact model-provider APIs.

## Scores and observational calibration

The request contains only description, operation, files, ambiguity and criticality.
It excludes user language, execution controls, targets, credentials and history.
Questions are generated from **eligible** candidate profiles. Only the explicit
local authentication header, if configured, carries the Laya credential.

To cancel position bias, each question is sent twice in the same request, with `criteria`
in the order A,B and B,A (laya-serve renders options in key order). The score is the mean
of the two "A" (yes) probabilities. `option_order` was not used or verified.

The returned number is an **uncalibrated score**, not a guaranteed probability of
success. `success_threshold` remains a transitional heuristic. If no eligible
candidate clears it, use the conservative heuristic and report `laya (no opinion)`.
An unavailable service reports `heuristic (laya unavailable)`; malformed JSON,
missing/invalid scores and HTTP contract errors stop visibly. They never masquerade
as successful fallback.

Observed calibration partitions scores into ten bins, separately by task profile,
host, effective candidate, resolved version and effort. At least
`min_calibration_samples` (default 20) labelled outcomes in the current bin are
required. The event's `no_rework` label, including later feedback, determines
first-pass success. Calibration reports a Laplace-smoothed estimate and Wilson
95% interval. With enough data, selection uses the calibrated lower bound for its
reliability constraint; otherwise it retains the labelled heuristic score and
conservative fallback. Sparse observations never become a numeric success guarantee.

Completion resources are estimated independently from verified history. No tokens
are divided by an uncalibrated score. The [v2 reference](router-v2.md) documents
sample sufficiency, version separation, sources/units and policy weights. Unknown
versions and incomplete metrics cannot drive empirical selection.

The public checkpoint is not trained or fine-tuned by this project. Outcomes of
selected candidates do not establish how untried alternatives would have performed.
Tests use a small local mock HTTP server and do not load the checkpoint.

## Difficulty mode

Set `"laya_mode": "difficulty"` (default `per_candidate`, the mode above, unchanged).
Laya answers one `choice` question, "How demanding is this task for an AI coding
agent?", with five levels (`trivial`, `mechanical`, `routine`, `complex`, `open`).
No model name appears in the request. Each level maps to one candidate per host
through `level_to_candidate`; `xhigh`, `max` and Fable rungs stay reachable only by
escalation or approval, as before.

Contract, checked against laya-serve 0.3.26:

- One `POST <laya_url>/batch` per `route.py` call or scheduler cycle, whatever the
  number of tasks (1 to 64; more is an error, matching laya-serve `MAX_BATCH_STATES`).
  Body: `{"states": [...], "questions": {...}, "model": "english"}`. Each state has
  only `description` (English; above 60 words it is cut and a warning is printed) and
  `operation`. `ambiguous`, `critical` and `files` stay with the heuristic.
- `questions` holds `laya_rotations` copies (`difficulty#r0` ... `#r4`) of the same
  question. Option keys are `L1` to `L5` (level order). Rotation `r` lists them as a
  cyclic shift by `r`, so with 5 rotations every level takes every slot once.
  laya-serve renders options in key insertion order and returns probabilities in that
  order.
- Response: `{"results": [{"answers": {"difficulty#r0": {"probabilities": {"L1": ...}}}}]}`,
  one result per state, in order. The router requires keys `L1` to `L5`, values in
  [0, 1] summing to 1, and averages each level over the rotations.

The decision, its `laya` key and the `history.jsonl` event carry `level`,
`distribution` (averaged), `answer_confidence` (maximum of the averaged
distribution), `expected_level` (0-based, probability-weighted), `heuristic_level`,
`combination`, `final_level`, `preferred`, `batch_states` and `request_s`.

Combination with the heuristic: the heuristic rung maps to the highest level whose
candidate rung is not above it (level 0 if none). Same level: use it. One level
apart: the higher if the task is `critical`, else the lower. Two or more apart: the
heuristic decides and the event says `conflict: heuristic used`. The chosen level's
candidate is only a preference: floors, ceilings, approval, eligibility and failure
diagnosis still apply afterwards. If `answer_confidence` is below
`laya_min_confidence`, the heuristic decides and the backend is `laya (abstained)`.

`laya_min_confidence` 0.5 is **uncalibrated** (`laya_min_confidence_calibrated`
is `false` and every event says so). Treat it as a placeholder until outcomes exist.

Live check on 2026-10-09, laya-serve 0.3.26, checkpoint `english`, CPU, 127.0.0.1:8001:

- Rotation: one state, rotations `r0` (`L1..L5`) and `r1` (`L2..L5,L1`). The response
  listed the probabilities in the key order sent for both. Every key's probability
  changed between the two rotations (for example `L4` 0.4557 against 0.4922), and a
  repeat of `r0` returned identical values. So slot order reaches the model and the
  runs are deterministic.
- Latency: a batch of 8 tasks with 5 rotations (40 rows, one request) took 8.6 to
  8.7 s wall clock over 5 runs (about 0.21 s per row). One task with 5 rotations
  took 1.2 s. The default `laya_timeout_s` is 30 s: on this CPU a batch of 64 tasks
  would take about 70 s and time out, so raise `laya_timeout_s` for large batches.
- On eight sample tasks, `answer_confidence` ranged from 0.30 to 0.82; five of
  eight were below 0.5, so abstention is frequent at this threshold.

## Gate

Before `backend: laya` with `laya_mode: difficulty` becomes the default, the offline
evaluation must show that it saves tokens without under-routing more. Run it with:

```bash
python3 scripts/eval_difficulty.py --operator claude                 # live laya-serve on laya_url
python3 scripts/eval_difficulty.py --operator claude --no-laya       # heuristic only
python3 scripts/eval_difficulty.py --history-labels tests/data/history_candidates.local.jsonl
```

Inputs: `tests/data/difficulty_gold.jsonl` (labels are yours to fill, see
`tests/data/README.md`) and, optionally, exact labels derived from the history by
`scripts/labels_from_history.py` (failed at level k then succeeded at k+1 gives the exact
label k+1; a first-try success at level k is censored, "level <= k", and the evaluation
ignores it). The four strategies are the heuristic, Laya `per_candidate`, Laya `difficulty`
(raw argmax level) and `combined` (difficulty plus heuristic, as `route.py` uses it). Metrics:
exact accuracy, within-1 accuracy, under-routing and over-routing rates, and expected tokens
per task, overall and per operation. Expected tokens per candidate are the median of the
tokens in `history.jsonl`, else `expected_tokens_by_candidate` in the config; if neither
exists for a candidate the run stops and names it. An under-routed task costs its predicted
level plus one more execution at the next level. The report goes to `--out` (default
`difficulty-eval.json` next to `history.jsonl`).

PASS needs all of: `difficulty` or `combined` cuts expected tokens by at least
`gate_token_saving_min` (0.10) against the heuristic; its under-routing rate rises by at most
`gate_under_routing_max_increase` (0.02, absolute); every level has at least
`gate_min_tasks_per_level` (10) labelled tasks. Otherwise FAIL, with the reasons.

**Verdict 2026-10-09: FAIL (insufficient labels).** The 10 shipped gold tasks are unlabelled
and 0 exact labels exist in the history (31 censored, 0 exact, from
`labels_from_history.py --operator claude`), so every level has 0 labelled tasks and no
saving can be measured. This is a statement about missing data, not about Laya's quality.
Consequence: `backend: heuristic`, `laya_mode: per_candidate`. Re-run the command above
after labelling at least 50 tasks (10 per level). If it prints PASS, set
`"backend": "laya"` and `"laya_mode": "difficulty"` in `config/ladder.json` (or run
`install.py --backend laya`) and update this section.

`level_to_candidate` is left as shipped. Whether a different mapping fits better depends on
the labels, so it is pending them.

## Calibration

`scripts/calibrate_difficulty.py` needs the live server and at least `--min-labels` (default
20) exact labels; with fewer it refuses and writes nothing. It fits a temperature for the
averaged 5-way distribution (grid search on negative log-likelihood) and the lowest
`laya_min_confidence` whose answers reach `--target-accuracy` (0.8) at `--min-coverage`
(0.2). The result goes to `laya-calibration.json` next to `history.jsonl`, never into the
skill folder. When that file exists, `difficulty.py` applies the temperature to every answer
and uses its `laya_min_confidence` instead of the config value; the decision then reports
`min_confidence_calibrated: true`. The config value stays the fallback. An invalid file
stops routing with `laya calibration: invalid file`. Delete the file to go back.
laya's own `fit_abstention_thresholds` was not used: it takes raw logits records, not the
averaged distribution of this mode.

## Fine-tuning

The public checkpoint is zero-shot. Once you have labels, you can fine-tune it on this
question.

1. Export. `python3 scripts/export_difficulty_dataset.py --operator claude` merges the
   labelled rows of `tests/data/difficulty_gold.jsonl` with the exact labels from the history
   (censored ones are ignored), checks every row (level name, English description, known
   operation), prints the counts (gold, history exact, total, per level) and writes
   `difficulty-train.jsonl` next to `history.jsonl`. Use `--out` to choose another path outside
   the skill folder; inside it, the script refuses. With 0 labelled rows it refuses and writes
   nothing. `--check-laya` also loads the file with `laya.evals.Dataset` (needs `laya`).
2. Train. Open the official notebook (`laya_finetune_typed_decisions_2xT4_kaggle.ipynb` on
   Kaggle, or `laya_finetune_typed_decisions_mps.py` on Apple Silicon, both in the
   [laya repository](https://github.com/NandhaKishorM/laya)) and give it the exported file.
   Hold some labelled tasks out of training and evaluate on them, not on the training items.
3. Use the checkpoint. Put the local checkpoint directory in `laya_checkpoint` (a path
   instead of `english`) in `config/ladder.json`, then restart laya-serve. The router sends
   this value as `model` in every `/batch` request.
4. Re-evaluate. Run `python3 scripts/eval_difficulty.py --operator claude` on the held-out
   gold tasks and check the [gate](#gate) again, then `scripts/calibrate_difficulty.py`.

The notebook is not part of the installed `laya` package, so its dataset reader could not be
checked here. The export follows the `laya.evals` dataset row of laya 0.3.26: `state`
(`description`, `operation`), `questions` (the five rotated `choice` questions the router
asks, options `L1` to `L5`), `expected` (per question, the key of the labelled level) and
`tags`. If the notebook expects another layout, convert from this file; the labels are the same.
