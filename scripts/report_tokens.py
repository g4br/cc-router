"""Tokens per completed, validated task: median and p90 overall, per backend, per level and per phase.

A phase is unknown (never zero) unless some record reported it. Explicit --phase-tokens win;
without them, execution is the first attempt's tokens and rework the retries' tokens (zero only
when the first attempt is labelled no-rework). total needs every phase known.
--before <commit-or-ISO-date> splits tasks by completion date so two periods can be compared.
"""
import argparse
import json
import math
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from statistics import median

from common import detect_operator, history_path, read_history, skill_dir
from telemetry import PHASES, attempts, numeric


def p90(values):
    # nearest rank: the smallest value with at least 90% of the sample at or below it
    ordered = sorted(values)
    return ordered[math.ceil(0.9 * len(ordered)) - 1]


def parse_date(text):
    try:
        moment = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.astimezone()


def cutoff(value):
    if re.match(r'\d{4}-\d{2}-\d{2}', value):
        moment = parse_date(value)
        if moment is None:
            raise ValueError(f'before: invalid ISO date {value!r}')
        return moment
    shown = subprocess.run(['git', '-C', str(skill_dir), 'show', '-s', '--format=%cI', value],
                           capture_output=True, text=True)
    if shown.returncode:
        raise ValueError(f'before: not an ISO date or a commit of {skill_dir}: {value!r}')
    return parse_date(shown.stdout.strip())


def phase_values(group, completions):
    reported = [r['result'].get('phase_tokens') or {} for r in group] + [e.get('phase_tokens') or {} for e in completions]
    values = {}
    for phase in PHASES:
        known = [p[phase] for p in reported if phase in p]
        if known:
            values[phase] = sum(known)
        elif phase == 'execution':
            values[phase] = group[0]['tokens'] if numeric(group[0]['tokens']) else None
        elif phase == 'rework':
            retries = [r['tokens'] for r in group[1:]]
            values[phase] = (sum(retries) if all(numeric(t) for t in retries) else None) if retries \
                else (0 if group[0]['no_rework'] is True else None)
        else:
            values[phase] = None
    values['total'] = sum(values[p] for p in PHASES) if all(values[p] is not None for p in PHASES) else None
    return values


def tasks(events):
    """One row per task whose last attempt passed verification and completed the criterion."""
    groups = {}
    for row in attempts(events):
        groups.setdefault(row['task_id'], []).append(row)
    completed = {}
    for e in events:
        if e.get('event') == 'task_completed':
            completed.setdefault(e.get('task_id'), []).append(e)
    rows = []
    for task_id, group in groups.items():
        last = group[-1]
        if not (last['success'] and last['result'].get('task_complete', True)):
            continue
        first = group[0]['decision']
        rows.append({'task_id': task_id, 'backend': first.get('backend') or 'unknown',
                     'level': (first.get('laya') or {}).get('final_level') or 'unknown',
                     'date': parse_date(last['result'].get('date')),
                     'phases': phase_values(group, completed.get(task_id, []))})
    return rows


def summary(rows):
    out = {'tasks': len(rows), 'phases': {}}
    for phase in (*PHASES, 'total'):
        known = [r['phases'][phase] for r in rows if r['phases'][phase] is not None]
        out['phases'][phase] = {'known': len(known), 'unknown': len(rows) - len(known),
                                'median': median(known) if known else None, 'p90': p90(known) if known else None}
    return out


def report(events, before=None):
    rows = tasks(events)
    periods = {'all': rows} if before is None else {
        'before': [r for r in rows if r['date'] and r['date'] < before],
        'after': [r for r in rows if r['date'] and r['date'] >= before],
        'undated': [r for r in rows if not r['date']]}
    out = {}
    for name, group in periods.items():
        out[name] = {'overall': summary(group)}
        for key in ('backend', 'level'):
            out[name]['by_' + key] = {value: summary([r for r in group if r[key] == value])
                                      for value in sorted({r[key] for r in group})}
    return out


def table(title, data):
    show = lambda v: 'unknown' if v is None else f'{v:g}'
    lines = [f"{title}: {data['tasks']} completed tasks", f"  {'phase':<15}{'known':>6}{'unknown':>8}{'median':>10}{'p90':>10}"]
    lines += [f"  {p:<15}{s['known']:>6}{s['unknown']:>8}{show(s['median']):>10}{show(s['p90']):>10}"
              for p, s in data['phases'].items()]
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--history', type=Path, help='history.jsonl to read (default: this host\'s)')
    parser.add_argument('--before', help='commit or ISO date: report tasks completed before and from it separately')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    path = args.history or history_path(detect_operator())
    result = report(read_history(path), cutoff(args.before) if args.before else None)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return
    print(f'history: {path}')
    for period, data in result.items():
        print(table(f'[{period}] overall', data['overall']))
        for key in ('backend', 'level'):
            for value, part in data['by_' + key].items():
                print(table(f'[{period}] {key}={value}', part))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        print(f'cc-router report_tokens: {error}', file=sys.stderr)
        sys.exit(1)
