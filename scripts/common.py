'''
Paths and functions shared by the cc-router scripts.

The ladder of configurations (model + effort) and the heuristic rules live in
config/ladder.json, the single source of truth: install.py builds the agents
from it and route.py decides on it.

The decision and result history lives outside the skill folder, because the
folder may be read-only and the history is the training set for the router.
'''
import os
import json
from pathlib import Path
from datetime import datetime

skill_dir     = Path(__file__).resolve().parent.parent
config_file   = skill_dir / 'config' / 'ladder.json'
agents_dir    = Path.home() / '.claude' / 'agents'
data_dir      = Path.home() / '.claude' / 'cc-router'
history_file  = data_dir / 'history.jsonl'
settings_file = Path.home() / '.claude' / 'settings.json'

# settings Claude Code reads from the project folder, besides the user settings.json
project_settings_files = [Path('.claude') / 'settings.json', Path('.claude') / 'settings.local.json']

# credentials that take precedence over the subscription login; in -p mode an API key is used without asking
non_subscription_vars = ['ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_BASE_URL', 'ANTHROPIC_PROFILE',
                         'CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX', 'CLAUDE_CODE_USE_FOUNDRY']

def load_config():
    return json.loads(config_file.read_text(encoding='utf-8'))

def find_skill(name):
    # 'plugin:skill' lives under ~/.claude/plugins; a bare 'skill' under ~/.claude/skills
    if ':' in name:
        plugin, skill = name.split(':', 1)
        candidates = (Path.home() / '.claude' / 'plugins').glob(f'**/skills/{skill}/SKILL.md')
        return next((c for c in candidates if plugin in c.parts), None)
    skill_file = Path.home() / '.claude' / 'skills' / name / 'SKILL.md'
    return skill_file if skill_file.exists() else None

def last_active_rung(ladder):
    # inactive rungs may only sit at the top; a gap in the middle would break escalation
    active = [rung['active'] for rung in ladder]
    last = len(active) - 1 - active[::-1].index(True)
    if not all(active[:last + 1]): raise ValueError('ladder.json: rungs with active=false may only sit at the top of the ladder')
    return last

def check_subscription():
    # cloud sessions (claude.ai/code) always use the subscription credential, per the
    # documentation, and set ANTHROPIC_BASE_URL themselves
    if os.environ.get('CLAUDE_CODE_REMOTE') == 'true':
        return
    #
    # anything found here would make Claude Code bill outside the subscription
    found = [name for name in non_subscription_vars if os.environ.get(name)]
    for settings in [settings_file] + project_settings_files:
        if not settings.exists():
            continue
        content = json.loads(settings.read_text(encoding='utf-8'))
        if 'apiKeyHelper' in content:
            found.append(f'apiKeyHelper in {settings}')
        found += [f'{name} in the env of {settings}' for name in non_subscription_vars if name in content.get('env', {})]
    if found: raise RuntimeError(f'Credential outside the subscription: {found}. Remove it before using the router (for example, start Claude Code with env -u ANTHROPIC_API_KEY claude) and check /status.')

def decision_events(decision_id):
    # returns the decision and the events tied to it; a wrong id would become an orphan record
    events = [json.loads(line) for line in history_file.read_text(encoding='utf-8').splitlines()]
    same_id = [e for e in events if e['id'] == decision_id]
    decisions = [e for e in same_id if e['event'] == 'decision']
    if not decisions: raise ValueError(f'No decision with id {decision_id} in {history_file}')
    return decisions[0], same_id

def log_event(event):
    # one JSON line per event; appending is safe with several sessions writing
    event = {'date': datetime.now().astimezone().isoformat(timespec='seconds'), **event}
    data_dir.mkdir(parents=True, exist_ok=True)
    with open(history_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(event, ensure_ascii=False, default=str) + '\n')
