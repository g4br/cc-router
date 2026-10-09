"""Offline evaluation of four difficulty strategies against a labelled gold set.

Strategies: heuristic, laya per_candidate, laya difficulty, combined (difficulty + heuristic).
Needs the live laya-serve (config laya_url) unless --no-laya. Labels: tests/data/difficulty_gold.jsonl
(label null = skipped and counted) plus optional exact labels from scripts/labels_from_history.py.
Cost model: expected tokens of the predicted level's candidate; an under-routed task also pays one
more execution at the next level.
"""
import argparse
import json
import sys
from pathlib import Path
from statistics import median
from urllib.error import URLError

from common import load_config, detect_operator, history_path, read_history, skill_dir
from telemetry import attempts, numeric
from route import heuristic_level, laya_probabilities, first_above_threshold
import difficulty

GOLD = skill_dir / 'tests' / 'data' / 'difficulty_gold.jsonl'
EPSILON = 1e-9


def load_tasks(paths, config, exact_only=()):
    """Labelled tasks from JSONL files; returns (tasks, skipped) with skipped counting unlabelled and censored lines."""
    levels = list(config['laya_difficulty']['levels'])
    tasks, skipped = [], {'unlabelled': 0, 'censored': 0}
    for path in paths:
        for number_, line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
            if not line.strip():
                continue
            where = f'{path}:{number_}'
            try:
                row = json.loads(line)
                description, operation, label = row['description'], row['operation'], row['label']
            except (json.JSONDecodeError, KeyError, TypeError):
                raise ValueError(f'{where}: expected an object with description, operation and label') from None
            if operation not in config['base_level_by_operation']:
                raise ValueError(f'{where}: unknown operation {operation!r}')
            if label is not None and label not in levels:
                raise ValueError(f'{where}: label {label!r} is not one of {levels}')
            if label is None:
                skipped['unlabelled'] += 1
                continue
            if path in exact_only and row.get('censored', False):
                skipped['censored'] += 1
                continue
            tasks.append({'description': description, 'operation': operation, 'label': levels.index(label),
                          'files': row.get('files', 0), 'ambiguous': row.get('ambiguous', False),
                          'critical': row.get('critical', False)})
    return tasks, skipped


def token_costs(config, history):
    """Candidate id -> expected tokens: median of the history, else config; None when unknown."""
    seen = {}
    for row in attempts(history):
        candidate = row['decision'].get('selected') or row['decision'].get('agent')
        if numeric(row['tokens']) and row['tokens'] > 0:
            seen.setdefault(candidate, []).append(row['tokens'])
    fallback = config['expected_tokens_by_candidate'].get(config['operator'], {})
    return {c['id']: median(seen[c['id']]) if c['id'] in seen else fallback.get(c['id']) for c in config['ladder']}


def predictions(tasks, config, use_laya):
    """Level index per task for each strategy; the three Laya ones only with use_laya."""
    ladder = config['ladder']
    heuristic_rungs = [heuristic_level(t, config)[0] for t in tasks]
    out = {'heuristic': [difficulty.level_for_rung(r, config) for r in heuristic_rungs]}
    if not use_laya:
        return out
    if not tasks:  # nothing to ask the server
        return dict(out, **{name: [] for name in ('laya per_candidate', 'laya difficulty', 'combined')})
    names = list(config['laya_difficulty']['levels'])
    try:
        answers = []
        for start in range(0, len(tasks), difficulty.MAX_STATES):
            answers += difficulty.request(tasks[start:start + difficulty.MAX_STATES], config)
        per_candidate = []
        for n, (t, rung) in enumerate(zip(tasks, heuristic_rungs), 1):
            if sys.stderr.isatty():
                print(f'per_candidate {n}/{len(tasks)}', file=sys.stderr)
            ceiling = min(config['ceiling_by_operation'].get(t['operation'], len(ladder) - 1), max(i for i, c in enumerate(ladder) if c['active']))
            chosen = first_above_threshold(laya_probabilities(t, config), ladder, 0, ceiling, config['success_threshold'])
            per_candidate.append(difficulty.level_for_rung(rung if chosen is None else ladder[chosen]['legacy_rank'], config))
    except (URLError, TimeoutError, ConnectionError) as error:
        raise RuntimeError(f"Laya server unreachable at {config['laya_url']} ({error}). "
                           'Start it with scripts/start_services.sh, or run with --no-laya.') from None
    out['laya per_candidate'] = per_candidate
    out['laya difficulty'] = [names.index(a['level']) for a in answers]
    out['combined'] = [names.index(difficulty.combine(a, r, t, config)['final_level'])
                       for a, r, t in zip(answers, heuristic_rungs, tasks)]
    return out


def metrics(pairs, cost):
    """pairs: (predicted, label) per task. Rework model: under-routed pays the next level once more."""
    n = len(pairs)
    if not n:
        return {'n': 0, 'exact': None, 'within1': None, 'under': None, 'over': None, 'expected_tokens': None}
    def tokens(p, label):
        return cost(p) + (cost(p + 1) if p < label else 0)
    return {'n': n, 'exact': sum(p == l for p, l in pairs) / n, 'within1': sum(abs(p - l) <= 1 for p, l in pairs) / n,
            'under': sum(p < l for p, l in pairs) / n, 'over': sum(p > l for p, l in pairs) / n,
            'expected_tokens': sum(tokens(p, l) for p, l in pairs) / n}


def gate(report, config):
    """(verdict, reasons). PASS needs enough labels per level and difficulty or combined beating the heuristic."""
    reasons = []
    short = {name: count for name, count in report['labelled_per_level'].items() if count < config['gate_min_tasks_per_level']}
    if short:
        reasons.append(f"insufficient labels: need >= {config['gate_min_tasks_per_level']} per level, have {report['labelled_per_level']}")
    heuristic = report['strategies']['heuristic']
    passing = False
    for name in ('laya difficulty', 'combined'):
        s = report['strategies'].get(name)
        if not s or s['n'] == 0 or heuristic['n'] == 0:
            reasons.append(f'{name}: not evaluated' + (' (no labelled tasks)' if heuristic['n'] == 0 else ''))
            continue
        saving = 1 - s['expected_tokens'] / heuristic['expected_tokens']
        increase = s['under'] - heuristic['under']
        ok = saving >= config['gate_token_saving_min'] - EPSILON and increase <= config['gate_under_routing_max_increase'] + EPSILON
        passing |= ok
        if not ok:
            reasons.append(f"{name}: token saving {saving:.1%} (need >= {config['gate_token_saving_min']:.0%}), "
                           f"under-routing change {increase:+.1%} (need <= {config['gate_under_routing_max_increase']:+.0%})")
    return ('PASS' if passing and not short else 'FAIL'), ([] if passing and not short else reasons)


def evaluate(tasks, skipped, config, history, use_laya=True):
    levels = list(config['laya_difficulty']['levels'])
    predicted = predictions(tasks, config, use_laya)
    costs = token_costs(config, history)
    candidates = [c['id'] for c in difficulty.level_candidates(config)]
    def cost(level):
        missing = costs[candidates[level]] is None
        if missing:
            raise ValueError(f"expected tokens unknown for {candidates[level]}: no history tokens and "
                             f"expected_tokens_by_candidate.{config['operator']}.{candidates[level]} is null in the config")
        return costs[candidates[level]]
    labels = [t['label'] for t in tasks]
    report = {'operator': config['operator'], 'labelled': len(tasks), 'unlabelled_skipped': skipped['unlabelled'], 'censored_skipped': skipped['censored'],
              'labelled_per_level': {n: labels.count(i) for i, n in enumerate(levels)},
              'laya_min_confidence': difficulty.calibration(config).get('laya_min_confidence', config['laya_min_confidence']),
              'strategies': {}}
    for name, levels_predicted in predicted.items():
        s = metrics(list(zip(levels_predicted, labels)), cost)
        s['by_operation'] = {op: metrics([(p, l) for p, l, t in zip(levels_predicted, labels, tasks) if t['operation'] == op], cost)
                             for op in sorted({t['operation'] for t in tasks})}
        report['strategies'][name] = s
    report['gate'] = dict(zip(('verdict', 'reasons'), gate(report, config)))
    return report


def table(report):
    f = lambda v, pct=True: '-' if v is None else (f'{v:.1%}' if pct else f'{v:,.0f}')
    lines = [f"{'strategy':<20}{'n':>5}{'exact':>9}{'within-1':>10}{'under':>9}{'over':>9}{'exp. tokens':>13}"]
    for name, s in report['strategies'].items():
        lines.append(f"{name:<20}{s['n']:>5}{f(s['exact']):>9}{f(s['within1']):>10}{f(s['under']):>9}{f(s['over']):>9}{f(s['expected_tokens'], False):>13}")
    lines += ['', f"labelled per level: {report['labelled_per_level']}; unlabelled skipped: {report['unlabelled_skipped']}; censored skipped: {report['censored_skipped']}",
              f"gate: {report['gate']['verdict']}"] + [f'  - {r}' for r in report['gate']['reasons']]
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--operator', choices=('claude', 'codex'))
    parser.add_argument('--gold', type=Path, default=GOLD)
    parser.add_argument('--history-labels', type=Path, help='JSONL from labels_from_history.py; only exact labels are used')
    parser.add_argument('--no-laya', action='store_true', help='evaluate the heuristic only; never contact the server')
    parser.add_argument('--out', type=Path, help='JSON report (default: difficulty-eval.json next to history.jsonl)')
    args = parser.parse_args()
    operator = args.operator or detect_operator()
    config = load_config(operator)
    paths = [args.gold] + ([args.history_labels] if args.history_labels else [])
    tasks, skipped = load_tasks(paths, config, exact_only=paths[1:])
    history = read_history(history_path(operator))
    report = evaluate(tasks, skipped, config, history, not args.no_laya)
    out = args.out or history_path(operator).with_name('difficulty-eval.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(table(report))
    print(f'report: {out}')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        print(f'cc-router: {error}', file=sys.stderr)
        sys.exit(1)
