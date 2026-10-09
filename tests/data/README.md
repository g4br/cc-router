# Difficulty gold set

`difficulty_gold.jsonl` holds tasks for the offline evaluation
(`scripts/eval_difficulty.py`) and the calibration (`scripts/calibrate_difficulty.py`).
One JSON object per line:

```json
{"description": "<English, at most 60 words>", "operation": "<operation>", "label": null, "source": "example"}
```

- `operation`: a key of `base_level_by_operation` in `config/ladder.json` (for example `read`, `tweak`, `implementation`, `debugging`).
- `label`: `null` until you fill it, then one of `trivial`, `mechanical`, `routine`, `complex`, `open`.
  The label is the **minimum level that completes the task without rework**: the cheapest level
  whose candidate (`level_to_candidate`) would have finished it on the first attempt.
- `source`: free text, for example `example` or `real`.

The 10 shipped lines are generic examples with `label: null`. Nothing is labelled for you: the
tools skip unlabelled lines and count them. You fill the labels.

The gate needs at least `gate_min_tasks_per_level` (default 10) labelled tasks in every level,
so 50 or more in total. To get candidates, export your recent real delegations (the last ~150 is a
good size) from the history with:

```bash
python3 scripts/labels_from_history.py --operator claude --last 150 --out tests/data/history_candidates.local.jsonl
```

That file has `label` and `censored` already set where the history proves them (see the script
docstring). Review them, copy the lines you trust into the gold set and label the rest by hand.
Files named `*.local.jsonl` are ignored by git, because they may hold private task text.
