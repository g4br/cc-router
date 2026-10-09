"""Exercise real local HTTP transport without loading Laya or contacting providers."""
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch
from test_v2 import fixture, STATE
from candidates import for_host
from route import route_one, laya_probabilities


class Handler(BaseHTTPRequestHandler):
    payload = b'{}'
    status = 200

    def do_POST(self):
        self.rfile.read(int(self.headers['Content-Length']))
        self.send_response(type(self).status)
        self.send_header('Content-Length', str(len(type(self).payload)))
        if type(self).status == 302:
            self.send_header('Location', 'https://example.invalid/forbidden')
        self.end_headers()
        self.wfile.write(type(self).payload)

    def log_message(self, *_):
        pass


class OrderHandler(Handler):
    # position-biased mock: yes ("A") scores 0.9 when listed first and 0.5 when listed second
    received = None

    def do_POST(self):
        OrderHandler.received = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        answers = {name: {'probabilities': {'A': 0.9 if next(iter(q['criteria'])) == 'A' else 0.5, 'B': 0}}
                   for name, q in OrderHandler.received['questions'].items()}
        encoded = json.dumps({'answers': answers}).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class TransportTest(unittest.TestCase):
    def test_bad_responses_fail_and_no_opinion_falls_back(self):
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        config = for_host(fixture(), 'codex')
        config.update(backend='laya', laya_url=f'http://127.0.0.1:{server.server_port}/v1/systemone')
        try:
            for status, payload in [(200, b'not json'), (200, b'{}'),
                                    (200, b'{"answers":{"basic":{"probabilities":{"A":true}},"deep":{"probabilities":{"A":0.9}}}}'),
                                    (500, b'{}'), (302, b'{}')]:
                Handler.status, Handler.payload = status, payload
                with self.subTest(status=status, payload=payload), self.assertRaisesRegex(ValueError, 'laya response'):
                    route_one(STATE, config, [])
            Handler.status = 200
            Handler.payload = json.dumps({'answers': {c['agent'] + suffix: {'probabilities': {'A': .1}}
                                                      for c in config['ladder'] for suffix in ('', '#swapped')}}).encode()
            decision = route_one(STATE, config, [])
            self.assertEqual(decision['backend'], 'laya (no opinion)')
            self.assertEqual(decision['selected'], 'basic')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_position_bias_is_averaged_out_in_one_request(self):
        server = HTTPServer(('127.0.0.1', 0), OrderHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        config = for_host(fixture(), 'codex')
        config.update(backend='laya', laya_url=f'http://127.0.0.1:{server.server_port}/v1/systemone')
        try:
            probabilities = laya_probabilities(STATE, config)
            questions = OrderHandler.received['questions']
            self.assertEqual(len(questions), 2 * len(config['ladder']))
            for rung in config['ladder']:
                name = rung['agent']
                self.assertEqual(list(questions[name]['criteria']), ['A', 'B'])
                self.assertEqual(list(questions[name + '#swapped']['criteria']), ['B', 'A'])
                self.assertAlmostEqual(probabilities[name], 0.7)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
