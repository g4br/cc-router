"""Difficulty labels from history.jsonl, as JSONL ready for eval_difficulty.py --history-labels.

Per task_id, attempts in history order, each mapped to a level (difficulty.level_for_rung):
- failed at level k, then succeeded at level k+1: exact label k+1 (censored false).
- succeeded on the first try at level k: label k with censored true, meaning "level <= k".
Other tasks are skipped and counted by reason, never silently. An attempt counts as failed when
it did not pass or was marked no_rework false. Failures not caused by difficulty (rate limit,
permission, missing context, host) are ignored.
"""
import argparse
import json
import sys
from pathlib import Path

from common import load_config, detect_operator, history_path, read_history
from telemetry import attempts
from difficulty import level_for_rung

NOT_DIFFICULTY = ('transient_host', 'rate_limit', 'permission_denied', 'missing_context', 'unavailable_model_or_effort')


def labels(events, config):
    names = list(config['laya_difficulty']['levels'])
    rank = {}
    for c in config['ladder']:
        rank[c['id']] = rank[c['agent']] = c['legacy_rank']
    tasks, skipped = {}, {}
    def skip(reason):
        skipped[reason] = skipped.get(reason, 0) + 1
    for row in attempts(events):
        candidate = row['decision'].get('selected') or row['decision'].get('agent')
        if row['result'].get('failure_kind') in NOT_DIFFICULTY and not row['success']:
            continue
        tasks.setdefault(row['task_id'], []).append((row, candidate))
    out = []
    for task_id, steps in tasks.items():
        state = steps[0][0]['decision'].get('state') or {}
        description = steps[0][0]['decision'].get('description') or state.get('description')
        operation = state.get('operation') or steps[0][0]['decision'].get('task_profile', {}).get('operation')
        if not description or not operation:
            skip('missing description or operation')
            continue
        if any(candidate not in rank for _, candidate in steps):
            skip('candidate not on the ladder')
            continue
        levels = [level_for_rung(rank[candidate], config) for _, candidate in steps]
        passed = [row['success'] and row['no_rework'] is not False for row, _ in steps]
        if True not in passed:
            skip('never succeeded without rework')
            continue
        j = passed.index(True)
        if j == 0:
            level, censored = levels[0], True
        elif levels[j] == levels[j - 1] + 1:
            level, censored = levels[j], False
        else:
            skip('success not exactly one level above the last failure')
            continue
        out.append({'description': description, 'operation': operation, 'label': names[level], 'censored': censored,
                    'task_id': task_id, **{k: state[k] for k in ('files', 'ambiguous', 'critical') if k in state}})
    return out, skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--operator', choices=('claude', 'codex'))
    parser.add_argument('--out', type=Path, help='output JSONL (default: stdout)')
    parser.add_argument('--last', type=int, help='keep only the last N tasks')
    args = parser.parse_args()
    operator = args.operator or detect_operator()
    config = load_config(operator)
    out, skipped = labels(read_history(history_path(operator)), config)
    if args.last:
        out = out[-args.last:]
    text = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in out)
    if args.out:
        args.out.write_text(text, encoding='utf-8')
    else:
        sys.stdout.write(text)
    exact = sum(not r['censored'] for r in out)
    print(f'labels: {exact} exact, {len(out) - exact} censored; skipped {sum(skipped.values())} {skipped or ""}'.rstrip(), file=sys.stderr)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        print(f'cc-router: {error}', file=sys.stderr)
        sys.exit(1)
