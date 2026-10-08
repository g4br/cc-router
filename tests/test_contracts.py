"""Public v1 contracts, retained during migration to v2."""
import json
import tempfile
import unittest
from pathlib import Path
import test_routing as legacy
STATE = legacy.STATE


class ContractTest(unittest.TestCase):
    run_script = legacy.RoutingTest.run_script
    def test_batch_contract_and_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            state = dict(json.loads(STATE), targets=[])
            result = self.run_script(home, 'route.py', json.dumps([state, state]), operator='codex')
            self.assertEqual(result.returncode, 0, result.stderr)
            decisions = json.loads(result.stdout)
            required = {'operator', 'agent', 'model', 'effort', 'needs_approval', 'alternative', 'backend', 'id', 'reason'}
            self.assertTrue(all(required <= d.keys() for d in decisions))
            self.assertEqual(decisions[0]['batch'], decisions[1]['batch'])
            self.assertNotEqual(decisions[0]['id'], decisions[1]['id'])
            high = dict(state, operation='research', critical=True)
            routed = self.run_script(home, 'route.py', json.dumps(high), operator='codex')
            decision = json.loads(routed.stdout)
            self.assertTrue(decision['needs_approval'])
            denied = self.run_script(home, 'justify.py', decision['id'], 'auto', 'reason', operator='codex')
            self.assertNotEqual(denied.returncode, 0)
            self.assertEqual(self.run_script(home, 'justify.py', decision['id'], 'declined', 'reason', operator='codex').returncode, 0)
            self.assertNotEqual(self.run_script(home, 'record.py', decision['id'], 'success', operator='codex').returncode, 0)

    def test_invalid_batch_is_not_logged(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            state = dict(json.loads(STATE), targets=['scripts'])
            result = self.run_script(home, 'route.py', json.dumps([state, state]), operator='codex')
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((home / '.codex/cc-router/history.jsonl').exists())

    def test_subscription_guard_keeps_cloud_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            bad = self.run_script(home, 'route.py', STATE, operator='claude', markers={'ANTHROPIC_API_KEY': 'secret-do-not-print'})
            self.assertNotEqual(bad.returncode, 0)
            self.assertNotIn('secret-do-not-print', bad.stderr)
            cloud = self.run_script(home, 'route.py', STATE, operator='claude', markers={'CLAUDE_CODE_REMOTE': 'true', 'ANTHROPIC_BASE_URL': 'cloud'})
            self.assertIn('not installed', cloud.stderr)
