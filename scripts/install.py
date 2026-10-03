import sys
import json

from common import load_config, check_subscription, detect_operator, last_active_rung, find_skill, agents_dir, history_path, settings_file

#-----------------------------------------------------------
# Input and paths
#-----------------------------------------------------------
if len(sys.argv) > 1: raise ValueError('usage: python install.py (no arguments; reads config/ladder.json)')

# the body is the subagent's system prompt; it does not see the orchestrator's conversation
agent_template = '''---
name: {agent}
description: cc-router executor ({label}). Use only when route.py selects this agent.
model: {model}
{effort_line}{skills_lines}---

You carry out a single step of a larger task, delegated by an orchestrator.
The delegation prompt gives the goal of the step, the context you need and the verification criterion.

- Do only the requested step, without widening the scope.
- Before reporting, verify the result against the given criterion: run the script or the test, validate the output, check the file.
- If the step is too ambiguous, essential context is missing, or it needs more reasoning than you can safely deliver, stop and answer with RESULT: ESCALATE and the reason. Handing back early costs less than delivering it wrong, and the orchestrator will pass the step to a more capable configuration.

Lean output: follow the preloaded skills ({skill_names}); if they are not in your context, invoke them with the Skill tool before you start.
- caveman applies to text: terse report. Code, commands, paths and error messages stay exact.
- ponytail applies to code: the least code that works, no speculative abstractions, standard library before dependencies. Validation, error handling and security are never cut.
- When code form conflicts, the project's style rules win (CLAUDE.md and style skills).

Always end with this report:

RESULT: done | partial | ESCALATE
DONE: what was changed or produced
VERIFICATION: how you checked it and what you saw
PENDING: what was left out, or "none"
'''
#-----------------------------------------------------------
# Build one agent per ladder rung
#-----------------------------------------------------------
operator = detect_operator()
config = load_config(operator)
last_active_rung(config['ladder'])
if operator == 'codex':
    print('Codex uses its native agent tool. No agent files or Claude Code settings are needed.')
    print(f'History in: {history_path(operator).parent}')
    sys.exit(0)

check_subscription()
agents_dir.mkdir(parents=True, exist_ok=True)
history_path(operator).parent.mkdir(parents=True, exist_ok=True)

# a skill listed in the frontmatter but not installed is skipped by Claude Code with no warning in the session
missing = [name for name in config['agent_skills'] if find_skill(name) is None]
if missing: raise FileNotFoundError(f'Skills not installed: {missing}. In Claude Code: /plugin marketplace add JuliusBrussee/caveman, /plugin install caveman@caveman, /plugin marketplace add DietrichGebert/ponytail, /plugin install ponytail@ponytail (one command per message).')

skills_lines = 'skills:\n' + ''.join(f'  - "{name}"\n' for name in config['agent_skills'])
skill_names  = ', '.join(name.split(':')[-1] for name in config['agent_skills'])

for rung in config['ladder']:
    agent_file = agents_dir / f"{rung['agent']}.md"
    #
    # an inactive rung is not installed, so nothing outside the router can call it
    if not rung['active']:
        agent_file.unlink(missing_ok=True)
        print(f"Inactive: {rung['agent']}")
        continue
    #
    # Haiku takes no effort; without the line the subagent runs without the parameter
    effort_line = f"effort: {rung['effort']}\n" if rung['effort'] else ''
    text = agent_template.format(effort_line=effort_line, skills_lines=skills_lines, skill_names=skill_names, **rung)
    agent_file.write_text(text, encoding='utf-8')
    print(f'Save: {agent_file}')

print(f'History in: {history_path(operator).parent}')
#-----------------------------------------------------------
# Approval lock in Claude Code
#-----------------------------------------------------------
# an explicit permissions.ask rule prompts in every mode, including auto and
# bypassPermissions, so these rungs never run without the user's approval, even if the
# orchestrator forgets to ask. Only Agent(exec-...) rules are rewritten, and inactive
# rungs keep their rule in case an old agent file is still around.
approval_rules = [f"Agent({rung['agent']})" for rung in config['ladder'] if rung['approval']]

settings = json.loads(settings_file.read_text(encoding='utf-8')) if settings_file.exists() else {}
permissions = settings.setdefault('permissions', {})
other_rules = [rule for rule in permissions.get('ask', []) if not rule.startswith('Agent(exec-')]
permissions['ask'] = other_rules + approval_rules

settings_file.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'Save: {settings_file} (permissions.ask: {approval_rules})')
