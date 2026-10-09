"""Labels from history, offline evaluation, gate and calibration; mock Laya only, no checkpoint."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_v2 import ROOT, STATE
from test_laya_difficulty import BatchHandler, Mock, TRUTH, LEVELS, peak, task
from candidates import for_host
from route import route_one
import calibrate_difficulty
import difficulty
import eval_difficulty
import labels_from_history

COSTS = {'exec-luna-low': 100, 'exec-sol-low': 200, 'exec-sol-medium': 300, 'exec-astra-medium': 1000, 'exec-astra-high': 1200}
LEVEL_TRUTH = {f'level{i} task': peak(i) for i in range(5)}


def setUpModule():
    global old_home, home
    old_home, home = os.environ.get('HOME'), tempfile.TemporaryDirectory()
    os.environ['HOME'] = home.name
    TRUTH.update(LEVEL_TRUTH)


def tearDownModule():
    for key in LEVEL_TRUTH:
        del TRUTH[key]
    os.environ['HOME'] = old_home
    home.cleanup()


def claude_config():
    return for_host(json.loads((ROOT / 'config/ladder.json').read_text()), 'claude')


def codex_config(mock, costs=COSTS):
    config = mock.config()
    config['expected_tokens_by_candidate'] = {'codex': dict(costs)}
    return config


def decision(did, task_id, agent, description='do the thing', operation='tweak'):
    return {'event': 'decision', 'id': did, 'task_id': task_id, 'selected': agent, 'description': description,
            'state': {'operation': operation, 'files': 1, 'ambiguous': False, 'critical': False}}


def result(did, ok, tokens=10, **extra):
    return dict({'event': 'result', 'id': did, 'result': 'success' if ok else 'failure', 'tokens': tokens, 'no_rework': ok}, **extra)


class GateConfigTest(unittest.TestCase):
    def test_shipped_defaults_and_bad_values(self):
        from candidates import validate_config
        raw = json.loads((ROOT / 'config/ladder.json').read_text())
        config = validate_config(raw)
        self.assertEqual((raw['backend'], raw['laya_mode']), ('heuristic', 'per_candidate'))
        self.assertEqual((config['gate_token_saving_min'], config['gate_under_routing_max_increase'], config['gate_min_tasks_per_level']),
                         (0.10, 0.02, 10))
        self.assertTrue(all(v is None for table in config['expected_tokens_by_candidate'].values() for v in table.values()))
        for change in (lambda r: r.update(gate_token_saving_min=2), lambda r: r.update(gate_min_tasks_per_level=0),
                       lambda r: r.update(expected_tokens_by_candidate={'other': {}}),
                       lambda r: r.update(expected_tokens_by_candidate={'claude': {'exec-haiku-low': -5}})):
            bad = json.loads(json.dumps(raw))
            change(bad)
            with self.assertRaises(ValueError):
                validate_config(bad)


class LabelsFromHistoryTest(unittest.TestCase):
    def events(self):
        no_description = decision('e1', 'E', 'exec-haiku-low', description=None)
        no_description['state'] = {'operation': 'tweak'}
        return [decision('a1', 'A', 'exec-haiku-low'), result('a1', False),
                decision('a2', 'A', 'exec-haiku-high'), result('a2', True),           # failed at 0, succeeded at 1: exact
                decision('b1', 'B', 'exec-sonnet-medium'), result('b1', True),         # first try at 2: censored
                decision('c1', 'C', 'exec-haiku-low'), result('c1', False),
                decision('c2', 'C', 'exec-sonnet-medium'), result('c2', True),         # jumped two levels: skipped
                decision('d1', 'D', 'exec-haiku-low'), result('d1', False),            # never succeeded: skipped
                no_description, result('e1', True),                                    # missing field: skipped
                decision('f1', 'F', 'exec-sonnet-medium'), result('f1', False, failure_kind='rate_limit'),
                decision('f2', 'F', 'exec-sonnet-medium'), result('f2', True),         # infra failure ignored: censored
                decision('g1', 'G', 'exec-removed-agent'), result('g1', True)]         # unknown candidate: skipped

    def test_exact_censored_and_visible_skips(self):
        out, skipped = labels_from_history.labels(self.events(), claude_config())
        by_task = {r['task_id']: r for r in out}
        self.assertEqual({k: (v['label'], v['censored']) for k, v in by_task.items()},
                         {'A': ('mechanical', False), 'B': ('routine', True), 'F': ('routine', True)})
        self.assertEqual(skipped, {'success not exactly one level above the last failure': 1,
                                   'never succeeded without rework': 1, 'missing description or operation': 1,
                                   'candidate not on the ladder': 1})
        self.assertEqual(by_task['A']['operation'], 'tweak')
        self.assertEqual(by_task['A']['files'], 1)

    def test_cli_prints_counts_to_stderr(self):
        with tempfile.TemporaryDirectory() as directory:
            history = Path(directory) / '.claude/cc-router/history.jsonl'
            history.parent.mkdir(parents=True)
            history.write_text(''.join(json.dumps(e) + '\n' for e in self.events()))
            out = Path(directory) / 'labels.jsonl'
            run = subprocess.run([sys.executable, str(ROOT / 'scripts/labels_from_history.py'), '--operator', 'claude', '--out', str(out)],
                                 env={'HOME': directory, 'PATH': os.environ['PATH']}, text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('1 exact, 2 censored; skipped 4', run.stderr)
            self.assertEqual(len(out.read_text().splitlines()), 3)


class EvalTest(unittest.TestCase):
    def tasks(self, *specs):
        return [{'description': d, 'operation': 'implementation', 'label': LEVELS.index(label), 'files': 0,
                 'ambiguous': False, 'critical': False} for d, label in specs]

    def test_metrics_and_expected_tokens_arithmetic(self):
        # heuristic: implementation = rung 2 = "routine" for all three; history overrides the config cost of sol-low
        tasks = self.tasks(('agree task', 'routine'), ('lower task', 'mechanical'), ('higher task', 'complex'))
        history = [e for i, tokens in enumerate((300, 500)) for e in (
            {'event': 'decision', 'id': f'h{i}', 'agent': 'exec-sol-low', 'state': {}}, result(f'h{i}', True, tokens))]
        with Mock() as mock, patch('eval_difficulty.laya_probabilities',
                                   return_value={c: 1.0 if c >= 'exec-sol-medium' else 0.0 for c in COSTS} | {'exec-sol-high': 1.0}) as per_candidate:
            config = codex_config(mock)
            report = eval_difficulty.evaluate(tasks, {'unlabelled': 2, 'censored': 0}, config, history)
        self.assertEqual(per_candidate.call_count, 3)
        h, d = report['strategies']['heuristic'], report['strategies']['laya difficulty']
        self.assertEqual((h['exact'], h['within1'], h['under'], h['over']), (1 / 3, 1.0, 1 / 3, 1 / 3))
        # costs: sol-low 400 (median of history), sol-medium 300, astra-medium 1000
        # heuristic: 300 + 300 (over) + (300 + 1000) (under: next level once more)
        self.assertAlmostEqual(h['expected_tokens'], (300 + 300 + 1300) / 3)
        self.assertEqual((d['exact'], d['under'], d['over']), (1.0, 0.0, 0.0))
        self.assertAlmostEqual(d['expected_tokens'], (300 + 400 + 1000) / 3)
        # combined: agree -> routine; lower task differs by 1, not critical -> lower; higher task -> lower (under)
        c = report['strategies']['combined']
        self.assertEqual((c['exact'], c['under'], c['over']), (2 / 3, 1 / 3, 0.0))
        self.assertEqual(report['strategies']['laya per_candidate']['n'], 3)
        self.assertEqual(h['by_operation']['implementation']['n'], 3)
        self.assertEqual(report['unlabelled_skipped'], 2)
        self.assertEqual(report['labelled_per_level'], {'trivial': 0, 'mechanical': 1, 'routine': 1, 'complex': 1, 'open': 0})
        self.assertEqual(report['gate']['verdict'], 'FAIL')
        self.assertTrue(report['gate']['reasons'][0].startswith('insufficient labels'))

    def test_missing_cost_names_the_candidate(self):
        with Mock() as mock:
            config = codex_config(mock, {**COSTS, 'exec-sol-medium': None})
            with self.assertRaisesRegex(ValueError, 'exec-sol-medium'):
                eval_difficulty.evaluate(self.tasks(('agree task', 'routine')), {'unlabelled': 0, 'censored': 0}, config, [], use_laya=False)

    def test_no_labels_fails_without_contacting_the_server(self):
        with Mock() as mock:
            report = eval_difficulty.evaluate([], {'unlabelled': 10, 'censored': 0}, codex_config(mock), [])
            self.assertEqual(BatchHandler.requests, [])
        self.assertEqual(list(report['strategies']), ['heuristic', 'laya per_candidate', 'laya difficulty', 'combined'])
        self.assertEqual(report['gate']['verdict'], 'FAIL')
        self.assertIn('insufficient labels', report['gate']['reasons'][0])

    def test_server_down_is_a_clear_error(self):
        with Mock() as mock:
            config = codex_config(mock)
        with self.assertRaisesRegex(RuntimeError, 'unreachable.*--no-laya'):
            eval_difficulty.evaluate(self.tasks(('agree task', 'routine')), {'unlabelled': 0, 'censored': 0}, config, [])

    def test_gate_passes_on_a_synthetic_set_that_meets_the_thresholds(self):
        tasks = self.tasks(*[(f'level{i} task', LEVELS[i]) for i in range(5) for _ in range(10)])
        with Mock() as mock, patch('eval_difficulty.laya_probabilities', return_value={c: 1.0 for c in COSTS} | {'exec-sol-high': 1.0}):
            report = eval_difficulty.evaluate(tasks, {'unlabelled': 0, 'censored': 0}, codex_config(mock), [])
        # heuristic always "routine": 300, 300, 300, 1300, 1300 -> 700; difficulty exact: 100..1200 -> 560 (-20%)
        self.assertAlmostEqual(report['strategies']['heuristic']['expected_tokens'], 700)
        self.assertAlmostEqual(report['strategies']['laya difficulty']['expected_tokens'], 560)
        self.assertEqual(report['gate'], {'verdict': 'PASS', 'reasons': []})

    def test_gate_thresholds(self):
        config = {'gate_token_saving_min': 0.10, 'gate_under_routing_max_increase': 0.02, 'gate_min_tasks_per_level': 10}
        def report(tokens, under, per_level=10):
            s = lambda t, u: {'n': 50, 'expected_tokens': t, 'under': u}
            return {'labelled_per_level': {n: per_level for n in LEVELS},
                    'strategies': {'heuristic': s(100, 0.10), 'laya difficulty': s(tokens, under), 'combined': s(100, 0.10)}}
        self.assertEqual(eval_difficulty.gate(report(90, 0.12), config)[0], 'PASS')      # exactly 10% and +2 pp
        self.assertEqual(eval_difficulty.gate(report(91, 0.10), config)[0], 'FAIL')      # saving 9%
        verdict, reasons = eval_difficulty.gate(report(80, 0.13), config)                # under-routing +3 pp
        self.assertEqual(verdict, 'FAIL')
        self.assertIn('under-routing', reasons[0])
        verdict, reasons = eval_difficulty.gate(report(50, 0.0, per_level=9), config)    # one level short
        self.assertEqual(verdict, 'FAIL')
        self.assertIn('insufficient labels', reasons[0])

    def test_load_tasks_skips_unlabelled_and_rejects_bad_rows(self):
        config = claude_config()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'gold.jsonl'
            rows = [{'description': 'a', 'operation': 'read', 'label': None}, {'description': 'b', 'operation': 'read', 'label': 'open'}]
            path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
            tasks, skipped = eval_difficulty.load_tasks([path], config)
            self.assertEqual((len(tasks), skipped['unlabelled']), (1, 1))
            path.write_text(json.dumps(dict(rows[1], label='hard')) + '\n')
            with self.assertRaisesRegex(ValueError, 'gold.jsonl:1.*hard'):
                eval_difficulty.load_tasks([path], config)

    def test_shipped_gold_has_ten_unlabelled_examples(self):
        rows = [json.loads(line) for line in (ROOT / 'tests/data/difficulty_gold.jsonl').read_text().splitlines()]
        self.assertEqual(len(rows), 10)
        self.assertEqual({r['label'] for r in rows}, {None})
        self.assertTrue(all(len(r['description'].split()) <= 60 for r in rows))
        self.assertEqual(eval_difficulty.load_tasks([ROOT / 'tests/data/difficulty_gold.jsonl'], claude_config())[0], [])


class CalibrationTest(unittest.TestCase):
    def calibration_file(self, **data):
        path = difficulty.calibration_path('codex')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
        self.addCleanup(path.unlink, missing_ok=True)

    def test_file_overrides_the_config_threshold(self):
        with Mock() as mock:
            config = mock.config()
            before = route_one(task('unsure task'), config, [])
            self.assertEqual(before['backend'], 'laya (abstained)')
            self.assertIs(before['laya']['min_confidence_calibrated'], False)
            self.calibration_file(temperature=1.0, laya_min_confidence=0.1)
            after = route_one(task('unsure task'), config, [])
        self.assertEqual(after['backend'], 'laya')
        self.assertEqual(after['laya']['min_confidence'], 0.1)
        self.assertIs(after['laya']['min_confidence_calibrated'], True)
        self.assertEqual(config['laya_min_confidence'], 0.5)

    def test_temperature_sharpens_and_invalid_file_is_an_error(self):
        self.assertEqual(difficulty.sharpen([0.2] * 5, 3), [0.2] * 5)
        sharp = difficulty.sharpen([0.5, 0.3, 0.1, 0.05, 0.05], 0.5)
        self.assertAlmostEqual(sharp[0], 0.25 / 0.355)  # squares then renormalises
        with Mock() as mock:
            config = mock.config()
            self.calibration_file(temperature=0.5, laya_min_confidence=0.1)
            plain = difficulty.request([task('agree task')], config, calibrated=False)[0]
            fitted = difficulty.request([task('agree task')], config)[0]
            self.assertGreater(fitted['answer_confidence'], plain['answer_confidence'])
            self.calibration_file(temperature=0)
            with self.assertRaisesRegex(ValueError, 'laya calibration'):
                difficulty.request([task('agree task')], config)

    def test_refuses_without_labels_and_fits_with_them(self):
        config = claude_config()
        with self.assertRaisesRegex(ValueError, 'refusing to calibrate: 0 exact-labelled'):
            calibrate_difficulty.calibrate([], config, 20, 0.8, 0.2)
        good, bad = [0.9, 0.025, 0.025, 0.025, 0.025], [0.4, 0.3, 0.1, 0.1, 0.1]
        cut = calibrate_difficulty.fit_threshold([good, good, bad, bad], [0, 0, 1, 1], 0.8, 0.2)
        self.assertEqual((cut['laya_min_confidence'], cut['coverage'], cut['accuracy']), (0.9, 0.5, 1.0))
        self.assertIsNone(calibrate_difficulty.fit_threshold([bad, bad], [1, 1], 0.8, 0.2))
        tasks = [{'description': f'level{i} task', 'operation': 'implementation', 'label': i, 'files': 0, 'ambiguous': False,
                  'critical': False} for i in range(5) for _ in range(4)]
        with Mock() as mock:
            fitted = calibrate_difficulty.calibrate(tasks, mock.config(), 20, 0.8, 0.2)
        self.assertEqual((fitted['n_labelled'], fitted['accuracy']), (20, 1.0))
        self.assertTrue(0 < fitted['laya_min_confidence'] <= 1)
        self.assertEqual(len(BatchHandler.requests), 1)

    def test_cli_refuses_with_the_shipped_unlabelled_gold(self):
        with tempfile.TemporaryDirectory() as directory:
            run = subprocess.run([sys.executable, str(ROOT / 'scripts/calibrate_difficulty.py'), '--operator', 'claude'],
                                 env={'HOME': directory, 'PATH': os.environ['PATH']}, text=True, capture_output=True)
            self.assertEqual(run.returncode, 1)
            self.assertIn('refusing to calibrate', run.stderr)
            self.assertFalse((Path(directory) / '.claude/cc-router/laya-calibration.json').exists())
            run = subprocess.run([sys.executable, str(ROOT / 'scripts/calibrate_difficulty.py'), '--operator', 'claude', '--out', str(ROOT / 'x.json')],
                                 env={'HOME': directory, 'PATH': os.environ['PATH']}, text=True, capture_output=True)
            self.assertIn('must not be written inside the skill folder', run.stderr)


if __name__ == '__main__':
    unittest.main()
