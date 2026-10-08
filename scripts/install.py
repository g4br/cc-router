import sys
import json
import shutil
import subprocess

from common import load_config, check_subscription, detect_operator, last_active_rung, find_skill, agents_dir, history_path, settings_file, config_file

#-----------------------------------------------------------
# Input and paths
#-----------------------------------------------------------
if len(sys.argv) > 1: raise ValueError('usage: python install.py (no arguments; reads config/ladder.json)')

# the body is the subagent's system prompt; it does not see the orchestrator's conversation
lean_template = '''Lean output: follow the preloaded skills ({skill_names}); if they are not in your context, invoke them with the Skill tool before you start.
- caveman applies to text: terse report. Code, commands, paths and error messages stay exact.
- ponytail applies to code: the least code that works, no speculative abstractions, standard library before dependencies. Validation, error handling and security are never cut.
- When code form conflicts, the project's style rules win (CLAUDE.md and style skills).
'''
# Candidates may omit helper skills to keep their system prompt short.
lean_short = 'Lean output: terse report, the least code that works. Code, commands, paths and error messages stay exact.\n'

agent_template = '''---
name: {agent}
description: {description_yaml}
model: {model}
{effort_line}{skills_lines}---

You carry out a single step of a larger task, delegated by an orchestrator.
The delegation prompt gives the goal of the step, the context you need and the verification criterion.

- Do only the requested step, without widening the scope.
- Before reporting, verify the result against the given criterion: run the script or the test, validate the output, check the file. A syntax-only check, or a check command that failed to start, does not count; if only the project's declared dependencies are missing, install them with its own package manager. If no real check can run here, say which one you did not run and why instead of reporting the step as done.
- Write the report in the user's language given in the delegation prompt. Keep RESULT, DONE, VERIFICATION, PENDING, STEP and DECISION as literal report labels. Use any explicitly requested language for the deliverable itself.
- If the step is too ambiguous, essential context is missing, or it needs more reasoning than you can safely deliver, stop and answer with RESULT: ESCALATE and the reason. Handing back early costs less than delivering it wrong, and the orchestrator will pass the step to a more capable configuration.

{lean_block}
Always end with this report:

RESULT: done | partial | ESCALATE
DONE: what was changed or produced
VERIFICATION: how you checked it and what you saw
PENDING: what was left out, or "none"
STEP: the step_id from the delegation prompt, or "none"
DECISION: the decision_id from the delegation prompt, or "none"
'''
#-----------------------------------------------------------
# Build one agent per ladder rung
#-----------------------------------------------------------
operator = detect_operator()
config = load_config(operator)
last_active_rung(config['ladder'])

#-----------------------------------------------------------
# Laya: package, public checkpoint and backend (both hosts)
#-----------------------------------------------------------
try:
    import laya, fastapi, uvicorn  # noqa: F401
except ImportError:
    print('Installing laya[serve] (PyTorch, Transformers, FastAPI, Uvicorn)...', flush=True)
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'laya[serve]'], check=True)
# a one-off prediction downloads the public checkpoint into the Hugging Face cache; later runs are instant
laya_cli = shutil.which('laya') or sys.exit('laya command not found after install; check that the pip bin directory is on PATH')
print(f"Downloading the Laya checkpoint '{config['laya_checkpoint']}' (first run only)...", flush=True)
subprocess.run([laya_cli, '--predict', '--model', config['laya_checkpoint'], '--device', 'cpu', '--json', 'warm-up'], check=True, stdout=subprocess.DEVNULL)
# string replace keeps the file layout; a backend already set to laya is left alone
text = config_file.read_text(encoding='utf-8')
if '"backend": "heuristic"' in text:
    config_file.write_text(text.replace('"backend": "heuristic"', '"backend": "laya"', 1), encoding='utf-8')
    print(f'Save: {config_file} (backend: laya)')

if operator == 'codex':
    print('Codex uses its native agent tool. No agent files or Claude Code settings are needed.')
    print(f'History in: {history_path(operator).parent}')
    sys.exit(0)

check_subscription()
agents_dir.mkdir(parents=True, exist_ok=True)
history_path(operator).parent.mkdir(parents=True, exist_ok=True)

# a skill listed in the frontmatter but not installed is skipped by Claude Code with no warning in the session
all_skills = {name for rung in config['ladder'] if rung['active'] for name in rung.get('skills', config['agent_skills'])}
missing = [name for name in sorted(all_skills) if find_skill(name) is None]
if missing: raise FileNotFoundError(f'Skills not installed: {missing}. In Claude Code: /plugin marketplace add JuliusBrussee/caveman, /plugin install caveman@caveman, /plugin marketplace add DietrichGebert/ponytail, /plugin install ponytail@ponytail (one command per message).')

# Refuse all ownership conflicts before modifying settings or agent files.
for candidate in config['ladder']:
    target = agents_dir / f"{candidate['agent']}.md"
    if candidate['active'] and target.exists() and 'cc-router executor (' not in target.read_text(encoding='utf-8'):
        raise ValueError('agent: refusing to overwrite an unowned file')

#-----------------------------------------------------------
# Approval lock in Claude Code
#-----------------------------------------------------------
# Preserve native ask rules. Host policy determines enforcement in this session.
# Install approval rules before exposing newly generated agents. Never remove
# pre-existing rules, including inactive candidate protections.
approval_rules = [f"Agent({rung['agent']})" for rung in config['ladder'] if rung['approval'] or rung['billing_mode'] != 'subscription']

settings = json.loads(settings_file.read_text(encoding='utf-8')) if settings_file.exists() else {}
if type(settings) is not dict:
    raise ValueError('settings: expected object')
permissions = settings.setdefault('permissions', {})
if type(permissions) is not dict or type(permissions.get('ask', [])) is not list or any(type(r) is not str for r in permissions.get('ask', [])):
    raise ValueError('settings.permissions.ask: expected string list')
other_rules = permissions.get('ask', [])
approval_rules = [rule for rule in approval_rules if rule not in other_rules]
permissions['ask'] = other_rules + approval_rules

settings_file.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'Save: {settings_file} (permissions.ask: {approval_rules})')

# an agent file left over from a renamed or removed rung would still be callable
names = {rung['agent'] for rung in config['ladder']}
for stale in agents_dir.glob('exec-*.md'):
    if stale.stem not in names and 'cc-router executor (' in stale.read_text(encoding='utf-8'):
        stale.unlink()
        print(f'Removed stale agent: {stale}')

for rung in config['ladder']:
    skills = rung.get('skills', config['agent_skills'])
    skills_lines = 'skills:\n' + ''.join('  - ' + json.dumps(name) + '\n' for name in skills) if skills else ''
    lean_block = lean_template.format(skill_names=', '.join(name.split(':')[-1] for name in skills)) if skills else lean_short
    agent_file = agents_dir / f"{rung['agent']}.md"
    #
    # an inactive rung is not installed, so nothing outside the router can call it
    if not rung['active']:
        if agent_file.exists() and 'cc-router executor (' in agent_file.read_text(encoding='utf-8'):
            agent_file.unlink()
        print(f"Inactive: {rung['agent']}")
        continue
    #
    # Null effort omits the parameter; never infer support from a model name.
    effort_line = f"effort: {rung['effort']}\n" if rung['effort'] else ''
    if agent_file.exists() and 'cc-router executor (' not in agent_file.read_text(encoding='utf-8'):
        raise ValueError('agent: refusing to overwrite an unowned file')
    text = agent_template.format(description_yaml=json.dumps(f"cc-router executor ({rung['label']}). Use only when route.py selects this agent."), effort_line=effort_line, skills_lines=skills_lines, lean_block=lean_block, **rung)
    agent_file.write_text(text, encoding='utf-8')
    print(f'Save: {agent_file}')

print(f'History in: {history_path(operator).parent}')
