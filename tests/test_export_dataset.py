"""Fine-tuning export on synthetic labels; no checkpoint, no server."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import export_difficulty_dataset as export
from common import load_config
from test_v2 import ROOT

SCRIPT = ROOT / 'scripts' / 'export_difficulty_dataset.py'
CONFIG = load_config('claude')
NAMES = list(CONFIG['laya_difficulty']['levels'])


def row(i, label, **extra):
    return {'description': f'Synthetic task number {i}.', 'operation': 'read', 'label': label, 'source': 'test', **extra}


def run(home, *args):
    env = dict(os.environ, HOME=home, CC_ROUTER_OPERATOR='claude')
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env)


class ExportTest(unittest.TestCase):
    def test_refuses_without_labels(self):
        with tempfile.TemporaryDirectory() as home:
            result = run(home)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('no labelled rows', result.stderr)
            self.assertFalse((Path(home) / '.claude' / 'cc-router' / 'difficulty-train.jsonl').exists())

    def test_exports_valid_file(self):
        with tempfile.TemporaryDirectory() as home:
            gold = Path(home) / 'gold.jsonl'
            gold.write_text(''.join(json.dumps(row(i, NAMES[i % 5])) + '\n' for i in range(10)) +
                            json.dumps(row(99, None)) + '\n', encoding='utf-8')
            out = Path(home) / 'train.jsonl'
            result = run(home, '--gold', str(gold), '--out', str(out))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('gold 10, history exact 0, total 10', result.stdout)
            rows = [json.loads(line) for line in out.read_text().splitlines()]
            self.assertEqual(len(rows), 10)
            first = rows[1]
            self.assertEqual(first['state'], {'description': 'Synthetic task number 1.', 'operation': 'read'})
            self.assertEqual(set(first['expected']), set(first['questions']))
            self.assertEqual(set(first['expected'].values()), {'L2'})
            for q in first['questions'].values():
                self.assertEqual(q['type'], 'choice')
                self.assertEqual(sorted(q['criteria']), ['L1', 'L2', 'L3', 'L4', 'L5'])

    def test_merge_history_and_dedupe(self):
        data, rows = export.merge([row(1, 'trivial')], [row(1, 'open'), row(2, 'open')], CONFIG)
        self.assertEqual([r['source'] for r in rows], ['gold', 'history'])
        self.assertEqual(len(data), 2)

    def test_validation(self):
        for bad in (row(1, 'huge'), row(1, 'open', operation='nope'), row(1, 'open', description='  '),
                    row(1, 'open', description='Leia o arquivo e conte as linhas já existentes ção ção')):
            with self.assertRaises(ValueError):
                export.check(bad, 'x', CONFIG)

    def test_refuses_inside_repo(self):
        with tempfile.TemporaryDirectory() as home:
            result = run(home, '--out', str(ROOT / 'x.jsonl'))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('refusing to write inside the skill folder', result.stderr)


if __name__ == '__main__':
    unittest.main()
