import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
STATE = json.dumps({
    'description': 'implement a scoped function',
    'operation': 'implementation',
    'files': 1,
    'ambiguous': False,
    'critical': False,
})


class RoutingTest(unittest.TestCase):
    def run_script(self, home, script, *args, operator=None, markers=None):
        env = {'HOME': str(home), 'PATH': os.environ.get('PATH', '')}
        config = json.loads((ROOT / 'config/ladder.json').read_text(encoding='utf-8'))
        config['backend'] = 'heuristic'
        config_path = home / 'ladder.json'
        config_path.write_text(json.dumps(config), encoding='utf-8')
        env['CC_ROUTER_CONFIG'] = str(config_path)
        if operator:
            env['CC_ROUTER_OPERATOR'] = operator
        env.update(markers or {})
        return subprocess.run(
            [sys.executable, str(SCRIPTS / script), *args],
            cwd=ROOT, env=env, text=True, capture_output=True,
        )

    def test_codex_detection_routing_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            result = self.run_script(home, 'route.py', STATE, markers={'CODEX_THREAD_ID': 'test'})
            self.assertEqual(result.returncode, 0, result.stderr)
            decision = json.loads(result.stdout)
            self.assertEqual((decision['operator'], decision['agent'], decision['model'], decision['effort']),
                             ('codex', 'exec-sol-medium', 'gpt-6.1-sol', 'medium'))
            self.assertFalse((home / '.claude').exists())
            self.assertTrue((home / '.codex/cc-router/history.jsonl').exists())
            justify = self.run_script(home, 'justify.py', decision['id'], 'auto', 'Scoped work fits Sol medium', operator='codex')
            self.assertEqual(justify.returncode, 0, justify.stderr)
            record = self.run_script(home, 'record.py', decision['id'], 'success', operator='codex')
            self.assertEqual(record.returncode, 0, record.stderr)

    def test_claude_routing_requires_installed_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            missing = self.run_script(home, 'route.py', STATE, operator='claude')
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn('not installed', missing.stderr)
            agents = home / '.claude/agents'
            agents.mkdir(parents=True)
            (agents / 'exec-sonnet-medium.md').write_text('test', encoding='utf-8')
            result = self.run_script(home, 'route.py', STATE, markers={'CLAUDECODE': '1'})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['model'], 'sonnet')

    def test_detection_conflict_requires_override(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_script(Path(directory), 'route.py', STATE,
                                     markers={'CODEX_SESSION_ID': 'test', 'CLAUDECODE': '1'})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('CC_ROUTER_OPERATOR', result.stderr)

    def test_codex_install_does_not_change_claude_files(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            result = self.run_script(home, 'install.py', markers={'CODEX_SESSION_ID': 'test'})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((home / '.claude').exists())

    def test_claude_install_keeps_other_permission_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            for plugin in ('caveman', 'ponytail'):
                skill = home / f'.claude/plugins/{plugin}/skills/{plugin}/SKILL.md'
                skill.parent.mkdir(parents=True, exist_ok=True)
                skill.write_text('test', encoding='utf-8')
            settings = home / '.claude/settings.json'
            settings.write_text(json.dumps({'permissions': {'ask': ['Bash(rm *)']}}), encoding='utf-8')
            result = self.run_script(home, 'install.py', operator='claude')
            self.assertEqual(result.returncode, 0, result.stderr)
            agent = (home / '.claude/agents/exec-sonnet-medium.md').read_text(encoding='utf-8')
            self.assertIn('model: sonnet', agent)
            self.assertIn("Write the report in the user's language", agent)
            rules = json.loads(settings.read_text(encoding='utf-8'))['permissions']['ask']
            self.assertIn('Bash(rm *)', rules)
            self.assertIn('Agent(exec-opus-xhigh)', rules)


if __name__ == '__main__':
    unittest.main()
