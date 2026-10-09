"""Print the fixed delegation brief for one task: no conversation history, one report format.

The orchestrator passes the printed text to the executor as its whole prompt. Over
brief_max_words, a warning goes to stderr and a brief_overflow event is logged, but the
brief is still printed.
"""
import argparse
import json
import sys
from pathlib import Path

from candidates import require, string, strings
from common import detect_operator, load_config, log_event

FIELDS = {'goal', 'write_targets', 'acceptance', 'verify', 'user_language', 'decision_id', 'step_id'}

# shared with install.py, which puts the same format in every executor's system prompt
REPORT_FORMAT = '''RESULT: done|failed|blocked
FILES: <changed paths>
CHECK: <command> -> <result>
PENDING: <items or none>
TOKENS: <host-reported or unknown>
STEP: <step_id from the brief, or none>
DECISION: <decision_id from the brief>'''


def report_rules(config):
    return (f"Report at most {config['report_max_lines']} lines in exactly this format:\n{REPORT_FORMAT}\n"
            "The orchestrator checks the diff and re-runs CHECK; it does not re-read unchanged files.")


def check_task(task):
    require(type(task) is dict and set(task) <= FIELDS, 'task', 'expected object with known fields')
    for key in ('goal', 'acceptance', 'verify', 'user_language', 'decision_id'):
        string(task.get(key), key, 2000)
    require('\n' not in task['goal'].strip(), 'goal', 'one sentence on one line')
    strings(task.get('write_targets', []), 'write_targets')
    string(task.get('step_id'), 'step_id', 128, nullable=True)


def build(task, config):
    check_task(task)
    targets = ', '.join(task.get('write_targets', [])) or 'none (read-only)'
    return '\n'.join([
        f"Goal: {task['goal'].strip()}",
        f'Owned files (write only these): {targets}',
        f"Acceptance: {task['acceptance'].strip()}",
        f"Verify with: {task['verify'].strip()}",
        f"Report language: {task['user_language']}",
        f"CC_ROUTER_DECISION: {task['decision_id']}",
        f"Echo STEP: {task.get('step_id') or 'none'} and DECISION: {task['decision_id']} in the report.",
        report_rules(config)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task', nargs='?', help='JSON object: ' + ', '.join(sorted(FIELDS)))
    parser.add_argument('--task-file', type=Path)
    args = parser.parse_args()
    if (args.task is None) == (args.task_file is None):
        parser.error('provide task JSON or --task-file')
    try:
        task = json.loads(args.task_file.read_text() if args.task_file else args.task)
    except json.JSONDecodeError:
        raise ValueError('task: invalid JSON') from None
    config = load_config(detect_operator())
    text = build(task, config)
    words = len(text.split())
    if words > config['brief_max_words']:
        print(f"cc-router: brief has {words} words, over brief_max_words={config['brief_max_words']}; shorten goal or acceptance",
              file=sys.stderr)
        log_event({'event': 'brief_overflow', 'id': task['decision_id'], 'decision_id': task['decision_id'],
                   'step_id': task.get('step_id'), 'words': words, 'max_words': config['brief_max_words']})
    print(text)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        print(f'cc-router brief: {error}', file=sys.stderr)
        sys.exit(1)
