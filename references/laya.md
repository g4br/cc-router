# Switching the heuristic for the Laya router

Repository: https://github.com/NandhaKishorM/laya. The fine-tuning guide is in `docs/finetune.md` and the notebook in `notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb`.

## Why the history alone is not enough

`history.jsonl` only records the result of the configuration that was chosen. It does not say whether a cheaper rung would have handled the same step. For the router to learn P(success | rung) you need the counterfactual: the same step run on other rungs.

## Stages

1. **Offline collection.**
   - Pick 300 or more `state` entries from the history, covering every operation.
   - Run each step on the rungs in headless mode (`claude -p` with the agents installed), always with the same delegation prompt.
   - Judge success by the step's objective criterion.
   - If you can, run each step-and-rung pair two or three times. The fraction of successes is exactly the kind of target Laya's training uses (see the next item).
   - Rungs 6 to 11 need approval. Ask the user for a single approval for the batch, with the list of steps, rungs and repetitions. Run each rung as the main session (`claude -p --agent exec-opus-xhigh "<delegation prompt>"`), not through the Agent tool: in `-p` mode nobody is there to answer the `permissions.ask` confirmation.
   - **The collection runs on the subscription and spends its limit.** In `-p` mode, an `ANTHROPIC_API_KEY` that is present is used without asking. Before starting, run `python <skill>/scripts/install.py`, which stops if it finds a non-subscription credential, and check `/status`. Do not use `--bare`: that mode does not read the subscription login. On a server without a browser, generate a subscription token with `claude setup-token` and export `CLAUDE_CODE_OAUTH_TOKEN`.
   - Spread the collection across the subscription's limit windows instead of running everything at once. Only collect on active rungs: with Fable off, it stays out of collection and training.
   - If you need a judge where there is no objective criterion, use `claude -p` too, never a direct API call.

2. **Dataset in the notebook's format.**
   - Training (RLCD) uses target distributions, not hard labels. Each dataset row has `state`, `questions` and `gold`.
   - `state` is the state JSON.
   - `questions` has one `choice` question per rung that was run, with `instructions` equal to `laya_question` from `ladder.json` formatted with the rung's `label`, and `criteria` identical to `route.py`'s: A = yes, B = no. Rungs that were not run stay out of the row.
   - `gold[agent]` is `{"probabilities": {"A": p, "B": 1 - p}, "label": "A" or "B"}`, where p is the fraction of successes (1 or 0 with a single run) and `label` is the most likely option.
   - The model learns that exact text. If `laya_question`, the `label`s or the `criteria` change, you have to retrain.
   - In the notebook, replace the two `load_dataset` calls with your file and keep this row schema.

3. **Base checkpoint.** The notebook starts from `MODEL_ID = "convaiinnovations/laya"`, the English checkpoint (ModernBERT-large, 421M). The skill's state descriptions and questions are in English, so the notebook runs unchanged and `laya_checkpoint` is `english` in `ladder.json`. If you write descriptions in another language, use the multilingual checkpoint (mmBERT-base, 322M): change `MODEL_ID` and `laya_checkpoint`, and check that the training script accepts mmBERT, which has not been verified.

4. **Fine-tuning.** Run the notebook on Kaggle with `GPU T4 x2`. The guide estimates 4 to 5 hours for about 30 thousand questions over four epochs. Hold out 20% of the data yourself for evaluation: the notebook's internal calibration slice is small on purpose and is not meant for validation.

5. **Calibration.**
   - The notebook fits one temperature per question type and writes it to `rl_agent_config.json`. Copy the checkpoint with that file, because without it the calibration is lost.
   - Check the ECE on your evaluation set. Without calibration, `success_threshold` means nothing.

6. **Baseline.**
   - Train embeddings of `description` + the structured fields in a LightGBM, on the same split.
   - Keep Laya only if it wins, or ties with some operational advantage.

7. **Serve with `scripts/serve_laya.py`, not with `laya-serve` directly.**
   - `laya-serve` only knows the three public checkpoints. An unknown name in the request's `model` field is ignored without error and the request falls back to language routing, which would send the router to an untrained checkpoint.
   - `serve_laya.py` puts the fine-tuned checkpoint in place of the `laya_checkpoint` name and serves the same HTTP contract, listening on the host and port of `laya_url`:

     ```bash
     pip install "laya[serve]"
     python <skill>/scripts/serve_laya.py /path/to/finetuned_checkpoint
     ```

   - `route.py` sends `"model": laya_checkpoint` in every request, so no request can drift to another checkpoint.
   - Set `LAYA_DEVICE` to choose the device. If the server is exposed beyond localhost, set `LAYA_API_KEY` on the server and in Claude Code's environment: the server then requires the `Authorization` header and `route.py` sends it.

8. **Turn it on.**
   - In `ladder.json`, set `"backend"` to `"laya"` and check `laya_url` and `laya_checkpoint`.
   - Choose `success_threshold` on the evaluation set by plotting cost against failure rate: a higher threshold escalates less but spends more.

## Version changes behind the aliases

The rungs use aliases (`opus`, `sonnet`...), so the question text does not change when a new version ships, and the checkpoint keeps accepting requests. What changes is the meaning: P(success) for "Opus at high effort" was learned on the previous version. When an alias changes version:
- split the history at the date of the change;
- collect a new sample with the current version and check calibration (ECE) on it;
- if calibration got worse, retrain on the new period, or on both periods with more weight on the new one.

## Decision rule with Laya

The router asks for each rung's P(success) in a single call. It picks the cheapest rung, between the escalation floor and the operation's ceiling, whose probability clears `success_threshold`. If none does, it goes to the ceiling. Every rung's probabilities are logged in the history of each decision.

## Collection cost with 12 rungs

Running each step on every active rung spends a lot of the subscription limit, and repeating runs multiplies it. If Fable is on, it adds to that. One option is to run every rung only on a smaller sample. For the remaining steps, run from the heuristic's rung downward until the first failure, which already gives each step's success boundary.
