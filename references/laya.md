# Using the public Laya checkpoint

`cc-router` uses the ready-made English checkpoint [`convaiinnovations/laya`](https://huggingface.co/convaiinnovations/laya) for both Claude Code and Codex. There is no export or training step. The skill sends its task descriptions in English and selects Laya's `english` model explicitly. The Laya server downloads the checkpoint when it loads the model and keeps it available for later requests.

## Start Laya locally

Install the official HTTP server in a Python 3.10+ environment, then run it on loopback:

```bash
python -m pip install "laya[serve]"
LAYA_HOST=127.0.0.1 LAYA_MODELS=english laya-serve
```

The server exposes `http://127.0.0.1:8000/v1/systemone`. One instance serves both operators because they use the same public checkpoint. Keep it running while routing. See Laya's [HTTP API documentation](https://github.com/NandhaKishorM/laya/blob/main/docs/http-api.md) for device, preload, port and authentication settings. If you change its port, update both URLs in `config/ladder.json`. If you set `LAYA_API_KEY` on the server, provide the same value to `route.py`.

The default `backend` is `laya` and `laya_enabled_operators` contains both `claude` and `codex`. If the server is unavailable, `route.py` reports the outage and uses the heuristic. A response error from a running server stops routing so a broken request is visible. You can explicitly use `"backend": "heuristic"` in `config/ladder.json`.

## What the decision means

For each eligible rung, the router asks Laya whether the rung's model profile suits the task and is likely to complete it on the first attempt without rework. It considers the escalation floor, operation ceiling, user ceiling and approval rules. The first rung with score at least `success_threshold` (default 0.8) is selected; if none clears it, the ceiling is selected. These are **zero-shot estimates** for this project's question. The public checkpoint has not been validated against this project's task outcomes, so the threshold must not be described as a measured 80% success guarantee.

When every eligible rung has at least `min_cost_samples` (default 20) observed token counts for the operation, the router compares median tokens divided by the Laya score and selects the lowest value among rungs above the threshold. With incomplete coverage, it uses ladder order. Observations come from completed routed steps, including heuristic fallback and Laya decisions. This comparison is descriptive: a run on one rung does not establish the cost or outcome of another rung for the same task.

After verifying a step, record its result and any token count reported by the host:

```bash
python <skill>/scripts/record.py <id> success 48210 37.5 --no-rework true
```

`--no-rework true` means the criterion passed on the first attempt without correction or retry. Use `false` if the final result needed rework. If you learn later that a label was wrong, use `python <skill>/scripts/feedback.py <id> false` (or `true` for a verified first-pass success). The history is stored separately for Claude Code and Codex under `~/.claude/cc-router/history.jsonl` and `~/.codex/cc-router/history.jsonl`.

Model aliases may resolve to new versions over time. Compare outcomes by date when that happens. Adjusting `laya_question`, rung labels or the threshold changes what Laya is asked; check actual outcomes before relying on the new scores. The official [model card](https://huggingface.co/convaiinnovations/laya) describes the checkpoint's general abilities and limits.
