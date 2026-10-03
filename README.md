# cc-router

Claude Code and Codex skill (`cc-router`) that routes delegated steps to a subagent with a model and effort suited to the step.

- **Operator-aware ladders:** Claude Code uses Haiku → Sonnet → Opus → Fable; Codex uses Luna → Sol → Astra. The router detects the active operator or accepts `CC_ROUTER_OPERATOR=claude|codex`.
- **Parallel batches:** independent steps run at the same time, each on its own model and effort.
- **Justification:** every model choice is justified to the user and logged.
- **Approval:** high-cost rungs require an explicit answer; Claude Code also uses a `permissions.ask` rule.
- **Escalation:** a failed step automatically moves up the ladder.
- **Claude Code subscription:** refuses to run when an Anthropic API credential would change billing; Fable is off by default.
- **Output helpers:** caveman for text and ponytail for code, with installation paths for Claude Code and Codex.
- **Laya:** uses the public [checkpoint](https://huggingface.co/convaiinnovations/laya) directly for both operators, with a heuristic fallback when the local server is unavailable.
- **History:** decisions, verified outcomes and token counts in operator-specific JSONL files.

## Requirements

- Claude Code with a subscription (check `/status`) or Codex with native subagent tools.
- Python 3.10+ for the Laya server; the routing scripts use only the standard library.
- For the output helpers: Node.js and the [caveman](https://github.com/JuliusBrussee/caveman) and [ponytail](https://github.com/DietrichGebert/ponytail) integrations. Ponytail's Codex hooks need `node` on the shell's PATH.

## Installation

### Codex

```bash
git clone https://github.com/g4br/cc-router ~/.codex/skills/cc-router
```

Codex's native agent tool uses the model and effort returned by `route.py`; no generated agent files are needed.

Install caveman's **skill** for Codex, using the command from its [official README](https://github.com/JuliusBrussee/caveman):

```bash
npx skills add JuliusBrussee/caveman --skill '*' -a codex --yes -g
```

This installs the skill, not caveman's optional proxy. Install the [ponytail Codex plugin](https://github.com/DietrichGebert/ponytail) with its official commands:

```bash
codex plugin marketplace add DietrichGebert/ponytail
codex plugin add ponytail@ponytail
```

Start Codex, open `/hooks`, review and trust ponytail's two lifecycle hooks, then start a new thread. For the Codex desktop app, restart the app after installation. `node` must be on the PATH used by the hooks.

### Claude Code

```bash
git clone https://github.com/g4br/cc-router ~/.claude/skills/cc-router
```

Install the two plugins, one command per message:

```
/plugin marketplace add JuliusBrussee/caveman
/plugin install caveman@caveman
/plugin marketplace add DietrichGebert/ponytail
/plugin install ponytail@ponytail
```

Then:

```bash
python ~/.claude/skills/cc-router/scripts/install.py
```

In Claude Code, `install.py`:
- checks that no credential would move billing off the subscription and that the caveman and ponytail skills are installed;
- writes one agent per active rung to `~/.claude/agents/`;
- writes the `permissions.ask` rules for rungs that need approval to `~/.claude/settings.json`, keeping the rest of the file.

Restart Claude Code if `~/.claude/agents/` did not exist before.

In Codex, `install.py` detects the operator and exits without changing Claude Code files. If detection is unavailable, set `CC_ROUTER_OPERATOR` explicitly. The router never uses an API key as an operator signal.

## Usage

Ask the operator to use `cc-router` for a task suited to delegation. The full protocol is in [SKILL.md](SKILL.md). Routing depends on the host's permission to delegate and its available models.

## Use the public Laya checkpoint

Install Laya once:

```bash
python -m pip install "laya[serve]"
```

Run the minimal SDK example from this repository in another terminal. It asks Laya to choose `low`, `medium` or `high` effort for `gpt-6.1-sol` on a sample task; the first run downloads the checkpoint:

```bash
python laya-example.py
```

Pass a different task in English to try it: `python laya-example.py "Debug a failing parser test"`.

For regular `cc-router` routing, start the bundled launcher for the official local server:

```bash
python scripts/serve_laya.py
```

The example and server launcher test a small PyTorch operation on available GPUs. They use a working GPU or fall back to CPU, including on an MX350 with a PyTorch build that cannot run `sm_61` kernels. The server listens on `127.0.0.1:8000` and loads only the English checkpoint by default.

Both operators use `http://127.0.0.1:8000/v1/systemone` by default. `backend` is already set to `laya` in `config/ladder.json`; if the server is unavailable, routing falls back to the heuristic. No training or GPU training job is needed. Laya's zero-shot scores for this model-selection question are unvalidated locally, so continue to verify outcomes. See the [Laya guide](references/laya.md) for setup and interpretation.

The skill translates each task summary into English for Laya to select the model and effort. It keeps the user's primary language for the delegated agent's report and the final response.

After each routed step, record whether it passed on the first attempt without rework and include reported token usage when available:

```bash
python scripts/record.py <decision-id> success 48210 37.5 --no-rework true
```

Token cost is tracked separately from the outcome because one observed run cannot establish which untried model would have used the fewest tokens.

## Files

| File | Purpose |
|---|---|
| `SKILL.md` | Orchestrator protocol |
| `laya-example.py` | Example of Laya choosing effort for a fixed model |
| `config/ladder.json` | Operator-specific ladders, heuristic, limits and settings |
| `scripts/install.py` | Builds the agents and the approval rules |
| `scripts/route.py` | Picks the rung for a step or a batch |
| `scripts/justify.py` | Logs the justification and the user's answer |
| `scripts/record.py` | Logs the step's result |
| `scripts/feedback.py` | Corrects a no-rework label discovered after recording |
| `scripts/laya_device.py` | Checks which GPU can run PyTorch, with CPU fallback |
| `scripts/serve_laya.py` | Starts the official Laya server on the selected device |
| `references/examples.md` | 49 routing examples for software development |
| `references/laya.md` | Public Laya checkpoint setup and decision limits |

History lives in `~/.claude/cc-router/history.jsonl` or `~/.codex/cc-router/history.jsonl`, according to the detected operator.

## License

MIT
