'''
Paths and functions shared by the cc-router scripts.

Configuration is validated and migrated in memory. Explicit CC_ROUTER_CONFIG
wins, then config/router.json if present, then the existing config/ladder.json.

The decision and result history lives outside the skill folder, because the
folder may be read-only. It records observed outcomes and token use.
'''
import os
import json
from pathlib import Path
from datetime import datetime
import uuid
import fcntl
import re
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from candidates import for_host

skill_dir     = Path(__file__).resolve().parent.parent
default_config = skill_dir / 'config' / 'router.json'
config_file = Path(os.environ.get('CC_ROUTER_CONFIG', default_config if default_config.exists() else skill_dir / 'config' / 'ladder.json'))
agents_dir    = Path.home() / '.claude' / 'agents'
settings_file = Path.home() / '.claude' / 'settings.json'

# settings Claude Code reads from the project folder, besides the user settings.json
project_settings_files = [Path('.claude') / 'settings.json', Path('.claude') / 'settings.local.json']

# credentials that take precedence over the subscription login; in -p mode an API key is used without asking
non_subscription_vars = ['ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_BASE_URL', 'ANTHROPIC_PROFILE',
                         'CLAUDE_CODE_USE_BEDROCK', 'CLAUDE_CODE_USE_VERTEX', 'CLAUDE_CODE_USE_FOUNDRY']

def detect_operator():
    override = os.environ.get('CC_ROUTER_OPERATOR', '').lower()
    if override:
        if override not in ('claude', 'codex'):
            raise ValueError('CC_ROUTER_OPERATOR must be claude or codex')
        return override
    codex = any(os.environ.get(name) for name in ('CODEX_THREAD_ID', 'CODEX_SESSION_ID'))
    claude = bool(os.environ.get('CLAUDECODE') or os.environ.get('CLAUDE_CODE_REMOTE'))
    if codex and claude:
        raise RuntimeError('Both Codex and Claude Code session markers are set; set CC_ROUTER_OPERATOR explicitly')
    if codex:
        return 'codex'
    if claude:
        return 'claude'
    raise RuntimeError('Cannot identify the operator; set CC_ROUTER_OPERATOR=claude or codex')

def load_config(operator=None):
    operator = operator or detect_operator()
    try:
        config = json.loads(config_file.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        raise ValueError('config: invalid JSON') from None
    return for_host(config, operator)

def laya_state(state):
    # The operator writes description in English for Laya. User language, retry
    # controls and write targets stay out of the task-difficulty input.
    return {name: state[name] for name in ('description', 'operation', 'files', 'ambiguous', 'critical')}

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("laya response: redirects are not permitted")

def post_json(url, body, timeout):
    # local Laya only: no proxy, no redirect; laya-serve requires a key only when started with LAYA_API_KEY
    headers = {'Content-Type': 'application/json'}
    if os.environ.get('LAYA_API_KEY'):
        headers['Authorization'] = f"Bearer {os.environ['LAYA_API_KEY']}"
    request = Request(url, data=json.dumps(body, ensure_ascii=False).encode('utf-8'), headers=headers)
    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=timeout) as response:
        return json.load(response)

def find_skill(name):
    # 'plugin:skill' lives under ~/.claude/plugins; a bare 'skill' under ~/.claude/skills
    if ':' in name:
        plugin, skill = name.split(':', 1)
        candidates = (Path.home() / '.claude' / 'plugins').glob(f'**/skills/{skill}/SKILL.md')
        return next((c for c in candidates if plugin in c.parts), None)
    skill_file = Path.home() / '.claude' / 'skills' / name / 'SKILL.md'
    return skill_file if skill_file.exists() else None

def last_active_rung(ladder):
    return max(i for i, rung in enumerate(ladder) if rung['active'])

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

def history_path(operator):
    return Path.home() / ('.claude' if operator == 'claude' else '.codex') / 'cc-router' / 'history.jsonl'

def calibration_path(operator):
    # fitted by scripts/calibrate_difficulty.py; local state, never inside the skill folder
    return history_path(operator).with_name('laya-calibration.json')

def decision_events(decision_id, operator=None):
    # returns the decision and the events tied to it; a wrong id would become an orphan record
    history_file = history_path(operator or detect_operator())
    events = read_history(history_file)
    same_id = [e for e in events if e['id'] == decision_id]
    decisions = [e for e in same_id if e['event'] == 'decision']
    if not decisions: raise ValueError(f'No decision with id {decision_id} in {history_file}')
    return decisions[0], same_id


def lock_decision(decision_id, operator=None):
    """Serialize collection/recording for one attempt; caller closes the fd.

    Different agents remain concurrent. The history append lock alone cannot
    protect a read-check-append sequence from duplicate results.
    """
    if not isinstance(decision_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', decision_id):
        raise ValueError('decision_id: invalid identifier')
    directory = history_path(operator or detect_operator()).parent / 'locks'
    directory.mkdir(parents=True, exist_ok=True)
    fd = os.open(directory / (decision_id + '.lock'), os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd

def read_history(path):
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue  # interrupted append or historical partial line
        if type(event) is dict and 'event' in event and 'id' in event:
            events.append(event)
    return events


def log_event(event):
    operator = event.get('operator') or detect_operator()
    history_file = history_path(operator)
    event = {'schema_version': 2, 'event_id': uuid.uuid4().hex, 'operator': operator,
             'date': datetime.now().astimezone().isoformat(timespec='seconds'), **event}
    history_file.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
    # O_APPEND plus one write per event: no buffered multi-write interleaving.
    fd = os.open(history_file, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        size = os.lseek(fd, 0, os.SEEK_END)
        if size and os.pread(fd, 1, size - 1) != b'\n':
            data = b'\n' + data
        if os.write(fd, data) != len(data):
            raise OSError('history: incomplete event write')
    finally:
        os.close(fd)
