import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from candidates import for_host, validate_config
from state import check_state

STATE = {'description': 'Implement a parser with a roundtrip test', 'operation': 'implementation',
         'files': 2, 'ambiguous': False, 'critical': False}


def fixture(host='codex'):
    return {'schema_version': 2, 'hosts': {host: {'candidates': [
        {'id': 'basic', 'model': 'modelo-futuro-xyz', 'effort': None, 'active': True,
         'approval': False, 'billing_mode': 'subscription', 'capabilities': ['implementation'],
         'resolved_model': 'version-1', 'consumption_tier': 0},
        {'id': 'deep', 'model': 'another-model', 'effort': 'custom', 'active': True,
         'approval': True, 'billing_mode': 'subscription', 'capabilities': ['implementation'],
         'resolved_model': 'version-2', 'consumption_tier': 1}]}}}


class V2ValidationTest(unittest.TestCase):
    def test_migration_preserves_custom_fields_and_candidates(self):
        raw = json.loads((ROOT / 'config/ladder.json').read_text())
        raw['custom_extension'] = {'keep': True}
        migrated = validate_config(raw)
        self.assertEqual(migrated, validate_config(raw))
        for host, ladder in raw['ladders'].items():
            self.assertEqual([c['agent'] for c in ladder], [c['id'] for c in migrated['hosts'][host]['candidates']])
        self.assertEqual(migrated['custom_extension'], raw['custom_extension'])
        self.assertNotIn('schema_version', raw)

    def test_invalid_state_fields(self):
        config = for_host(fixture(), 'codex')
        for key, value in [('files', -1), ('files', True), ('ambiguous', 'false'), ('critical', 0),
                           ('operation', 'bogus'), ('description', ''), ('targets', 'x'),
                           ('failed_with', 3), ('user_ceiling', 'missing'), ('attempt_count', False),
                           ('targets', ['../escape']), ('isolation', 'pretend')]:
            with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, key):
                check_state(dict(STATE, **{key: value}), config)

    def test_catalog_supports_future_names_null_and_custom_effort(self):
        for host in ('codex', 'claude'):
            config = for_host(fixture(host), host)
            self.assertIsNone(config['ladder'][0]['effort'])
            self.assertEqual(config['ladder'][1]['effort'], 'custom')

    def test_invalid_configuration(self):
        for mutation in ('duplicate', 'alias', 'empty', 'effort', 'bool', 'external_url', 'version'):
            raw = fixture()
            data = raw['hosts']['codex']
            if mutation == 'duplicate':
                data['candidates'].append(copy.deepcopy(data['candidates'][0]))
            elif mutation == 'alias':
                data['candidates'][0]['agent'] = 'deep'
            elif mutation == 'empty':
                data['candidates'] = []
            elif mutation == 'effort':
                data['supported_combinations'] = [{'model': 'modelo-futuro-xyz', 'effort': None}]
            elif mutation == 'bool':
                data['candidates'][0]['active'] = 'false'
            elif mutation == 'external_url':
                raw['laya_url'] = 'https://paid.example/v1'
            else:
                raw['schema_version'] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_config(raw)

    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'project'
            root.mkdir()
            (root / 'escape').symlink_to(root.parent, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'outside project_root'):
                check_state(dict(STATE, project_root=str(root), targets=['escape/file']), for_host(fixture(), 'codex'))

    def test_invalid_cli_does_not_write_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text(json.dumps(fixture()))
            env = dict(os.environ, HOME=directory, CC_ROUTER_CONFIG=str(path), CC_ROUTER_OPERATOR='codex')
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/route.py'), json.dumps(dict(STATE, files=-1))], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((Path(directory) / '.codex/cc-router/history.jsonl').exists())

from selection import eligible_candidates, select
from telemetry import estimates, summarize, profile
from failures import diagnose
from route import route_one


def observations(c, count, tokens, failures=0, host='codex', task_state=None):
    events = []
    for i in range(count):
        ident = f'{c["id"]}-{i}'
        events.append({'event': 'decision', 'id': ident, 'operator': host, 'task_id': ident,
                       'task_profile': profile(task_state or STATE), 'scores': {c['id']: .9}})
        events.append({'event': 'result', 'id': ident, 'result': 'success' if i >= failures else 'failure',
                       'verification': 'passed' if i >= failures else 'failed', 'no_rework': i >= failures,
                       'host_confirmed': True, 'effective_candidate': c['id'], 'resolved_model': c['resolved_model'],
                       'effective_effort': c['effort'], 'duration_s': tokens / 10,
                       'metrics': {'total_tokens': tokens, 'source': 'host_report', 'unit': 'tokens'}})
    return events


class SelectionTest(unittest.TestCase):
    def test_evidence_beats_order_for_both_hosts(self):
        for host in ('codex', 'claude'):
            config = for_host(fixture(host), host)
            candidates = config['ladder']
            events = observations(candidates[0], 40, 1000, host=host) + observations(candidates[1], 40, 100, host=host)
            data = estimates(events, STATE, candidates, config, {c['id']: .9 for c in candidates})
            for policy in ('economy', 'balanced', 'performance'):
                chosen, _, confidence, _ = select(dict(STATE, policy=policy), config, candidates, data, 0)
                self.assertEqual(chosen['id'], 'deep')
                self.assertEqual(confidence, 'observational')
            self.assertIsNotNone(data['deep']['calibration'])
            self.assertLess(data['deep']['calibration']['estimate'], 1)
            chosen, _, _, _ = select(STATE, config, candidates[::-1], data, 0)
            self.assertEqual(chosen['id'], 'deep')

    def test_versions_profiles_and_small_samples_do_not_mix(self):
        config = for_host(fixture(), 'codex')
        candidates = config['ladder']
        events = observations(candidates[0], 40, 100)
        candidates[0]['resolved_model'] = 'new-version'
        data = estimates(events, STATE, candidates, config)
        self.assertEqual(data['basic']['samples'], 0)
        candidates[0]['resolved_model'] = 'version-1'
        data = estimates(events, dict(STATE, critical=True), candidates, config)
        self.assertEqual(data['basic']['samples'], 0)
        data = estimates(observations(candidates[1], 1, 1), STATE, candidates, config)
        chosen, _, confidence, _ = select(STATE, config, candidates, data, 0)
        self.assertEqual(chosen['id'], 'basic')
        self.assertEqual(confidence, 'low')

    def test_constraints_and_billing(self):
        raw = fixture()
        raw['hosts']['codex']['candidates'][0]['availability'] = 'unavailable'
        config = for_host(raw, 'codex')
        eligible, excluded = eligible_candidates(STATE, config, diagnose(STATE, config))
        self.assertEqual([c['id'] for c in eligible], ['deep'])
        self.assertIn('unavailable_model_or_effort', excluded[0]['reasons'])
        eligible, _ = eligible_candidates(dict(STATE, user_ceiling='basic'), config, diagnose(STATE, config))
        self.assertEqual(eligible, [])
        config['ladder'][1]['billing_mode'] = 'external'
        eligible, _ = eligible_candidates(STATE, config, diagnose(STATE, config))
        self.assertEqual(eligible, [])

    def test_failure_stops_and_safe_retry(self):
        config = for_host(fixture(), 'codex')
        for kind in ('rate_limit', 'permission_denied', 'missing_context', 'unknown'):
            state = dict(STATE, failed_with='basic', failure_kind=kind, idempotent=True, diff_verified=True)
            decision = route_one(state, config, [])
            self.assertIsNone(decision['selected'])
            self.assertFalse(decision['execution']['applied'])
        for kind in ('transient_host', 'syntax_or_local_fix'):
            state = dict(STATE, failed_with='basic', failure_kind=kind, idempotent=True, diff_verified=True)
            decision = route_one(state, config, [])
            self.assertEqual(decision['selected'], 'basic')
            self.assertEqual(diagnose(dict(state, attempt_count=3), config)['action'], 'attempt_limit_reached')
            self.assertEqual(diagnose(dict(state, diff_verified=False), config)['action'], 'inspect_worktree_diff')
            self.assertEqual(diagnose(dict(state, idempotent=False), config)['action'], 'approve_non_idempotent_retry')

    def test_failure_and_retry_cost_is_attributed_to_completion(self):
        config = for_host(fixture(), 'codex')
        events = observations(config['ladder'][0], 2, 100, failures=1)
        events[0]['task_id'] = events[2]['task_id'] = 'same-task'
        report = summarize(events)
        self.assertEqual(report['completed_tasks'], 1)
        self.assertEqual(report['failures'], 1)
        self.assertEqual(report['completion_details'][0]['tokens'], 200)
        self.assertEqual(report['mean_attempts_to_completion'], 2)
        events[3]['metrics']['total_tokens'] = None
        self.assertIsNone(summarize(events)['completion_details'][0]['tokens'])

from unittest.mock import patch
from urllib.error import URLError
from common import read_history, log_event
from planning import plan, verify_changes


class LayaContractTest(unittest.TestCase):
    def test_offline_fallback_and_bad_contract_are_distinct(self):
        config = for_host(fixture(), 'codex')
        config['backend'] = 'laya'
        with patch('route.laya_probabilities', side_effect=URLError('offline')):
            decision = route_one(STATE, config, [])
        self.assertEqual(decision['backend'], 'heuristic (laya unavailable)')
        with patch('route.laya_probabilities', side_effect=ValueError('laya response: invalid')):
            with self.assertRaisesRegex(ValueError, 'laya response'):
                route_one(STATE, config, [])

    def test_heuristic_has_no_network(self):
        config = for_host(fixture(), 'codex')
        with patch('route.laya_probabilities', side_effect=AssertionError('network')):
            decision = route_one(STATE, config, [])
        self.assertFalse(decision['execution']['applied'])
        self.assertIsNone(decision['execution']['resolved_model'])


class PlanningTest(unittest.TestCase):
    def setUp(self):
        self.config = for_host(fixture(), 'codex')

    def test_dag_waves_and_host_limit(self):
        states = [dict(STATE, step_id='one', targets=['src/a']),
                  dict(STATE, step_id='two', targets=['src/a'], depends_on=['one']),
                  dict(STATE, step_id='three', targets=['src/b'])]
        schedule = plan(states, self.config)
        self.assertEqual([s['wave'] for s in schedule], [0, 1, 0])
        self.assertEqual([s['ready'] for s in schedule], [True, False, True])
        self.config['max_parallel'] = 1
        self.assertEqual([s['wave'] for s in plan(states, self.config)], [0, 1, 2])

    def test_cycles_write_read_resource_and_symlink_conflicts(self):
        a = dict(STATE, step_id='one', targets=['src'])
        b = dict(STATE, step_id='two', targets=['src/file'])
        with self.assertRaisesRegex(ValueError, 'conflict'):
            plan([a, b], self.config)
        b = dict(b, targets=[], read_targets=['src/file'])
        with self.assertRaisesRegex(ValueError, 'conflict'):
            plan([a, b], self.config)
        a['depends_on'], b['depends_on'] = ['two'], ['one']
        with self.assertRaisesRegex(ValueError, 'cycle'):
            plan([a, b], self.config)
        a = dict(STATE, targets=[], shared_resources=['database'])
        with self.assertRaisesRegex(ValueError, 'conflict'):
            plan([a, a], self.config)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'real').mkdir()
            (root / 'link').symlink_to(root / 'real', target_is_directory=True)
            a = dict(STATE, targets=['real'], project_root=directory)
            b = dict(STATE, targets=['link/new'], project_root=directory)
            with self.assertRaisesRegex(ValueError, 'conflict'):
                plan([a, b], self.config)

    def test_isolation_and_actual_changes(self):
        a = dict(STATE, step_id='a', targets=['src/a'], isolation='worktree')
        with self.assertRaisesRegex(ValueError, 'worktree support'):
            plan([a], self.config)
        a['isolation'] = 'sequential'
        b = dict(STATE, step_id='b', targets=['src/a'])
        self.assertEqual([s['wave'] for s in plan([a, b], self.config)], [0, 1])
        result = verify_changes([a, b], {'a': ['src/a', 'surprise'], 'b': ['src/a']})
        self.assertEqual(result['unexpected_steps'], ['a'])
        self.assertTrue(result['conflicts'])


class HistoryTest(unittest.TestCase):
    def test_multiple_process_append_and_partial_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            code = ('import sys; sys.path.insert(0, sys.argv[1]); from common import log_event; '
                    '[log_event({"event":"probe", "id":sys.argv[2]+"-"+str(i)}) for i in range(60)]')
            env = dict(os.environ, HOME=directory, CC_ROUTER_OPERATOR='codex')
            processes = [subprocess.Popen([sys.executable, '-c', code, str(ROOT / 'scripts'), str(i)], env=env,
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in range(6)]
            for process in processes:
                _, error = process.communicate(timeout=20)
                self.assertEqual(process.returncode, 0, error)
            path = Path(directory) / '.codex/cc-router/history.jsonl'
            events = read_history(path)
            self.assertEqual(len(events), 360)
            self.assertEqual(len({e['event_id'] for e in events}), 360)
            with path.open('a') as handle:
                handle.write('{"partial":')
            self.assertEqual(len(read_history(path)), 360)

    def test_cli_lifecycle_metrics_privacy_and_task_linkage(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text(json.dumps(fixture()))
            env = dict(os.environ, HOME=directory, CC_ROUTER_CONFIG=str(path), CC_ROUTER_OPERATOR='codex')
            def run(script, *args):
                result = subprocess.run([sys.executable, str(ROOT / 'scripts' / script), *args], env=env, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout
            first = json.loads(run('route.py', json.dumps(dict(STATE, description='secret-marker-not-for-history'))))
            run('justify.py', first['id'], 'auto', 'private-justification')
            run('record.py', first['id'], 'failure', '30', '--failure-kind', 'syntax_or_local_fix')
            second = json.loads(run('route.py', json.dumps(dict(STATE, task_id=first['task_id'], idempotent=True, diff_verified=True))))
            self.assertEqual(second['task_id'], first['task_id'])
            self.assertEqual(second['attempt_count'], 2)
            self.assertNotEqual(first['attempt_id'], second['attempt_id'])
            run('justify.py', second['id'], 'auto', 'retry')
            run('record.py', second['id'], 'success', '--input-tokens', '10', '--output-tokens', '20',
                '--reasoning-tokens', '5', '--host-confirmed', '--effective-candidate', 'basic', '--resolved-model', 'version-1')
            history = Path(directory) / '.codex/cc-router/history.jsonl'
            self.assertNotIn('secret-marker-not-for-history', history.read_text())
            self.assertNotIn('private-justification', history.read_text())
            events = read_history(history)
            results = [e for e in events if e['event'] == 'result']
            self.assertIsNone(results[0]['resolved_model'])
            self.assertEqual(results[1]['tokens'], 30)
            self.assertEqual(summarize(events)['completion_details'][0]['tokens'], 60)

class AdditionalContractsTest(unittest.TestCase):
    def test_installer_preserves_unowned_agents_and_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = fixture('claude')
            path = root / 'config.json'
            path.write_text(json.dumps(raw))
            agents = root / '.claude/agents'
            agents.mkdir(parents=True)
            unrelated = agents / 'exec-other-skill.md'
            unrelated.write_text('owned by another skill')
            settings = root / '.claude/settings.json'
            settings.write_text(json.dumps({'unrelated': {'a': 1}, 'permissions': {'ask': ['Agent(exec-other-skill)', 'Bash(rm *)']}}))
            env = dict(os.environ, HOME=directory, CC_ROUTER_CONFIG=str(path), CC_ROUTER_OPERATOR='claude')
            # Exercise credential guard without inheriting process credentials.
            from common import non_subscription_vars
            for name in non_subscription_vars:
                env.pop(name, None)
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/install.py')], env=env, text=True, capture_output=True, stdin=subprocess.DEVNULL)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(unrelated.read_text(), 'owned by another skill')
            current = json.loads(settings.read_text())
            self.assertEqual(current['unrelated'], {'a': 1})
            self.assertIn('Agent(exec-other-skill)', current['permissions']['ask'])
            self.assertIn('Agent(deep)', current['permissions']['ask'])
            self.assertNotIn('effort:', (agents / 'basic.md').read_text())
            self.assertIn('effort: custom', (agents / 'deep.md').read_text())

    def test_append_after_interrupted_line_preserves_next_event(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.jsonl'
            path.write_text('{"partial":')
            with patch('common.history_path', return_value=path):
                log_event({'event': 'probe', 'id': 'next', 'operator': 'codex'})
            self.assertEqual([e['id'] for e in read_history(path)], ['next'])

    def test_record_rejects_unverified_metrics_and_blocked_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            history = home / '.codex/cc-router/history.jsonl'
            history.parent.mkdir(parents=True)
            history.write_text('\n'.join(json.dumps(e) for e in [
                {'event': 'decision', 'id': 'x', 'agent': 'basic', 'needs_approval': False},
                {'event': 'justification', 'id': 'x', 'answer': 'auto'}]) + '\n')
            env = dict(os.environ, HOME=directory, CC_ROUTER_OPERATOR='codex')
            for args in [('--resolved-model', 'unknown'), ('0', 'nan'),
                         ('--output-tokens', '10', '--reasoning-tokens', '20'),
                         ('--verification', 'unknown')]:
                result = subprocess.run([sys.executable, str(ROOT / 'scripts/record.py'), 'x', 'success', *args],
                                        env=env, text=True, capture_output=True)
                self.assertNotEqual(result.returncode, 0, args)
            self.assertEqual(len(read_history(history)), 2)

    def test_explicit_migration_backups_and_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'router.json'
            path.write_text(json.dumps(fixture()))
            original = path.read_bytes()
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/migrate.py'), str(path), '--write', str(path)], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(next(Path(directory).glob('*.bak')).read_bytes(), original)
            self.assertEqual(json.loads(path.read_text())['schema_version'], 2)

    def test_benchmark_is_offline_and_exercises_both_hosts(self):
        from benchmark import run
        report = run()
        self.assertEqual(report['api_calls'], 0)
        self.assertEqual(len(report['rows']), 48)
        self.assertEqual({row['host'] for row in report['rows']}, {'claude', 'codex'})

class RegressionMatrixTest(unittest.TestCase):
    def test_cold_start_matches_legacy_heuristic_roles(self):
        from route import choose_level
        raw = json.loads((ROOT / 'config/ladder.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            agents = Path(directory)
            for host in ('claude', 'codex'):
                config = for_host(raw, host)
                config['backend'] = 'heuristic'
                for candidate in config['ladder']:
                    (agents / (candidate['agent'] + '.md')).write_text('fixture')
                names = [c['agent'] for c in config['ladder']]
                last_active = max(i for i, c in enumerate(config['ladder']) if c['active'])
                for operation in config['base_level_by_operation']:
                    for mask in range(8):
                        state = dict(STATE, operation=operation, files=5 if mask & 1 else 2,
                                     ambiguous=bool(mask & 2), critical=bool(mask & 4))
                        ceiling = min(last_active, config['ceiling_by_operation'].get(operation, last_active))
                        level, _, _, _ = choose_level(state, config, names, 0, ceiling)
                        with patch('route.agents_dir', agents):
                            actual = route_one(state, config, [])
                        self.assertEqual(actual['agent'], names[level], (host, operation, mask))

    def test_context_recovery_requires_confirmation_and_diff(self):
        config = for_host(fixture(), 'codex')
        state = dict(STATE, failed_with='basic', failure_kind='missing_context', idempotent=True, diff_verified=True)
        self.assertFalse(diagnose(state, config)['retry_allowed'])
        resumed = dict(state, recovery_confirmed=True)
        self.assertEqual(route_one(resumed, config, [])['selected'], 'basic')
        self.assertFalse(diagnose(dict(resumed, diff_verified=False), config)['retry_allowed'])

    def test_unconfirmed_metrics_never_influence_selection(self):
        config = for_host(fixture(), 'codex')
        events = observations(config['ladder'][0], 30, 100)
        for event in events:
            event.pop('host_confirmed', None)
        self.assertEqual(estimates(events, STATE, config['ladder'], config)['basic']['samples'], 0)
