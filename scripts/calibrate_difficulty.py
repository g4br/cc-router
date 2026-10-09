"""Fit a temperature and an abstention threshold for the Laya difficulty distribution from exact labels.

Writes laya-calibration.json next to history.jsonl (never inside the skill folder); difficulty.py
then applies the temperature and uses laya_min_confidence from it. Needs the live laya-serve.
Stdlib grid search: laya's fit_abstention_thresholds works on raw logits records, not on the
averaged 5-way distribution this mode produces.
"""
import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import URLError

from common import load_config, detect_operator, calibration_path, skill_dir
from eval_difficulty import GOLD, load_tasks
import difficulty

TEMPERATURES = [0.25 + 0.05 * i for i in range(76)]  # 0.25 .. 4.00


def distributions(tasks, config):
    answers = []
    for start in range(0, len(tasks), difficulty.MAX_STATES):
        answers += difficulty.request(tasks[start:start + difficulty.MAX_STATES], config, calibrated=False)
    return [[a['distribution'][n] for n in config['laya_difficulty']['levels']] for a in answers]


def fit_temperature(dists, labels):
    nll = lambda t: -sum(math.log(max(difficulty.sharpen(d, t)[l], 1e-9)) for d, l in zip(dists, labels))
    return min(TEMPERATURES, key=nll)


def fit_threshold(dists, labels, target_accuracy, min_coverage):
    """Lowest confidence cut whose covered answers reach target_accuracy at >= min_coverage; None if none does."""
    scored = sorted(((max(d), d.index(max(d)) == l) for d, l in zip(dists, labels)))
    for i, (cut, _) in enumerate(scored):
        covered = scored[i:]
        accuracy, coverage = sum(ok for _, ok in covered) / len(covered), len(covered) / len(scored)
        if coverage < min_coverage:
            break
        if accuracy >= target_accuracy:
            return {'laya_min_confidence': math.floor(cut * 1e6) / 1e6, 'coverage': coverage, 'accuracy': accuracy}
    return None


def calibrate(tasks, config, min_labels, target_accuracy, min_coverage):
    if len(tasks) < max(min_labels, 1):
        raise ValueError(f'refusing to calibrate: {len(tasks)} exact-labelled tasks, need at least {max(min_labels, 1)}. '
                         'Fill the labels in tests/data/difficulty_gold.jsonl (see tests/data/README.md).')
    labels = [t['label'] for t in tasks]
    dists = distributions(tasks, config)
    temperature = fit_temperature(dists, labels)
    scaled = [difficulty.sharpen(d, temperature) for d in dists]
    threshold = fit_threshold(scaled, labels, target_accuracy, min_coverage)
    if threshold is None:
        raise ValueError(f'no abstention threshold reaches {target_accuracy:.0%} accuracy at >= {min_coverage:.0%} coverage '
                         f'(temperature {temperature:.2f}, {len(tasks)} tasks); nothing written')
    return dict(temperature=temperature, **threshold, target_accuracy=target_accuracy, n_labelled=len(tasks),
                checkpoint=config['laya_checkpoint'], rotations=config['laya_rotations'],
                fitted_at=datetime.now().astimezone().isoformat(timespec='seconds'))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--operator', choices=('claude', 'codex'))
    parser.add_argument('--gold', type=Path, default=GOLD)
    parser.add_argument('--history-labels', type=Path, help='JSONL from labels_from_history.py; only exact labels are used')
    parser.add_argument('--min-labels', type=int, default=20)
    parser.add_argument('--target-accuracy', type=float, default=0.8)
    parser.add_argument('--min-coverage', type=float, default=0.2)
    parser.add_argument('--out', type=Path, help='default: laya-calibration.json next to history.jsonl')
    args = parser.parse_args()
    operator = args.operator or detect_operator()
    config = load_config(operator)
    out = args.out or calibration_path(operator)
    if skill_dir in out.resolve().parents:
        raise ValueError(f'{out}: the calibration is local state and must not be written inside the skill folder')
    paths = [args.gold] + ([args.history_labels] if args.history_labels else [])
    tasks, _ = load_tasks(paths, config, exact_only=paths[1:])
    try:
        result = calibrate(tasks, config, args.min_labels, args.target_accuracy, args.min_coverage)
    except (URLError, TimeoutError, ConnectionError) as error:
        raise RuntimeError(f"Laya server unreachable at {config['laya_url']} ({error}). Start it with scripts/start_services.sh.") from None
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    print(f'written: {out}')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        print(f'cc-router: {error}', file=sys.stderr)
        sys.exit(1)
