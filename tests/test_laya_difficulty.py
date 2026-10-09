"""Laya difficulty mode against a local mock of /v1/systemone/batch; never contacts laya-serve."""
import copy
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from test_v2 import ROOT, STATE
from candidates import for_host, validate_config
from route import route_one
import difficulty

BIAS = 0.3
LEVELS = ['trivial', 'mechanical', 'routine', 'complex', 'open']


def setUpModule():
    # difficulty.calibration reads a file under HOME; never let the user's real one reach these tests
    global old_home, home
    old_home, home = os.environ.get('HOME'), tempfile.TemporaryDirectory()
    os.environ['HOME'] = home.name


def tearDownModule():
    os.environ['HOME'] = old_home
    home.cleanup()


def peak(index):
    return [0.9 if i == index else 0.025 for i in range(5)]


# description -> the "true" distribution over L1..L5 that the mock model believes
TRUTH = {'agree task': peak(2), 'lower task': peak(1), 'higher task': peak(3), 'far task': peak(4),
         'unsure task': [0.2] * 5}


class BatchHandler(BaseHTTPRequestHandler):
    # position-biased mock: the first listed option gains BIAS before normalising, so every
    # rotation returns a different distribution and only the average recovers the truth
    requests = []
    status = 200
    payload = None

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        BatchHandler.requests.append((self.path, body))
        if BatchHandler.payload is not None:
            encoded = BatchHandler.payload
        else:
            results = []
            for state in body['states']:
                truth = TRUTH.get(state['description'].split('\n')[0], TRUTH['unsure task'])
                answers = {}
                for name, question in body['questions'].items():
                    scores = {key: truth[int(key[1]) - 1] + (BIAS if key == next(iter(question['criteria'])) else 0)
                              for key in question['criteria']}
                    total = sum(scores.values())
                    answers[name] = {'probabilities': {key: value / total for key, value in scores.items()}}
                results.append({'answers': answers})
            encoded = json.dumps({'results': results}).encode()
        self.send_response(BatchHandler.status)
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_):
        pass


def difficulty_raw(port, **overrides):
    raw = json.loads((ROOT / 'config/ladder.json').read_text())
    raw.update(backend='laya', laya_mode='difficulty', **overrides)
    raw['laya_urls']['codex'] = f'http://127.0.0.1:{port}/v1/systemone'
    return raw


class Mock:
    def __enter__(self):
        BatchHandler.requests, BatchHandler.status, BatchHandler.payload = [], 200, None
        self.server = HTTPServer(('127.0.0.1', 0), BatchHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @property
    def port(self):
        return self.server.server_port

    def config(self, **overrides):
        return for_host(difficulty_raw(self.port, **overrides), 'codex')


def task(description, **overrides):
    return dict(STATE, description=description, **overrides)


class DifficultyRoutingTest(unittest.TestCase):
    def test_rotations_in_one_batch_request_and_average(self):
        with Mock() as mock:
            decision = route_one(task('agree task'), mock.config(), [])
        self.assertEqual(len(BatchHandler.requests), 1)
        path, body = BatchHandler.requests[0]
        self.assertEqual(path, '/v1/systemone/batch')
        self.assertEqual(list(body['questions']), [f'difficulty#r{r}' for r in range(5)])
        orders = [list(q['criteria']) for q in body['questions'].values()]
        self.assertEqual(orders[0], ['L1', 'L2', 'L3', 'L4', 'L5'])
        self.assertEqual(orders[1], ['L2', 'L3', 'L4', 'L5', 'L1'])
        self.assertEqual({o[0] for o in orders}, {'L1', 'L2', 'L3', 'L4', 'L5'})
        self.assertEqual(len({q['instructions'] for q in body['questions'].values()}), 1)
        self.assertNotIn('exec-', json.dumps(body))
        laya = decision['laya']
        self.assertEqual(laya['level'], 'routine')
        # every level leads one rotation: mean = (truth + BIAS / 5) / (1 + BIAS)
        expected = {n: (p + BIAS / 5) / (1 + BIAS) for n, p in zip(LEVELS, peak(2))}
        for name in LEVELS:
            self.assertAlmostEqual(laya['distribution'][name], expected[name])
        self.assertAlmostEqual(sum(laya['distribution'].values()), 1)
        self.assertAlmostEqual(laya['answer_confidence'], expected['routine'])
        self.assertAlmostEqual(laya['expected_level'], sum(i * expected[n] for i, n in enumerate(LEVELS)))
        self.assertEqual(laya['rotations'], 5)

    def test_rotations_return_different_distributions(self):
        # a flat truth leaves only the position bias: each rotation favours its first-listed key
        TRUTH['weak task'] = [0.2] * 5
        try:
            with Mock() as mock:
                decision = route_one(task('weak task'), mock.config(laya_min_confidence=0), [])
        finally:
            del TRUTH['weak task']
        questions = BatchHandler.requests[0][1]['questions']
        self.assertEqual(len({list(q['criteria'])[0] for q in questions.values()}), 5)
        for value in decision['laya']['distribution'].values():
            self.assertAlmostEqual(value, 0.2)

    def test_minimal_state_and_truncation(self):
        long_description = ' '.join(f'word{i}' for i in range(100))
        with Mock() as mock:
            with patch('sys.stderr') as stderr:
                route_one(task(long_description, files=2, ambiguous=True, critical=True, user_language='pt-BR'), mock.config(), [])
        sent = BatchHandler.requests[0][1]['states'][0]
        self.assertEqual(set(sent), {'description', 'operation'})
        self.assertEqual(len(sent['description'].split()), difficulty.MAX_WORDS)
        self.assertTrue(any('truncated' in str(call) for call in stderr.write.call_args_list))

    def test_agree_and_differ_by_one_and_conflict(self):
        # heuristic: implementation = rung 2 = exec-sol-medium = level "routine"
        cases = [('agree task', False, 'agree', 'exec-sol-medium'),
                 ('lower task', False, 'differ by 1: lower (not critical)', 'exec-sol-low'),
                 ('lower task', True, 'differ by 1: higher (critical)', 'exec-sol-medium'),
                 ('higher task', False, 'differ by 1: lower (not critical)', 'exec-sol-medium'),
                 ('higher task', True, 'differ by 1: higher (critical)', 'exec-astra-medium'),
                 ('far task', False, 'conflict: heuristic used', 'exec-sol-medium'),
                 ('far task', True, 'conflict: heuristic used', 'exec-sol-high')]
        with Mock() as mock:
            config = mock.config()
            for description, critical, combination, selected in cases:
                with self.subTest(description=description, critical=critical):
                    decision = route_one(task(description, critical=critical), config, [])
                    self.assertEqual(decision['laya']['combination'], combination)
                    self.assertEqual(decision['selected'], selected)
                    self.assertEqual(decision['backend'], 'laya')
                    self.assertIn(combination, decision['reason'])
                    self.assertEqual(decision['laya']['preferred'] is None, combination.startswith('conflict'))

    def test_abstains_below_min_confidence(self):
        with Mock() as mock:
            decision = route_one(task('unsure task'), mock.config(), [])
            self.assertEqual(decision['backend'], 'laya (abstained)')
            self.assertEqual(decision['laya']['combination'], 'abstained')
            self.assertEqual(decision['selected'], 'exec-sol-medium')
            self.assertIs(decision['laya']['min_confidence_calibrated'], False)
            self.assertIn('uncalibrated threshold', decision['reason'])
            # the threshold is configurable: 0.1 lets the 0.2 answer through
            decision = route_one(task('unsure task'), mock.config(laya_min_confidence=0.1), [])
            self.assertEqual(decision['backend'], 'laya')

    def test_gates_keep_priority_over_laya(self):
        with Mock() as mock:
            config = mock.config()
            capped = route_one(task('higher task', critical=True, user_ceiling='exec-sol-low'), config, [])
            self.assertEqual(capped['laya']['preferred'], 'exec-astra-medium')
            self.assertEqual(capped['selected'], 'exec-sol-low')
            floored = route_one(task('lower task', user_floor='exec-sol-high'), config, [])
            self.assertEqual(floored['selected'], 'exec-sol-high')
            # "open" is exec-astra-high, never the approval-gated xhigh/max rungs
            open_level = route_one(task('far task', operation='research'), config, [])
            self.assertNotIn(open_level['selected'], ('exec-astra-xhigh', 'exec-astra-max'))

    def test_unavailable_and_invalid_responses(self):
        with Mock() as mock:
            config = mock.config()
            with patch('difficulty.request', side_effect=URLError('offline')):
                decision = route_one(task('agree task'), config, [])
            self.assertEqual(decision['backend'], 'heuristic (laya unavailable)')
            self.assertNotIn('laya', decision)
            for status, payload in [(200, b'not json'), (200, b'{}'), (200, b'{"results":[]}'),
                                    (200, b'{"results":[{"answers":{}}]}'), (500, b'{}'),
                                    (200, json.dumps({'results': [{'answers': {f'difficulty#r{r}': {'probabilities': {
                                        'L1': .9, 'L2': .9, 'L3': 0, 'L4': 0, 'L5': 0}} for r in range(5)}}]}).encode())]:
                BatchHandler.status, BatchHandler.payload = status, payload
                with self.subTest(status=status, payload=payload[:30]), self.assertRaisesRegex(ValueError, 'laya response'):
                    route_one(task('agree task'), config, [])

    def test_more_than_64_states_is_refused_without_a_request(self):
        with Mock() as mock:
            with self.assertRaisesRegex(ValueError, 'at most|1 to 64'):
                difficulty.request([task('agree task')] * 65, mock.config())
        self.assertEqual(BatchHandler.requests, [])

    def test_per_candidate_mode_is_the_default_and_unchanged(self):
        raw = json.loads((ROOT / 'config/ladder.json').read_text())
        del raw['laya_mode']
        self.assertEqual(validate_config(raw)['laya_mode'], 'per_candidate')
        config = for_host(raw, 'codex')
        config['backend'] = 'laya'
        with patch('route.laya_probabilities', return_value={c['agent']: .1 for c in config['ladder']}) as probabilities, \
                patch('difficulty.request', side_effect=AssertionError('difficulty mode off')):
            decision = route_one(task('agree task'), config, [])
        probabilities.assert_called_once()
        self.assertEqual(decision['backend'], 'laya (no opinion)')
        self.assertNotIn('laya', decision)


class DifficultyCLITest(unittest.TestCase):
    def run_route(self, directory, raw, payload, *args):
        config_path = Path(directory) / 'config.json'
        config_path.write_text(json.dumps(raw))
        env = {'HOME': directory, 'PATH': os.environ.get('PATH', ''),
               'CC_ROUTER_OPERATOR': 'codex', 'CC_ROUTER_CONFIG': str(config_path)}
        return subprocess.run([sys.executable, str(ROOT / 'scripts/route.py'), json.dumps(payload), *args],
                              cwd=ROOT, env=env, text=True, capture_output=True)

    def test_batch_of_8_makes_one_request_and_logs_the_event(self):
        names = ['agree task', 'lower task', 'higher task', 'far task'] * 2
        states = [task(n, targets=[]) for n in names]
        with Mock() as mock, tempfile.TemporaryDirectory() as directory:
            result = self.run_route(directory, difficulty_raw(mock.port), states)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(BatchHandler.requests), 1)
            path, body = BatchHandler.requests[0]
            self.assertEqual(path, '/v1/systemone/batch')
            self.assertEqual([s['description'] for s in body['states']], names)
            self.assertEqual(len(body['questions']), 5)
            decisions = json.loads(result.stdout)
            self.assertEqual([d['laya']['level'] for d in decisions], ['routine', 'mechanical', 'complex', 'open'] * 2)
            self.assertEqual({d['laya']['batch_states'] for d in decisions}, {8})
            events = [json.loads(line) for line in (Path(directory) / '.codex/cc-router/history.jsonl').read_text().splitlines()]
            logged = [e for e in events if e['event'] == 'decision']
            self.assertEqual(len(logged), 8)
            for event, decision in zip(logged, decisions):
                for key in ('level', 'distribution', 'answer_confidence', 'expected_level', 'combination', 'final_level'):
                    self.assertEqual(event['laya'][key], decision['laya'][key])
                self.assertEqual(set(event['laya']['distribution']), set(LEVELS))

    def test_single_task_and_more_than_64_tasks_via_cli(self):
        with Mock() as mock, tempfile.TemporaryDirectory() as directory:
            result = self.run_route(directory, difficulty_raw(mock.port), task('agree task'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['laya']['level'], 'routine')
            self.assertEqual(len(BatchHandler.requests), 1)
            states = [dict(task('agree task'), step_id=f's{i}', write_targets=[]) for i in range(65)]
            result = self.run_route(directory, difficulty_raw(mock.port), states)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('64', result.stderr)
            self.assertEqual(len(BatchHandler.requests), 1)


class DifficultySchedulerTest(unittest.TestCase):
    def test_next_routes_all_ready_tasks_in_one_request(self):
        from scheduler import initialize, reserve
        with Mock() as mock:
            config = mock.config()
            names = ['agree task', 'lower task', 'higher task', 'far task']
            plan = [dict(STATE, step_id=f's{i}', description=n, write_targets=[f's{i}'], acceptance='tests pass')
                    for i, n in enumerate(names)]
            plan.append(dict(plan[0], step_id='last', depends_on=['s0'], write_targets=['last']))
            run = initialize(plan, config)
            dispatch = reserve(run, config, [], 4)
        self.assertEqual(len(dispatch), 4)
        self.assertEqual(len(BatchHandler.requests), 1)
        self.assertEqual(len(BatchHandler.requests[0][1]['states']), 4)
        levels = [run['tasks'][d['step_id']]['decision']['laya']['level'] for d in dispatch]
        self.assertEqual(levels, ['routine', 'mechanical', 'complex', 'open'])


class DifficultyConfigTest(unittest.TestCase):
    def base(self):
        return json.loads((ROOT / 'config/ladder.json').read_text())

    def test_shipped_config_validates(self):
        config = validate_config(self.base())
        self.assertEqual(config['laya_mode'], 'per_candidate')
        self.assertEqual(list(config['laya_difficulty']['levels']), LEVELS)
        self.assertEqual(config['level_to_candidate']['claude']['open'], 'exec-opus-high')
        self.assertNotIn('exec-opus-xhigh', config['level_to_candidate']['claude'].values())

    def test_bad_difficulty_config_is_rejected(self):
        def mutate(change):
            raw = self.base()
            change(raw)
            return raw
        bad = {
            'mode': lambda r: r.update(laya_mode='both'),
            'rotations zero': lambda r: r.update(laya_rotations=0),
            'rotations six': lambda r: r.update(laya_rotations=6),
            'rotations bool': lambda r: r.update(laya_rotations=True),
            'confidence high': lambda r: r.update(laya_min_confidence=1.5),
            'confidence negative': lambda r: r.update(laya_min_confidence=-0.1),
            'calibrated type': lambda r: r.update(laya_min_confidence_calibrated='no'),
            'four levels': lambda r: r['laya_difficulty']['levels'].pop('open'),
            'six levels': lambda r: r['laya_difficulty']['levels'].update(extreme='x'),
            'empty level text': lambda r: r['laya_difficulty']['levels'].update(trivial=''),
            'no question': lambda r: r['laya_difficulty'].pop('question'),
            'unknown agent': lambda r: r['level_to_candidate']['codex'].update(open='exec-missing'),
            'agent of another host': lambda r: r['level_to_candidate']['codex'].update(open='exec-opus-high'),
            'missing level': lambda r: r['level_to_candidate']['codex'].pop('open'),
            'unknown host': lambda r: r['level_to_candidate'].update(other={}),
            'decreasing rungs': lambda r: r['level_to_candidate']['codex'].update(trivial='exec-astra-high'),
        }
        for name, change in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                validate_config(mutate(change))

    def test_difficulty_mode_requires_a_mapping_for_enabled_hosts(self):
        raw = self.base()
        raw.update(laya_mode='difficulty')
        del raw['level_to_candidate']['codex']
        raw['ladders']['codex'][0]['agent'] = 'exec-renamed'  # the default mapping no longer fits this ladder
        with self.assertRaisesRegex(ValueError, 'level_to_candidate.codex'):
            validate_config(raw)
        raw['laya_enabled_operators'] = ['claude']
        validate_config(raw)


class MigrateTest(unittest.TestCase):
    def test_migrate_adds_new_keys_with_timestamped_backup(self):
        raw = json.loads((ROOT / 'config/ladder.json').read_text())
        for key in ('laya_mode', 'laya_difficulty', 'laya_rotations', 'laya_min_confidence',
                    'laya_min_confidence_calibrated', 'level_to_candidate'):
            del raw[key]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'router.json'
            original = json.dumps(raw)
            path.write_text(original)
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/migrate.py'), str(path), '--write', str(path)],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            backups = list(Path(directory).glob('router.json.*.bak'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), original)
            migrated = json.loads(path.read_text())
            self.assertEqual(migrated['laya_mode'], 'per_candidate')
            self.assertEqual(migrated['laya_rotations'], 5)
            self.assertEqual(migrated['laya_min_confidence'], 0.5)
            self.assertIs(migrated['laya_min_confidence_calibrated'], False)
            self.assertEqual(list(migrated['laya_difficulty']['levels']), LEVELS)
            self.assertEqual(migrated['level_to_candidate']['codex']['trivial'], 'exec-luna-low')
            self.assertEqual(migrated, validate_config(migrated))


if __name__ == '__main__':
    unittest.main()
