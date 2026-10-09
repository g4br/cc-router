"""Phase 4: brief template, collision/ownership handling, one-level escalation and per-phase tokens."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timedelta
from unittest.mock import patch

from test_v2 import ROOT, STATE, fixture
from test_scheduler import task
import brief
import report_tokens
from candidates import for_host, validate_config
from common import read_history
from failures import diagnose
from planning import verify_changes
from route import link_task, route_one
from scheduler import initialize, reserve, finish, status

LADDER = json.loads((ROOT / 'config/ladder.json').read_text())
BRIEF = {'goal': 'Add a timeout to the HTTP client.', 'write_targets': ['client.py', 'tests/test_client.py'],
         'acceptance': 'Timeout tests pass.', 'verify': 'python -m unittest tests.test_client',
         'user_language': 'pt-BR', 'decision_id': 'abc123', 'step_id': 'client'}


class BriefTest(unittest.TestCase):
    def setUp(self):
        self.config = for_host(LADDER, 'codex')

    def test_config_bounds(self):
        self.assertEqual((self.config['brief_max_words'], self.config['report_max_lines'], self.config['max_same_level_retries']),
                         (250, 15, 2))
        for key in ('brief_max_words', 'report_max_lines', 'max_same_level_retries'):
            for bad in (0, -1, 1.5, True, '5'):
                with self.subTest(key=key, bad=bad), self.assertRaisesRegex(ValueError, key):
                    validate_config(dict(LADDER, **{key: bad}))

    def test_fixed_brief_contents(self):
        text = brief.build(BRIEF, self.config)
        for part in ('Goal: Add a timeout', 'client.py, tests/test_client.py', 'Acceptance: Timeout tests pass.',
                     'Verify with: python -m unittest', 'Report language: pt-BR', 'STEP: client and DECISION: abc123',
                     'at most 15 lines', 'RESULT: done|failed|blocked', 'FILES: <changed paths>',
                     'CHECK: <command> -> <result>', 'PENDING: <items or none>', 'TOKENS: <host-reported or unknown>'):
            self.assertIn(part, text)
        self.assertIn('none (read-only)', brief.build(dict(BRIEF, write_targets=[], step_id=None), self.config))
        self.assertIn('STEP: none', brief.build({k: v for k, v in BRIEF.items() if k != 'step_id'}, self.config))

    def test_strict_validation(self):
        for bad in (dict(BRIEF, extra=1), dict(BRIEF, goal='one\ntwo'), dict(BRIEF, goal=''),
                    {k: v for k, v in BRIEF.items() if k != 'verify'}, dict(BRIEF, write_targets='x')):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                brief.build(bad, self.config)

    def test_overflow_warns_logs_and_still_prints(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.json'
            config.write_text(json.dumps(dict(LADDER, brief_max_words=20)))
            env = dict(os.environ, HOME=directory, CC_ROUTER_OPERATOR='codex', CC_ROUTER_CONFIG=str(config))
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/brief.py'), json.dumps(BRIEF)],
                                    env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('over brief_max_words=20', result.stderr)
            self.assertIn('Goal: Add a timeout', result.stdout)
            events = read_history(Path(directory) / '.codex/cc-router/history.jsonl')
            self.assertEqual([(e['event'], e['id']) for e in events], [('brief_overflow', 'abc123')])
            self.assertEqual(events[0]['max_words'], 20)
            # within the limit: no warning, no event
            config.write_text(json.dumps(LADDER))
            quiet = subprocess.run([sys.executable, str(ROOT / 'scripts/brief.py'), json.dumps(BRIEF)],
                                   env=env, text=True, capture_output=True)
            self.assertEqual(quiet.stderr, '')
            self.assertEqual(len(read_history(Path(directory) / '.codex/cc-router/history.jsonl')), 1)


def collision_tasks(**second):
    shared = dict(STATE, acceptance='Tests pass and the diff is reviewed', write_targets=['shared.py'])
    return [dict(shared, step_id='a'), dict(shared, step_id='b', **second)]


class OwnershipTest(unittest.TestCase):
    def setUp(self):
        self.config = for_host(fixture(), 'codex')
        self.events = []

    def drain(self, run):
        self.events.extend(run['outbox'])
        run['outbox'] = []

    def complete(self, run, ident, paths, **extra):
        decision = run['tasks'][ident]['decision']
        if not any(e.get('id') == decision['id'] and e['event'] == 'result' for e in self.events):
            self.events.append({'event': 'result', 'id': decision['id'], 'result': 'success', 'verification': 'passed',
                                'task_complete': True, 'metrics': {'total_tokens': 10, 'unit': 'tokens'}})
        finish(run, ident, {'decision_id': decision['id'], 'changed_paths': paths, 'evidence': 'log',
                            'output_ref': ident + '.txt', **extra}, self.events)
        self.drain(run)

    def test_plan_rejects_unordered_overlap_before_any_reservation(self):
        with self.assertRaisesRegex(ValueError, 'conflict between independent steps'):
            initialize(collision_tasks(), self.config)
        with self.assertRaisesRegex(ValueError, 'conflict between independent steps'):
            initialize(collision_tasks(write_targets=['.']), self.config)

    def test_collision_serialises_instead_of_erroring(self):
        run = initialize([dict(t, write_targets=[t['step_id']]) for t in collision_tasks()], self.config)
        for t in run['tasks'].values():
            t['state']['write_targets'] = ['shared.py']  # a collision the plan check did not see
        with patch('scheduler.plan'):
            first = reserve(run, self.config, self.events, 2)
            self.drain(run)
            self.assertEqual([d['step_id'] for d in first], ['a'])
            self.assertEqual(reserve(run, self.config, self.events, 2), [])
            self.complete(run, 'a', ['shared.py'])
            self.assertEqual([d['step_id'] for d in reserve(run, self.config, self.events, 2)], ['b'])

    def test_verify_changes_names_paths_outside_ownership(self):
        state = task('a')
        report = verify_changes([state], {'a': ['a', 'other.py']})
        self.assertEqual((report['unexpected_steps'], report['outside_paths']), (['a'], {'a': ['other.py']}))
        self.assertEqual(verify_changes([state], {'a': ['a']})['outside_paths'], {})

    def test_change_outside_ownership_marks_serial_recheck_not_rework(self):
        run = initialize([task('a'), task('b'), task('c', ['a'])], self.config)
        reserve(run, self.config, self.events, 2)
        self.drain(run)
        self.complete(run, 'a', ['a', 'stray.py'])
        self.assertEqual(run['tasks']['a']['status'], 'RECHECK')
        shown = status(run, self.events)
        self.assertEqual((shown['tasks']['a'], shown['recheck']), ('RECHECK', {'a': ['stray.py']}))
        self.assertIn('task_recheck', [e['event'] for e in self.events])
        self.assertNotIn('task_completed', [e['event'] for e in self.events])
        # same report again is a no-op; the dependent stays blocked and nothing new starts
        self.complete(run, 'a', ['a', 'stray.py'])
        self.assertEqual(reserve(run, self.config, self.events, 4), [])
        self.assertEqual(run['tasks']['c']['status'], 'PENDING')
        # no attempt was added: the result stays the single outcome of the decision
        self.assertEqual(len([e for e in self.events if e['event'] == 'result']), 1)
        with self.assertRaisesRegex(ValueError, 're-check evidence'):
            self.complete(run, 'a', ['a'])
        self.complete(run, 'a', ['a', 'stray.py'], recheck='Reviewed stray.py diff serially; it is a needed fixture')
        self.assertEqual(run['tasks']['a']['status'], 'DONE')
        self.assertEqual([d['step_id'] for d in reserve(run, self.config, self.events, 4)], ['c'])
        with self.assertRaisesRegex(ValueError, 'no pending re-check'):
            self.complete(run, 'b', ['b'], recheck='x')

    def test_finish_phase_tokens_validated_and_emitted(self):
        run = initialize([task('a')], self.config)
        reserve(run, self.config, self.events, 1)
        self.drain(run)
        for bad in ({'sleeping': 1}, {'planning': -1}, {'planning': 1.5}, {}):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, 'phase_tokens'):
                self.complete(run, 'a', ['a'], phase_tokens=bad)
        self.complete(run, 'a', ['a'], phase_tokens={'validation': 7}, tokens_source='estimated')
        done = [e for e in self.events if e['event'] == 'task_completed'][0]
        self.assertEqual((done['phase_tokens'], done['tokens_source']), ({'validation': 7}, 'estimated'))


def ladder_config(host='codex'):
    return for_host(LADDER, host)


class EscalationTest(unittest.TestCase):
    def retry(self, config, failed, kind, **extra):
        state = dict(STATE, failed_with=failed, failure_kind=kind, idempotent=True, diff_verified=True,
                     attempt_count=1, **extra)
        return route_one(state, config, [])

    def test_verification_and_reasoning_failures_climb_exactly_one_level(self):
        config = ladder_config()
        for failed, kind, expected, levels in [
                ('exec-luna-low', 'verification_failed', 'exec-sol-low', ('trivial', 'mechanical')),
                ('exec-sol-medium', 'verification_failed', 'exec-astra-medium', ('routine', 'complex')),
                ('exec-sol-low', 'design_or_reasoning_failure', 'exec-sol-medium', ('mechanical', 'routine')),
                ('exec-astra-medium', 'design_or_reasoning_failure', 'exec-astra-high', ('complex', 'open'))]:
            with self.subTest(failed=failed):
                decision = self.retry(config, failed, kind, critical=True, ambiguous=True)  # heuristic would aim higher
                self.assertEqual(decision['selected'], expected)
                self.assertEqual(decision['escalation'], {'kind': kind, 'from_candidate': failed, 'to_candidate': expected,
                                                          'from_level': levels[0], 'to_level': levels[1]})

    def test_top_level_and_missing_level_map_climb_one_rung(self):
        config = ladder_config()
        top = self.retry(config, 'exec-astra-high', 'verification_failed')
        self.assertEqual((top['selected'], top['escalation']['from_level'], top['escalation']['to_level']),
                         ('exec-astra-xhigh', 'open', 'open'))
        plain = for_host(fixture(), 'codex')
        self.assertNotIn('codex', plain.get('level_to_candidate', {}))
        decision = self.retry(plain, 'basic', 'verification_failed')
        self.assertEqual(decision['escalation'], {'kind': 'verification_failed', 'from_candidate': 'basic',
                                                  'to_candidate': 'deep', 'from_level': None, 'to_level': None})

    def test_unreachable_next_level_is_an_error_not_a_jump(self):
        with self.assertRaisesRegex(ValueError, 'one level above'):
            self.retry(ladder_config(), 'exec-sol-medium', 'verification_failed', user_ceiling='exec-sol-high')

    def test_environment_failure_retries_same_rung_without_escalation(self):
        config = ladder_config()
        for kind in ('transient_host', 'syntax_or_local_fix'):
            decision = self.retry(config, 'exec-sol-medium', kind)
            self.assertEqual(decision['selected'], 'exec-sol-medium')
            self.assertNotIn('escalation', decision)

    def test_same_level_retry_limit(self):
        config = dict(ladder_config(), max_attempts=10)
        for streak, allowed in [(0, True), (1, True), (2, False)]:
            state = dict(STATE, failed_with='exec-sol-medium', failure_kind='transient_host', idempotent=True,
                         diff_verified=True, attempt_count=streak + 1, same_level_retries=streak)
            diagnosis = diagnose(state, config)
            self.assertEqual(diagnosis['retry_allowed'], allowed)
            if not allowed:
                self.assertEqual(diagnosis['action'], 'same_level_retry_limit')
                self.assertEqual(route_one(state, config, [])['execution']['status'], 'blocked')
        # a verification failure is not limited by the same-level counter
        state = dict(STATE, failed_with='exec-sol-medium', failure_kind='verification_failed', idempotent=True,
                     diff_verified=True, attempt_count=2, same_level_retries=5)
        self.assertTrue(diagnose(state, config)['retry_allowed'])
        config['max_same_level_retries'] = 4
        state.update(failure_kind='transient_host', same_level_retries=3)
        self.assertTrue(diagnose(state, config)['retry_allowed'])

    def test_link_task_counts_consecutive_attempts_on_one_candidate(self):
        config = ladder_config()
        events = []
        for i, (selected, kind) in enumerate([('exec-sol-low', 'verification_failed'), ('exec-sol-medium', 'transient_host'),
                                              ('exec-sol-medium', 'transient_host')]):
            events += [{'event': 'decision', 'id': f'd{i}', 'task_id': 't', 'selected': selected,
                        'task_profile': __import__('telemetry').profile(STATE, config['file_limit'])},
                       {'event': 'result', 'id': f'd{i}', 'result': 'failure', 'failure_kind': kind}]
        state = dict(STATE, task_id='t')
        link_task(state, events, config)
        self.assertEqual((state['failed_with'], state['attempt_count'], state['same_level_retries']),
                         ('exec-sol-medium', 3, 1))
        state = dict(STATE, task_id='t')
        link_task(state, events[:2], config)
        self.assertEqual(state['same_level_retries'], 0)


def result_events(task_id, date, tokens, phases=None, backend='heuristic', level=None, retries=(), no_rework=True):
    """A completed task: one first attempt, then retries; every attempt tokens known unless None."""
    events = []
    for i, attempt_tokens in enumerate([tokens, *retries]):
        ident = f'{task_id}-{i}'
        last = i == len(retries)
        events += [{'event': 'decision', 'id': ident, 'task_id': task_id, 'backend': backend,
                    **({'laya': {'final_level': level}} if level else {})},
                   {'event': 'result', 'id': ident, 'result': 'success' if last else 'failure', 'task_complete': last,
                    'verification': 'passed' if last else 'failed', 'date': date, 'tokens': attempt_tokens,
                    'no_rework': no_rework if i == 0 else None,
                    **({'phase_tokens': phases} if phases and i == 0 else {})}]
    return events


class ReportTokensTest(unittest.TestCase):
    def test_median_p90_and_unknowns_never_zero(self):
        events = []
        for i, tokens in enumerate([100, 200, 300, 400, 1000]):
            events += result_events(f't{i}', '2026-10-01T10:00:00+00:00', tokens, level='routine' if i < 3 else None)
        events += result_events('unknown-tokens', '2026-10-01T10:00:00+00:00', None, no_rework=None)
        # failed task is not counted
        events += [{'event': 'decision', 'id': 'bad', 'task_id': 'bad'},
                   {'event': 'result', 'id': 'bad', 'result': 'failure', 'verification': 'failed', 'tokens': 5}]
        result = report_tokens.report(events)['all']
        execution = result['overall']['phases']['execution']
        self.assertEqual((result['overall']['tasks'], execution['known'], execution['unknown']), (6, 5, 1))
        self.assertEqual((execution['median'], execution['p90']), (300, 1000))  # nearest rank: ceil(.9*5) = 5th value
        self.assertEqual(result['overall']['phases']['rework'], {'known': 5, 'unknown': 1, 'median': 0, 'p90': 0})
        for phase in ('planning', 'classification', 'delegation', 'validation', 'total'):
            self.assertEqual(result['overall']['phases'][phase],
                             {'known': 0, 'unknown': 6, 'median': None, 'p90': None})
        self.assertEqual(result['by_level']['routine']['tasks'], 3)
        self.assertEqual(result['by_level']['unknown']['tasks'], 3)
        self.assertEqual(sorted(result['by_backend']), ['heuristic'])
        self.assertEqual(report_tokens.p90(list(range(1, 11))), 9)

    def test_reported_phases_total_and_rework(self):
        phases = {'planning': 10, 'classification': 0, 'delegation': 20, 'validation': 30}
        events = result_events('a', '2026-10-01T10:00:00+00:00', 100, phases, backend='laya', level='complex', retries=(40,), no_rework=False)
        events += result_events('b', '2026-10-01T10:00:00+00:00', 300, phases, backend='laya', level='complex')
        events += result_events('c', '2026-10-01T10:00:00+00:00', 100, {'planning': 10}, backend='laya', level='complex')
        overall = report_tokens.report(events)['all']['overall']['phases']
        self.assertEqual(overall['classification'], {'known': 2, 'unknown': 1, 'median': 0, 'p90': 0})  # a reported zero stays zero
        self.assertEqual(overall['rework']['known'], 3)
        self.assertEqual((overall['total']['known'], overall['total']['unknown']), (2, 1))
        # a: 10+0+20+100+30+40 = 200, b: 10+0+20+300+30+0 = 360
        self.assertEqual((overall['total']['median'], overall['total']['p90']), (280, 360))

    def test_before_split_and_cli(self):
        events = (result_events('old', '2026-09-01T10:00:00+00:00', 100)
                  + result_events('new1', '2026-10-05T10:00:00+00:00', 50)
                  + result_events('new2', '2026-10-06T10:00:00+00:00', 70)
                  + result_events('nodate', None, 9))
        cut = report_tokens.cutoff('2026-10-01')
        result = report_tokens.report(events, cut)
        self.assertEqual({k: v['overall']['tasks'] for k, v in result.items()}, {'before': 1, 'after': 2, 'undated': 1})
        self.assertEqual(result['after']['overall']['phases']['execution']['median'], 60)
        with tempfile.TemporaryDirectory() as directory:
            history = Path(directory) / 'history.jsonl'
            history.write_text(''.join(json.dumps(e) + '\n' for e in events))
            env = dict(os.environ, HOME=directory, CC_ROUTER_OPERATOR='codex')
            run = subprocess.run([sys.executable, str(ROOT / 'scripts/report_tokens.py'), '--history', str(history),
                                  '--before', '2026-10-01'], env=env, text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('[after] overall: 2 completed tasks', run.stdout)
            self.assertIn('unknown', run.stdout)
            bad = subprocess.run([sys.executable, str(ROOT / 'scripts/report_tokens.py'), '--history', str(history),
                                  '--before', 'no-such-commit'], env=env, text=True, capture_output=True)
            self.assertEqual(bad.returncode, 1)
            self.assertIn('not an ISO date or a commit', bad.stderr)

    def test_before_accepts_a_commit(self):
        committed = subprocess.run(['git', '-C', str(ROOT), 'show', '-s', '--format=%cI', 'HEAD'], capture_output=True, text=True)
        if committed.returncode:
            self.skipTest('not a git checkout')
        self.assertEqual(report_tokens.cutoff('HEAD'), datetime.fromisoformat(committed.stdout.strip()))


class RecordPhaseTokensTest(unittest.TestCase):
    def test_record_stores_only_reported_phases(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'config.json'
            config.write_text(json.dumps(fixture()))
            env = dict(os.environ, HOME=directory, CC_ROUTER_OPERATOR='codex', CC_ROUTER_CONFIG=str(config))

            def call(script, *args, ok=True):
                result = subprocess.run([sys.executable, str(ROOT / 'scripts' / script), *map(str, args)],
                                        env=env, text=True, capture_output=True)
                self.assertEqual(result.returncode == 0, ok, result.stderr)
                return result
            routed = json.loads(call('route.py', json.dumps(STATE)).stdout)
            call('justify.py', routed['id'], 'auto')
            for bad in (['planning'], ['sleeping=1'], ['planning=-1'], ['planning=x'], ['planning=1', 'planning=2']):
                call('record.py', routed['id'], 'success', '100', '--phase-tokens', *bad, ok=False)
            call('record.py', routed['id'], 'success', '--tokens-source', 'host', ok=False)
            call('record.py', routed['id'], 'success', '100', '--phase-tokens', 'planning=12', 'classification=0',
                 '--tokens-source', 'estimated')
            result = [e for e in read_history(Path(directory) / '.codex/cc-router/history.jsonl') if e['event'] == 'result'][0]
            self.assertEqual((result['phase_tokens'], result['tokens_source'], result['tokens']),
                             ({'planning': 12, 'classification': 0}, 'estimated', 100))
            self.assertNotIn('delegation', result['phase_tokens'])


if __name__ == '__main__':
    unittest.main()
