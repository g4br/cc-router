import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FeedbackTest(unittest.TestCase):
    def test_record_and_feedback_validate_outcome(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            history = home / '.codex/cc-router/history.jsonl'
            history.parent.mkdir(parents=True)
            history.write_text('\n'.join(json.dumps(event) for event in (
                {'event': 'decision', 'id': 'one', 'agent': 'exec-sol-medium', 'needs_approval': False},
                {'event': 'justification', 'id': 'one', 'answer': 'auto'},
            )) + '\n', encoding='utf-8')
            env = {'HOME': str(home), 'PATH': os.environ.get('PATH', ''), 'CC_ROUTER_OPERATOR': 'codex'}

            def run(name, *args):
                return subprocess.run([sys.executable, str(ROOT / 'scripts' / name), *args],
                                      cwd=ROOT, env=env, text=True, capture_output=True)

            recorded = run('record.py', 'one', 'success', '100', '--no-rework', 'true')
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            corrected = run('feedback.py', 'one', 'false')
            self.assertEqual(corrected.returncode, 0, corrected.stderr)
            duplicate = run('record.py', 'one', 'success')
            self.assertNotEqual(duplicate.returncode, 0)
            self.assertIn('already has a result', duplicate.stderr)


if __name__ == '__main__':
    unittest.main()
