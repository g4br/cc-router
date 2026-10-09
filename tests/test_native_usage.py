"""Native host fixtures contain no real conversations, IDs or credentials."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from candidates import for_host
from native_usage import collect, locate
from telemetry import estimates, segmented_report


def config(host='codex'):
    model = 'native-model-v1'
    return for_host({'schema_version': 2, 'hosts': {host: {'candidates': [
        {'id': 'exec-basic', 'model': model, 'resolved_model': model, 'effort': 'medium',
         'active': True, 'approval': False, 'billing_mode': 'subscription',
         'capabilities': ['implementation']}]}}}, host)


def codex_usage(inp=100, out=20):
    return {'input_tokens': inp, 'output_tokens': out, 'cached_input_tokens': 40,
            'cache_write_input_tokens': 0, 'reasoning_output_tokens': 5, 'total_tokens': inp + out}


def codex_rows(decision='decision-1', turn='turn-1', inp=100):
    def event(kind, **kw):
        return {'type': 'event_msg', 'timestamp': '2026-10-09T12:00:00Z', 'payload': {'type': kind, **kw}}
    return [
        {'type': 'session_meta', 'payload': {'id': 'agent-1', 'source': {'subagent': {'spawn': {}}}}},
        event('task_started', turn_id=turn),
        event('user_message', message=f'CC_ROUTER_DECISION: {decision}\nImplement a fixture'),
        {'type': 'turn_context', 'payload': {'turn_id': turn, 'model': 'native-model-v1', 'effort': 'medium'}},
        {'type': 'response_item', 'payload': {'role': 'assistant', 'content': []}},
        {'type': 'token_usage_record', 'payload': {'thread_id': 'agent-1', 'turn_id': turn,
            'response_id': 'response-' + turn, 'usage': codex_usage(inp), 'turn_token_usage': codex_usage(inp)}},
        # This second representation of the same usage must NOT be added again.
        event('token_count', info={'total_token_usage': codex_usage(inp), 'last_token_usage': codex_usage(inp)}),
        dict(event('task_complete', turn_id=turn), timestamp='2026-10-09T12:00:03Z')]


def claude_rows(decision='decision-1'):
    base = {'agentId': 'agent-1', 'isSidechain': True, 'timestamp': '2026-10-09T12:00:00Z'}
    response = dict(base, type='assistant', effort='high', perTurnEffort='medium',
                    message={'id': 'message-1', 'model': 'native-model-v1', 'content': [],
                             'usage': {'input_tokens': 10, 'output_tokens': 20,
                                       'cache_creation_input_tokens': 30, 'cache_read_input_tokens': 60}})
    return [dict(base, type='user', message={'content': f'CC_ROUTER_DECISION: {decision}'}),
            response, copy.deepcopy(response)]


class NativeUsageTest(unittest.TestCase):
    def read(self, rows, host='codex', **kw):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'transcript.jsonl'
            path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
            return collect(host, path, 'agent-1', 'decision-1', config(host), **kw)

    def test_codex_deduplicates_responses_and_ignores_other_turns(self):
        rows = codex_rows()
        rows.insert(6, copy.deepcopy(rows[5]))
        rows += codex_rows('different-decision', 'turn-2', 900)[1:]
        got = self.read(rows)
        self.assertEqual((got['metrics']['total_tokens'], got['metrics']['reasoning_tokens']), (120, 5))
        self.assertEqual((got['effective_candidate'], got['effective_effort'], got['resolved_model']),
                         ('exec-basic', 'medium', 'native-model-v1'))
        self.assertEqual(got['duration_s'], 3)
        self.assertNotIn('transcript_path', got['host_usage'])

    def test_codex_legacy_counters_not_summed(self):
        rows = [r for r in codex_rows() if r['type'] != 'token_usage_record']
        rows.insert(-1, copy.deepcopy(rows[-2]))
        got = self.read(rows)
        self.assertEqual(got['metrics']['total_tokens'], 120)
        # A fork inherits 900 input tokens; only this response's usage counts.
        for r in rows:
            if r.get('payload', {}).get('type') == 'token_count':
                r['payload']['info']['total_token_usage'] = codex_usage(1000)
        self.assertEqual(self.read(rows)['metrics']['total_tokens'], 120)

    def test_codex_requires_exact_identity_scope_and_completion(self):
        mutations = []
        rows = codex_rows(); rows[0]['payload']['id'] = 'parent'; mutations.append(rows)
        rows = codex_rows(); rows[0]['payload']['source'] = 'cli'; mutations.append(rows)
        rows = codex_rows('wrong-decision'); mutations.append(rows)
        rows = codex_rows()[:-1]; mutations.append(rows)
        rows = codex_rows(); rows[5]['payload']['thread_id'] = 'other-agent'; mutations.append(rows)
        rows = codex_rows(); rows[5]['payload']['turn_token_usage'] = codex_usage(200); mutations.append(rows)
        for rows in mutations:
            with self.subTest(rows=rows[0]), self.assertRaises(ValueError):
                self.read(rows)
        rows = codex_rows() + codex_rows(turn='turn-2')[1:]
        with self.assertRaisesRegex(ValueError, 'turn_id'):
            self.read(rows)
        self.assertEqual(self.read(rows, turn_id='turn-2')['metrics']['total_tokens'], 120)

    def test_unknown_effort_is_not_copied_from_candidate(self):
        rows = codex_rows()
        del rows[3]['payload']['effort']
        got = self.read(rows)
        self.assertIsNone(got['effective_effort'])
        self.assertIsNone(got['effective_candidate'])
        self.assertEqual(got['metrics']['total_tokens'], 120)

    def test_claude_cache_normalization_and_stream_deduplication(self):
        rows = claude_rows()
        rows[-1]['message']['usage']['output_tokens'] = 25
        got = self.read(rows, 'claude')
        self.assertEqual(got['metrics']['input_tokens'], 100)
        self.assertEqual(got['metrics']['total_tokens'], 125)
        self.assertEqual((got['metrics']['cache_tokens'], got['metrics']['cache_write_tokens']), (60, 30))
        self.assertEqual(got['effective_effort'], 'medium')
        self.assertIsNone(got['metrics']['reasoning_tokens'])

    def test_claude_mixed_models_preserve_segments_without_false_candidate(self):
        rows = claude_rows()
        extra = copy.deepcopy(rows[-1])
        extra['message'].update(id='message-2', model='substituted-model')
        rows.append(extra)
        got = self.read(rows, 'claude')
        self.assertEqual(got['metrics']['total_tokens'], 240)
        self.assertEqual(len(got['execution_segments']), 2)
        self.assertIsNone(got['resolved_model'])
        self.assertIsNone(got['effective_candidate'])

    def test_claude_missing_metrics_stay_unknown_and_invalid_are_rejected(self):
        rows = claude_rows()
        for row in rows[1:]:
            del row['message']['usage']['cache_creation_input_tokens']
        got = self.read(rows, 'claude')
        self.assertIsNone(got['metrics']['input_tokens'])
        self.assertIsNone(got['metrics']['total_tokens'])
        rows = claude_rows(); rows[1]['message']['usage']['input_tokens'] = True
        with self.assertRaises(ValueError): self.read(rows, 'claude')
        rows = claude_rows(); rows[-1]['message']['usage']['input_tokens'] = 900
        with self.assertRaisesRegex(ValueError, 'conflicting'): self.read(rows, 'claude')

    def test_claude_parent_or_multiple_decisions_rejected(self):
        rows = claude_rows(); rows[0]['isSidechain'] = False
        with self.assertRaisesRegex(ValueError, 'subagent'): self.read(rows, 'claude')
        rows = claude_rows(); rows.append(dict(rows[0], message={'content': 'DECISION: another'}))
        with self.assertRaisesRegex(ValueError, 'decision'): self.read(rows, 'claude')

    def test_claude_host_agent_type_maps_alias_without_guessing_model_names(self):
        rows = claude_rows()
        for row in rows[1:]: row['message']['model'] = 'provider-resolved-version'
        got = self.read(rows, 'claude', agent_type='exec-basic')
        self.assertEqual(got['effective_candidate'], 'exec-basic')
        self.assertEqual(got['resolved_model'], 'provider-resolved-version')
        self.assertIsNone(self.read(rows, 'claude')['effective_candidate'])

    def test_discovery_uses_explicit_agent_id_and_rejects_ambiguity(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, CODEX_HOME=directory):
            root = Path(directory) / 'sessions'; root.mkdir()
            a = root / 'rollout-agent-1.jsonl'; a.write_text('')
            self.assertEqual(locate('codex', 'agent-1'), a)
            (root / 'duplicate-agent-1.jsonl').write_text('')
            with self.assertRaises(ValueError): locate('codex', 'agent-1')
            with self.assertRaises(ValueError): locate('codex', '../escape')


class NativeUsageCLITest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.host = 'codex'
        self.config = self.root / 'config.json'
        self.configure('codex')

    def configure(self, host):
        self.host = host
        # for_host's host-normalized tables are not a serialized config; use the
        # schema-level fields only.
        c = config(host)
        self.config.write_text(json.dumps({'schema_version': 2, 'hosts': c['hosts']}))
        self.env = dict(os.environ, HOME=str(self.root), CC_ROUTER_OPERATOR=host,
                        CC_ROUTER_CONFIG=str(self.config), CODEX_HOME=str(self.root / '.codex'))
        if host == 'claude':
            agents = self.root / '.claude/agents'; agents.mkdir(parents=True, exist_ok=True)
            (agents / 'exec-basic.md').write_text('fixture')

    def call(self, script, *args, stdin=None, ok=True):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts' / script), *map(str, args)],
                                env=self.env, input=stdin, text=True, capture_output=True)
        self.assertEqual(result.returncode == 0, ok, result.stderr)
        return result

    def route(self):
        state = {'description': 'Implement fixture', 'operation': 'implementation', 'files': 1,
                 'ambiguous': False, 'critical': False}
        d = json.loads(self.call('route.py', json.dumps(state)).stdout)
        self.call('justify.py', d['id'], 'auto')
        return d

    def transcript(self, decision):
        path = self.root / 'native.jsonl'
        rows = codex_rows(decision['id']) if self.host == 'codex' else claude_rows(decision['id'])
        path.write_text(''.join(json.dumps(r) + '\n' for r in rows))
        return path

    def events(self):
        return [json.loads(s) for s in (self.root / f'.{self.host}/cc-router/history.jsonl').read_text().splitlines()]

    def test_collect_then_record_automatically_consumes_observation(self):
        d = self.route(); path = self.transcript(d)
        for _ in range(2): self.call('usage.py', d['id'], '--agent-id', 'agent-1', '--transcript', path)
        self.assertEqual(sum(e['event'] == 'host_usage' for e in self.events()), 1)
        self.assertFalse(any(e['event'] == 'result' for e in self.events()))
        self.call('record.py', d['id'], 'success', '999', ok=False)
        self.call('record.py', d['id'], 'success', '--no-rework', 'true')
        result = self.events()[-1]
        self.assertEqual((result['tokens'], result['resolved_model'], result['effective_effort']), (120, 'native-model-v1', 'medium'))
        self.assertTrue(result['host_confirmed'])
        self.assertNotIn('Implement fixture', json.dumps(result))
        # Observations can now feed telemetry when the host version is configured.
        evidence = estimates(self.events(), {'operation': 'implementation', 'files': 1, 'ambiguous': False, 'critical': False},
                             config()['ladder'], config())
        self.assertEqual(evidence['exec-basic']['samples'], 1)

    def test_direct_record_collects_and_preserves_verification_gate(self):
        d = self.route(); path = self.transcript(d)
        args = (d['id'], 'success', '--agent-id', 'agent-1', '--transcript', path)
        self.call('record.py', *args, '--verification', 'failed', ok=False)
        self.call('record.py', *args)
        self.assertEqual(self.events()[-1]['metrics']['total_tokens'], 120)
        self.call('record.py', *args, ok=False)

    def test_hook_collects_only_usage_and_leaves_success_to_orchestrator(self):
        self.configure('claude')
        d = self.route(); path = self.transcript(d)
        payload = json.dumps({'hook_event_name': 'SubagentStop', 'agent_id': 'agent-1',
                              'agent_type': 'exec-basic', 'agent_transcript_path': str(path),
                              'last_assistant_message': 'TOKENS: 999999'})
        self.call('usage.py', '--claude-hook', stdin=payload)
        self.call('usage.py', '--claude-hook', stdin=payload)
        self.assertEqual(sum(e['event'] == 'host_usage' for e in self.events()), 1)
        self.assertFalse(any(e['event'] == 'result' for e in self.events()))
        self.call('record.py', d['id'], 'success')
        self.assertEqual(self.events()[-1]['metrics']['total_tokens'], 120)
        self.assertEqual(self.events()[-1]['effective_candidate'], 'exec-basic')
        report = segmented_report(self.events())
        self.assertEqual(report['native_executions'][0]['segments'][0]['metrics']['total_tokens'], 120)

    def test_installer_preserves_other_hooks_and_is_idempotent(self):
        self.configure('claude')
        (self.root / '.claude/agents/exec-basic.md').unlink()  # test-only placeholder, not an owned installed agent
        settings = self.root / '.claude/settings.json'
        other = {'matcher': 'Explore', 'hooks': [{'type': 'command', 'command': 'echo existing'}]}
        settings.write_text(json.dumps({'hooks': {'SubagentStop': [other]}, 'permissions': {'ask': ['Bash(rm *)']}}))
        self.call('install.py')
        self.call('install.py')
        saved = json.loads(settings.read_text())
        self.assertEqual(saved['hooks']['SubagentStop'][0], other)
        self.assertEqual(len(saved['hooks']['SubagentStop']), 2)
        self.assertIn('--claude-hook', saved['hooks']['SubagentStop'][1]['hooks'][0]['command'])
        self.assertIn('Bash(rm *)', saved['permissions']['ask'])

    def test_usage_only_install_preserves_settings_and_keeps_backup(self):
        settings = self.root / '.claude/settings.json'
        settings.parent.mkdir(parents=True)
        original = {'permissions': {'ask': ['Bash(rm *)']}, 'hooks': {'PreToolUse': []}, 'unrelated': 17}
        settings.write_text(json.dumps(original))
        self.call('usage.py', '--install-claude-hook')
        self.call('usage.py', '--install-claude-hook')
        backups = list(settings.parent.glob('settings.json.*.bak'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text()), original)
        saved = json.loads(settings.read_text())
        self.assertEqual(saved['permissions'], original['permissions'])
        self.assertEqual(saved['unrelated'], 17)
        self.assertEqual(len(saved['hooks']['SubagentStop']), 1)
        self.assertFalse((settings.parent / 'agents').exists())

    def test_failed_import_never_records_a_result(self):
        d = self.route(); path = self.transcript(d)
        path.write_text(path.read_text() + '{"partial":')
        self.call('record.py', d['id'], 'failure', '--agent-id', 'agent-1', '--transcript', path, ok=False)
        self.assertFalse(any(e['event'] == 'result' for e in self.events()))

    def test_concurrent_record_does_not_double_count(self):
        d = self.route(); path = self.transcript(d)
        command = [sys.executable, str(ROOT / 'scripts/record.py'), d['id'], 'success', '--agent-id', 'agent-1', '--transcript', str(path)]
        procs = [subprocess.Popen(command, env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        for p in procs: p.communicate(timeout=10)
        self.assertEqual(sorted(p.returncode for p in procs), [0, 1])
        self.assertEqual(sum(e['event'] == 'result' for e in self.events()), 1)


if __name__ == '__main__':
    unittest.main()
