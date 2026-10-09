"""Training JSONL for fine-tuning Laya on the 5-way difficulty question.

Merges the labelled rows of tests/data/difficulty_gold.jsonl with the exact labels from
labels_from_history.py (censored labels are ignored). One output row per task, in the
laya-evals dataset format (laya.evals.Dataset.from_jsonl): {"state", "questions", "expected"}.
`questions` holds the same rotated choice questions the router sends (difficulty.questions);
`expected` maps each rotation to the key of the labelled level (L1..L5), so a trainer sees every
level in every slot. Refuses when there are 0 labelled rows. Default output: next to history.jsonl.
"""
import argparse
import json
import sys
from pathlib import Path

from common import load_config, detect_operator, history_path, read_history
from labels_from_history import labels
from difficulty import KEYS, questions, difficulty_state

GOLD = Path(__file__).resolve().parent.parent / 'tests' / 'data' / 'difficulty_gold.jsonl'
REPO = GOLD.parents[2]


def check(row, where, config):
    names = list(config['laya_difficulty']['levels'])
    description = row.get('description')
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f'{where}: description must be a non-empty string')
    if sum(ord(c) > 127 for c in description) > len(description) // 20:
        raise ValueError(f'{where}: description must be English (more than 5% non-ASCII characters)')
    if row.get('operation') not in config['base_level_by_operation']:
        raise ValueError(f"{where}: unknown operation {row.get('operation')!r}")
    if row['label'] not in names:
        raise ValueError(f"{where}: label {row['label']!r} not in {names}")


def gold_rows(path, config):
    rows = []
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            raise ValueError(f'{path.name}:{number}: invalid JSON') from None
        if row.get('label') is not None:
            check(row, f'{path.name}:{number}', config)
            rows.append(row)
    return rows


def build(rows, config):
    names = list(config['laya_difficulty']['levels'])
    qs = questions(config)
    return [{'state': difficulty_state(r), 'questions': qs,
             'expected': {name: KEYS[names.index(r['label'])] for name in qs}, 'tags': [r['source']]} for r in rows]


def merge(gold, history, config):
    seen, rows = set(), []
    for source, group in (('gold', gold), ('history', history)):
        for row in group:
            if row['description'] in seen:
                continue
            seen.add(row['description'])
            rows.append({**row, 'source': source})
    return build(rows, config), rows


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--operator', choices=('claude', 'codex'))
    parser.add_argument('--gold', type=Path, default=GOLD)
    parser.add_argument('--out', type=Path, help='output JSONL (default: difficulty-train.jsonl next to history.jsonl)')
    parser.add_argument('--check-laya', action='store_true', help='also load the file with laya.evals.Dataset (needs laya)')
    args = parser.parse_args()
    operator = args.operator or detect_operator()
    config = load_config(operator)
    out = (args.out or history_path(operator).with_name('difficulty-train.jsonl')).resolve()
    if out.is_relative_to(REPO):
        raise ValueError(f'refusing to write inside the skill folder ({REPO}): the file may hold private task text')
    gold = gold_rows(args.gold, config)
    exact = [r for r in labels(read_history(history_path(operator)), config)[0] if not r['censored']]
    for r in exact:
        check(r, f"history task {r.get('task_id')}", config)
    data, rows = merge(gold, exact, config)
    if not data:
        raise ValueError('no labelled rows: fill "label" in the gold set (see tests/data/README.md) or collect exact labels in the history; nothing written')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(''.join(json.dumps(d, ensure_ascii=False) + '\n' for d in data), encoding='utf-8')
    per_level = {name: sum(r['label'] == name for r in rows) for name in config['laya_difficulty']['levels']}
    print(f"gold {len(gold)}, history exact {len(exact)}, total {len(data)} (duplicates dropped: {len(gold) + len(exact) - len(data)})")
    print('per level: ' + ', '.join(f'{k} {v}' for k, v in per_level.items()))
    print(f'wrote {out}')
    if args.check_laya:
        try:
            from laya.evals import Dataset
        except ImportError:
            raise RuntimeError('--check-laya needs laya: python3 -m pip install "laya[serve]"') from None
        print(f'laya.evals accepted {len(Dataset.from_jsonl(str(out)))} rows')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        print(f'cc-router: {error}', file=sys.stderr)
        sys.exit(1)
