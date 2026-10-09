"""Collect native usage independently of verification; also a Claude SubagentStop hook."""
import argparse
import json
import os
import shlex
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import sys

from candidates import require
from common import decision_events, detect_operator, load_config, log_event, lock_decision, settings_file
from native_usage import collect, locate, markers, read_transcript, text_content


def configure_claude_hook(settings):
    require(type(settings) is dict, 'settings', 'expected object')
    hooks = settings.setdefault('hooks', {})
    require(type(hooks) is dict and type(hooks.get('SubagentStop', [])) is list,
            'settings.hooks.SubagentStop', 'expected hook list')
    entry = {'matcher': '^exec-', 'hooks': [{'type': 'command',
             'command': shlex.join([sys.executable, str(Path(__file__).resolve()), '--claude-hook'])}]}
    stop_hooks = hooks.setdefault('SubagentStop', [])
    if entry in stop_hooks:
        return False
    stop_hooks.append(entry)
    return True


def install_claude_hook(path):
    """Install just the collector, preserving settings and backing up before change."""
    settings = json.loads(path.read_text()) if path.exists() else {}
    if not configure_claude_hook(settings):
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if path.exists():
        backup = path.with_name(path.name + '.' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f') + '.bak')
        shutil.copy2(path, backup)
    fd, temporary = tempfile.mkstemp(prefix='.cc-router-hooks-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(settings, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return backup


def latest(events):
    observations = [e['observation'] for e in events if e.get('event') == 'host_usage']
    identities = {(o['host_usage']['host'], o['host_usage']['agent_id'], o['host_usage']['turn_id']) for o in observations}
    require(len(identities) <= 1, 'host_usage', 'multiple executions for one decision; use a separate attempt')
    return observations[-1] if observations else None


def save(decision_id, host, observation):
    fd = lock_decision(decision_id, host)
    try:
        return save_locked(decision_id, host, observation)
    finally:
        os.close(fd)


def save_locked(decision_id, host, observation):
    decision, events = decision_events(decision_id, host)
    require(decision.get('execution', {}).get('status') != 'blocked', 'decision', 'blocked execution')
    require(not any(e.get('answer') == 'declined' for e in events), 'decision', 'declined execution')
    prior = latest(events)
    if prior:
        a, b = prior['host_usage'], observation['host_usage']
        require((a['agent_id'], a['turn_id']) == (b['agent_id'], b['turn_id']), 'host_usage', 'execution already bound')
        if prior == observation:
            return False
    require(not any(e['event'] == 'result' for e in events), 'host_usage', 'result already recorded; collect before record.py')
    log_event({'event': 'host_usage', 'id': decision_id, 'decision_id': decision_id,
               'operator': host, 'task_id': decision.get('task_id'),
               'attempt_id': decision.get('attempt_id'), 'observation': observation})
    return True


def claude_hook(payload):
    require(type(payload) is dict and payload.get('hook_event_name') == 'SubagentStop', 'hook', 'expected SubagentStop')
    agent_type = payload.get('agent_type')
    config = load_config('claude')
    # Ignore unrelated native agents. No model text or last_assistant_message is
    # accepted as evidence of decision identity, usage or task success.
    if agent_type not in {c['agent'] for c in config['ladder']}:
        return
    path = payload.get('agent_transcript_path')
    require(type(path) is str and bool(path), 'agent_transcript_path')
    rows, _ = read_transcript(path)
    decisions = set()
    for row in rows:
        if row.get('type') == 'user':
            decisions |= markers(text_content(row.get('message', {}).get('content')))
    if not decisions:
        return  # this agent was not given a router brief
    require(len(decisions) == 1, 'decision_id', 'multiple router attempts in one subagent')
    decision_id = next(iter(decisions))
    observation = collect('claude', path, payload.get('agent_id'), decision_id, config, agent_type=agent_type)
    save(decision_id, 'claude', observation)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('decision_id', nargs='?')
    parser.add_argument('--agent-id', help='native Codex thread ID or Claude subagent ID')
    parser.add_argument('--transcript', type=Path, help='explicit JSONL path when discovery is unavailable')
    parser.add_argument('--turn-id', help='Codex turn ID when the thread contains multiple matching turns')
    parser.add_argument('--claude-hook', action='store_true', help='read SubagentStop JSON from stdin; never records success')
    parser.add_argument('--install-claude-hook', action='store_true', help='install only the usage hook, preserving and backing up existing settings')
    args = parser.parse_args()
    if args.install_claude_hook:
        require(not any((args.decision_id, args.agent_id, args.transcript, args.turn_id, args.claude_hook)),
                'hook', 'installation cannot be mixed with collection')
        backup = install_claude_hook(settings_file)
        print(f'Claude usage hook configured in {settings_file}' + (f'; backup: {backup}' if backup else ''))
        return
    if args.claude_hook:
        require(not any((args.decision_id, args.agent_id, args.transcript, args.turn_id)), 'hook', 'cannot mix CLI collection and hook')
        claude_hook(json.load(sys.stdin))
        return
    require(bool(args.decision_id) and bool(args.agent_id), 'usage', 'decision_id and --agent-id are required')
    host = detect_operator()
    decision_events(args.decision_id, host)
    observation = collect(host, args.transcript or locate(host, args.agent_id), args.agent_id,
                          args.decision_id, load_config(host), args.turn_id)
    save(args.decision_id, host, observation)
    print(json.dumps(observation, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, TypeError, KeyError, RuntimeError, OSError) as error:
        print(f'cc-router usage: {error}', file=sys.stderr)
        sys.exit(1)
