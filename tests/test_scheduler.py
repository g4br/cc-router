"""Behavioral scheduler contracts: lazy routing, events, retries and complete costs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_v2 import ROOT, STATE, fixture
from candidates import for_host
from scheduler import initialize, reserve, finish, revise, usage, status
from telemetry import workflow_efficiency, segmented_report
from state import check_state


def task(ident, deps=(), **overrides):
    return dict(STATE, step_id=ident, depends_on=list(deps), write_targets=[ident],
                acceptance='Roundtrip test passes and actual diff is reviewed', **overrides)


class SchedulerTest(unittest.TestCase):
    def setUp(self):
        self.config = for_host(fixture(), 'codex')
        self.events = []
        self.run = initialize([task('a'), task('b', ['a']), task('c', ['a']), task('d', ['b', 'c'])], self.config)

    def drain(self):
        self.events.extend(self.run['outbox'])
        self.run['outbox'] = []

    def next(self, capacity=4):
        result = reserve(self.run, self.config, self.events, capacity)
        self.drain()
        return result

    def complete(self, ident, success=True, tokens=100, report=None):
        decision = self.run['tasks'][ident]['decision']
        self.events.append({'event': 'result', 'id': decision['id'], 'result': 'success' if success else 'failure',
                            'verification': 'passed' if success else 'failed', 'task_complete': success,
                            'failure_kind': None if success else 'syntax_or_local_fix',
                            'metrics': {'total_tokens': tokens, 'unit': 'tokens'}})
        report = report or {'decision_id': decision['id'], 'changed_paths': [ident],
                            'evidence': 'Test report artifact', 'output_ref': ident + '.txt'}
        finish(self.run, ident, report, self.events)
        self.drain()
        return report

    def test_classify_ready_only_and_release_without_wave_barrier(self):
        self.assertFalse(any(e['event'] == 'decision' for e in self.run['outbox']))
        with patch('scheduler.route_one', wraps=__import__('route').route_one) as route:
            self.assertEqual([d['step_id'] for d in self.next()], ['a'])
            self.assertEqual(route.call_count, 1)
            self.assertEqual(self.next(), [])
            self.complete('a')
            self.assertEqual([d['step_id'] for d in self.next()], ['b', 'c'])
            self.assertIn('a.txt', route.call_args.args[0]['description'])
            self.complete('b')
            self.assertEqual(self.next(), [])
            self.complete('c')
            self.assertEqual([d['step_id'] for d in self.next()], ['d'])
            self.assertEqual(route.call_count, 4)

    def test_independent_branch_does_not_wait_for_slower_peer(self):
        self.run = initialize([task('a'), task('b'), task('c', ['a'])], self.config)
        self.assertEqual([d['step_id'] for d in self.next(2)], ['a', 'b'])
        self.complete('a')
        self.assertEqual([d['step_id'] for d in self.next(1)], ['c'])

    def test_capacity_zero_and_sequential_reservations(self):
        self.run = initialize([task('a', isolation='sequential'), task('b')], self.config)
        self.assertEqual(self.next(0), [])
        self.assertEqual([d['step_id'] for d in self.next()], ['a'])
        self.assertEqual(self.next(), [])
        self.complete('a')
        self.assertEqual([d['step_id'] for d in self.next()], ['b'])

    def test_requires_recorded_verified_complete_owned_changes(self):
        self.next()
        decision = self.run['tasks']['a']['decision']
        report = {'decision_id': decision['id'], 'changed_paths': ['unexpected'],
                  'evidence': 'tests', 'output_ref': 'artifact'}
        with self.assertRaisesRegex(ValueError, 'record exactly one'):
            finish(self.run, 'a', report, self.events)
        self.events.append({'event': 'result', 'id': decision['id'], 'result': 'success',
                            'verification': 'passed', 'task_complete': False})
        with self.assertRaisesRegex(ValueError, 'criterion'):
            finish(self.run, 'a', report, self.events)
        self.events[-1]['task_complete'] = True
        with self.assertRaisesRegex(ValueError, 'ownership'):
            finish(self.run, 'a', report, self.events)
        self.assertEqual(self.next(), [])
        report['changed_paths'] = ['a']
        finish(self.run, 'a', report, self.events)
        count = len(self.run['outbox'])
        finish(self.run, 'a', report, self.events)
        self.assertEqual(len(self.run['outbox']), count)
        with self.assertRaisesRegex(ValueError, 'stale'):
            finish(self.run, 'a', dict(report, decision_id='old'), self.events)

    def test_retry_preserves_identity_and_counts_and_expires_attestations(self):
        self.next()
        identity = self.run['tasks']['a']['state']['task_id']
        self.complete('a', success=False)
        self.assertEqual(self.next(), [])
        revise(self.run, 'a', {'idempotent': True, 'diff_verified': True}, self.config, self.events, retry=True)
        second = self.next()[0]['decision']
        self.assertEqual(second['task_id'], identity)
        self.assertEqual(self.run['tasks']['a']['decision']['attempt_count'], 2)
        self.complete('a', success=False)
        revise(self.run, 'a', {}, self.config, self.events, retry=True)
        self.assertEqual(self.next(), [])
        blocked = self.run['tasks']['a']['decision']
        self.assertEqual(blocked['failure']['action'], 'inspect_worktree_diff')

    def test_refine_unclassified_task_and_boolean_recovery(self):
        revise(self.run, 'b', {'files': 8, 'critical': True}, self.config, self.events)
        self.next()
        with self.assertRaisesRegex(ValueError, 'classified'):
            revise(self.run, 'a', {'files': 8}, self.config, self.events)
        check_state(dict(STATE, failed_with='basic', failure_kind='missing_context', recovery_confirmed=True), self.config)

    def test_all_workflow_costs_include_failed_attempts_and_unknowns(self):
        self.next()
        self.complete('a', success=False, tokens=30)
        revise(self.run, 'a', {'idempotent': True, 'diff_verified': True}, self.config, self.events, retry=True)
        self.next()
        self.complete('a', tokens=70)
        partial = status(self.run, self.events)['efficiency']
        self.assertIsNone(partial['total_tokens'])
        self.assertEqual(partial['known_tokens'], 100)
        usage(self.run, {'planning': 10, 'classification': 0, 'delegation': 20, 'validation': 30})
        self.drain()
        report = status(self.run, self.events)['efficiency']
        self.assertEqual(report['total_tokens'], 160)
        self.assertEqual(report['tasks_per_token'], 1 / 160)
        self.assertEqual(report['phase_tokens']['execution'], 30)
        self.assertEqual(report['phase_tokens']['rework'], 70)
        self.assertEqual(segmented_report(self.events)['workflows'][0]['total_tokens'], 160)
        with self.assertRaisesRegex(ValueError, 'cannot decrease'):
            usage(self.run, {'planning': 0})
        self.next()
        self.assertIsNone(status(self.run, self.events)['efficiency']['total_tokens'])

    def test_unknown_metrics_are_not_zero_and_reasoning_is_not_added(self):
        overhead = {k: 0 for k in ('planning', 'classification', 'delegation', 'validation')}
        events = [{'event': 'decision', 'id': 'd', 'task_id': 't', 'selected': 'basic'},
                  {'event': 'result', 'id': 'd', 'metrics': {'total_tokens': 100, 'reasoning_tokens': 30, 'unit': 'tokens'}}]
        self.assertEqual(workflow_efficiency(events, ['t'], 1, overhead)['total_tokens'], 100)
        events[1]['metrics']['total_tokens'] = None
        self.assertIsNone(workflow_efficiency(events, ['t'], 1, overhead)['tasks_per_token'])


class SchedulerCLITest(unittest.TestCase):
    def test_lifecycle_concurrent_reservations_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'config.json'
            config.write_text(json.dumps(fixture()))
            env = dict(os.environ, HOME=directory, CC_ROUTER_OPERATOR='codex', CC_ROUTER_CONFIG=str(config))
            plan = root / 'plan.json'
            plan.write_text(json.dumps([task('a'), task('b', ['a'])]))
            runfile = root / 'run.json'
            def call(script, *args):
                result = subprocess.run([sys.executable, str(ROOT / 'scripts' / script), *map(str, args)],
                                        env=env, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout
            call('scheduler.py', 'init', runfile, plan)
            command = [sys.executable, str(ROOT / 'scripts/scheduler.py'), 'next', str(runfile), '--capacity', '2']
            processes = [subprocess.Popen(command, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
            dispatch = []
            for process in processes:
                out, err = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, err)
                dispatch.extend(json.loads(out)['dispatch'])
            self.assertEqual(len(dispatch), 1)
            decision = dispatch[0]['decision']
            call('justify.py', decision['id'], 'auto')
            call('record.py', decision['id'], 'success', '100')
            report = {'decision_id': decision['id'], 'changed_paths': ['a'], 'evidence': 'test log', 'output_ref': 'a.txt'}
            call('scheduler.py', 'finish', runfile, 'a', json.dumps(report))
            completed = json.loads(call('scheduler.py', 'status', runfile))
            self.assertEqual(completed['tasks']['a'], 'DONE')
            next_task = json.loads(call('scheduler.py', 'next', runfile, '--capacity', '1'))['dispatch']
            self.assertEqual([d['step_id'] for d in next_task], ['b'])
            self.assertEqual(next_task[0]['dependencies'], {'a': 'a.txt'})
            self.assertEqual(runfile.stat().st_mode & 0o777, 0o600)
            from common import read_history
            history = read_history(root / '.codex/cc-router/history.jsonl')
            self.assertEqual(len([e for e in history if e['event'] == 'decision']), 2)
            self.assertEqual(len([e for e in history if e['event'] == 'task_completed']), 1)
            self.assertNotIn(STATE['description'], (root / '.codex/cc-router/history.jsonl').read_text())
