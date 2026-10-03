# claude-router

Claude Code skill (`cc-router`) that routes each step of a task to a subagent with the model and effort that fit the step's complexity.

- **12-rung ladder:** Haiku → Sonnet low/medium/high → Opus medium/high/xhigh/max → Fable low/medium/high/xhigh, by family alias.
- **Parallel batches:** independent steps run at the same time, each on its own model and effort.
- **Justification:** every model choice is justified to the user and logged.
- **Approval:** Opus xhigh and above only run with approval, through the orchestrator's question and a Claude Code `permissions.ask` rule.
- **Escalation:** a failed step automatically moves up the ladder.
- **Subscription only:** refuses to run with an API credential in the environment; Fable is off by default.
- **Lean output:** caveman for text, ponytail for code.
- **History:** decisions and results in JSONL, the basis for training a [Laya](https://github.com/NandhaKishorM/laya) router.

## Requirements

- An up-to-date Claude Code (`claude update`), logged in with a subscription (Pro, Max, Team or Enterprise). Check with `/status`.
- Python 3 (standard library only).
- The [caveman](https://github.com/JuliusBrussee/caveman) and [ponytail](https://github.com/DietrichGebert/ponytail) plugins.

## Installation

```bash
git clone https://github.com/g4br/claude-router ~/.claude/skills/cc-router
```

In Claude Code, one command per message:

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

`install.py`:
- checks that no credential would move billing off the subscription and that the caveman and ponytail skills are installed;
- writes one agent per active rung to `~/.claude/agents/`;
- writes the `permissions.ask` rules for rungs that need approval to `~/.claude/settings.json`, keeping the rest of the file.

Restart Claude Code if `~/.claude/agents/` did not exist before.

## Usage

Ask Claude Code for a multi-step task, or call `/cc-router`. The full protocol is in [SKILL.md](SKILL.md).

## Files

| File | Purpose |
|---|---|
| `SKILL.md` | Orchestrator protocol |
| `config/ladder.json` | Ladder, heuristic, limits and settings |
| `scripts/install.py` | Builds the agents and the approval rules |
| `scripts/route.py` | Picks the rung for a step or a batch |
| `scripts/justify.py` | Logs the justification and the user's answer |
| `scripts/record.py` | Logs the step's result |
| `scripts/serve_laya.py` | Serves a fine-tuned Laya checkpoint (optional) |
| `references/examples.md` | 49 routing examples for software development |
| `references/laya.md` | How to replace the heuristic with a trained Laya router |

The history lives in `~/.claude/cc-router/history.jsonl`.

## License

MIT
