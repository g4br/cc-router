import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class LayaHandler(BaseHTTPRequestHandler):
    received = None

    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        LayaHandler.received = json.loads(body)
        answers = {name: {'probabilities': {'A': 0.9 if name in ('exec-sol-medium', 'exec-sol-high') else 0.1}}
                   for name in LayaHandler.received['questions']}
        encoded = json.dumps({'answers': answers}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_):
        pass


class LayaRoutingTest(unittest.TestCase):
    def test_eligible_rung_uses_observed_tokens_when_coverage_is_complete(self):
        server = HTTPServer(('127.0.0.1', 0), LayaHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                config = json.loads((ROOT / 'config/ladder.json').read_text())
                self.assertEqual(config['backend'], 'laya')
                self.assertEqual(set(config['laya_enabled_operators']), {'claude', 'codex'})
                config['min_cost_samples'] = 2
                config['laya_urls']['codex'] = f'http://127.0.0.1:{server.server_port}/v1/systemone'
                config_path = home / 'ladder.json'
                config_path.write_text(json.dumps(config))
                history = home / '.codex/cc-router/history.jsonl'
                history.parent.mkdir(parents=True)
                state = {'description': 'prior task', 'operation': 'implementation', 'files': 1,
                         'ambiguous': False, 'critical': False}
                events = []
                for agent, tokens, backend in (('exec-sol-medium', 200, 'heuristic'),
                                               ('exec-sol-medium', 220, 'heuristic'),
                                               ('exec-sol-high', 90, 'heuristic'),
                                               ('exec-sol-high', 110, 'laya')):
                    decision_id = str(len(events))
                    events.append({'event': 'decision', 'id': decision_id, 'agent': agent,
                                   'state': state, 'backend': backend})
                    events.append({'event': 'result', 'id': decision_id, 'tokens': tokens})
                history.write_text(''.join(json.dumps(event) + '\n' for event in events))
                env = {'HOME': str(home), 'PATH': os.environ.get('PATH', ''),
                       'CC_ROUTER_OPERATOR': 'codex', 'CC_ROUTER_CONFIG': str(config_path)}
                payload = dict(state, description='new task', user_language='pt-BR', failed_with=None)
                result = subprocess.run([sys.executable, str(ROOT / 'scripts/route.py'), json.dumps(payload)],
                                        cwd=ROOT, env=env, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                decision = json.loads(result.stdout)
                self.assertEqual(decision['agent'], 'exec-sol-high')
                self.assertEqual(decision['user_language'], 'pt-BR')
                self.assertIn('estimated tokens', decision['reason'])
                self.assertNotIn('failed_with', LayaHandler.received['state'])
                self.assertNotIn('user_language', LayaHandler.received['state'])
                self.assertEqual(LayaHandler.received['state']['description'], 'new task')
                self.assertEqual(LayaHandler.received['model'], 'english')
                self.assertIn('clear scope where verification matters',
                              LayaHandler.received['questions']['exec-sol-high']['instructions'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
