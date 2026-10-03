---
name: cc-router
description: Route substantial independent task steps to subagents with a model and reasoning effort suited to each step. Detects Claude Code or Codex, uses that operator's ladder, explains decisions, and records outcomes. Use for explicit model routing, cost-aware delegation, or multi-step work that benefits from subagents.
---

# cc-router: operator-aware model and effort router

Each delegated step goes to a subagent whose model and effort are chosen by `scripts/route.py`. The main session stays on its selected model. Plan, justify and verify in the main session; execute delegated steps through the chosen operator's ladder. Follow the host's delegation policy: this skill does not grant permission to spawn agents when higher-priority instructions prohibit it.

Determine the user's primary language from their request and conversation. For each step, translate a short, faithful task summary into English for the `description` field; Laya reads this summary when choosing the model and effort together. Preserve paths, commands, identifiers, constraints and the verification criterion. Put the user's language in `user_language` (for example, `pt-BR`). Address the user in that language, and have subagents report in it unless the user explicitly requests another output language.

The ladders live in `config/ladder.json`. `route.py` detects Codex from `CODEX_THREAD_ID` or `CODEX_SESSION_ID`, and Claude Code from `CLAUDECODE` or `CLAUDE_CODE_REMOTE`. Set `CC_ROUTER_OPERATOR=codex|claude` when neither marker is available or both are present. API keys and `CODEX_HOME` are not operator markers. The returned `operator` field is authoritative for delegation.

The Claude Code ladder is ordered first by family and then by effort:

| Rung | Agent | Model | Effort | Approval | Active by default |
|---|---|---|---|---|---|
| 0 | `exec-haiku` | `haiku` | (none) | no | yes |
| 1 | `exec-sonnet-low` | `sonnet` | low | no | yes |
| 2 | `exec-sonnet-medium` | `sonnet` | medium | no | yes |
| 3 | `exec-sonnet-high` | `sonnet` | high | no | yes |
| 4 | `exec-opus-medium` | `opus` | medium | no | yes |
| 5 | `exec-opus-high` | `opus` | high | no | yes |
| 6 | `exec-opus-xhigh` | `opus` | xhigh | **yes** | yes |
| 7 | `exec-opus-max` | `opus` | max | **yes** | yes |
| 8 | `exec-fable-low` | `fable` | low | **yes** | **no** |
| 9 | `exec-fable-medium` | `fable` | medium | **yes** | **no** |
| 10 | `exec-fable-high` | `fable` | high | **yes** | **no** |
| 11 | `exec-fable-xhigh` | `fable` | xhigh | **yes** | **no** |

About the ladder:
- Models are family aliases: each points to the latest version of the family in Claude Code, so a new version comes in without touching the skill. Details in [Model aliases](#model-aliases).
- The current Haiku takes no effort, so rung 0 has no such field. If a future version does, add rungs in `ladder.json`.
- A rung with `"active": false` is not installed and becomes the ceiling: the router never picks above the last active rung. Inactive rungs may only sit at the top.
- Fable is off by default because, depending on the plan, it bills usage credits instead of drawing on the subscription (see [Subscription only](#subscription-only)).
- The order between Opus max and Fable low is an assumption; the history will tell whether it holds.

The Codex ladder has Luna low (rung 0), Sol low/medium/high (1–3), and Astra medium/high/xhigh/max (4–7). These are routing roles, not claims of cross-provider performance equivalence. Codex does not use the Fable rungs or Claude Code agent files. Check available models and supported effort levels in the host before delegation; if a chosen setting is unavailable, do not report that it ran as selected. Route again with an available ceiling or execute directly and disclose the actual model.

In the commands below, `<skill>` is this skill's base directory, shown when it loads.

## Before first use

In Codex, install this folder as a Codex skill (for example, under `~/.codex/skills/cc-router`) and invoke it in a session with native subagent tools. Install caveman's Codex skill and ponytail's Codex plugin using the commands in [README.md](README.md#codex). Ponytail's hooks require `node` on the shell's PATH; review and trust them under `/hooks`, then start a new thread. No generated agent files or Claude Code settings are needed. `install.py` detects Codex and exits without changing Claude Code files.

For either operator, start the public Laya checkpoint as described in [references/laya.md](references/laya.md). The router uses it by default and falls back to the heuristic while the local server is unavailable.

In Claude Code, install the following plugins, one command per message:


```
/plugin marketplace add JuliusBrussee/caveman
/plugin install caveman@caveman
/plugin marketplace add DietrichGebert/ponytail
/plugin install ponytail@ponytail
```

Then:

```bash
python <skill>/scripts/install.py
```

For Claude Code, the script:
- checks that no credential would move billing off the subscription (see below);
- checks that the skills in `agent_skills` are installed;
- writes one agent file per active rung to `~/.claude/agents/` and deletes the file of any inactive rung;
- writes a `permissions.ask` rule `Agent(<agent>)` to `~/.claude/settings.json` for each rung that needs approval. It only rewrites `Agent(exec-...)` rules and keeps the rest of the file.

Run it again whenever the ladder or this skill's agent instructions change. If `~/.claude/agents/` did not exist when the session started, restart Claude Code so it sees the agents. `route.py` stops with an error if the chosen agent is not installed.

## Claude Code subscription

The Claude Code path runs on the subscription login (Pro, Max, Team or Enterprise). Its subagents count against the same usage limit as the main session. No script in this skill calls the Anthropic or OpenAI API. The Claude credential check does not run in Codex; Codex account access and billing follow the host's configuration.

There are three ways billing can leave the subscription, and the skill handles each:

1. **API credential in the environment.** `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `apiKeyHelper`, `ANTHROPIC_PROFILE`, `ANTHROPIC_BASE_URL` or a provider such as Bedrock take precedence over the subscription login. In `-p` mode the API key is used without asking. `install.py` and `route.py` stop with an error if they find any of them in the environment or in the user's and project's `settings.json`. This check only sees the environment that reaches the shell; the definitive confirmation is `/status`, which shows the credential in use.
2. **Fable billing usage credits.** Off by default. To turn it on, open `/model`: if the Fable row does not show "Requires usage credits", it is within your plan's limit. Then set `"active"` to `true` on the four Fable rungs in `ladder.json` and run `install.py` again.
3. **Usage credits after hitting the limit.** If usage credits are enabled on the account, usage can continue past the limit and be billed. Keeping them off guarantees that work stops at the limit instead of billing. This is an account setting, not a skill setting: https://support.claude.com/en/articles/12429409-extra-usage-for-paid-claude-plans.

## Per-step protocol

1. **Break the task into steps**, each with an objective verification criterion: the test that must pass, the script that must run, the output that must validate.

2. **Decide whether the step is worth delegating.** A subagent starts with an empty context, so delegating has a fixed cost. Reading a file, a grep or a one-line edit you do directly, without routing. Steps that depend on a lot of this conversation's context are only worth delegating if you can pass that context in the prompt. Independent steps go together in a parallel batch: see [Parallel batches](#parallel-batches), which applies these same steps to several at once.

3. **Build the state and run the router:**

   ```bash
   python <skill>/scripts/route.py '{"description": "fix grid reader for lon 0-360 and 12Z accumulation", "user_language": "pt-BR", "operation": "implementation", "files": 2, "ambiguous": false, "critical": true}'
   ```

   The output is one JSON line and includes `operator` (`claude` or `codex`):

   ```json
   {"id": "3f9a1c2e", "operator": "claude", "batch": null, "description": "fix grid reader for lon 0-360 and 12Z accumulation", "user_language": "pt-BR", "agent": "exec-sonnet-high", "label": "Sonnet at high effort", "model": "sonnet", "effort": "high", "suited_for": "clear scope where verification matters and edge cases are likely", "reason": "operation=implementation (rung 2); +1 critical", "below": "Sonnet at medium effort: day-to-day work with a clear scope", "needs_approval": false, "alternative": null, "backend": "heuristic"}
   ```

   The JSON goes inside single quotes in the shell. If the description has an apostrophe, rephrase it without one.

4. **Justify the choice to the user**, always, before delegating. The format is in [Justification](#justification).
   - If `needs_approval` is `false`, show the justification and proceed.
   - If it is `true`, **ask and wait for the answer**, as described in [Approval](#approval). Do not delegate before that.

5. **Log the justification** with the user's answer:

   ```bash
   python <skill>/scripts/justify.py 3f9a1c2e auto 'Sonnet high: ...'
   ```

   The answer is `auto` for a rung without approval, or `approved`/`declined` for what the user answered. The script rejects `auto` on a rung that needs approval.

6. **Delegate using the detected operator:**
   - **Claude Code:** call Agent with `subagent_type` equal to `agent`. Do not pass `model`: the generated agent frontmatter already selects it.
   - **Codex:** use the native subagent tool with the returned `model` and `effort` when it supports both. The `agent` field is a routing identifier for history, not a Codex agent type. Respect the host's concurrency and permission rules. Do not launch a second CLI or API session merely to force a model choice.

   The delegation prompt needs these details, because the subagent may not see this conversation:
   - the goal of the step;
   - the context it needs (files, decisions already made, project conventions);
   - the verification criterion.
   - the `user_language` and an instruction to report in that language. Keep the task's explicitly requested output language for files or deliverables.

   The report format is already in the agent's system prompt.

7. **Check the result yourself.** The subagent's report is a claim, not proof. Apply the step's criterion: run the test, open the file. Only what passes the criterion counts as success.

8. **Record the result** with the decision `id`:

   ```bash
   python <skill>/scripts/record.py 3f9a1c2e success 48210 37.5 --no-rework true
   ```

   The two trailing numbers (tokens and duration in seconds) come from the subagent's completion notification; leave them out if they are not available. The result is one of:
   - `success`: passed the criterion;
   - `failure`: delivered, but wrong or incomplete;
   - `escalated`: the agent answered `RESULT: ESCALATE`.

   For a successful step, set `--no-rework true` only when its criterion passed on the first attempt without corrections or retries; otherwise set `false`. Record tokens when the host reports them: the quality outcome and token cost are separate observations. If later work reveals rework, correct the label with `python <skill>/scripts/feedback.py <id> false`.

   `record.py` rejects the result if there is no logged justification, if the decision needed approval and was not approved, or if it was declined.

9. **On failure or escalation**, run `route.py` again with the same state plus `"failed_with": "<agent that failed>"`.
   - The decision jumps `escalation_jump` rungs (2 by default). Raising only the effort of the same model rarely fixes what it could not.
   - Adjust the delegation prompt with what went wrong.
   - The new decision goes through steps 4 and 5 again. In the justification, say what failed on the previous rung.
   - After the second escalation of the same step, the problem is usually the step's definition, not the model. Before escalating again, revisit the step: split it or clarify the criterion.
   - If the router says the step already failed at the ceiling, stop and ask the user: repeating at the top only spends.

## Parallel batches

Independent steps may run at the same time, each on its own rung, when the host permits parallel delegation.

**What goes in the same batch**
- Steps that do not depend on each other's results.
- Steps that do not write to the same files. In a batch, each state declares `targets`: the files or folders the step writes, or `[]` if it only reads. The router rejects the batch if two steps share a target, including a folder that contains the other's file. Parallel agents writing to the same file overwrite each other without warning. For those steps, run them in sequence or pass `isolation: "worktree"` in the Agent call and merge the changes afterwards.
- At most `max_parallel` steps (8 by default, in `ladder.json`), further limited by the host's available concurrency. For Claude Code, each agent also draws on the subscription usage window.

**Batch flow**

1. **Run the router once with the list of states:**

   ```bash
   python <skill>/scripts/route.py '[{"description": "list call sites of calc_eto", "user_language": "pt-BR", "operation": "search", "files": 1, "ambiguous": false, "critical": false, "targets": []}, {"description": "script for an ERA5-Land point series", "user_language": "pt-BR", "operation": "implementation", "files": 1, "ambiguous": false, "critical": false, "targets": ["scripts/era5_point.py"]}]'
   ```

   The output is a list of decisions, one per step, in the same order, each with its own `id` and all with the same `batch`. If any step is invalid, nothing is logged.

2. **Show the user a table** with step, model and effort, justification, and whether it needs approval. Each row's justification follows [Justification](#justification).

3. **Log the justifications** of the steps that need no approval. The `justify.py` commands can be chained in a single shell call.

4. **Fire the steps that need no approval together** with the operator's native agent tool and the settings from step 6 of the per-step protocol.

5. **For steps that need approval**, ask with the host's user-input tool, log the answers, and run only the approved steps. Claude Code also enforces its generated `permissions.ask` rule.

6. **Check and record each step as it finishes**, without waiting for the whole batch. Failed steps can go back together in a new batch, with `failed_with` in each state, as long as they remain independent.

7. **At the end, report a table** with step, model and effort, and result.

## Output helpers

Claude Code uses caveman and ponytail as plugins. Codex uses caveman as a skill and ponytail as a plugin; see [installation](README.md#codex). Follow the host and project's rules if they conflict with these helpers.

Everything this skill produces comes out with the least text and code:
- **caveman** shortens text: answers, justifications, tables and the subagents' reports. Code, commands, paths and error messages stay exact.
- **ponytail** shortens code: the least code that works, no speculative abstractions, standard library before dependencies. Validation, error handling and security are never cut.

**In the main session (you):** in Claude Code, ponytail turns itself on through its session-start hook. In Codex, its hooks take effect after they are trusted and a new thread starts. Invoke an installed helper skill when its rules are needed and are not already in context.

**In Claude Code subagents:** `install.py` preloads both in each agent's frontmatter (`agent_skills` in `ladder.json`) and stops with an error if either is missing. In Codex, native subagents use the skills and hooks available to that host; do not assume that the Claude Code frontmatter applies there.

**What does not shrink:**
- the approval question: full justification, cost and options, because it is the user's spending decision;
- security warnings and confirmations, which caveman itself returns as full sentences;
- the content of the justification: terse, but it still answers both questions in the next section.

**When code form conflicts,** the project's style rules win (CLAUDE.md and style skills): ponytail decides what exists; the style rules decide how it is written.

**Do not use the caveman proxy** (`caveman claude`). The skill does not need it, and traffic would go through a local address that `route.py` treats as a non-subscription credential (`ANTHROPIC_BASE_URL`).

## Justification

One or two terse sentences per step, starting with the step and the chosen model. It answers two questions:

- **Why this rung:** what, in this concrete step, calls for this model and effort. Cite the step (the file, the edge case, the risk), not just the category.
- **Why not the rung below:** what the rung below lacks for this step. On rung 0, say why you did not do the step directly. On an escalation, say what failed on the previous rung.

Ground it in the router output fields: `suited_for` of the chosen rung, `below` (the rung below and what it is suited for) and `reason` (the operation and flags that added up, or Laya's probabilities on the Claude ladder). These are task-fit heuristics. **Do not invent model behavior** ("Sonnet would get this wrong"): justify by what the step requires, compared with what each rung is suited for.

Examples:

> **S2 → Sonnet high.** Grid reader: lon 0–360, 12Z accumulation. Edge-case bug leaks silently into maps. Clear scope + edge cases = high. Medium: no such risk.

> **S1 → Haiku.** Banners `# ====` → `#----`, swap with no decisions. Delegated: 2k-line file, diff stays out of this context.

> **S3 → Opus medium (escalation).** Sonnet medium: upsert without natural key, duplicated rows in test. Step needs data-model design = design judgment. Sonnet high: edge cases within an already-designed scope.

## Approval

Rungs marked `approval: true` in the selected ladder only run with the user's explicit approval. When `needs_approval` is `true`:

1. **Ask with the host's user-input tool.** The question carries the justification and expected usage impact. The options are:
   - approve the chosen rung (for example, "Approve Opus xhigh");
   - use the `alternative`, when it is not `null` (the most capable rung below that needs no approval);
   - do not run this step.

   Do not mark any option as recommended: spending is the user's call.

2. **Depending on the answer:**
   - **Approved:** log `approved` with `justify.py` and delegate. Claude Code will also show its native `permissions.ask` confirmation.
   - **Chose the alternative:** log `declined` and run `route.py` with the same state plus `"user_ceiling": "<alternative>"`. The new decision follows the normal protocol.
   - **Do not run:** log `declined` and treat the step as pending in the final report.

3. **No way to ask:** do not delegate these rungs. Leave the step pending, say which rung it asked for and why, and carry on with independent steps.

## Filling in the state

| Field | Type | Meaning |
|---|---|---|
| `description` | text | Faithful English summary of the user's step; Laya uses it to choose model and effort |
| `user_language` | text, optional for direct CLI callers | User's primary response language, such as `pt-BR`; copied to router output, not sent to Laya |
| `operation` | text | One of the categories below |
| `files` | integer | How many files or artifacts the step reads or changes substantially |
| `ambiguous` | bool | `true` if the step allows more than one reasonable interpretation or depends on a design decision not yet made |
| `critical` | bool | `true` if a mistake is costly: production, irreversible data, security, silent numerical error, or output other steps will consume without review |
| `failed_with` | text, optional | Agent that failed this step (escalation only) |
| `user_ceiling` | text, optional | Highest agent the user accepted (when they chose the alternative) |
| `targets` | list, required in a batch | Files or folders the step writes; `[]` if read-only |

| `operation` | Base rung | When to use |
|---|---|---|
| `search` | 0 | find definitions and call sites, list files, scan logs |
| `read` | 0 | summarize a file or traceback, extract values |
| `mechanical_edit` | 0 | replace, rename, format, convert format, no decisions |
| `tweak` | 1 | small change following an existing pattern (new argument, new config entry, simple test) |
| `implementation` | 2 | write a function, script or endpoint with a clear scope |
| `writing` | 2 | documentation, README, technical text |
| `data_analysis` | 2 | load, aggregate, compare, plot |
| `debugging` | 3 | find the cause of an error or a failing test |
| `review` | 4 | critical review of code or results |
| `architecture` | 5 | design a structure or contract, choose an approach |
| `research` | 6 | open problem, algorithm with no reference, model diagnosis |
| `security` | 6 | security review or vulnerability hunting (ceiling at rung 7) |
| `investigation` | 9 | unknown root cause spanning several systems |
| `long_task` | 9 | long cohesive block that loses meaning if split |

The `files > 3`, `ambiguous` and `critical` fields each add one rung.

Base rungs above the active ladder are capped at its last rung. On the Claude ladder, `security` stops at Opus max; Fable reroutes flagged cybersecurity requests to an earlier model. On the Codex ladder, `security`, `investigation` and `long_task` cap at Astra max.

**When unsure about the operation or the flags, read `references/examples.md`.** It has 49 software-development cases, one block per rung, all checked against this router.

Fill it in honestly, without inflating it "to be safe". History goes to `~/.claude/cc-router/history.jsonl` or `~/.codex/cc-router/history.jsonl`, according to the operator. Both ladders use the same public Laya checkpoint. When `backend: laya` is selected but the operator is absent from `laya_enabled_operators`, routing stays heuristic and reports that fallback in `backend`.

## When the selected settings may not apply

In Codex, native subagent tools, model overrides and effort settings depend on the host. If a tool or setting is unavailable, do not claim that the configured rung ran; report the actual execution or handle the step directly. The checks below apply to Claude Code:

- **`CLAUDE_CODE_EFFORT_LEVEL` set**: it overrides the frontmatter `effort`, and every agent runs at the same effort. Unset it for routing to work.
- **`CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`**: Claude Code ignores the agents' `model`.
- **Model blocked** by `availableModels` or an organization restriction: Claude Code substitutes the model and shows a warning.
- **Content fallback**: Fable and recent Opus and Sonnet versions reroute flagged cybersecurity or biology requests to another model and stay on it.

To check, run `/tasks` while the subagent runs: its row shows the model and effort in use.

## Model aliases

Each agent's `model` is `haiku`, `sonnet`, `opus` or `fable`, never a version. How Claude Code resolves these names:
- **New version:** the alias points to it once Claude Code is updated. Nothing changes in the skill.
- **Same family as the main session:** the subagent runs on the session's exact version. With the session on an Opus pinned via `/model`, the `opus` rungs use that same Opus.
- **Pinning a version:** to hold a family at a version, set `ANTHROPIC_DEFAULT_OPUS_MODEL` (or `_SONNET_`, `_HAIKU_`, `_FABLE_`) to its ID in the `env` of `settings.json`. The skill keeps using the aliases.
- **Unsupported effort:** if a new version does not accept a level, Claude Code uses the highest supported level below it.
- **A family renamed or retired:** then edit `model` in `ladder.json` and run `install.py`.

The side effect lands in the history. When an alias changes version, the same rung starts meaning a different model, and old and new outcomes stop being directly comparable. Every event has a date; use it when comparing periods after a version change (see `references/laya.md`).

## Using the public Laya checkpoint

Read [references/laya.md](references/laya.md) to install and run the public `convaiinnovations/laya` checkpoint. No project-specific training is required. Laya is enabled by default for both operators. Its scores for this project's model-selection question have not been validated on local outcomes, so present them as estimates and verify the selected agent's work. Token counts are observed separately; history of only chosen rungs cannot establish how untried rungs would have performed.
- If the server is down, `route.py` decides with the heuristic and says so in the output's `backend` field and on stderr.
- If the server answers with an error, the script stops.
- The escalation floor, the per-operation ceiling, `user_ceiling` and approval apply to both backends.
