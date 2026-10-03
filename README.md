# cc-router

Claude Code and Codex skill (`cc-router`) that routes delegated steps to a subagent with a model and effort suited to the step.

- **Operator-aware ladders:** Claude Code uses Haiku → Sonnet → Opus → Fable; Codex uses Luna → Sol → Astra. The router detects the active operator or accepts `CC_ROUTER_OPERATOR=claude|codex`.
- **Parallel batches:** independent steps run at the same time, each on its own model and effort.
- **Justification:** every model choice is justified to the user and logged.
- **Approval:** high-cost rungs require an explicit answer; Claude Code also uses a `permissions.ask` rule.
- **Escalation:** a failed step automatically moves up the ladder.
- **Claude Code subscription:** refuses to run when an Anthropic API credential would change billing; Fable is off by default.
- **Output helpers:** caveman for text and ponytail for code, with installation paths for Claude Code and Codex.
- **History:** decisions and results in JSONL, the basis for training a [Laya](https://github.com/NandhaKishorM/laya) router.

## Requirements

- Claude Code with a subscription (check `/status`) or Codex with native subagent tools.
- Python 3 (standard library only).
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

## Files

| File | Purpose |
|---|---|
| `SKILL.md` | Orchestrator protocol |
| `config/ladder.json` | Operator-specific ladders, heuristic, limits and settings |
| `scripts/install.py` | Builds the agents and the approval rules |
| `scripts/route.py` | Picks the rung for a step or a batch |
| `scripts/justify.py` | Logs the justification and the user's answer |
| `scripts/record.py` | Logs the step's result |
| `scripts/serve_laya.py` | Serves a fine-tuned Laya checkpoint (optional) |
| `references/examples.md` | 49 routing examples for software development |
| `references/laya.md` | How to replace the heuristic with a trained Laya router |

History lives in `~/.claude/cc-router/history.jsonl` or `~/.codex/cc-router/history.jsonl`, according to the detected operator. Laya is trained only for the Claude Code ladder.

## License

MIT
